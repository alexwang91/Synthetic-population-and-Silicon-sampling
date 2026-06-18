#!/usr/bin/env python3
"""Prepare or validate LLM short choice interviews for all representative personas.

This script is the intended synthetic-respondent interview entrypoint. It keeps
the original product design intact: every selected representative persona can be
asked the same product choice task and should produce one discrete choice row.

Initial implementation supports prompt export and response normalization. It
intentionally does not assume a specific LLM provider SDK is available.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


PROMPT_VERSION = "llm_choice_short_v0_1"
ALLOWED_CHOICES = {"focal_product", "competitor", "none_or_delay"}


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_number}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"line {line_number}: expected JSON object")
            value["_line_number"] = line_number
            yield value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


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


def concise_persona(persona: dict[str, Any], *, include_story: bool, max_story_chars: int) -> dict[str, Any]:
    payload = {
        "persona_id": persona.get("persona_id"),
        "population_weight": persona.get("population_weight"),
        "hard": persona.get("hard", {}),
        "soft": persona.get("soft", {}),
    }
    if include_story:
        story = persona.get("story") or persona.get("narrative") or persona.get("persona_story")
        if isinstance(story, str) and story.strip():
            payload["story"] = story.strip()[:max_story_chars]
    return payload


def concise_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    alternatives = []
    for item in scenario.get("alternatives", []):
        if not isinstance(item, dict):
            continue
        alternatives.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "is_outside_option": item.get("is_outside_option", False),
                "price": item.get("price"),
                "currency": item.get("currency", scenario.get("currency")),
                "brand": item.get("brand"),
                "warranty": item.get("warranty"),
                "normalized_attributes": item.get("normalized_attributes", {}),
                "raw_attributes": item.get("raw_attributes", {}),
            }
        )
    return {
        "scenario_id": scenario.get("scenario_id"),
        "category": scenario.get("category"),
        "currency": scenario.get("currency"),
        "choice_task_type": scenario.get("choice_task_type"),
        "alternatives": alternatives,
    }


def prompt_text(persona_payload: dict[str, Any], scenario_payload: dict[str, Any]) -> str:
    return (
        "You are simulating one isolated synthetic consumer respondent.\n"
        "Answer only as this respondent. Do not use aggregate shares, quotas, or other respondents.\n"
        "Choose exactly one option from the product scenario.\n"
        "Return strict JSON with keys: choice, chosen_alternative_id, chosen_alternative_name, interview_response, main_drivers, main_barriers, switch_conditions, answer_confidence.\n"
        "Allowed choice values: focal_product, competitor, none_or_delay.\n"
        "Use focal_product for the first non-outside alternative, competitor for other product alternatives, and none_or_delay for the outside option.\n"
        "Keep interview_response to 1-3 sentences.\n\n"
        f"PERSONA:\n{json.dumps(persona_payload, ensure_ascii=False, sort_keys=True)}\n\n"
        f"PRODUCT_SCENARIO:\n{json.dumps(scenario_payload, ensure_ascii=False, sort_keys=True)}\n"
    )


def build_prompt_rows(
    personas_path: Path,
    scenario: dict[str, Any],
    *,
    limit: int | None,
    include_story: bool,
    max_story_chars: int,
) -> list[dict[str, Any]]:
    scenario_payload = concise_scenario(scenario)
    rows: list[dict[str, Any]] = []
    for index, persona in enumerate(iter_jsonl(personas_path), 1):
        if limit is not None and len(rows) >= limit:
            break
        persona_id = str(persona.get("persona_id") or f"row_{index}")
        persona_payload = concise_persona(persona, include_story=include_story, max_story_chars=max_story_chars)
        task_id = hashlib.sha256(f"{persona_id}:{scenario_payload.get('scenario_id')}:{PROMPT_VERSION}".encode("utf-8")).hexdigest()[:24]
        rows.append(
            {
                "task_id": task_id,
                "persona_id": persona_id,
                "population_weight": numeric(persona.get("population_weight"), 0.0),
                "prompt_version": PROMPT_VERSION,
                "prompt": prompt_text(persona_payload, scenario_payload),
                "persona": persona_payload,
                "scenario_id": scenario_payload.get("scenario_id"),
                "expected_output_schema": {
                    "choice": "focal_product|competitor|none_or_delay",
                    "chosen_alternative_id": "string",
                    "chosen_alternative_name": "string",
                    "interview_response": "1-3 sentences",
                    "main_drivers": "array[string]",
                    "main_barriers": "array[string]",
                    "switch_conditions": "array[string]",
                    "answer_confidence": "high|medium|low",
                },
            }
        )
    return rows


def normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def normalize_response_row(response: dict[str, Any], prompt_by_persona: dict[str, dict[str, Any]]) -> dict[str, Any]:
    persona_id = str(response.get("persona_id") or "")
    prompt_row = prompt_by_persona.get(persona_id, {})
    choice = str(response.get("choice") or "").strip()
    if choice not in ALLOWED_CHOICES:
        choice = "none_or_delay"
    confidence = str(response.get("answer_confidence") or "medium").strip().lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"
    return {
        "persona_id": persona_id,
        "population_weight": numeric(response.get("population_weight"), numeric(prompt_row.get("population_weight"), 0.0)),
        "choice": choice,
        "chosen_alternative_id": response.get("chosen_alternative_id"),
        "chosen_alternative_name": response.get("chosen_alternative_name"),
        "interview_response": str(response.get("interview_response") or ""),
        "main_drivers": normalize_list(response.get("main_drivers")),
        "main_barriers": normalize_list(response.get("main_barriers")),
        "switch_conditions": normalize_list(response.get("switch_conditions")),
        "answer_confidence": confidence,
        "isolation": {
            "context_scope": "single_persona",
            "saw_other_answers": False,
            "saw_aggregate_results": False,
            "saw_target_proportion": False,
        },
        "generation_controls": {
            "method": "llm_short_choice_interview",
            "prompt_version": PROMPT_VERSION,
            "task_id": response.get("task_id") or prompt_row.get("task_id"),
            "model": response.get("model"),
            "temperature": response.get("temperature"),
        },
        "quality_controls": {
            "llm_generated": True,
            "score_only": False,
            "discrete_choice_record": True,
            "probabilities_are_diagnostics_only": False,
            "calibration_level": "synthetic_llm_respondent_uncalibrated" if not response.get("calibration_level") else response.get("calibration_level"),
        },
    }


def normalize_responses(prompt_file: Path, response_file: Path, output_file: Path, audit_file: Path | None) -> dict[str, Any]:
    prompt_rows = list(iter_jsonl(prompt_file))
    prompt_by_persona = {str(row.get("persona_id")): row for row in prompt_rows}
    output_rows: list[dict[str, Any]] = []
    missing_persona_ids = []
    for response in iter_jsonl(response_file):
        row = normalize_response_row(response, prompt_by_persona)
        if not row["persona_id"]:
            missing_persona_ids.append(response.get("_line_number"))
        output_rows.append(row)
    write_jsonl(output_file, output_rows)
    audit = {
        "prompt_version": PROMPT_VERSION,
        "prompt_count": len(prompt_rows),
        "response_count": len(output_rows),
        "missing_persona_id_rows": missing_persona_ids,
        "coverage_rate": (len(output_rows) / len(prompt_rows)) if prompt_rows else 0.0,
        "output": str(output_file),
        "method": "normalize_llm_choice_interview_responses",
        "warnings": [] if len(output_rows) == len(prompt_rows) else ["response_count_does_not_match_prompt_count"],
    }
    if audit_file:
        write_json(audit_file, audit)
    return audit


def export_prompts(args: argparse.Namespace) -> int:
    scenario = load_json(args.normalized_choice_scenario)
    rows = build_prompt_rows(
        args.personas_enriched,
        scenario,
        limit=args.limit,
        include_story=args.include_story,
        max_story_chars=args.max_story_chars,
    )
    write_jsonl(args.output_prompts, rows)
    audit = {
        "prompt_version": PROMPT_VERSION,
        "mode": "export_prompts",
        "prompt_count": len(rows),
        "personas_input": str(args.personas_enriched),
        "scenario_input": str(args.normalized_choice_scenario),
        "output_prompts": str(args.output_prompts),
        "include_story": args.include_story,
        "max_story_chars": args.max_story_chars,
        "llm_provider": "external_batch_or_future_provider_integration",
        "scientific_boundary": "These prompts implement the intended all-persona LLM short choice interview mode; aggregation must still use population_weight over discrete choices.",
    }
    if args.audit:
        write_json(args.audit, audit)
    else:
        print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    export = subparsers.add_parser("export-prompts", help="Create JSONL prompts for all or selected personas.")
    export.add_argument("personas_enriched", type=Path)
    export.add_argument("normalized_choice_scenario", type=Path)
    export.add_argument("--output-prompts", type=Path, required=True)
    export.add_argument("--audit", type=Path)
    export.add_argument("--limit", type=int)
    export.add_argument("--include-story", action="store_true")
    export.add_argument("--max-story-chars", type=int, default=900)

    normalize = subparsers.add_parser("normalize-responses", help="Normalize external LLM response JSONL to choice_results.jsonl.")
    normalize.add_argument("prompt_file", type=Path)
    normalize.add_argument("response_file", type=Path)
    normalize.add_argument("--output", type=Path, required=True)
    normalize.add_argument("--audit", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "export-prompts":
        if args.limit is not None and args.limit <= 0:
            raise ValueError("--limit must be positive when supplied")
        if args.max_story_chars <= 0:
            raise ValueError("--max-story-chars must be positive")
        return export_prompts(args)
    if args.command == "normalize-responses":
        normalize_responses(args.prompt_file, args.response_file, args.output, args.audit)
        return 0
    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
