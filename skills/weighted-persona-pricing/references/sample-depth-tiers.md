# Sample Depth Tiers

Use tiered depth when the user wants both stable quantitative results and readable human stories.

## Three Tiers

| Tier | Typical size | Purpose | Output |
|---|---:|---|---|
| Shallow panel | 10,000+ | One short interview answer per person, stable totals, weighted shares, confidence intervals, segment lift | `personas_core.jsonl`, `choice_results.jsonl` |
| Medium panel | 1,000 | Longer interview answers, segment-level reasoning, drivers/barriers, representative explanations | `personas_narrative.jsonl` |
| Deep casebook | 100 | Human-readable cases, story, shopping path, sales/strategy empathy | `personas_deep_casebook.jsonl` |

Default mode: 100 isolated LLM deep interviews, 1,000 isolated short LLM interviews, and 10,000 isolated structured shallow interviews using a calibrated respondent engine unless the user explicitly chooses 10,000 LLM micro-calls.

## Division Of Labor

Use 10,000 shallow records to calculate:

```text
discrete product choice
overall share
represented population
bootstrap intervals
price sensitivity
segment lift
effective sample size
```

Use 1,000 medium records to explain:

```text
natural answer
why choose
why reject
channel and media path
message angle
feature tradeoff
trust and risk barriers
```

Use 100 deep records to show:

```text
full background
purchase journey
household decision dynamics
representative quote-style summary
what would change their mind
```

## Sampling From Large To Small

Do not generate 100 deep cases independently from the population. Derive them from the weighted panel:

1. Generate or load the 10,000 shallow weighted records.
2. Run identity-first choice interviews and segment lift.
3. Select medium records by stratified sampling across important segments, including positive, negative, and uncertain segments.
4. Select deep cases from the medium records using diversity constraints.
5. Keep `persona_id` links across all tiers.

## Recommended Allocation

For a product scenario:

```text
10,000 shallow:
  all statistical cells, HTE labels, one final choice, one short reason
  low temperature or deterministic respondent engine
  stable seed by scenario_id + persona_id + task_id

1,000 medium:
  oversample high-lift, low-lift, and switchable segments; include natural answers
  preferably independent short LLM calls with strict JSON schema

100 deep:
  40 likely focal buyers
  30 competitor buyers
  20 none/delay
  10 uncertain or switchable
  one independent LLM conversation per persona
```

Reweight outputs back to population weights after oversampling explanation tiers.

## Repeated Validation

Use repeated runs at the shallow tier:

```text
base seed
soft-trait seed variant
choice-noise seed variant
price sensitivity grid
prompt variant sample
calibration-level comparison
test-retest sample
consistency judge sample
```

Use the medium and deep tiers for explanation, not for the final denominator.

## Display Rule

In the final report:

- Say the 10,000 panel is the statistical base.
- Say the 1,000 panel explains segment reasons.
- Say the 100 casebook illustrates representative stories.
- Never imply the 100 deep stories alone determine market share.
- Never show the 10,000 or 1,000 layer as score-only rows; each person needs a final choice.
- Say whether the 10,000 layer used LLM micro-calls or a calibrated respondent engine.
- Report test-retest, prompt-sensitivity, and consistency-judge status when LLM interviews are used.
