# Interview Quality Controls

Use this reference when the task needs isolated digital respondents, LLM interview batches, test-retest, prompt sensitivity, response schema, answer confidence, or consistency judging.

## Recommended Architecture

Default to a three-tier mixed interview system:

| Tier | Default method | Reason |
|---|---|---|
| 100 deep | 100 isolated LLM conversations | Rich stories, motivations, objections, switch conditions |
| 1,000 medium | 1,000 isolated short LLM interviews | Reason distribution, segment language, respondent-engine calibration |
| 10,000 shallow | Isolated structured micro-interviews, usually calibrated respondent engine | Stable shares, confidence intervals, segment lift |

Use 10,000 independent LLM calls only when the user explicitly accepts cost, latency, failure handling, and storage needs. Do not use one long conversation to simulate many respondents.

## Isolation Rules

Each respondent may see only:

```text
fixed identity
product scenario
allowed output schema
current task instructions
```

Each respondent must not see:

```text
previous or next respondent answers
aggregate shares or quotas
desired market split
segment-level results
casebook examples from other personas
```

Store isolation metadata when LLM calls are used:

```json
{
  "isolation": {
    "context_scope": "individual",
    "conversation_id": "scenario_id:persona_id",
    "saw_other_answers": false,
    "saw_aggregate_results": false,
    "batch_size": 1
  }
}
```

Small batched calls are allowed only when each item is hard-delimited and the prompt explicitly forbids cross-item influence. Mark the run as `context_scope: "hard_delimited_batch"` and audit the risk.

## Generation Controls

Use deterministic controls for statistical layers:

| Layer | Temperature | Seed |
|---|---:|---|
| 10,000 shallow | 0.0-0.3 | `scenario_id + persona_id + task_id` |
| 1,000 medium | 0.1-0.4 | same stable seed rule |
| 100 deep | 0.4-0.7 | stable seed if reproducibility matters |

Store:

```json
{
  "generation_controls": {
    "model": "model-name",
    "temperature": 0.2,
    "seed": "hungary-watch:HU-WATCH-00001:base",
    "prompt_variant": "base",
    "schema_version": "choice_interview_v1"
  }
}
```

## Response Schema

Require strict JSON:

```json
{
  "choice": "focal_product|competitor|none_or_delay",
  "interview_response": "first-person answer",
  "main_drivers": ["enumerated_label"],
  "main_barriers": ["enumerated_label"],
  "rejected_alternatives": {},
  "switch_conditions": ["condition"],
  "answer_confidence": "low|medium|high"
}
```

Avoid fake precision. Use `low|medium|high`, not `0.873`.

## Answer Confidence

Use:

| Confidence | Meaning |
|---|---|
| high | Choice strongly follows identity, budget, need, and product fit |
| medium | Choice is plausible but has meaningful tradeoffs |
| low | Persona is switchable, low-urgency, budget-constrained, or internally conflicted |

Low confidence is not bad. It identifies switchable respondents and sensitivity targets.

## Test-Retest

Sample 5%-10% of respondents and ask the same task again with the same identity and no aggregate context.

Report:

```text
choice_stability_rate
driver_stability_rate
barrier_stability_rate
low_confidence_retest_flip_rate
```

If stability is low, reduce temperature, tighten schema, improve product scenario clarity, or mark the run as high-uncertainty.

## Prompt Sensitivity

Run 2-3 equivalent prompt variants on a stratified sample. Keep product facts identical and vary only wording.

Report:

```text
overall_share_delta_by_prompt
segment_order_stability
reason_label_jaccard_similarity
segments_that_flip_direction
```

If prompt variants move the focal share by more than the bootstrap interval, the result is prompt-sensitive and should not be presented as robust.

## Consistency Judge

After each LLM interview or on a sampled audit subset, run a separate judge. The judge is not the respondent.

Judge checks:

```text
identity facts respected
budget and price reasoning consistent
choice supported by drivers
barriers do not contradict choice
no aggregate or other-respondent context leakage
no protected-class pricing recommendation
```

Store:

```json
{
  "quality_controls": {
    "consistency_judge": "pass|review|fail",
    "judge_reasons": [],
    "test_retest_status": "not_sampled|stable|flipped",
    "prompt_sensitivity_status": "not_sampled|stable|sensitive"
  }
}
```

Retry or quarantine `fail` rows. Keep `review` rows but report their share.

## Validator

Run:

```bash
python scripts/validate_choice_interviews.py choice_results.jsonl --audit choice_interview_validation.json
```

For LLM interview batches, use:

```bash
python scripts/validate_choice_interviews.py choice_results.jsonl --require-controls --strict
```

The strict mode fails rows with unsafe isolation, missing controls, invalid confidence labels, contamination phrases, or probability-only outputs.
