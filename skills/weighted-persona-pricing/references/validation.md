# Validation

## Minimum Metrics

Statistical fit:

```text
region_fit_error
age_sex_fit_error
education_fit_error
household_fit_error
income_fit_error
urban_rural_fit_error
```

Persona quality:

```text
coherence_score
duplicate_score
long_tail_coverage
attribute_missing_rate
contradiction_rate
imputation_score
```

Choice simulation:

```text
choice_record_contract_pass_rate
interview_response_presence_rate
discrete_choice_presence_rate
isolation_control_presence_rate
generation_control_presence_rate
quality_control_presence_rate
context_contamination_rate
consistency_judge_pass_rate
test_retest_choice_stability_rate
prompt_sensitivity_share_delta
choice_share_stability
price_elasticity_reasonableness
segment_lift_stability
none_option_rate
WTP_distribution_shape
preference_segment_stability
effective_sample_size_by_segment
```

External calibration:

```text
match_to_real_survey
match_to_sales_data
match_to_click_data
test_retest_reliability
prompt_sensitivity
model_version_sensitivity
variance_ratio_vs_human
```

## Audit Report

Include:

```json
{
  "country": "Serbia",
  "sample_size": 10000,
  "coverage": "adult purchase decision makers",
  "calibration_level": "level_1",
  "data_sources": [],
  "marginal_fit": {},
  "mean_absolute_percentage_error": 0.012,
  "duplicate_rate": 0.004,
  "coherence_pass_rate": 0.972,
  "prompt_sensitivity": {},
  "model_version_sensitivity": {},
  "test_retest": {},
  "choice_interview_validation": {},
  "isolation_controls": {},
  "consistency_judge": {},
  "segment_stability": {},
  "high_imputation_fields": [],
  "limitations": []
}
```

## Uncertainty And Sensitivity

Run these checks whenever the output contains market share, WTP, elasticity, segment lift, HTE, or uplift:

1. Bootstrap over personas with weights.
2. Repeat generation with at least two random seeds for soft traits.
3. Repeat LLM reasoning on a sample with prompt variants.
4. Compare current model version against a saved benchmark when available.
5. Report variance ratio against human benchmark data when available.
6. Suppress or collapse segments with weak effective sample size.
7. Validate choice interview records with `validate_choice_interviews.py`.
8. For LLM respondents, run a consistency judge on all deep/medium records and at least a stratified sample of shallow records.

LLM synthetic survey work often matches means better than variance. Treat suspiciously narrow intervals, uniform confidence, or unstable prompt results as a failure mode.

## Product Scenario Sensitivity

For country-category-product scenarios, include:

```text
base case
focal price -10%, -5%, +5%, +10%
competitor price -10%, +10% when relevant
brand trust penalty/boost
warranty value penalty/boost
feature importance low/base/high
calibration level comparison
```

Store this as `sensitivity_report.json` and summarize it in the readable report. Report the conclusion as robust only when the directional finding survives the relevant sensitivity cases.

## Interview Contract Validation

Before using `choice_results.jsonl` for market shares, run:

```bash
python scripts/validate_choice_interviews.py choice_results.jsonl --audit choice_interview_validation.json
```

For LLM interview batches:

```bash
python scripts/validate_choice_interviews.py choice_results.jsonl --require-controls --strict
```

Minimum pass criteria:

```text
no probability-only rows
no invalid choice values
no invalid answer_confidence labels
no contamination from aggregate shares or other respondents
no failed consistency judge rows in final denominator
```

If strict validation fails, quarantine bad rows, retry isolated interviews, or report the failure and do not present the affected share as robust.

## Readable Report Validation

Before producing `readable_report.md`, check:

- Every market share has an interval.
- Every market share is aggregated from discrete `choice` answers unless the report clearly marks a legacy probability diagnostic.
- `choice_results.jsonl` rows include natural `interview_response` text and structured drivers/barriers.
- LLM interview rows include isolation, generation controls, and quality controls, or the report states why those controls were not available.
- Every top segment has sample count, weighted population share, and lift.
- Every reason is linked to a segment label, product attribute, or choice driver.
- The report has both choose and reject reasons.
- Deep stories are explicitly illustrative and linked to the quantitative segment they represent.

## Required Limitations

State these when reporting results:

1. Synthetic respondents are not real consumers.
2. Narrative details are explanatory, not statistical facts.
3. LLM-generated preference signals can understate variance.
4. The output is for hypothesis screening before real research or A/B testing.
5. Sensitive attributes must not be used for discriminatory pricing recommendations.

## Red Flags

Stop and revise if:

- The panel has no source metadata.
- Population weights are missing or invented by text generation.
- A story contradicts hard demographic fields.
- Every persona chooses the same product at suspiciously high confidence.
- Choice rows contain only `choice_probability` or utility scores and no final `choice`.
- Respondent text mentions aggregate share, quota, target proportion, previous respondents, or other respondents.
- Many respondents are generated in one rolling conversation without hard isolation.
- LLM interview outputs omit seed/temperature/prompt variant metadata.
- Answer confidence uses fake precision or uniform high confidence.
- Medium or deep persona outputs lack natural interview answers.
- No-purchase is missing from a realistic pricing task.
- The report gives point estimates without calibration level or uncertainty.
- The recommendation says to raise prices for a protected or sensitive group.
- HTE/CATE wording is used without causal evidence.
- Segment lift is reported for sparse or unstable labels.
