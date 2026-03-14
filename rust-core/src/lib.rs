use chrono::{DateTime, NaiveDate, NaiveDateTime, NaiveTime};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList, PyString};
use regex::Regex;
use rust_decimal::prelude::ToPrimitive;
use rust_decimal::Decimal;
use serde_json::{Map, Number, Value};
use std::collections::HashMap;
use std::str::FromStr;
use url::Url;
use uuid::Uuid;

#[pyclass]
#[derive(Clone)]
struct CompiledSchema {
    fields: Vec<(String, String)>,
    types: HashMap<String, String>,
    rules: HashMap<String, FieldRules>,
}

#[derive(Clone, Default)]
struct FieldRules {
    allow_blank: Option<bool>,
    min_length: Option<usize>,
    max_length: Option<usize>,
    min_value: Option<f64>,
    max_value: Option<f64>,
    min_value_decimal: Option<Decimal>,
    max_value_decimal: Option<Decimal>,
    choices: Option<Vec<Value>>,
    regex: Option<Regex>,
    format: Option<String>,
    max_digits: Option<u32>,
    decimal_places: Option<u32>,
}

#[pyfunction]
fn parse_path_params(pattern: &str, path: &str) -> Option<HashMap<String, String>> {
    let pattern_parts: Vec<&str> = pattern.split('/').filter(|p| !p.is_empty()).collect();
    let path_parts: Vec<&str> = path.split('/').filter(|p| !p.is_empty()).collect();
    if pattern_parts.len() != path_parts.len() {
        return None;
    }
    let mut out = HashMap::new();
    for (pp, pv) in pattern_parts.iter().zip(path_parts.iter()) {
        if pp.starts_with('{') && pp.ends_with('}') {
            let key = pp.trim_start_matches('{').trim_end_matches('}');
            out.insert(key.to_string(), (*pv).to_string());
        } else if pp != pv {
            return None;
        }
    }
    Some(out)
}

#[pyfunction]
fn compile_schema(schema: HashMap<String, String>) -> CompiledSchema {
    let mut fields: Vec<(String, String)> = schema.into_iter().collect();
    fields.sort_by(|a, b| a.0.cmp(&b.0));
    let mut types = HashMap::new();
    for (k, v) in &fields {
        types.insert(k.clone(), v.clone());
    }
    CompiledSchema {
        fields,
        types,
        rules: HashMap::new(),
    }
}

#[pyfunction]
fn compile_schema_with_rules(
    schema: HashMap<String, String>,
    rules: HashMap<String, Py<PyAny>>,
    py: Python<'_>,
) -> PyResult<CompiledSchema> {
    let mut compiled = compile_schema(schema);
    let mut out_rules = HashMap::new();
    for (field, raw) in rules {
        let bound = raw.bind(py);
        let dict = bound
            .downcast::<PyDict>()
            .map_err(|_| PyValueError::new_err("field rule must be dict"))?;
        let rule = parse_field_rules(dict)?;
        out_rules.insert(field, rule);
    }
    compiled.rules = out_rules;
    Ok(compiled)
}

#[pyfunction]
fn validate_compiled(
    compiled: PyRef<'_, CompiledSchema>,
    data: HashMap<String, Py<PyAny>>,
    py: Python<'_>,
) -> PyResult<HashMap<String, Py<PyAny>>> {
    let mut out = HashMap::new();
    for (field, expected) in &compiled.fields {
        let value = data
            .get(field)
            .ok_or_else(|| PyValueError::new_err(format!("missing field: {}", field)))?;
        let bound = value.bind(py);
        let coerced = coerce_value(&bound, expected, py)?;
        apply_rules(compiled.rules.get(field), field, &coerced.bind(py))?;
        out.insert(field.clone(), coerced);
    }
    Ok(out)
}

#[pyfunction]
fn validate_partial_compiled(
    compiled: PyRef<'_, CompiledSchema>,
    data: HashMap<String, Py<PyAny>>,
    py: Python<'_>,
) -> PyResult<HashMap<String, Py<PyAny>>> {
    let mut out = HashMap::new();
    for (field, value) in data {
        let expected = compiled
            .types
            .get(&field)
            .ok_or_else(|| PyValueError::new_err(format!("unknown field: {}", field)))?;
        let bound = value.bind(py);
        let coerced = coerce_value(&bound, expected, py)?;
        apply_rules(compiled.rules.get(&field), &field, &coerced.bind(py))?;
        out.insert(field, coerced);
    }
    Ok(out)
}

