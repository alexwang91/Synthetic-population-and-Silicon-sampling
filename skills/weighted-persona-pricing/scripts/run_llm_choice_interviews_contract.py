#!/usr/bin/env python3
"""Run LLM choice interviews with prompt/model-bound cache contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

CACHE_CONTRACT_VERSION = "llm_choice_cache_v0_2"
CACHE_CONTRACT_FIELDS = ["cache_contract_version", "prompt_hash", "prompt_version", "prompt_variant", "order_policy", "provider", "model", "temperature"]
LEGACY_SCRIPT = Path(__file__).with_name("run_llm_choice_interviews.py")
NO_SAMPLING_MODEL_MARKERS = ("opus-4-8", "opus-4-7", "fable-5")


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                value = json.loads(stripped)
                if isinstance(value, dict):
                    yield value


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def model_accepts_temperature(model: str) -> bool:
    lowered = model.lower()
    return not any(marker in lowered for marker in NO_SAMPLING_MODEL_MARKERS)


def effective_temperature(provider: str, model: str, temperature: float) -> float | None:
    if provider == "anthropic" and model_accepts_temperature(model):
        return temperature
    return None


def prompt_hash(row: dict[str, Any]) -> str:
    existing = row.get("prompt_hash")
    if isinstance(existing, str) and len(existing) == 64:
        return existing
    return sha256_text(str(row.get("prompt", "")))


def cache_contract(row: dict[str, Any], *, provider: str, model: str, temperature: float) -> dict[str, Any]:
    return {
        "cache_contract_version": CACHE_CONTRACT_VERSION,
        "prompt_hash": prompt_hash(row),
        "prompt_version": row.get("prompt_version"),
        "prompt_variant": row.get("prompt_variant"),
        "order_policy": row.get("order_policy"),
        "provider": provider,
        "model": model,
        "temperature": effective_temperature(provider, model, temperature),
    }


def cache_key(row: dict[str, Any], *, provider: str, model: str, temperature: float) -> str:
    return sha256_text(canonical_json(cache_contract(row, provider=provider, model=model, temperature=temperature)))[:32]


def batch_namespace(rows: list[dict[str, Any]], *, provider: str, model: str, temperature: float) -> str:
    payload = {
        "cache_contract_version": CACHE_CONTRACT_VERSION,
        "provider": provider,
        "model": model,
        "temperature": effective_temperature(provider, model, temperature),
        "row_contracts": [cache_contract(row, provider=provider, model=model, temperature=temperature) for row in rows],
    }
    return sha256_text(canonical_json(payload))[:32]


def run_legacy(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def enrich_prompts(path: Path) -> list[dict[str, Any]]:
    rows = list(iter_jsonl(path))
    for row in rows:
        row["prompt_hash"] = prompt_hash(row)
    write_jsonl(path, rows)
    return rows


def enrich_choice_results(path: Path, prompt_rows: list[dict[str, Any]], *, provider: str, model: str, temperature: float) -> int:
    prompt_by_persona = {str(row.get("persona_id")): row for row in prompt_rows}
    rows = list(iter_jsonl(path))
    for row in rows:
        prompt_row = prompt_by_persona.get(str(row.get("persona_id")), {})
        generation = row.setdefault("generation_controls", {})
        if isinstance(generation, dict):
            generation["prompt_hash"] = prompt_hash(prompt_row)
            generation["cache_key"] = cache_key(prompt_row, provider=provider, model=model, temperature=temperature)
    write_jsonl(path, rows)
    return len(rows)


def enrich_audit(path: Path, prompt_rows: list[dict[str, Any]], *, provider: str, model: str, temperature: float, namespace: str | None, choice_row_count: int | None = None) -> None:
    audit = read_json(path)
    cache_keys = {cache_key(row, provider=provider, model=model, temperature=temperature) for row in prompt_rows}
    audit["prompt_hash_count"] = len({prompt_hash(row) for row in prompt_rows})
    audit["cache_key_count"] = len(cache_keys)
    audit["cache_contract"] = {"version": CACHE_CONTRACT_VERSION, "fields": CACHE_CONTRACT_FIELDS, "key_length": 32}
    if namespace is not None:
        audit["cache_namespace_key"] = namespace
    if choice_row_count is not None:
        audit["choice_row_count"] = choice_row_count
    write_json(path, audit)


def export_prompts(args: argparse.Namespace) -> int:
    command = [sys.executable, str(LEGACY_SCRIPT), "export-prompts", str(args.personas_enriched), str(args.normalized_choice_scenario), "--output-prompts", str(args.output_prompts), "--order-policy", args.order_policy, "--prompt-variant", args.prompt_variant]
    if args.audit:
        command.extend(["--audit", str(args.audit)])
    if args.limit is not None:
        command.extend(["--limit", str(args.limit)])
    if args.include_story:
        command.append("--include-story")
        command.extend(["--max-story-chars", str(args.max_story_chars)])
    run_legacy(command)
    rows = enrich_prompts(args.output_prompts)
    if args.audit:
        audit = read_json(args.audit)
        audit["prompt_hash_count"] = len({row.get("prompt_hash") for row in rows})
        audit.setdefault("risk_controls", []).append("prompt_hash_recorded_for_cache_and_replay_audit")
        write_json(args.audit, audit)
    return 0


def normalize_responses(args: argparse.Namespace) -> int:
    command = [sys.executable, str(LEGACY_SCRIPT), "normalize-responses", str(args.prompt_file), str(args.response_file), "--output", str(args.output)]
    audit_path = args.audit or (Path(tempfile.mkdtemp()) / "normalize_audit.json")
    command.extend(["--audit", str(audit_path)])
    run_legacy(command)
    prompt_rows = enrich_prompts(args.prompt_file)
    count = enrich_choice_results(args.output, prompt_rows, provider="external", model="external", temperature=0.0)
    enrich_audit(audit_path, prompt_rows, provider="external", model="external", temperature=0.0, namespace=None, choice_row_count=count)
    if args.audit is None:
        print(json.dumps(read_json(audit_path), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def run_batch(args: argparse.Namespace) -> int:
    prompt_rows = enrich_prompts(args.prompt_file)
    if args.limit is not None:
        prompt_rows = prompt_rows[: args.limit]
    namespace = batch_namespace(prompt_rows, provider=args.provider, model=args.model, temperature=args.temperature)
    cache_dir = args.cache_dir / namespace if args.cache_dir else None
    command = [sys.executable, str(LEGACY_SCRIPT), "run-batch", str(args.prompt_file), "--output", str(args.output), "--provider", args.provider, "--model", args.model, "--temperature", str(args.temperature), "--max-output-tokens", str(args.max_output_tokens), "--concurrency", str(args.concurrency), "--max-retries", str(args.max_retries), "--timeout", str(args.timeout)]
    audit_path = args.audit or (Path(tempfile.mkdtemp()) / "batch_audit.json")
    command.extend(["--audit", str(audit_path)])
    if args.limit is not None:
        command.extend(["--limit", str(args.limit)])
    if cache_dir:
        command.extend(["--cache-dir", str(cache_dir)])
    run_legacy(command)
    count = enrich_choice_results(args.output, prompt_rows, provider=args.provider, model=args.model, temperature=args.temperature)
    enrich_audit(audit_path, prompt_rows, provider=args.provider, model=args.model, temperature=args.temperature, namespace=namespace, choice_row_count=count)
    if args.audit is None:
        print(json.dumps(read_json(audit_path), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    export = subparsers.add_parser("export-prompts")
    export.add_argument("personas_enriched", type=Path)
    export.add_argument("normalized_choice_scenario", type=Path)
    export.add_argument("--output-prompts", type=Path, required=True)
    export.add_argument("--audit", type=Path)
    export.add_argument("--limit", type=int)
    export.add_argument("--include-story", action="store_true")
    export.add_argument("--max-story-chars", type=int, default=900)
    export.add_argument("--order-policy", choices=["canonical", "reverse", "rotate"], default="rotate")
    export.add_argument("--prompt-variant", choices=["neutral", "tradeoff"], default="tradeoff")

    normalize = subparsers.add_parser("normalize-responses")
    normalize.add_argument("prompt_file", type=Path)
    normalize.add_argument("response_file", type=Path)
    normalize.add_argument("--output", type=Path, required=True)
    normalize.add_argument("--audit", type=Path)

    batch = subparsers.add_parser("run-batch")
    batch.add_argument("prompt_file", type=Path)
    batch.add_argument("--output", type=Path, required=True)
    batch.add_argument("--audit", type=Path)
    batch.add_argument("--provider", choices=["anthropic", "mock"], default="anthropic")
    batch.add_argument("--model", default="claude-haiku-4-5")
    batch.add_argument("--temperature", type=float, default=0.7)
    batch.add_argument("--max-output-tokens", type=int, default=600)
    batch.add_argument("--concurrency", type=int, default=4)
    batch.add_argument("--max-retries", type=int, default=5)
    batch.add_argument("--timeout", type=float, default=60.0)
    batch.add_argument("--limit", type=int)
    batch.add_argument("--cache-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "export-prompts":
        return export_prompts(args)
    if args.command == "normalize-responses":
        return normalize_responses(args)
    if args.command == "run-batch":
        return run_batch(args)
    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
