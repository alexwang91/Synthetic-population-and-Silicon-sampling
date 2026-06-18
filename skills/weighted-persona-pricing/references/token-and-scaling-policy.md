# Token and Scaling Policy

This project keeps row-level synthetic population generation separate from LLM-heavy explanation layers.

## Core rule

Do not place full `personas_enriched.jsonl`, `choice_results.jsonl`, or other row-level artifacts into an LLM prompt or Markdown report.

Use JSON/JSONL artifacts as storage and compute surfaces. Use Markdown, HTML dashboards, or LLM summaries only on aggregated outputs.

## Recommended tiers

| Tier | Typical size | Method | LLM use |
|---|---:|---|---|
| Shallow statistics | 10,000+ | deterministic sampling, soft traits, rule-based choice, weighted aggregation | none |
| Medium explanation | ~1,000 | selected rows, reason-code summaries, stratified examples | optional, only if needed |
| Deep cases | ~100 | high-value or uncertain personas, qualitative explanation | allowed with isolation controls |

## Pipeline cost boundary

The deterministic pipeline stages do not call an LLM per persona:

```text
country pack
→ seed cells
→ IPF/raking
→ persona skeletons
→ soft traits
→ coherence validation
→ product normalization
→ rule-based choice
→ bootstrap
→ concise report / dashboard data
```

LLM costs appear only if a later LLM interview or narrative layer is added.

## Report and dashboard boundary

`market_report.md` is a compact text surface. It is not meant to display the full study.

A richer HTML dashboard should read compact artifacts such as:

- `market_report.json`
- `choice_model_audit.json`
- `choice_interview_validation.json`
- `bootstrap_intervals.json`
- `pipeline_artifact_validation.json`
- aggregated reason-code tables
- sampled examples, not all rows

## Future LLM interview policy

If LLM interviews are added:

1. Never show a respondent other respondents' answers.
2. Never show aggregate shares, quotas, or target proportions.
3. Run LLM interviews on bounded samples, not all 10,000 rows by default.
4. Store each row-level response in JSONL.
5. Aggregate with deterministic scripts.
6. Summarize aggregated artifacts, not full row text.
7. Record prompt version, model, seed/temperature, and isolation controls.

## Failure mode to avoid

Do not run this pattern:

```text
10,000 personas
→ 10,000 long LLM interviews
→ paste all answers into one Markdown or LLM summary
```

That pattern is expensive, hard to audit, and likely to compress variance during summarization.

Use this pattern instead:

```text
10,000 deterministic rows
→ weighted aggregation
→ uncertainty intervals
→ top drivers/barriers
→ dashboard JSON
→ optional sampled LLM deep dives
```
