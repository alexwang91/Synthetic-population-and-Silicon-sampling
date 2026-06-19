#!/usr/bin/env python3
"""Prepare or validate LLM short choice interviews for all representative personas.

This script is the intended synthetic-respondent interview entrypoint. It keeps
the original product design intact: every selected representative persona can be
asked the same product choice task and should produce one discrete choice row.

The prompt exporter implements current LLM-survey risk controls: explicit
choice-role mapping, optional deterministic alternative-order counterbalancing,
recorded prompt variants, and compact prompts that avoid exposing aggregate
results or other respondents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


PROMPT_VERSION = "llm_choice_short_v0_2"
BATCH_VERSION = "llm_choice_batch_v0_1"
ALLOWED_CHOICES = {"focal_product", "competitor", "none_or_delay"}

ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-haiku-4-5"
# Opus 4.7/4.8 and Fable 5 reject temperature/top_p/top_k (HTTP 400). Detect by id
# substring so the batch runner omits temperature for those models automatically.
NO_SAMPLING_MODEL_MARKERS = ("opus-4-8", "opus-4-7", "fable-5")
BATCH_SYSTEM_PROMPT = (
    "You simulate one isolated synthetic consumer respondent answering a product choice task. "
    "Respond with exactly one minified JSON object and no other text, code fences, or commentary."
)


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


def stable_int(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], 16)


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


def canonical_choice_label(item: dict[str, Any], non_outside_index: int) -> str:
    if item.get("is_outside_option", False):
        return "none_or_delay"
    if non_outside_index == 0:
        return "focal_product"
    return "competitor"


def base_alternatives(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    alternatives: list[dict[str, Any]] = []
    non_outside_index = 0
    for canonical_position, item in enumerate(scenario.get("alternatives", []), 1):
        if not isinstance(item, dict):
            continue
        label = canonical_choice_label(item, non_outside_index)
        if not item.get("is_outside_option", False):
            non_outside_index += 1
        alternatives.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "canonical_choice_label": label,
                "canonical_position": canonical_position,
                "is_outside_option": item.get("is_outside_option", False),
                "price": item.get("price"),
                "currency": item.get("currency", scenario.get("currency")),
                "brand": item.get("brand"),
                "warranty": item.get("warranty"),
                "normalized_attributes": item.get("normalized_attributes", {}),
                "raw_attributes": item.get("raw_attributes", {}),
            }
        )
    return alternatives


def counterbalanced_order(alternatives: list[dict[str, Any]], key: str, policy: str) -> list[dict[str, Any]]:
    if policy == "canonical":
        ordered = list(alternatives)
    elif policy == "reverse":
        product_alts = [alt for alt in alternatives if not alt.get("is_outside_option")]
        outside = [alt for alt in alternatives if alt.get("is_outside_option")]
        ordered = list(reversed(product_alts)) + outside
    elif policy == "rotate":
        product_alts = [alt for alt in alternatives if not alt.get("is_outside_option")]
        outside = [alt for alt in alternatives if alt.get("is_outside_option")]
        if product_alts:
            shift = stable_int(key) % len(product_alts)
            ordered = product_alts[shift:] + product_alts[:shift] + outside
        else:
            ordered = outside
    else:
        raise ValueError("order policy must be one of: canonical, reverse, rotate")
    result = []
    for presented_position, alt in enumerate(ordered, 1):
        copy = dict(alt)
        copy["presented_position"] = presented_position
        result.append(copy)
    return result


def concise_scenario(scenario: dict[str, Any], *, persona_id: str, order_policy: str) -> dict[str, Any]:
    alternatives = counterbalanced_order(base_alternatives(scenario), f"{persona_id}:{scenario.get('scenario_id')}", order_policy)
    return {
        "scenario_id": scenario.get("scenario_id"),
        "category": scenario.get("category"),
        "currency": scenario.get("currency"),
        "choice_task_type": scenario.get("choice_task_type"),
        "choice_label_rule": "Return the canonical_choice_label of the option you choose; do not infer choice from presented_position.",
        "order_policy": order_policy,
        "alternatives": alternatives,
    }


def prompt_text(persona_payload: dict[str, Any], scenario_payload: dict[str, Any], *, prompt_variant: str) -> str:
    variant_line = {
        "neutral": "Make the choice that best fits this respondent's needs and constraints.",
        "tradeoff": "Focus on realistic trade-offs across price, brand trust, features, warranty, risk, and outside option.",
    }[prompt_variant]
    return (
        "You are simulating one isolated synthetic consumer respondent.\n"
        "Answer only as this respondent. Do not use aggregate shares, quotas, target proportions, or other respondents.\n"
        "Choose exactly one option from the product scenario.\n"
        f"{variant_line}\n"
        "Return strict JSON with keys: choice, chosen_alternative_id, chosen_alternative_name, interview_response, main_drivers, main_barriers, switch_conditions, answer_confidence.\n"
        "Allowed choice values: focal_product, competitor, none_or_delay.\n"
        "Use the selected option's canonical_choice_label as the choice value. Do not use option order or presented_position to decide the label.\n"
        "Do not choose an option merely because it is shown first or last.\n"
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
    order_policy: str,
    prompt_variant: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, persona in enumerate(iter_jsonl(personas_path), 1):
        if limit is not None and len(rows) >= limit:
            break
        persona_id = str(persona.get("persona_id") or f"row_{index}")
        persona_payload = concise_persona(persona, include_story=include_story, max_story_chars=max_story_chars)
        scenario_payload = concise_scenario(scenario, persona_id=persona_id, order_policy=order_policy)
        task_id = hashlib.sha256(f"{persona_id}:{scenario_payload.get('scenario_id')}:{PROMPT_VERSION}:{order_policy}:{prompt_variant}".encode("utf-8")).hexdigest()[:24]
        rows.append(
            {
                "task_id": task_id,
                "persona_id": persona_id,
                "population_weight": numeric(persona.get("population_weight"), 0.0),
                "prompt_version": PROMPT_VERSION,
                "prompt_variant": prompt_variant,
                "order_policy": order_policy,
                "presented_alternative_order": [alt.get("id") for alt in scenario_payload.get("alternatives", [])],
                "choice_label_map": {alt.get("id"): alt.get("canonical_choice_label") for alt in scenario_payload.get("alternatives", [])},
                "prompt": prompt_text(persona_payload, scenario_payload, prompt_variant=prompt_variant),
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
    choice_label_map = prompt_row.get("choice_label_map", {}) if isinstance(prompt_row.get("choice_label_map"), dict) else {}
    chosen_id = response.get("chosen_alternative_id")
    choice = str(response.get("choice") or "").strip()
    mapped_choice = choice_label_map.get(str(chosen_id)) if chosen_id is not None else None
    if isinstance(mapped_choice, str) and mapped_choice in ALLOWED_CHOICES:
        choice = mapped_choice
    elif choice not in ALLOWED_CHOICES:
        choice = "none_or_delay"
    confidence = str(response.get("answer_confidence") or "medium").strip().lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"
    return {
        "persona_id": persona_id,
        "population_weight": numeric(response.get("population_weight"), numeric(prompt_row.get("population_weight"), 0.0)),
        "choice": choice,
        "chosen_alternative_id": chosen_id,
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
            "prompt_variant": prompt_row.get("prompt_variant"),
            "order_policy": prompt_row.get("order_policy"),
            "presented_alternative_order": prompt_row.get("presented_alternative_order"),
            "choice_label_map": choice_label_map,
            "task_id": response.get("task_id") or prompt_row.get("task_id"),
            "seed": response.get("seed") or f"task:{response.get('task_id') or prompt_row.get('task_id')}",
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
    choice_remap_count = 0
    for response in iter_jsonl(response_file):
        row = normalize_response_row(response, prompt_by_persona)
        prompt_row = prompt_by_persona.get(str(response.get("persona_id") or ""), {})
        choice_label_map = prompt_row.get("choice_label_map", {}) if isinstance(prompt_row.get("choice_label_map"), dict) else {}
        chosen_id = response.get("chosen_alternative_id")
        if chosen_id is not None and choice_label_map.get(str(chosen_id)) and response.get("choice") != choice_label_map.get(str(chosen_id)):
            choice_remap_count += 1
        if not row["persona_id"]:
            missing_persona_ids.append(response.get("_line_number"))
        output_rows.append(row)
    write_jsonl(output_file, output_rows)
    audit = {
        "prompt_version": PROMPT_VERSION,
        "prompt_count": len(prompt_rows),
        "response_count": len(output_rows),
        "missing_persona_id_rows": missing_persona_ids,
        "choice_remap_count": choice_remap_count,
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
        order_policy=args.order_policy,
        prompt_variant=args.prompt_variant,
    )
    write_jsonl(args.output_prompts, rows)
    order_counts: dict[str, int] = {}
    for row in rows:
        key = "|".join(str(item) for item in row.get("presented_alternative_order", []))
        order_counts[key] = order_counts.get(key, 0) + 1
    audit = {
        "prompt_version": PROMPT_VERSION,
        "mode": "export_prompts",
        "prompt_count": len(rows),
        "personas_input": str(args.personas_enriched),
        "scenario_input": str(args.normalized_choice_scenario),
        "output_prompts": str(args.output_prompts),
        "include_story": args.include_story,
        "max_story_chars": args.max_story_chars,
        "prompt_variant": args.prompt_variant,
        "order_policy": args.order_policy,
        "presented_order_counts": order_counts,
        "llm_provider": "external_batch_or_future_provider_integration",
        "scientific_boundary": "These prompts implement the intended all-persona LLM short choice interview mode; aggregation must still use population_weight over discrete choices.",
        "risk_controls": [
            "single_persona_isolation",
            "explicit_canonical_choice_label_map",
            "optional_counterbalanced_alternative_order",
            "recorded_prompt_variant",
            "no_aggregate_or_target_share_context",
        ],
    }
    if args.audit:
        write_json(args.audit, audit)
    else:
        print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def model_accepts_temperature(model: str) -> bool:
    lowered = model.lower()
    return not any(marker in lowered for marker in NO_SAMPLING_MODEL_MARKERS)


def extract_json_object(text: str) -> dict[str, Any]:
    """Best-effort parse of a single JSON object from raw model output."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        newline = text.find("\n")
        if newline != -1 and text[:newline].strip().lower() in {"json", ""}:
            text = text[newline + 1 :]
        text = text.strip()
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : index + 1]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    raise ValueError("no JSON object found in model output")