#[pyfunction]
fn validate_query_compiled(
    compiled: PyRef<'_, CompiledSchema>,
    data: HashMap<String, String>,
    py: Python<'_>,
) -> PyResult<HashMap<String, Py<PyAny>>> {
    let mut out = HashMap::new();
    for (field, raw) in data {
        let expected = compiled
            .types
            .get(&field)
            .ok_or_else(|| PyValueError::new_err(format!("unknown field: {}", field)))?;
        let coerced = coerce_query_value(&raw, expected, py)?;
        apply_rules(compiled.rules.get(&field), &field, &coerced.bind(py))?;
        out.insert(field, coerced);
    }
    Ok(out)
}

#[pyfunction]
fn serialize_json(value: Py<PyAny>, py: Python<'_>) -> PyResult<String> {
    let as_json = py_to_json(&value.bind(py))?;
    serde_json::to_string(&as_json)
        .map_err(|e| PyValueError::new_err(format!("json serialization failed: {}", e)))
}

fn coerce_value(value: &Bound<'_, PyAny>, expected: &str, py: Python<'_>) -> PyResult<Py<PyAny>> {
    match expected {
        "str" => {
            let extracted: String = value.extract().map_err(|_| PyValueError::new_err("expected str"))?;
            Ok(PyString::new_bound(py, &extracted).into_py(py))
        }
        "int" => {
            if value.extract::<bool>().is_ok() {
                return Err(PyValueError::new_err("expected int, got bool"));
            }
            let extracted: i64 = value.extract().map_err(|_| PyValueError::new_err("expected int"))?;
            Ok(extracted.into_py(py))
        }
        "float" => {
            if value.extract::<bool>().is_ok() {
                return Err(PyValueError::new_err("expected float, got bool"));
            }
            let extracted: f64 = value.extract().map_err(|_| PyValueError::new_err("expected float"))?;
            Ok(extracted.into_py(py))
        }
        "bool" => {
            let extracted: bool = value.extract().map_err(|_| PyValueError::new_err("expected bool"))?;
            Ok(extracted.into_py(py))
        }
        "dict" => {
            let _dict = value.downcast::<PyDict>().map_err(|_| PyValueError::new_err("expected dict"))?;
            Ok(value.clone().unbind())
        }
        "list" => {
            let _list = value.downcast::<PyList>().map_err(|_| PyValueError::new_err("expected list"))?;
            Ok(value.clone().unbind())
        }
        other => Err(PyValueError::new_err(format!("unsupported schema type: {}", other))),
    }
}

fn coerce_query_value(raw: &str, expected: &str, py: Python<'_>) -> PyResult<Py<PyAny>> {
    match expected {
        "str" => Ok(PyString::new_bound(py, raw).into_py(py)),
        "int" => {
            let parsed = raw
                .parse::<i64>()
                .map_err(|_| PyValueError::new_err("expected int"))?;
            Ok(parsed.into_py(py))
        }
        "float" => {
            let parsed = raw
                .parse::<f64>()
                .map_err(|_| PyValueError::new_err("expected float"))?;
            Ok(parsed.into_py(py))
        }
        "bool" => {
            let normalized = raw.trim().to_ascii_lowercase();
            match normalized.as_str() {
                "1" | "true" | "yes" | "on" => Ok(true.into_py(py)),
                "0" | "false" | "no" | "off" => Ok(false.into_py(py)),
                _ => Err(PyValueError::new_err("expected bool")),
            }
        }
        "dict" => {
            let parsed: Value =
                serde_json::from_str(raw).map_err(|_| PyValueError::new_err("expected json object"))?;
            if !parsed.is_object() {
                return Err(PyValueError::new_err("expected json object"));
            }
            json_to_py(&parsed, py)
        }
        "list" => {
            let parsed: Value =
                serde_json::from_str(raw).map_err(|_| PyValueError::new_err("expected json array"))?;
            if !parsed.is_array() {
                return Err(PyValueError::new_err("expected json array"));
            }
            json_to_py(&parsed, py)
        }
        other => Err(PyValueError::new_err(format!("unsupported schema type: {}", other))),
    }
}

