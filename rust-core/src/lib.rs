use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList, PyString};
use serde_json::{Map, Number, Value};
use std::collections::HashMap;

#[pyclass]
#[derive(Clone)]
struct CompiledSchema {
    fields: Vec<(String, String)>,
    types: HashMap<String, String>,
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
    CompiledSchema { fields, types }
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

#[pymodule]
fn pyferox_rust(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<CompiledSchema>()?;
    m.add_function(wrap_pyfunction!(parse_path_params, m)?)?;
    m.add_function(wrap_pyfunction!(compile_schema, m)?)?;
    m.add_function(wrap_pyfunction!(validate_compiled, m)?)?;
    m.add_function(wrap_pyfunction!(validate_partial_compiled, m)?)?;
    m.add_function(wrap_pyfunction!(validate_query_compiled, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_json, m)?)?;
    Ok(())
}