def anthropic_message(
    prompt: str,
    *,
    model: str,
    temperature: float,
    max_output_tokens: int,
    api_key: str,
    base_url: str,
    timeout: float,
) -> str:
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": max_output_tokens,
        "system": BATCH_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
    }
    # Opus 4.7/4.8 and Fable 5 reject sampling params; only send temperature where supported.
    if model_accepts_temperature(model):
        body["temperature"] = temperature
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        base_url,
        data=data,
        method="POST",
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    blocks = payload.get("content") or []
    texts = [block.get("text", "") for block in blocks if isinstance(block, dict) and block.get("type") == "text"]
    return "".join(texts)


def call_with_retry(fn, *, max_retries: int, base_delay: float) -> str:
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in {408, 409, 429} and exc.code < 500:
                raise
        except urllib.error.URLError as exc:
            last_error = exc
        if attempt < max_retries:
            delay = min(base_delay * (2 ** attempt), 30.0) + random.uniform(0, base_delay)
            time.sleep(delay)
    assert last_error is not None
    raise last_error


def mock_raw_response(prompt_row: dict[str, Any]) -> dict[str, Any]:
    """Deterministic offline stand-in for a model response.

    Produces a schema-valid choice derived from the persona id and the scenario's
    own alternatives so the full llm_short_all path is runnable and testable with
    no API key. It is NOT a model and must never be presented as one.
    """
    label_map = prompt_row.get("choice_label_map", {})
    if not isinstance(label_map, dict) or not label_map:
        return {"choice": "none_or_delay", "answer_confidence": "low", "interview_response": "No options were available."}
    persona_id = str(prompt_row.get("persona_id") or "")
    persona = prompt_row.get("persona", {}) if isinstance(prompt_row.get("persona"), dict) else {}
    soft = persona.get("soft", {}) if isinstance(persona.get("soft"), dict) else {}
    psych = soft.get("psychographics", {}) if isinstance(soft.get("psychographics"), dict) else {}
    bucket = stable_int(persona_id + ":mock") % 100
    price_sensitivity = numeric(psych.get("price_sensitivity"), 0.5)
    outside_ids = [alt_id for alt_id, label in label_map.items() if label == "none_or_delay"]
    product_ids = [alt_id for alt_id, label in label_map.items() if label != "none_or_delay"]
    if outside_ids and price_sensitivity > 0.8 and bucket < 25:
        chosen_id = outside_ids[0]
    elif product_ids:
        chosen_id = product_ids[bucket % len(product_ids)]
    else:
        chosen_id = next(iter(label_map))
    label = label_map.get(chosen_id, "none_or_delay")
    confidence = ["high", "medium", "low"][bucket % 3]
    return {
        "choice": label,
        "chosen_alternative_id": chosen_id,
        "chosen_alternative_name": chosen_id,
        "interview_response": "Deterministic offline mock answer for pipeline and test coverage; not a real model response.",
        "main_drivers": ["mock_fit"],
        "main_barriers": ["mock_tradeoff"],
        "switch_conditions": ["mock_condition"],
        "answer_confidence": confidence,
    }