fn py_to_json(value: &Bound<'_, PyAny>) -> PyResult<Value> {
    if value.is_none() {
        return Ok(Value::Null);
    }
    if let Ok(v) = value.extract::<bool>() {
        return Ok(Value::Bool(v));
    }
    if let Ok(v) = value.extract::<i64>() {
        return Ok(Value::Number(Number::from(v)));
    }
    if let Ok(v) = value.extract::<f64>() {
        let n = Number::from_f64(v).ok_or_else(|| PyValueError::new_err("invalid float"))?;
        return Ok(Value::Number(n));
    }
    if let Ok(v) = value.extract::<String>() {
        return Ok(Value::String(v));
    }
    if let Ok(list) = value.downcast::<PyList>() {
        let mut arr = Vec::with_capacity(list.len());
        for item in list.iter() {
            arr.push(py_to_json(&item)?);
        }
        return Ok(Value::Array(arr));
    }
    if let Ok(dict) = value.downcast::<PyDict>() {
        let mut map = Map::new();
        for (k, v) in dict.iter() {
            let key: String = k.extract().map_err(|_| PyValueError::new_err("dict key must be str"))?;
            map.insert(key, py_to_json(&v)?);
        }
        return Ok(Value::Object(map));
    }
    Err(PyValueError::new_err("unsupported value for JSON serialization"))
}

fn parse_field_rules(dict: &Bound<'_, PyDict>) -> PyResult<FieldRules> {
    let mut out = FieldRules::default();
    if let Some(v) = dict.get_item("allow_blank")? {
        if !v.is_none() {
            out.allow_blank = Some(v.extract::<bool>().map_err(|_| PyValueError::new_err("allow_blank must be bool"))?);
        }
    }
    if let Some(v) = dict.get_item("min_length")? {
        if !v.is_none() {
            out.min_length = Some(v.extract::<usize>().map_err(|_| PyValueError::new_err("min_length must be int"))?);
        }
    }
    if let Some(v) = dict.get_item("max_length")? {
        if !v.is_none() {
            out.max_length = Some(v.extract::<usize>().map_err(|_| PyValueError::new_err("max_length must be int"))?);
        }
    }
    if let Some(v) = dict.get_item("min_value")? {
        if !v.is_none() {
            out.min_value = Some(v.extract::<f64>().map_err(|_| PyValueError::new_err("min_value must be number"))?);
        }
    }
    if let Some(v) = dict.get_item("max_value")? {
        if !v.is_none() {
            out.max_value = Some(v.extract::<f64>().map_err(|_| PyValueError::new_err("max_value must be number"))?);
        }
    }
    if let Some(v) = dict.get_item("min_value_decimal")? {
        if !v.is_none() {
            let raw = v
                .extract::<String>()
                .map_err(|_| PyValueError::new_err("min_value_decimal must be str"))?;
            out.min_value_decimal =
                Some(Decimal::from_str(&raw).map_err(|_| PyValueError::new_err("min_value_decimal is invalid decimal"))?);
        }
    }
    if let Some(v) = dict.get_item("max_value_decimal")? {
        if !v.is_none() {
            let raw = v
                .extract::<String>()
                .map_err(|_| PyValueError::new_err("max_value_decimal must be str"))?;
            out.max_value_decimal =
                Some(Decimal::from_str(&raw).map_err(|_| PyValueError::new_err("max_value_decimal is invalid decimal"))?);
        }
    }
    if let Some(v) = dict.get_item("choices")? {
        if !v.is_none() {
            let as_json = py_to_json(&v)?;
            let items = as_json
                .as_array()
                .ok_or_else(|| PyValueError::new_err("choices must be a list"))?;
            out.choices = Some(items.clone());
        }
    }
    if let Some(v) = dict.get_item("regex")? {
        if !v.is_none() {
            let pattern = v.extract::<String>().map_err(|_| PyValueError::new_err("regex must be str"))?;
            let compiled = Regex::new(&pattern).map_err(|_| PyValueError::new_err("invalid regex pattern"))?;
            out.regex = Some(compiled);
        }
    }
    if let Some(v) = dict.get_item("format")? {
        if !v.is_none() {
            out.format = Some(v.extract::<String>().map_err(|_| PyValueError::new_err("format must be str"))?);
        }
    }
    if let Some(v) = dict.get_item("max_digits")? {
        if !v.is_none() {
            out.max_digits = Some(v.extract::<u32>().map_err(|_| PyValueError::new_err("max_digits must be int"))?);
        }
    }
    if let Some(v) = dict.get_item("decimal_places")? {
        if !v.is_none() {
            out.decimal_places = Some(v.extract::<u32>().map_err(|_| PyValueError::new_err("decimal_places must be int"))?);
        }
    }
    Ok(out)
}

