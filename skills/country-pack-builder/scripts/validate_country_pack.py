#!/usr/bin/env python3
"""Validate a country pack JSON file.

This is a structural and audit-readiness validator. It does not verify every
external statistic against source websites.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

REQUIRED_TOP_LEVEL = {
    "country_identity",
    "coverage_scope",
    "source_priority",
    "required_tables",
    "optional_tables",
    "extracted_anchor_values",
    "statistical_constraints",
    "imputation_policy",
    "quality_checks",
    "build_status",
    "next_actions",
}

REQUIRED_COUNTRY_IDENTITY = {
    "country_name",
    "iso2",
    "iso3",
    "pack_version",
    "population_year",
}

REQUIRED_TABLE_FIELDS = {
    "file_name",
    "grain",
    "variables",
    "source_name",
    "official_or_imputed",
    "required_for_level",
    "missing_status",
}

REQUIRED_CONSTRAINT_FIELDS = {
    "constraint_id",
    "type",
    "variable_set",
    "values_available",
    "geography_level",
    "population_base",
    "year",
    "confidence",
    "use_in_ipf",
}

ALLOWED_BUILD_STATUS = {
    "empty",
    "source_mapped",
    "anchor_ready",
    "ipf_ready",
    "calibrated_ready",
    "partial_country_pack_v0_1",
}

ALLOWED_CONSTRAINT_TYPES = {
    "official_margin",
    "survey_margin",
    "derived_margin",
    "imputed_prior",
    "unavailable",
}

ALLOWED_CONFIDENCE = {"high", "medium", "low"}

CORE_VARIABLES = {
    "region",
    "age_band",
    "sex",
    "education_level",
    "household_size",
    "employment_status",
    "income_band",
    "income_decile",
    "urban_rural",
    "settlement_type",
    "internet_frequency",
    "digital_access_level",
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("country pack must be a JSON object")
    return value


def missing_fields(obj: Any, required: set[str]) -> list[str]:
    if not isinstance(obj, dict):
        return sorted(required)
    return sorted(field for field in required if field not in obj)


def validate_tables(pack: dict[str, Any]) -> tuple[list[dict[str, Any]], Counter[str], set[str]]:
    errors: list[dict[str, Any]] = []
    missing_status_counts: Counter[str] = Counter()
    variables_seen: set[str] = set()

    for section in ("required_tables", "optional_tables"):
        tables = pack.get(section, [])
        if not isinstance(tables, list):
            errors.append({"section": section, "issue": "not_array"})
            continue
        for idx, table in enumerate(tables):
            missing = missing_fields(table, REQUIRED_TABLE_FIELDS)
            if missing:
                errors.append({"section": section, "index": idx, "issue": "missing_table_fields", "fields": missing})
                continue
            variables = table.get("variables")
            if not isinstance(variables, list) or not all(isinstance(v, str) for v in variables):
                errors.append({"section": section, "index": idx, "issue": "variables_not_string_array"})
            else:
                variables_seen.update(variables)
            missing_status_counts[str(table.get("missing_status"))] += 1
            if not table.get("source_url"):
                errors.append({"section": section, "index": idx, "file_name": table.get("file_name"), "issue": "missing_source_url"})
    return errors, missing_status_counts, variables_seen


def validate_constraints(pack: dict[str, Any]) -> tuple[list[dict[str, Any]], Counter[str], set[str]]:
    errors: list[dict[str, Any]] = []
    type_counts: Counter[str] = Counter()
    ipf_variables: set[str] = set()

    constraints = pack.get("statistical_constraints", [])
    if not isinstance(constraints, list):
        return [{"section": "statistical_constraints", "issue": "not_array"}], type_counts, ipf_variables

    ids: Counter[str] = Counter()
    for idx, constraint in enumerate(constraints):
        missing = missing_fields(constraint, REQUIRED_CONSTRAINT_FIELDS)
        if missing:
            errors.append({"index": idx, "issue": "missing_constraint_fields", "fields": missing})
            continue
        cid = str(constraint.get("constraint_id"))
        ids[cid] += 1
        ctype = constraint.get("type")
        if ctype not in ALLOWED_CONSTRAINT_TYPES:
            errors.append({"index": idx, "constraint_id": cid, "issue": "invalid_constraint_type", "type": ctype})
        confidence = constraint.get("confidence")
        if confidence not in ALLOWED_CONFIDENCE:
            errors.append({"index": idx, "constraint_id": cid, "issue": "invalid_confidence", "confidence": confidence})
        variable_set = constraint.get("variable_set")
        if not isinstance(variable_set, list) or not all(isinstance(v, str) for v in variable_set):
            errors.append({"index": idx, "constraint_id": cid, "issue": "variable_set_not_string_array"})
        elif constraint.get("use_in_ipf") is True:
            ipf_variables.update(variable_set)
        if not isinstance(constraint.get("use_in_ipf"), bool):
            errors.append({"index": idx, "constraint_id": cid, "issue": "use_in_ipf_not_boolean"})
        type_counts[str(ctype)] += 1

    duplicate_ids = sorted(cid for cid, count in ids.items() if count > 1)
    for cid in duplicate_ids:
        errors.append({"constraint_id": cid, "issue": "duplicate_constraint_id"})

    return errors, type_counts, ipf_variables


def validate(pack: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    missing_top = missing_fields(pack, REQUIRED_TOP_LEVEL)
    if missing_top:
        errors.append({"section": "top_level", "issue": "missing_required", "fields": missing_top})

    identity_missing = missing_fields(pack.get("country_identity"), REQUIRED_COUNTRY_IDENTITY)
    if identity_missing:
        errors.append({"section": "country_identity", "issue": "missing_required", "fields": identity_missing})

    build_status = pack.get("build_status", {})
    if not isinstance(build_status, dict):
        errors.append({"section": "build_status", "issue": "not_object"})
        status = None
    else:
        status = build_status.get("status")
        if status not in ALLOWED_BUILD_STATUS:
            errors.append({"section": "build_status", "issue": "invalid_status", "status": status})
        for field in ("can_generate_demo_panel", "can_claim_census_calibrated_panel"):
            if not isinstance(build_status.get(field), bool):
                errors.append({"section": "build_status", "issue": f"{field}_not_boolean"})

    source_priority = pack.get("source_priority", [])
    if not isinstance(source_priority, list) or not source_priority:
        errors.append({"section": "source_priority", "issue": "empty_or_not_array"})
    else:
        for idx, source in enumerate(source_priority):
            missing = missing_fields(source, {"rank", "source_type", "source_name"})
            if missing:
                errors.append({"section": "source_priority", "index": idx, "issue": "missing_source_fields", "fields": missing})

    table_errors, missing_status_counts, variables_seen = validate_tables(pack)
    errors.extend(table_errors)

    constraint_errors, constraint_type_counts, ipf_variables = validate_constraints(pack)
    errors.extend(constraint_errors)

    next_actions = pack.get("next_actions", [])
    if not isinstance(next_actions, list) or not all(isinstance(item, str) for item in next_actions):
        errors.append({"section": "next_actions", "issue": "not_string_array"})

    if status in {"ipf_ready", "calibrated_ready"}:
        minimum_ipf = {"region", "age_band", "sex"}
        missing_ipf = sorted(v for v in minimum_ipf if v not in ipf_variables)
        if missing_ipf:
            errors.append({"section": "statistical_constraints", "issue": "ipf_ready_but_missing_core_ipf_variables", "fields": missing_ipf})

    if build_status.get("can_claim_census_calibrated_panel") is True and status not in {"ipf_ready", "calibrated_ready"}:
        errors.append({"section": "build_status", "issue": "census_claim_true_but_pack_not_ipf_ready", "status": status})

    missing_core_variables = sorted(v for v in CORE_VARIABLES if v not in variables_seen and v not in ipf_variables)
    if missing_core_variables:
        warnings.append({"issue": "core_variables_not_seen_in_tables_or_ipf_constraints", "fields": missing_core_variables})

    unavailable_constraints = [
        c.get("constraint_id")
        for c in pack.get("statistical_constraints", [])
        if isinstance(c, dict) and c.get("type") == "unavailable"
    ]

    return {
        "country": pack.get("country_identity", {}).get("country_name"),
        "iso2": pack.get("country_identity", {}).get("iso2"),
        "build_status": status,
        "required_table_count": len(pack.get("required_tables", [])) if isinstance(pack.get("required_tables"), list) else 0,
        "optional_table_count": len(pack.get("optional_tables", [])) if isinstance(pack.get("optional_tables"), list) else 0,
        "constraint_count": len(pack.get("statistical_constraints", [])) if isinstance(pack.get("statistical_constraints"), list) else 0,
        "constraint_type_counts": dict(constraint_type_counts),
        "table_missing_status_counts": dict(missing_status_counts),
        "ipf_variables": sorted(ipf_variables),
        "unavailable_constraints": unavailable_constraints,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors[:100],
        "warnings": warnings[:100],
        "passes_country_pack_integrity": len(errors) == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("country_pack", type=Path)
    parser.add_argument("--audit", type=Path)
    args = parser.parse_args()

    pack = load_json(args.country_pack)
    summary = validate(pack)
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.audit:
        args.audit.write_text(text + "\n", encoding="utf-8")
    return 0 if summary["passes_country_pack_integrity"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
