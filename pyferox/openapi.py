from __future__ import annotations


def build_openapi_schema(routes, *, title: str, version: str):
    paths = {}
    components = {"schemas": {}}
    for route in routes:
        path = _to_openapi_path(route.path_pattern)
        method = route.method.lower()
        route_doc = paths.setdefault(path, {})
        operation = {
            "operationId": f"{method}_{route.handler.__name__}",
            "responses": {
                "200": {"description": "OK"},
                "400": {"description": "Bad Request"},
                "401": {"description": "Unauthorized"},
                "403": {"description": "Forbidden"},
                "404": {"description": "Not Found"},
                "422": {"description": "Validation Error"},
                "500": {"description": "Internal Server Error"},
            },
        }
        if route.tags:
            operation["tags"] = route.tags
        query_params = _query_parameters(route.query_schema)
        if query_params:
            operation["parameters"] = query_params
        request_body = _request_body(route.input_schema, components)
        if request_body:
            operation["requestBody"] = request_body
        response_schema = _response_schema(route.output_schema, components)
        if response_schema:
            operation["responses"]["200"]["content"] = {"application/json": {"schema": response_schema}}
        route_doc[method] = operation
    return {"openapi": "3.1.0", "info": {"title": title, "version": version}, "paths": paths, "components": components}


def _to_openapi_path(pattern: str):
    return pattern


def _query_parameters(contract):
    if contract is None:
        return []
    annotations = getattr(contract, "__annotations__", {})
    out = []
    for name, value_type in annotations.items():
        out.append(
            {
                "name": name,
                "in": "query",
                "required": True,
                "schema": {"type": _type_name(value_type)},
            }
        )
    return out


def _request_body(contract, components):
    if contract is None:
        return None
    schema_ref = _contract_schema_ref(contract, components)
    if schema_ref is None:
        return None
    return {"required": True, "content": {"application/json": {"schema": schema_ref}}}


def _response_schema(contract, components):
    if contract is None:
        return None
    return _contract_schema_ref(contract, components)


def _contract_schema_ref(contract, components):
    annotations = getattr(contract, "__annotations__", {})
    if not annotations and hasattr(contract, "Meta"):
        model = getattr(contract.Meta, "model", None)
        annotations = getattr(model, "__annotations__", {}) if model is not None else {}
    if not annotations:
        return None
    name = getattr(contract, "__name__", "AnonymousSchema")
    if name not in components["schemas"]:
        properties = {}
        required = []
        for field_name, value_type in annotations.items():
            properties[field_name] = {"type": _type_name(value_type)}
            required.append(field_name)
        components["schemas"][name] = {"type": "object", "properties": properties, "required": required}
    return {"$ref": f"#/components/schemas/{name}"}


def _type_name(tp):
    mapping = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
    }
    return mapping.get(tp, "string")