fn apply_rules(rules: Option<&FieldRules>, field_name: &str, value: &Bound<'_, PyAny>) -> PyResult<()> {
    let Some(rule) = rules else {
        return Ok(());
    };

    if let Some(allow_blank) = rule.allow_blank {
        if !allow_blank {
            if let Ok(v) = value.extract::<String>() {
                if v.is_empty() {
                    return Err(PyValueError::new_err(format!("blank is not allowed for {}", field_name)));
                }
            }
        }
    }

    if rule.min_length.is_some() || rule.max_length.is_some() {
        if let Ok(v) = value.extract::<String>() {
            if let Some(min_len) = rule.min_length {
                if v.len() < min_len {
                    return Err(PyValueError::new_err(format!("min_length violation for {}", field_name)));
                }
            }
            if let Some(max_len) = rule.max_length {
                if v.len() > max_len {
                    return Err(PyValueError::new_err(format!("max_length violation for {}", field_name)));
                }
            }
        }
    }

    if let Some(re) = &rule.regex {
        if let Ok(v) = value.extract::<String>() {
            if !regex_full_match(re, &v) {
                return Err(PyValueError::new_err(format!("regex violation for {}", field_name)));
            }
        }
    }

    let needs_decimal = rule.max_digits.is_some()
        || rule.decimal_places.is_some()
        || rule.min_value_decimal.is_some()
        || rule.max_value_decimal.is_some()
        || rule.format.as_deref() == Some("decimal");
    let decimal_value = if needs_decimal {
        Some(extract_decimal(value, field_name)?)
    } else {
        None
    };

    if let Some(format) = &rule.format {
        if let Ok(v) = value.extract::<String>() {
            validate_format(format, &v, field_name, decimal_value.as_ref())?;
        }
    }

    if rule.min_value.is_some()
        || rule.max_value.is_some()
        || rule.min_value_decimal.is_some()
        || rule.max_value_decimal.is_some()
    {
        if value.extract::<bool>().is_err() {
            if let Ok(v) = value.extract::<f64>() {
                if let Some(min_v) = rule.min_value {
                    if v < min_v {
                        return Err(PyValueError::new_err(format!("min_value violation for {}", field_name)));
                    }
                }
                if let Some(max_v) = rule.max_value {
                    if v > max_v {
                        return Err(PyValueError::new_err(format!("max_value violation for {}", field_name)));
                    }
                }
            } else if let Some(dec) = decimal_value.as_ref() {
                if let Some(min_v) = rule.min_value_decimal.as_ref() {
                    if dec < min_v {
                        return Err(PyValueError::new_err(format!("min_value violation for {}", field_name)));
                    }
                } else if let Some(min_v) = rule.min_value {
                    if let Some(v) = dec.to_f64() {
                        if v < min_v {
                            return Err(PyValueError::new_err(format!("min_value violation for {}", field_name)));
                        }
                    }
                }
                if let Some(max_v) = rule.max_value_decimal.as_ref() {
                    if dec > max_v {
                        return Err(PyValueError::new_err(format!("max_value violation for {}", field_name)));
                    }
                } else if let Some(max_v) = rule.max_value {
                    if let Some(v) = dec.to_f64() {
                        if v > max_v {
                            return Err(PyValueError::new_err(format!("max_value violation for {}", field_name)));
                        }
                    }
                }
            }
        }
    }

    if let Some(max_digits) = rule.max_digits {
        if let Some(dec) = decimal_value.as_ref() {
            let digits = decimal_digit_count(*dec);
            if digits > max_digits {
                return Err(PyValueError::new_err(format!("max_digits violation for {}", field_name)));
            }
        }
    }

    if let Some(decimal_places) = rule.decimal_places {
        if let Some(dec) = decimal_value.as_ref() {
            if dec.scale() > decimal_places {
                return Err(PyValueError::new_err(format!("decimal_places violation for {}", field_name)));
            }
        }
    }

    if let Some(choices) = &rule.choices {
        let current = py_to_json(value)?;
        if !choices.iter().any(|item| item == &current) {
            return Err(PyValueError::new_err(format!("invalid choice for {}", field_name)));
        }
    }
    Ok(())
}

