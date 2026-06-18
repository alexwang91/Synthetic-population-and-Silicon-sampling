#!/usr/bin/env python3
"""Generate dashboard-ready JSON from a scenario pipeline manifest.

This script is a presentation-data layer. It does not create or modify choices.
It consolidates aggregate results, uncertainty intervals, method settings,
quality diagnostics, subgroup diagnostics, archetype summaries, segment cubes,
reason cubes, and artifact links into one JSON file for a future HTML/dashboard UI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DASHBOARD_DATA_VERSION = "0.2.0"
DEFAULT_PANEL_FIELDS = ["region", "sex", "education_level", "income_decile", "settlement_type", "employment_status"]
DEFAULT_SEGMENT_PAIRS = [("region", "sex"), ("region", "income_decile"), ("income_decile", "settlement_type"), ("education_level", "income_decile")]
CHOICES = ["focal_product", "competitor", "none_or_delay"]


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return default


def iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                value["_line_number"] = line_number
                yield value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_output(manifest: dict[str, Any], key: str, run_dir: Path, default_name: str) -> Path:
    outputs = manifest.get("outputs", {}) if isinstance(manifest.get("outputs"), dict) else {}
    raw = outputs.get(key)
    if isinstance(raw, str) and raw:
        return Path(raw)
    return run_dir / default_name


def rel(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path)


def stable_int(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], 16)


def numeric(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


def get_nested(obj: dict[str, Any], dotted_path: str, default: Any = None) -> Any:
    current: Any = obj
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def first_numeric(obj: dict[str, Any], paths: Iterable[str], default: float | None = None) -> float | None:
    for path in paths:
        value = get_nested(obj, path)
        parsed = numeric(value, math.nan)
        if not math.isnan(parsed):
            return parsed
    return default


def tier_from_score(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "unknown"
    if value < 0.34:
        return "low"
    if value < 0.67:
        return "medium"
    return "high"


def income_tier(value: Any) -> str:
    number = numeric(value, math.nan)
    if math.isnan(number):
        return "unknown"
    if number <= 3:
        return "low"
    if number <= 7:
        return "middle"
    return "high"


def hard_value(persona: dict[str, Any], field: str) -> str:
    hard = persona.get("hard") if isinstance(persona.get("hard"), dict) else {}
    value = hard.get(field, "missing")
    if value is None or value == "":
        return "missing"
    return str(value)


def choice_value(row: dict[str, Any]) -> str:
    value = str(row.get("choice") or "missing")
    return value if value in set(CHOICES) else value


def load_joined_records(personas_path: Path, choice_results_path: Path) -> list[dict[str, Any]]:
    personas: dict[str, dict[str, Any]] = {}
    for persona in iter_jsonl(personas_path) or []:
        persona_id = str(persona.get("persona_id") or "")
        if persona_id:
            personas[persona_id] = persona
    records: list[dict[str, Any]] = []
    for choice in iter_jsonl(choice_results_path) or []:
        persona_id = str(choice.get("persona_id") or "")
        persona = personas.get(persona_id, {})
        weight = numeric(choice.get("population_weight"), numeric(persona.get("population_weight"), 1.0))
        if weight <= 0:
            weight = 1.0
        record = {
            "persona_id": persona_id,
            "population_weight": weight,
            "persona": persona,
            "choice_row": choice,
            "choice": choice_value(choice),
            "answer_confidence": str(choice.get("answer_confidence") or "missing"),
        }
        archetype = infer_archetype(record)
        record["archetype"] = archetype
        records.append(record)
    return records


def weighted_choice_shares(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, float] = defaultdict(float)
    for record in records:
        counts[record["choice"]] += numeric(record.get("population_weight"), 1.0)
    total = sum(counts.values())
    shares = {choice: (counts.get(choice, 0.0) / total if total else 0.0) for choice in sorted(set(CHOICES) | set(counts))}
    return {
        "weighted_counts": dict(counts),
        "weighted_shares": shares,
        "total_weighted_population": total,
        "respondent_count": len(records),
    }


def weighted_reason_counts_from_records(records: list[dict[str, Any]], field: str, max_items: int) -> list[dict[str, Any]]:
    counts: dict[str, float] = defaultdict(float)
    raw_counts: Counter[str] = Counter()
    for record in records:
        row = record.get("choice_row", {})
        weight = numeric(record.get("population_weight"), 1.0)
        values = row.get(field)
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            continue
        for value in values:
            label = str(value)
            counts[label] += weight
            raw_counts[label] += 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:max_items]
    return [{"label": label, "weighted_count": value, "row_count": raw_counts[label]} for label, value in ordered]


def weighted_reason_counts(choice_results: Path, field: str, max_items: int) -> list[dict[str, Any]]:
    counts: dict[str, float] = defaultdict(float)
    raw_counts: Counter[str] = Counter()
    for row in iter_jsonl(choice_results) or []:
        weight = numeric(row.get("population_weight"), 1.0)
        if weight <= 0:
            weight = 1.0
        values = row.get(field)
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            continue
        for value in values:
            label = str(value)
            counts[label] += weight
            raw_counts[label] += 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:max_items]
    return [{"label": label, "weighted_count": value, "row_count": raw_counts[label]} for label, value in ordered]


def infer_archetype(record: dict[str, Any]) -> dict[str, Any]:
    persona = record.get("persona") if isinstance(record.get("persona"), dict) else {}
    hard = persona.get("hard") if isinstance(persona.get("hard"), dict) else {}
    settlement = str(hard.get("settlement_type") or hard.get("urban_rural") or "unknown")
    income = income_tier(hard.get("income_decile") or hard.get("income_band"))
    digital_score = first_numeric(
        persona,
        [
            "soft.media_habits.digital_intensity",
            "soft.media_habits.digital_engagement_score",
            "soft.media_habits.internet_use_frequency_share",
            "soft.shopping_habits.online_shopping_propensity",
            "soft.psychographics.innovation_openness",
        ],
    )
    price_score = first_numeric(
        persona,
        [
            "soft.psychographics.price_sensitivity",
            "soft.shopping_habits.price_sensitivity",
            "soft.category_priors.price_sensitivity",
            "soft.category_priors.price_sensitivity_index",
        ],
    )
    risk_score = first_numeric(persona, ["soft.psychographics.risk_aversion", "soft.category_priors.risk_aversion"])
    digital = tier_from_score(digital_score)
    price = tier_from_score(price_score)
    risk = tier_from_score(risk_score)
    archetype_id = f"{settlement}_{income}_income_{digital}_digital_{price}_price"
    label = f"{settlement.title()} {income} income, {digital} digital, {price} price-sensitive"
    return {
        "archetype_id": archetype_id.replace(" ", "_").lower(),
        "label": label,
        "profile": {
            "settlement_type": settlement,
            "income_tier": income,
            "digital_intensity": digital,
            "price_sensitivity": price,
            "risk_aversion": risk,
        },
        "raw_scores": {
            "digital_intensity": digital_score,
            "price_sensitivity": price_score,
            "risk_aversion": risk_score,
        },
    }


def distribution_for_field(records: list[dict[str, Any]], field: str, total_weight: float) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = defaultdict(lambda: {"weighted_population": 0.0, "respondent_count": 0})
    for record in records:
        value = hard_value(record.get("persona", {}), field)
        groups[value]["weighted_population"] += numeric(record.get("population_weight"), 1.0)
        groups[value]["respondent_count"] += 1
    rows = []
    for value, payload in groups.items():
        weighted_population = payload["weighted_population"]
        rows.append(
            {
                "value": value,
                "weighted_population": weighted_population,
                "weighted_share": weighted_population / total_weight if total_weight else 0.0,
                "respondent_count": payload["respondent_count"],
            }
        )
    rows.sort(key=lambda row: (-row["weighted_population"], row["value"]))
    return rows


def build_country_panel(records: list[dict[str, Any]], fields: list[str]) -> dict[str, Any]:
    total_weight = sum(numeric(record.get("population_weight"), 1.0) for record in records)
    return {
        "respondent_count": len(records),
        "total_weighted_population": total_weight,
        "distributions": {field: distribution_for_field(records, field, total_weight) for field in fields},
    }


def build_filter_options(country_panel: dict[str, Any]) -> dict[str, list[str]]:
    distributions = country_panel.get("distributions", {}) if isinstance(country_panel.get("distributions"), dict) else {}
    options: dict[str, list[str]] = {}
    for field, rows in distributions.items():
        if isinstance(rows, list):
            options[field] = [str(row.get("value")) for row in rows if isinstance(row, dict)]
    return options


def build_archetypes(records: list[dict[str, Any]], max_archetypes: int) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[record["archetype"]["archetype_id"]].append(record)
    total_weight = sum(numeric(record.get("population_weight"), 1.0) for record in records)
    rows = []
    for archetype_id, group in groups.items():
        group_weight = sum(numeric(record.get("population_weight"), 1.0) for record in group)
        archetype = group[0]["archetype"]
        choice = weighted_choice_shares(group)
        rows.append(
            {
                "archetype_id": archetype_id,
                "label": archetype["label"],
                "weighted_population": group_weight,
                "weighted_share": group_weight / total_weight if total_weight else 0.0,
                "respondent_count": len(group),
                "profile": archetype["profile"],
                "choice_shares": choice["weighted_shares"],
                "top_drivers": weighted_reason_counts_from_records(group, "main_drivers", 5),
                "top_barriers": weighted_reason_counts_from_records(group, "main_barriers", 5),
            }
        )
    rows.sort(key=lambda row: (-row["weighted_population"], row["archetype_id"]))
    return rows[:max_archetypes]


def segment_group_key(record: dict[str, Any], fields: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(hard_value(record.get("persona", {}), field) for field in fields)


def segment_row(records: list[dict[str, Any]], fields: tuple[str, ...], values: tuple[str, ...], total_weight: float, min_support: int) -> dict[str, Any]:
    weight = sum(numeric(record.get("population_weight"), 1.0) for record in records)
    choice = weighted_choice_shares(records)
    return {
        "segment": {field: value for field, value in zip(fields, values)},
        "segment_level": "x".join(fields),
        "weighted_population": weight,
        "weighted_population_share": weight / total_weight if total_weight else 0.0,
        "respondent_count": len(records),
        "low_support": len(records) < min_support,
        "choice_shares": choice["weighted_shares"],
    }


def build_segment_choice_cube(records: list[dict[str, Any]], fields: list[str], max_rows: int, min_support: int) -> list[dict[str, Any]]:
    total_weight = sum(numeric(record.get("population_weight"), 1.0) for record in records)
    specs: list[tuple[str, ...]] = [(field,) for field in fields]
    for pair in DEFAULT_SEGMENT_PAIRS:
        if pair[0] in fields and pair[1] in fields:
            specs.append(pair)
    rows = []
    for spec in specs:
        groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            groups[segment_group_key(record, spec)].append(record)
        for values, group in groups.items():
            rows.append(segment_row(group, spec, values, total_weight, min_support))
    rows.sort(key=lambda row: (-row["weighted_population"], row["segment_level"], json.dumps(row["segment"], sort_keys=True)))
    return rows[:max_rows]


def build_reason_cube(records: list[dict[str, Any]], segment_cube: list[dict[str, Any]], max_segments: int, max_reasons: int) -> list[dict[str, Any]]:
    rows = []
    rows.append(
        {
            "segment": {"all": "all"},
            "segment_level": "all",
            "choice": "all",
            "top_drivers": weighted_reason_counts_from_records(records, "main_drivers", max_reasons),
            "top_barriers": weighted_reason_counts_from_records(records, "main_barriers", max_reasons),
        }
    )
    for segment in segment_cube[:max_segments]:
        segment_fields = tuple(segment["segment"].keys())
        segment_values = tuple(segment["segment"].values())
        segment_records = [record for record in records if segment_group_key(record, segment_fields) == segment_values]
        for choice in sorted(set(record["choice"] for record in segment_records)):
            choice_records = [record for record in segment_records if record["choice"] == choice]
            if not choice_records:
                continue
            rows.append(
                {
                    "segment": segment["segment"],
                    "segment_level": segment["segment_level"],
                    "choice": choice,
                    "weighted_population": sum(numeric(record.get("population_weight"), 1.0) for record in choice_records),
                    "respondent_count": len(choice_records),
                    "top_drivers": weighted_reason_counts_from_records(choice_records, "main_drivers", max_reasons),
                    "top_barriers": weighted_reason_counts_from_records(choice_records, "main_barriers", max_reasons),
                }
            )
    return rows


def confidence_priority(value: str) -> float:
    return {"low": 1.0, "medium": 0.55, "high": 0.15}.get(value, 0.35)


def selection_score(record: dict[str, Any]) -> float:
    weight = max(numeric(record.get("population_weight"), 1.0), 1.0)
    score = math.log1p(weight) + confidence_priority(record.get("answer_confidence", "missing"))
    score += (stable_int(str(record.get("persona_id"))) % 1000) / 1_000_000
    return score


def diverse_sample(records: list[dict[str, Any]], target_size: int) -> list[dict[str, Any]]:
    if target_size >= len(records):
        return list(records)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[(record.get("choice", "missing"), record["archetype"]["archetype_id"])].append(record)
    ordered_groups = []
    for key, group in groups.items():
        group.sort(key=lambda record: (-selection_score(record), str(record.get("persona_id"))))
        group_weight = sum(numeric(record.get("population_weight"), 1.0) for record in group)
        ordered_groups.append((key, group_weight, group))
    ordered_groups.sort(key=lambda item: (-item[1], item[0]))
    selected: list[dict[str, Any]] = []
    used: set[str] = set()
    while len(selected) < target_size:
        added = False
        for _, _, group in ordered_groups:
            while group and str(group[0].get("persona_id")) in used:
                group.pop(0)
            if group:
                record = group.pop(0)
                used.add(str(record.get("persona_id")))
                selected.append(record)
                added = True
                if len(selected) >= target_size:
                    break
        if not added:
            break
    return selected


def sample_summary(records: list[dict[str, Any]], selected: list[dict[str, Any]], purpose: str, target_size: int) -> dict[str, Any]:
    choice = weighted_choice_shares(selected)
    strata: dict[str, dict[str, Any]] = defaultdict(lambda: {"respondent_count": 0, "weighted_population": 0.0})
    for record in selected:
        key = f"{record.get('choice')}|{record['archetype']['archetype_id']}"
        strata[key]["respondent_count"] += 1
        strata[key]["weighted_population"] += numeric(record.get("population_weight"), 1.0)
    strata_rows = [
        {"stratum": key, "respondent_count": value["respondent_count"], "weighted_population": value["weighted_population"]}
        for key, value in sorted(strata.items(), key=lambda item: (-item[1]["weighted_population"], item[0]))[:30]
    ]
    return {
        "target_size": target_size,
        "selected_count": len(selected),
        "purpose": purpose,
        "selection_policy": "diverse deterministic sample across choice x archetype, prioritized by population_weight and lower answer_confidence",
        "choice_shares": choice["weighted_shares"],
        "weighted_population": choice["total_weighted_population"],
        "strata_summary": strata_rows,
        "persona_id_preview": [record.get("persona_id") for record in selected[:25]],
    }


def compact_case_card(record: dict[str, Any]) -> dict[str, Any]:
    persona = record.get("persona", {}) if isinstance(record.get("persona"), dict) else {}
    hard = persona.get("hard", {}) if isinstance(persona.get("hard"), dict) else {}
    row = record.get("choice_row", {}) if isinstance(record.get("choice_row"), dict) else {}
    return {
        "persona_id": record.get("persona_id"),
        "population_weight": record.get("population_weight"),
        "archetype_id": record["archetype"]["archetype_id"],
        "archetype_label": record["archetype"]["label"],
        "hard": {key: hard.get(key) for key in DEFAULT_PANEL_FIELDS if key in hard},
        "choice": record.get("choice"),
        "answer_confidence": record.get("answer_confidence"),
        "main_drivers": row.get("main_drivers", [])[:3] if isinstance(row.get("main_drivers"), list) else [],
        "main_barriers": row.get("main_barriers", [])[:3] if isinstance(row.get("main_barriers"), list) else [],
        "switch_conditions": row.get("switch_conditions", [])[:2] if isinstance(row.get("switch_conditions"), list) else [],
    }


def build_sample_layers(records: list[dict[str, Any]], medium_size: int, deep_size: int) -> dict[str, Any]:
    medium = diverse_sample(records, min(medium_size, len(records)))
    deep = diverse_sample(medium if medium else records, min(deep_size, len(medium if medium else records)))
    return {
        "quantitative_panel": {
            "target_size": len(records),
            "selected_count": len(records),
            "purpose": "full weighted quantitative choice estimation and segment filtering",
            "choice_shares": weighted_choice_shares(records)["weighted_shares"],
        },
        "medium_explanation_sample": sample_summary(records, medium, "medium-detail explanation and reason-code review", medium_size),
        "deep_case_sample": sample_summary(records, deep, "compact persona case cards and qualitative dashboard examples", deep_size),
        "deep_case_cards": [compact_case_card(record) for record in deep],
    }


def choice_rows(choice_audit: dict[str, Any], bootstrap: dict[str, Any]) -> list[dict[str, Any]]:
    shares = choice_audit.get("weighted_choice_shares", {}) if isinstance(choice_audit, dict) else {}
    if not isinstance(shares, dict):
        shares = {}
    intervals = {}
    point = {}
    if isinstance(bootstrap, dict):
        overall = bootstrap.get("overall", {}) if isinstance(bootstrap.get("overall"), dict) else {}
        intervals = overall.get("intervals", {}) if isinstance(overall.get("intervals"), dict) else {}
        point = overall.get("point", {}) if isinstance(overall.get("point"), dict) else {}
    if not shares:
        shares = point
    keys = sorted(set(shares) | set(intervals))
    rows = []
    for key in keys:
        interval = intervals.get(key, {}) if isinstance(intervals.get(key), dict) else {}
        rows.append(
            {
                "choice": key,
                "share": shares.get(key),
                "p2_5": interval.get("p2_5"),
                "p50": interval.get("p50"),
                "p97_5": interval.get("p97_5"),
            }
        )
    rows.sort(key=lambda row: (-(row.get("share") or 0), row.get("choice") or ""))
    return rows


def audit_card(name: str, status: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "status": status, "details": details}


def build_quality_cards(artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    ipf = artifacts.get("ipf_audit") or {}
    cards.append(audit_card("IPF / raking", "pass" if ipf.get("converged") is True else "review", {"iterations": ipf.get("iterations_completed"), "warnings": ipf.get("warning_count")}))
    persona = artifacts.get("persona_coherence_audit") or {}
    cards.append(audit_card("Persona coherence", "pass" if persona.get("passes_persona_coherence") is True else "review", {"errors": persona.get("error_count"), "warnings": persona.get("warning_count")}))
    product = artifacts.get("product_scenario_audit") or {}
    cards.append(audit_card("Product scenario", "pass" if product.get("passes_product_scenario_normalization") is True else "review", {"alternatives": product.get("alternative_count"), "outside_option": product.get("outside_option_included")}))
    choice = artifacts.get("choice_interview_validation") or {}
    cards.append(audit_card("Choice row integrity", "pass" if choice.get("passes_choice_interview_integrity") is True else "review", {"records": choice.get("record_count"), "errors": choice.get("error_count"), "warnings": choice.get("warning_count")}))
    llm_quality = artifacts.get("llm_choice_quality_audit") or {}
    if llm_quality:
        cards.append(audit_card("LLM choice quality", "pass" if llm_quality.get("passes_llm_choice_quality_validation") is True else "review", {"errors": llm_quality.get("error_count"), "warnings": llm_quality.get("warning_count")}))
    artifact_validation = artifacts.get("pipeline_artifact_validation") or {}
    if artifact_validation:
        cards.append(audit_card("Pipeline artifact validation", "pass" if artifact_validation.get("passes_pipeline_artifact_validation") is True else "review", {"errors": artifact_validation.get("error_count"), "warnings": artifact_validation.get("warning_count")}))
    return cards


def product_summary(scenario: dict[str, Any]) -> dict[str, Any]:
    alternatives = []
    for item in scenario.get("alternatives", []) if isinstance(scenario.get("alternatives"), list) else []:
        if not isinstance(item, dict):
            continue
        alternatives.append({"id": item.get("id"), "name": item.get("name"), "is_outside_option": item.get("is_outside_option"), "price": item.get("price"), "currency": item.get("currency", scenario.get("currency")), "normalized_attributes": item.get("normalized_attributes", {})})
    return {"scenario_id": scenario.get("scenario_id"), "category": scenario.get("category"), "currency": scenario.get("currency"), "choice_task_type": scenario.get("choice_task_type"), "alternatives": alternatives}


def risk_summary(llm_quality: dict[str, Any]) -> dict[str, Any]:
    warnings = llm_quality.get("warnings", []) if isinstance(llm_quality.get("warnings"), list) else []
    errors = llm_quality.get("errors", []) if isinstance(llm_quality.get("errors"), list) else []
    issue_counts: Counter[str] = Counter()
    for item in warnings + errors:
        if isinstance(item, dict):
            issue_counts[str(item.get("issue", "unknown"))] += 1
    return {"error_count": llm_quality.get("error_count", 0), "warning_count": llm_quality.get("warning_count", 0), "issue_counts": dict(issue_counts), "warnings": warnings[:20], "errors": errors[:20], "choice_distribution": llm_quality.get("choice_distribution", {}), "confidence_distribution": llm_quality.get("confidence_distribution", {}), "subgroup_choice_analysis": (llm_quality.get("diagnostics", {}) or {}).get("subgroup_choice_analysis", {}), "position_shares": (llm_quality.get("diagnostics", {}) or {}).get("position_shares", {})}


def build_dashboard_data(manifest_path: Path, max_reasons: int, max_artifacts: int, max_archetypes: int, max_segments: int, max_reason_segments: int, min_segment_support: int, medium_sample_size: int, deep_sample_size: int) -> dict[str, Any]:
    manifest = load_json(manifest_path, {}) or {}
    run_dir = manifest_path.resolve().parent
    root = Path.cwd()
    outputs = manifest.get("outputs", {}) if isinstance(manifest.get("outputs"), dict) else {}
    boundary = manifest.get("scientific_boundary", {}) if isinstance(manifest.get("scientific_boundary"), dict) else {}
    inputs = manifest.get("inputs", {}) if isinstance(manifest.get("inputs"), dict) else {}

    paths = {
        "personas_enriched": resolve_output(manifest, "personas_enriched", run_dir, "personas_enriched.jsonl"),
        "choice_results": resolve_output(manifest, "choice_results", run_dir, "choice_results.jsonl"),
        "choice_model_audit": resolve_output(manifest, "choice_model_audit", run_dir, "choice_model_audit.json"),
        "llm_choice_prompt_audit": resolve_output(manifest, "llm_choice_prompt_audit", run_dir, "llm_choice_prompt_audit.json"),
        "llm_choice_interview_audit": resolve_output(manifest, "llm_choice_interview_audit", run_dir, "llm_choice_interview_audit.json"),
        "llm_choice_quality_audit": resolve_output(manifest, "llm_choice_quality_audit", run_dir, "llm_choice_quality_audit.json"),
        "choice_interview_validation": resolve_output(manifest, "choice_interview_validation", run_dir, "choice_interview_validation.json"),
        "bootstrap_intervals": resolve_output(manifest, "bootstrap_intervals", run_dir, "bootstrap_intervals.json"),
        "persona_coherence_audit": resolve_output(manifest, "persona_coherence_audit", run_dir, "persona_coherence_audit.json"),
        "ipf_audit": resolve_output(manifest, "ipf_audit", run_dir, "ipf_audit.json"),
        "product_scenario_audit": resolve_output(manifest, "product_scenario_audit", run_dir, "product_scenario_audit.json"),
        "normalized_choice_scenario": resolve_output(manifest, "normalized_choice_scenario", run_dir, "normalized_choice_scenario.json"),
        "pipeline_artifact_validation": resolve_output(manifest, "pipeline_artifact_validation", run_dir, "pipeline_artifact_validation.json"),
        "market_report_json": resolve_output(manifest, "market_report_json", run_dir, "market_report.json"),
    }

    artifacts = {key: load_json(path, {}) or {} for key, path in paths.items() if key not in {"choice_results", "personas_enriched"}}
    choice_model = artifacts.get("choice_model_audit") or {}
    bootstrap = artifacts.get("bootstrap_intervals") or {}
    validation = artifacts.get("choice_interview_validation") or {}
    llm_quality = artifacts.get("llm_choice_quality_audit") or {}
    llm_prompt = artifacts.get("llm_choice_prompt_audit") or {}
    llm_interview = artifacts.get("llm_choice_interview_audit") or {}
    records = load_joined_records(paths["personas_enriched"], paths["choice_results"])
    panel_fields = list((load_json(paths["personas_enriched"], {}) or {}).keys()) if False else DEFAULT_PANEL_FIELDS
    country_panel = build_country_panel(records, panel_fields)
    segment_cube = build_segment_choice_cube(records, panel_fields, max_segments, min_segment_support)

    artifact_list = []
    for key, raw in sorted(outputs.items()):
        if len(artifact_list) >= max_artifacts:
            break
        if isinstance(raw, str):
            artifact_list.append({"name": key, "path": rel(Path(raw), root)})

    total_weight = choice_model.get("total_weight") or bootstrap.get("total_weight") or country_panel.get("total_weighted_population")
    if not total_weight and isinstance(bootstrap.get("overall"), dict):
        total_weight = bootstrap.get("overall", {}).get("total_weight")

    return {
        "dashboard_data_version": DASHBOARD_DATA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run": {"run_id": manifest.get("run_id"), "pipeline_status": manifest.get("status"), "pipeline_version": manifest.get("pipeline_version"), "created_at": manifest.get("created_at")},
        "method": {"pipeline_method": manifest.get("method"), "interview_engine": manifest.get("interview_engine", "rule_based_baseline"), "calibration_level": boundary.get("choice_model_calibration_level"), "order_policy": inputs.get("llm_order_policy") or llm_prompt.get("order_policy"), "prompt_variant": inputs.get("llm_prompt_variant") or llm_prompt.get("prompt_variant"), "prompt_version": llm_prompt.get("prompt_version") or llm_interview.get("prompt_version"), "original_plan_alignment": boundary.get("original_plan_alignment"), "llm_risk_controls": boundary.get("llm_risk_controls", []), "limitations": boundary.get("limitations", [])},
        "inputs": inputs,
        "country_panel": country_panel,
        "archetypes": build_archetypes(records, max_archetypes),
        "filter_options": build_filter_options(country_panel),
        "segment_choice_cube": segment_cube,
        "reason_cube": build_reason_cube(records, segment_cube, max_reason_segments, max_reasons),
        "sample_layers": build_sample_layers(records, medium_sample_size, deep_sample_size),
        "product_scenario": product_summary(artifacts.get("normalized_choice_scenario") or {}),
        "results": {"record_count": choice_model.get("record_count") or validation.get("record_count") or len(records), "total_weight": total_weight, "choice_shares": choice_rows(choice_model, bootstrap), "confidence_counts": validation.get("answer_confidence_counts", {}), "top_drivers": weighted_reason_counts(paths["choice_results"], "main_drivers", max_reasons), "top_barriers": weighted_reason_counts(paths["choice_results"], "main_barriers", max_reasons)},
        "quality": {"cards": build_quality_cards(artifacts), "llm_risk_summary": risk_summary(llm_quality), "choice_validation": validation, "pipeline_artifact_validation": artifacts.get("pipeline_artifact_validation") or {}},
        "artifacts": artifact_list,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-reasons", type=int, default=12)
    parser.add_argument("--max-artifacts", type=int, default=40)
    parser.add_argument("--max-archetypes", type=int, default=8)
    parser.add_argument("--max-segments", type=int, default=250)
    parser.add_argument("--max-reason-segments", type=int, default=80)
    parser.add_argument("--min-segment-support", type=int, default=10)
    parser.add_argument("--medium-sample-size", type=int, default=1000)
    parser.add_argument("--deep-sample-size", type=int, default=100)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for name in ["max_reasons", "max_artifacts", "max_archetypes", "max_segments", "max_reason_segments", "min_segment_support", "medium_sample_size", "deep_sample_size"]:
        if getattr(args, name) <= 0:
            raise ValueError(f"--{name.replace('_', '-')} must be positive")
    manifest = args.manifest.resolve()
    output = args.output or manifest.parent / "dashboard_data.json"
    data = build_dashboard_data(manifest, args.max_reasons, args.max_artifacts, args.max_archetypes, args.max_segments, args.max_reason_segments, args.min_segment_support, args.medium_sample_size, args.deep_sample_size)
    write_json(output, data)
    print(json.dumps({"run_id": data["run"].get("run_id"), "output": str(output), "dashboard_data_version": DASHBOARD_DATA_VERSION}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
