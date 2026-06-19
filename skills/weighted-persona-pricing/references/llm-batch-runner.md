# LLM Choice Batch Runner

`scripts/run_llm_choice_interviews.py` is the synthetic-respondent interview entrypoint. It has three subcommands that together close the loop from exported prompts to a validated `choice_results.jsonl`:

| Subcommand | Role |
|---|---|
| `export-prompts` | Build one isolated, counterbalanced choice prompt per representative persona. |
| `run-batch` | **Call a live LLM (or a deterministic mock) over those prompts and write `choice_results.jsonl` directly.** |
| `normalize-responses` | Ingest an externally generated response file (batch API, manual run) into the same schema. |

`run-batch` is what makes the intended `llm_short_all` mode a real, runnable silicon-sampling pass instead of a prompt export that waits for an external party.

## Design boundaries

- Standard library only. The Anthropic client is a thin `urllib.request` POST to `/v1/messages`; there is no SDK dependency.
- Every respondent is an isolated call. Prompts never expose aggregate shares, quotas, target proportions, or other respondents' answers.
- Aggregation is unchanged: market share is still `sum(weight * 1(choice == option)) / sum(weight)` over discrete choices. The runner only produces respondent-level answers.
- Output flows through the same `normalize_response_row` contract as `normalize-responses`, so `validate_choice_interviews.py` (including `--strict`) treats batch rows and external rows identically.

## Providers

```bash
# Live LLM (requires ANTHROPIC_API_KEY in the environment)
python scripts/run_llm_choice_interviews.py run-batch llm_choice_prompts.jsonl \
  --output choice_results.jsonl --audit llm_choice_interview_audit.json \
  --provider anthropic --model claude-haiku-4-5 --temperature 0.7 \
  --concurrency 4 --cache-dir runs/<run>/llm_cache

# Deterministic offline mock (no API key; used by tests and CI)
python scripts/run_llm_choice_interviews.py run-batch llm_choice_prompts.jsonl \
  --output choice_results.jsonl --provider mock
```

- `anthropic`: real model calls. Concurrency via a thread pool; retry with exponential backoff on 408/409/429/5xx and connection errors.
- `mock`: a deterministic, schema-valid stand-in derived from each persona id and the scenario's own alternatives. It is **not** a model and is never presented as one (`model` is recorded as `mock_deterministic_engine`, `calibration_level` as `mock_offline_uncalibrated`). It exists so the whole pipeline and test suite run offline.

## Model and temperature

Default model is `claude-haiku-4-5`: cost-appropriate for large panels, and it accepts `temperature`, so per-respondent temperature variance supplies the stochasticity in *random* silicon sampling.

Opus 4.7 / Opus 4.8 / Fable 5 reject `temperature`/`top_p`/`top_k` (HTTP 400). The runner detects these by model-id substring and omits `temperature` automatically, so `--model claude-opus-4-8` works without a 400. Pick a sampling-capable model when answer diversity matters.

## Resumability and cost control

`--cache-dir` stores each respondent's raw response keyed by `task_id` (which encodes persona + scenario + prompt version + order policy + variant). Re-running with the same cache reuses prior answers, so an interrupted 10,000-respondent batch resumes without re-paying for completed rows. The pipeline sets the cache dir to `runs/<run_id>/llm_cache` automatically.

For very large panels also consider the provider's Batch API (50% cost) via the `normalize-responses` path, or restrict the live LLM tier to 100/1,000 and keep 10,000 on the rule-based baseline or mock.

## Failure handling

Per-respondent failures (after retries) do not abort the batch: the row falls back to a low-confidence `none_or_delay` answer and is counted in the audit's `failure_count`/`failures`. Inspect `coverage_rate` and `failure_count` in `llm_choice_interview_audit.json` before treating a run as deliverable.

## Pipeline integration

In `run_scenario_pipeline.py`, set `interview_engine: "llm_short_all"` and:

```json
{
  "llm_call_mode": "run_batch",
  "llm_provider": "anthropic",
  "llm_model": "claude-haiku-4-5",
  "llm_temperature": 0.7,
  "llm_concurrency": 4
}
```

`llm_call_mode` defaults to `await_external` (export prompts, then stop at `awaiting_llm_responses` or normalize a supplied `llm_response_file`) to preserve the prior behavior. Set it to `run_batch` to call the model in-pipeline. The offline example `examples/serbia_smartwatch_llm_mock_pipeline_config.json` uses `run_batch` + `mock` to exercise the full path with no API key.
