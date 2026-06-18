#!/usr/bin/env python3
"""Create seed statistical cells from a country pack and explicit dimensions.

This script does not estimate population weights. It creates the seed grid that
`run_ipf.py` can later rake to official or survey margins.
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("country pack must be a JSON object")
    return value


def parse_dimension(raw: str) -> tuple[str, list[str]]:
    if "=" not in raw:
        raise ValueError(f"dimension must use field=value1,value2 syntax: {raw!r}")
    field, values_raw = raw.split("=", 1)
    field = field.strip()
    values = [value.strip() for value in values_raw.split(",") if value.strip()]
    if not field:
        raise ValueError(f"dimension field is empty: {raw!r}")
    if not values:
        raise ValueError(f"dimension has no values: {raw!r}")
    return field, values


def load_dimensions(args: argparse.Namespace) -> dict[str, list[str]]:
    dimensions: dict[str, list[str]] = {}

    if args.dimension_json:
        loaded = load_json(args.dimension_json)
        for field, values in loaded.items():
            if not isinstance(field, str) or not field:
                raise ValueError("dimension JSON keys must be non-empty strings")
            if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                raise ValueError(f"dimension JSON value for {field!r} must be a string array")
            if not values:
                raise ValueError(f"dimension JSON value for {field!r} is empty")
            dimensions[field] = values

    for raw in args.dimension:
        field, values = parse_dimension(raw)
        if field in dimensions:
            raise ValueError(f"duplicate dimension field: {field}")
        dimensions[field] = values

    if not dimensions:
        raise ValueError("at least one --dimension or --dimension-json entry is required")
    return dimensions


def cell_id(iso2: str, index: int) -> str:
    return f"{iso2}-CELL-{index:06d}"


def constraint_inventory(pack: dict[str, Any]) -> list[dict[str, Any]]:
    constraints = pack.get("statistical_constraints", [])
    if not isinstance(constraints, list):
        return []
    result: list[dict[str, Any]] = []
    for item in constraints:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "constraint_id": item.get("constraint_id"),
                "type": item.get("type"),
                "variable_set": item.get("variable_set"),
                "values_available": item.get("values_available"),
                "use_in_ipf": item.get("use_in_ipf"),
                "confidence": item.get("confidence"),
            }
        )
    return result


def build_cells(pack: dict[str, Any], dimensions: dict[str, list[str]], seed_weight: float, max_cells: int) -> list[dict[str, Any]]:
    identity = pack.get("country_identity", {}) if isinstance(pack.get("country_identity"), dict) else {}
    build_status = pack.get("build_status", {}) if isinstance(pack.get("build_status"), dict) else {}
    iso2 = str(identity.get("iso2", "XX")).upper()
    country = identity.get("country_name")
    population_year = identity.get("population_year")

    fields = list(dimensions)
    combos = itertools.product(*(dimensions[field] for field in fields))
    cells: list[dict[str, Any]] = []
    for index, values in enumerate(combos, 1):
        if index > max_cells:
            raise ValueError(f"cell count exceeds --max-cells={max_cells}")
        hard = dict(zip(fields, values, strict=True))
        cells.append(
            {
                "cell_id": cell_id(iso2, index),
                "country": country,
                "iso2": iso2,
                "population_year": population_year,
                "hard": hard,
                "seed_weight": seed_weight,
                "population_weight": None,
                "ipf_weight": seed_weight,
                "ipf_ready": False,
                "calibration_trace": {
                    "country_pack_status": build_status.get("status"),
                    "country_pack_calibration_level": build_status.get("current_calibration_level"),
                    "dimensions_source": "explicit_cli_or_json",
                },
            }
        )
    return cells


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("country_pack", type=Path)
    parser.add_argument("--dimension", action="append", default=[], help="Dimension as field=value1,value2. Repeatable.")
    parser.add_argument("--dimension-json", type=Path, help="JSON object of field -> string array dimensions.")
    parser.add_argument("--seed-weight", type=float, default=1.0)
    parser.add_argument("--max-cells", type=int, default=100000)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--constraints-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.seed_weight <= 0:
        raise ValueError("--seed-weight must be positive")
    pack = load_json(args.country_pack)
    dimensions = load_dimensions(args)
    cells = build_cells(pack, dimensions, args.seed_weight, args.max_cells)
    write_jsonl(args.output, cells)
    if args.constraints_output:
        args.constraints_output.parent.mkdir(parents=True, exist_ok=True)
        args.constraints_output.write_text(
            json.dumps(
                {
                    "cell_count": len(cells),
                    "dimensions": dimensions,
                    "constraints": constraint_inventory(pack),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
