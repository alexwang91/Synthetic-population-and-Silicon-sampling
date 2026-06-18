---
name: weighted-persona-pricing
description: Use when the user needs to generate, evaluate, or design census-weighted synthetic consumers, digital personas, silicon samples, synthetic respondents, country data packs, weighted persona panels, isolated respondent interviews, product A/B choice, pricing, WTP, purchase intent, segment lift, HTE/CATE/uplift labels, calibration, audit reports, or safeguards around LLM-based market research.
---

# Weighted Persona Pricing

## Overview

Build census-weighted synthetic consumer panels for pricing and competitive choice interviews. Use statistics to decide who exists, conditional models to decide what they are plausibly like, digital respondents to answer product scenarios in natural language, and deterministic aggregation to count what they chose.

This skill is for designing or executing a pipeline, not for asking an LLM to freely invent 1,000 to 10,000 personas and not for replacing each person with a score table.

Default to a three-tier mixed interview system: 100 isolated LLM deep interviews, 1,000 isolated short LLM medium interviews, and 10,000 isolated structured shallow interviews using either LLM micro-calls or a calibrated respondent engine. Use 10,000 independent LLM calls only when the user explicitly accepts cost, latency, retry, and audit overhead.

## First Decision

Classify the user's request before acting:

| User needs | Use this mode | Read |
|---|---|---|
| Natural-language country/category/product/competitor question | Product scenario mode | `references/product-scenario-workflow.md` |
| A country data package or source plan | Country pack mode | `references/data-packs.md` |
| A weighted synthetic panel | Panel generation mode | `references/architecture.md`, `references/persona-schema.md` |
| Rich persona stories or casebooks | Narrative mode | `references/persona-schema.md`, `references/prompts.md` |
| Pricing, WTP, product A/B, conjoint, DCE | Interview-first choice mode | `references/choice-simulation.md` |
| Isolation, context pollution, LLM respondent settings, seed/temperature, test-retest, prompt sensitivity, consistency judge | Interview QA mode | `references/interview-quality-controls.md` |
| Segment lift, HTE, CATE, uplift, targeting labels | HTE segmentation mode | `references/hte-segmentation.md` |
| Credibility, calibration, validation, limitations | Audit mode | `references/validation.md` |
| Unsure which statistical method applies | Method routing mode | `references/methodology-map.md` |

If the user asks for an end-to-end product question such as "Romania phones, my product vs competitor, who chooses it and why", use product scenario mode first, then country pack, panel generation, choice simulation, HTE segmentation, narrative, audit, and report.

## Core Rules

- Keep statistical weights controlled by data and deterministic code. Do not let life stories or LLM completions alter population weights.
- Make the final person-level result a discrete interview answer: `choice`, `interview_response`, `main_drivers`, `main_barriers`, and `switch_conditions`.
- Do not report 10,000 or 1,000 person rows as score comparisons. Scores, utilities, propensities, or probabilities are optional diagnostics only, not the respondent's answer.
- When using a model to help choose, convert it into a sampled or judged one-person answer before aggregation. The denominator must count choices, not averaged score sheets.
- Do not simulate many respondents inside one shared conversation. Each respondent must have isolated input/output and must not see prior answers, aggregate shares, quotas, or target proportions.
- Store generation controls for LLM respondents: model, temperature, stable seed, prompt variant, and schema version.
- Use `answer_confidence` as `low|medium|high`, not fake-precise numeric confidence.
- Run or design test-retest, prompt sensitivity, and consistency-judge checks whenever LLM interview outputs materially affect conclusions.
- Treat hard demographics, soft inferred traits, and narrative story fields as different evidence levels.
- Prefer JSONL outputs for panels. Keep long narrative text separate from the core statistical panel.
- Never claim synthetic respondents are real consumers or a replacement for real surveys, sales data, or A/B tests.
- Show calibration level and uncertainty whenever reporting market shares, price elasticity, WTP, or segment lift.
- Separate descriptive heterogeneity from causal heterogeneity. Do not call a segment difference HTE/CATE unless treatment assignment, counterfactual design, or calibrated causal assumptions support it.
- For large panels, generate many structured records and only a smaller narrative subset.
- Use the depth tiers deliberately: 10,000 shallow records for stable totals and intervals, 1,000 medium records for segment reasoning, and 100 deep cases for readable human-facing stories.

## Recommended Pipeline

1. Define the market scope: country, population, category, sample size, language, population year, and calibration level.
2. Build or inspect the country statistical data pack with source metadata.
3. Create statistical cells from hard variables such as region, age, sex, education, household size, income, employment, and urban/rural status.
4. Use IPF/raking or another documented method to estimate joint distributions from marginal constraints.
5. Sample weighted skeletons from the joint distribution.
6. Expand soft traits only through documented conditional assumptions.
7. Generate narrative profiles for a sampled subset or archetypes.
8. Validate coherence, duplication, missing fields, marginal fit, and imputation burden.
9. Run product choice interviews with structured alternatives and a none option. Each persona must answer in natural language and then be parsed into one final choice.
10. Produce descriptive segment lift, preference heterogeneity, or causal HTE labels according to the evidence available.
11. Produce an audit report that separates facts, imputations, model assumptions, narrative inventions, and limitations.