fn validate_format(format: &str, value: &str, field_name: &str, decimal_value: Option<&Decimal>) -> PyResult<()> {
    match format {
        "email" => {
            let re = Regex::new(r"^[^@\s]+@[^@\s]+\.[^@\s]+$").map_err(|_| PyValueError::new_err("invalid regex"))?;
            if !re.is_match(value) {
                return Err(PyValueError::new_err(format!("invalid email for {}", field_name)));
            }
        }
        "url" => {
            let parsed = Url::parse(value).map_err(|_| PyValueError::new_err(format!("invalid url for {}", field_name)))?;
            if parsed.scheme() != "http" && parsed.scheme() != "https" {
                return Err(PyValueError::new_err(format!("invalid url for {}", field_name)));
            }
            if parsed.host_str().is_none() {
                return Err(PyValueError::new_err(format!("invalid url for {}", field_name)));
            }
        }
        "uuid" => {
            Uuid::parse_str(value).map_err(|_| PyValueError::new_err(format!("invalid uuid for {}", field_name)))?;
        }
        "date" => {
            NaiveDate::parse_from_str(value, "%Y-%m-%d")
                .map_err(|_| PyValueError::new_err(format!("invalid date for {}", field_name)))?;
        }
        "datetime" => {
            let normalized = if value.ends_with('Z') {
                format!("{}+00:00", &value[..value.len() - 1])
            } else {
                value.to_string()
            };
            if DateTime::parse_from_rfc3339(&normalized).is_err()
                && NaiveDateTime::parse_from_str(value, "%Y-%m-%dT%H:%M:%S%.f").is_err()
            {
                return Err(PyValueError::new_err(format!("invalid datetime for {}", field_name)));
            }
        }
        "time" => {
            NaiveTime::parse_from_str(value, "%H:%M:%S%.f")
                .map_err(|_| PyValueError::new_err(format!("invalid time for {}", field_name)))?;
        }
        "decimal" => {
            if decimal_value.is_none() {
                return Err(PyValueError::new_err(format!("invalid decimal for {}", field_name)));
            }
        }
        _ => {}
    }
    Ok(())
}

fn regex_full_match(re: &Regex, value: &str) -> bool {
    if let Some(m) = re.find(value) {
        m.start() == 0 && m.end() == value.len()
    } else {
        false
    }
}

fn extract_decimal(value: &Bound<'_, PyAny>, field_name: &str) -> PyResult<Decimal> {
    if let Ok(raw) = value.extract::<String>() {
        return Decimal::from_str(&raw).map_err(|_| PyValueError::new_err(format!("invalid decimal for {}", field_name)));
    }
    if let Ok(v) = value.extract::<i64>() {
        return Ok(Decimal::from(v));
    }
    if let Ok(v) = value.extract::<f64>() {
        return Decimal::from_f64_retain(v)
            .ok_or_else(|| PyValueError::new_err(format!("invalid decimal for {}", field_name)));
    }
    Err(PyValueError::new_err(format!("invalid decimal for {}", field_name)))
}

fn decimal_digit_count(decimal: Decimal) -> u32 {
    let normalized = decimal.normalize();
    let int = normalized.mantissa().abs();
    if int == 0 {
        return 1;
    }
    int.to_string().len() as u32
}

fn json_to_py(value: &Value, py: Python<'_>) -> PyResult<Py<PyAny>> {
    match value {
        Value::Null => Ok(py.None()),
        Value::Bool(v) => Ok(v.into_py(py)),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                Ok(i.into_py(py))
            } else if let Some(f) = n.as_f64() {
                Ok(f.into_py(py))
            } else {
                Err(PyValueError::new_err("invalid json number"))
            }
        }
        Value::String(s) => Ok(PyString::new_bound(py, s).into_py(py)),
        Value::Array(arr) => {
            let items = PyList::empty_bound(py);
            for item in arr {
                items.append(json_to_py(item, py)?)?;
            }
            Ok(items.into_py(py))
        }
        Value::Object(obj) => {
            let dict = PyDict::new_bound(py);
            for (k, v) in obj {
                dict.set_item(k, json_to_py(v, py)?)?;
            }
            Ok(dict.into_py(py))
        }
    }
}

#[pymodule]
fn pyferox_rust(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<CompiledSchema>()?;
    m.add_function(wrap_pyfunction!(parse_path_params, m)?)?;
    m.add_function(wrap_pyfunction!(compile_schema, m)?)?;
    m.add_function(wrap_pyfunction!(compile_schema_with_rules, m)?)?;
    m.add_function(wrap_pyfunction!(validate_compiled, m)?)?;
    m.add_function(wrap_pyfunction!(validate_partial_compiled, m)?)?;
    m.add_function(wrap_pyfunction!(validate_query_compiled, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_json, m)?)?;
    Ok(())
}
