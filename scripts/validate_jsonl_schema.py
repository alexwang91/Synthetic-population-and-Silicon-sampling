#!/usr/bin/env python3
"""Validate a JSONL file against a small stdlib-supported JSON Schema subset.

This validator intentionally avoids third-party dependencies. It supports the
schema features used by this repository's artifact contracts: type, required,
properties, additionalProperties, items, enum, anyOf, minimum, maximum,
exclusiveMinimum, exclusiveMaximum, minLength, maxLength, minItems, and maxItems.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def type_matches(value: Any, expected: str) -> bool:
    actual = json_type(value)
    if expected == "number":
        return actual in {"integer", "number"}
    return actual == expected


def validate_value(value: Any, schema: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []

    if "anyOf" in schema:
        options = schema.get("anyOf")
        if not isinstance(options, list) or not options:
            return [f"{path}: anyOf must be a non-empty array"]
        option_errors = [validate_value(value, option, path) for option in options if isinstance(option, dict)]
        if any(not item for item in option_errors):
            return []
        return [f"{path}: value did not match any allowed schema"]

    expected_type = schema.get("type")
    if isinstance(expected_type, list):
        if not any(isinstance(item, str) and type_matches(value, item) for item in expected_type):
            errors.append(f"{path}: expected type {expected_type}, got {json_type(value)}")
            return errors
    elif isinstance(expected_type, str) and not type_matches(value, expected_type):
        errors.append(f"{path}: expected type {expected_type}, got {json_type(value)}")
        return errors

    if "enum" in schema:
        enum = schema.get("enum")
        if isinstance(enum, list) and value not in enum:
            errors.append(f"{path}: expected one of {enum!r}, got {value!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < float(schema["minimum"]):
            errors.append(f"{path}: value {value!r} is below minimum {schema['minimum']!r}")
        if "maximum" in schema and value > float(schema["maximum"]):
            errors.append(f"{path}: value {value!r} is above maximum {schema['maximum']!r}")
        if "exclusiveMinimum" in schema and value <= float(schema["exclusiveMinimum"]):
            errors.append(f"{path}: value {value!r} must be greater than {schema['exclusiveMinimum']!r}")
        if "exclusiveMaximum" in schema and value >= float(schema["exclusiveMaximum"]):
            errors.append(f"{path}: value {value!r} must be less than {schema['exclusiveMaximum']!r}")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            errors.append(f"{path}: string is shorter than minLength {schema['minLength']!r}")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            errors.append(f"{path}: string is longer than maxLength {schema['maxLength']!r}")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            errors.append(f"{path}: array has fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            errors.append(f"{path}: array has more than {schema['maxItems']} items")
        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            for index, item in enumerate(value):
                errors.extend(validate_value(item, items_schema, f"{path}[{index}]"))

    if isinstance(value, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if isinstance(key, str) and key not in value:
                    errors.append(f"{path}: missing required field {key!r}")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                if key in value and isinstance(child_schema, dict):
                    errors.extend(validate_value(value[key], child_schema, f"{path}.{key}"))
            if schema.get("additionalProperties") is False:
                allowed = set(properties)
                for key in value:
                    if key not in allowed:
                        errors.append(f"{path}: unexpected additional field {key!r}")

    return errors


def validate_jsonl(path: Path, schema: dict[str, Any], max_errors: int) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    record_count = 0
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped:
                continue
            record_count += 1
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                errors.append({"line_number": line_number, "path": "$", "issue": f"invalid JSON: {exc}"})
                if len(errors) >= max_errors:
                    break
                continue
            for issue in validate_value(value, schema, "$"):
                errors.append({"line_number": line_number, "path": issue.split(":", 1)[0], "issue": issue})
                if len(errors) >= max_errors:
                    break
            if len(errors) >= max_errors:
                break
    return {
        "jsonl_path": str(path),
        "record_count": record_count,
        "error_count": len(errors),
        "errors": errors,
        "passes_schema_validation": len(errors) == 0,
        "max_errors": max_errors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("schema", type=Path)
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--max-errors", type=int, default=100)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_errors <= 0:
        raise ValueError("--max-errors must be positive")
    schema = load_json(args.schema)
    audit = validate_jsonl(args.jsonl, schema, args.max_errors)
    text = json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.audit:
        args.audit.parent.mkdir(parents=True, exist_ok=True)
        args.audit.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if audit["passes_schema_validation"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
