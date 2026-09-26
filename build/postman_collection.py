"""Build api/skytowers.postman_collection.json from api/openapi.yml (spec §12 API freeze).

Deterministic output (sorted, no generated ids) so CI can check it is up to date.
Usage: python build/postman_collection.py [api_dir]
"""

import json
import re
import sys
from pathlib import Path

import yaml

METHODS = ("get", "post", "put", "patch", "delete")


def _example(schema: dict, components: dict, depth: int = 0):
    if "$ref" in schema:
        return _example(
            components[schema["$ref"].rsplit("/", 1)[-1]], components, depth
        )
    if depth > 3:
        return None
    if "enum" in schema:
        return schema["enum"][0]
    if "allOf" in schema:
        return _example(schema["allOf"][0], components, depth)
    if "oneOf" in schema:
        return _example(schema["oneOf"][0], components, depth)
    kind = schema.get("type")
    if kind == "object":
        props = schema.get("properties", {})
        required = schema.get("required", list(props))
        return {
            k: _example(v, components, depth + 1)
            for k, v in props.items()
            if k in required and not v.get("readOnly")
        }
    if kind == "array":
        return []
    if kind == "integer":
        return 0
    if kind == "boolean":
        return False
    return ""


def _request(path: str, method: str, op: dict, components: dict) -> dict:
    url_path = re.sub(r"\{(\w+)\}", r":\1", path).lstrip("/")
    variables = [{"key": name, "value": ""} for name in re.findall(r"\{(\w+)\}", path)]
    query = [
        {"key": p["name"], "value": "", "disabled": True}
        for p in op.get("parameters", [])
        if p.get("in") == "query"
    ]
    request = {
        "method": method.upper(),
        "header": [],
        "url": {
            "raw": "{{base_url}}/" + url_path,
            "host": ["{{base_url}}"],
            "path": url_path.split("/"),
            "query": query,
            "variable": variables,
        },
        "description": (op.get("description") or "").strip(),
    }
    content = op.get("requestBody", {}).get("content", {})
    if "application/json" in content:
        body = _example(content["application/json"]["schema"], components)
        request["header"].append({"key": "Content-Type", "value": "application/json"})
        request["body"] = {
            "mode": "raw",
            "raw": json.dumps(body, ensure_ascii=False, indent=2),
        }
    elif "multipart/form-data" in content:
        request["body"] = {"mode": "formdata", "formdata": []}
    return {"name": op["operationId"], "request": request}


def build(schema: dict) -> dict:
    components = schema.get("components", {}).get("schemas", {})
    folders: dict[str, list] = {}
    for path in sorted(schema["paths"]):
        item = schema["paths"][path]
        folder = path.removeprefix("/api/v1/").split("/", 1)[0]
        for method in METHODS:
            if method in item:
                folders.setdefault(folder, []).append(
                    _request(path, method, item[method], components)
                )
    return {
        "info": {
            "name": f"{schema['info']['title']} {schema['info']['version']}",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            "description": "Generated from api/openapi.yml by build/postman_collection.py. Sign in with "
            "auth/password or auth/pin, then set the `token` variable.",
        },
        "auth": {
            "type": "apikey",
            "apikey": [
                {"key": "key", "value": "Authorization", "type": "string"},
                {"key": "value", "value": "Token {{token}}", "type": "string"},
                {"key": "in", "value": "header", "type": "string"},
            ],
        },
        "variable": [
            {"key": "base_url", "value": "http://127.0.0.1:8471"},
            {"key": "token", "value": ""},
        ],
        "item": [{"name": name, "item": items} for name, items in folders.items()],
    }


def main(api_dir: Path) -> None:
    schema = yaml.safe_load((api_dir / "openapi.yml").read_text(encoding="utf-8"))
    out = api_dir / "skytowers.postman_collection.json"
    out.write_text(
        json.dumps(build(schema), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main(
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parent.parent / "api"
    )