def run_one_task(
    prompt_row: dict[str, Any],
    *,
    provider: str,
    model: str,
    temperature: float,
    max_output_tokens: int,
    api_key: str,
    base_url: str,
    timeout: float,
    max_retries: int,
    cache_dir: Path | None,
) -> tuple[dict[str, Any], bool]:
    task_id = str(prompt_row.get("task_id") or prompt_row.get("persona_id"))
    cache_file = (cache_dir / f"{task_id}.json") if cache_dir else None
    raw: dict[str, Any] | None = None
    cached = False
    if cache_file and cache_file.exists():
        try:
            loaded = json.loads(cache_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = loaded
                cached = True
        except (json.JSONDecodeError, OSError):
            raw = None
    if raw is None:
        if provider == "mock":
            raw = mock_raw_response(prompt_row)
        else:
            text = call_with_retry(
                lambda: anthropic_message(
                    str(prompt_row.get("prompt", "")),
                    model=model,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    api_key=api_key,
                    base_url=base_url,
                    timeout=timeout,
                ),
                max_retries=max_retries,
                base_delay=1.0,
            )
            raw = extract_json_object(text)
        if cache_file:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(raw, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    response = dict(raw)
    response["persona_id"] = prompt_row.get("persona_id")
    response["population_weight"] = prompt_row.get("population_weight")
    response["task_id"] = task_id
    response["model"] = "mock_deterministic_engine" if provider == "mock" else model
    response["temperature"] = None if provider == "mock" else (temperature if model_accepts_temperature(model) else None)
    response["calibration_level"] = "mock_offline_uncalibrated" if provider == "mock" else "synthetic_llm_respondent_uncalibrated"
    return response, cached


def run_batch(args: argparse.Namespace) -> int:
    prompt_rows = list(iter_jsonl(args.prompt_file))
    if args.limit is not None:
        prompt_rows = prompt_rows[: args.limit]
    if not prompt_rows:
        raise ValueError("no prompt rows found; run export-prompts first")
    provider = args.provider
    api_key = ""
    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise SystemExit("ANTHROPIC_API_KEY is not set; export it or use --provider mock for an offline run")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", ANTHROPIC_ENDPOINT)
    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    prompt_by_persona = {str(row.get("persona_id")): row for row in prompt_rows}

    responses: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    cache_hits = 0

    def task(row: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        return run_one_task(
            row,
            provider=provider,
            model=args.model,
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
            api_key=api_key,
            base_url=base_url,
            timeout=args.timeout,
            max_retries=args.max_retries,
            cache_dir=cache_dir,
        )

    workers = max(1, args.concurrency)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(task, row): row for row in prompt_rows}
        for future in as_completed(future_map):
            row = future_map[future]
            persona_id = str(row.get("persona_id"))
            try:
                response, cached = future.result()
                responses[persona_id] = response
                if cached:
                    cache_hits += 1
            except Exception as exc:  # noqa: BLE001 - record and fall back; never abort the whole batch
                failures.append({"persona_id": persona_id, "error": f"{type(exc).__name__}: {exc}"})
                responses[persona_id] = {
                    "persona_id": persona_id,
                    "population_weight": row.get("population_weight"),
                    "task_id": row.get("task_id"),
                    "choice": "none_or_delay",
                    "answer_confidence": "low",
                    "interview_response": "",
                    "model": args.model,
                    "calibration_level": "synthetic_llm_respondent_uncalibrated",
                }

    output_rows = [
        normalize_response_row(responses[str(row.get("persona_id"))], prompt_by_persona)
        for row in prompt_rows
        if str(row.get("persona_id")) in responses
    ]
    write_jsonl(args.output, output_rows)

    audit = {
        "batch_version": BATCH_VERSION,
        "prompt_version": PROMPT_VERSION,
        "mode": "run_batch",
        "provider": provider,
        "model": "mock_deterministic_engine" if provider == "mock" else args.model,
        "temperature": (args.temperature if (provider == "anthropic" and model_accepts_temperature(args.model)) else None),
        "concurrency": workers,
        "prompt_count": len(prompt_rows),
        "response_count": len(output_rows),
        "failure_count": len(failures),
        "failures": failures[:50],
        "cache_hits": cache_hits,
        "cache_dir": str(cache_dir) if cache_dir else None,
        "coverage_rate": (len(output_rows) / len(prompt_rows)) if prompt_rows else 0.0,
        "output": str(args.output),
        "scientific_boundary": (
            "Mock provider rows are deterministic offline placeholders for pipeline and test coverage, not model output."
            if provider == "mock"
            else "Rows are synthetic LLM respondent answers aggregated by population_weight over discrete choices; uncalibrated, not observed consumer behavior."
        ),
        "warnings": [] if len(output_rows) == len(prompt_rows) else ["response_count_does_not_match_prompt_count"],
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
    export.add_argument("--order-policy", choices=["canonical", "reverse", "rotate"], default="rotate")
    export.add_argument("--prompt-variant", choices=["neutral", "tradeoff"], default="tradeoff")

    normalize = subparsers.add_parser("normalize-responses", help="Normalize external LLM response JSONL to choice_results.jsonl.")
    normalize.add_argument("prompt_file", type=Path)
    normalize.add_argument("response_file", type=Path)
    normalize.add_argument("--output", type=Path, required=True)
    normalize.add_argument("--audit", type=Path)

    batch = subparsers.add_parser("run-batch", help="Call a live LLM (or deterministic mock) over exported prompts and write choice_results.jsonl directly.")
    batch.add_argument("prompt_file", type=Path)
    batch.add_argument("--output", type=Path, required=True)
    batch.add_argument("--audit", type=Path)
    batch.add_argument("--provider", choices=["anthropic", "mock"], default="anthropic")
    batch.add_argument("--model", default=DEFAULT_MODEL)
    batch.add_argument("--temperature", type=float, default=0.7)
    batch.add_argument("--max-output-tokens", type=int, default=600)
    batch.add_argument("--concurrency", type=int, default=4)
    batch.add_argument("--max-retries", type=int, default=5)
    batch.add_argument("--timeout", type=float, default=60.0)
    batch.add_argument("--limit", type=int)
    batch.add_argument("--cache-dir", type=Path, help="Reuse prior responses keyed by task_id; makes runs resumable and avoids re-paying.")
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
    if args.command == "run-batch":
        if args.limit is not None and args.limit <= 0:
            raise ValueError("--limit must be positive when supplied")
        if args.concurrency <= 0:
            raise ValueError("--concurrency must be positive")
        if args.max_output_tokens <= 0:
            raise ValueError("--max-output-tokens must be positive")
        if args.max_retries < 0:
            raise ValueError("--max-retries must be non-negative")
        return run_batch(args)
    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