## Expected Inputs

Ask for or infer these fields:

```json
{
  "country": "Serbia",
  "target_population": "adult_purchase_decision_makers",
  "sample_size": 1000,
  "population_year": 2022,
  "category": "smartphone",
  "focal_product": {},
  "competitors": [],
  "persona_depth": "shallow|medium|deep|tiered",
  "calibration_level": "level_0|level_1|level_2|level_3",
  "hte_mode": "descriptive|preference|causal",
  "respondent_mode": "three_tier_mixed|llm_microcall|respondent_engine",
  "isolation_mode": "individual|hard_delimited_batch",
  "output_mode": "data|readable_report|both"
}
```

If a country data pack is missing, stay in design or data-discovery mode. Do not pretend the panel is census-calibrated.

## Expected Outputs

Use these artifacts when building a real panel:

```text
personas_core.jsonl
personas_narrative.jsonl
personas_deep_casebook.jsonl
choice_tasks.jsonl
choice_results.jsonl
market_choice_summary.json
segment_lift_table.json
sensitivity_report.json
readable_report.md
audit_report.json
choice_interview_validation.json
```

For planning tasks, output a system design, data requirements, schemas, calibration plan, and validation plan instead of fake records.

`choice_results.jsonl` must be interview-first. At minimum, each row needs:

```json
{
  "persona_id": "HU-WATCH-00001",
  "population_weight": 10.0,
  "choice": "focal_product",
  "interview_response": "I would choose Huawei because the battery matters more to me than Google Pay.",
  "main_drivers": ["battery_life", "ios_compatibility"],
  "main_barriers": ["higher_price"],
  "switch_conditions": ["Samsung improves iOS compatibility or Huawei rises above my budget"],
  "answer_confidence": "medium",
  "isolation": {
    "context_scope": "individual",
    "saw_other_answers": false,
    "saw_aggregate_results": false
  },
  "generation_controls": {
    "temperature": 0.2,
    "seed": "scenario:HU-WATCH-00001",
    "prompt_variant": "base"
  },
  "quality_controls": {
    "consistency_judge": "pass"
  }
}
```

## Resource Map

- `references/architecture.md`: module layout, MVP plan, full product decomposition.
- `references/product-scenario-workflow.md`: natural-language product/competitor input, expected outputs, and readable report shape.
- `references/interview-quality-controls.md`: isolated respondent design, three-tier recommendation, seed/temperature, response schema, confidence, test-retest, prompt sensitivity, consistency judge.
- `references/sample-depth-tiers.md`: 100 deep, 1,000 medium, and 10,000 shallow panel strategy.
- `references/methodology-map.md`: when to use IPF/raking, MRP, multilevel calibration, CBC, SSR, causal forests, meta-learners, or uplift modeling.
- `references/data-packs.md`: country pack schema, source metadata, calibration levels.
- `references/persona-schema.md`: three evidence layers, 80+ field taxonomy, output files.
- `references/choice-simulation.md`: interview-first product choice, optional diagnostics, and weighted aggregation.
- `references/hte-segmentation.md`: expanded HTE and segment-label taxonomy, evidence rules, and output schema.
- `references/prompts.md`: persona expander, story, judge, choice reasoning, audit prompts.
- `references/validation.md`: metrics, compliance boundaries, audit report expectations.
- `scripts/validate_persona_panel.py`: basic JSONL panel validator.
- `scripts/validate_choice_interviews.py`: validates interview choice schema, isolation controls, confidence labels, and contamination red flags.
- `scripts/bootstrap_choice_intervals.py`: bootstrap intervals for weighted choice shares and segment lift.

## Validation Command

When the user provides or you generate `personas_core.jsonl`, run:

```bash
python scripts/validate_persona_panel.py personas_core.jsonl --audit audit_report.json
```

Use the script output as a basic integrity check, then apply the deeper validation guidance in `references/validation.md`.

When the user provides or you generate `choice_results.jsonl`, run:

```bash
python scripts/validate_choice_interviews.py choice_results.jsonl --audit choice_interview_validation.json
python scripts/bootstrap_choice_intervals.py choice_results.jsonl --segment-field hte_labels.price_value --segment-field hte_labels.risk_trust
```

Use it to support confidence intervals and segment lift stability in the readable report. Prefer discrete `choice` records; probability records are legacy-compatible only.

For LLM interview batches, validate stricter controls:

```bash
python scripts/validate_choice_interviews.py choice_results.jsonl --require-controls --strict
```
