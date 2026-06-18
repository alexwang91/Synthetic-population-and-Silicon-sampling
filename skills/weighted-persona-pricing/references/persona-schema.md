# Persona Schema

## Evidence Layers

Keep these layers separate:

| Layer | Examples | Representativeness |
|---|---|---|
| Hard demographics | age, sex, region, education, income, household, employment | Can be census-calibrated |
| Soft inferred traits | media habits, shopping habits, price sensitivity, risk aversion | Plausible only with source and assumptions |
| Narrative story | childhood, family atmosphere, hobbies, life story | Explanatory only, not statistical fact |

## Core Record

```json
{
  "persona_id": "RS-000001",
  "country": "Serbia",
  "population_weight": 638.4,
  "statistical_cell": "Belgrade | female | 35-44 | tertiary | urban | employed | household_3",
  "hard": {},
  "soft": {},
  "hte_labels": {},
  "choice_state": {
    "last_choice": "focal_product",
    "last_interview_id": "TASK-001"
  },
  "calibration_trace": {},
  "uncertainty_score": 0.18
}
```

## Field Groups

Hard statistical fields:

```text
age, age_band, sex, region, municipality_type, birthplace_region,
migration_status, education_level, employment_status, occupation_group,
industry, household_size, marital_status, children_count, elderly_dependents,
housing_tenure, income_decile, monthly_disposable_income_band,
computer_literacy, internet_frequency, urban_access_index
```

Household and life structure:

```text
family_role, household_budget_control, care_responsibilities,
commute_pattern, free_time_hours_weekly, home_cooking_frequency,
holiday_pattern, savings_orientation
```

Media and information channels:

```text
tv_usage, facebook_usage, instagram_usage, tiktok_usage, youtube_usage,
news_portal_usage, forum_usage, influencer_trust, expert_review_trust,
word_of_mouth_trust, offline_store_reliance
```

Consumer psychology:

```text
price_sensitivity, brand_loyalty, risk_aversion, novelty_seeking,
discount_responsiveness, warranty_sensitivity, review_dependency,
impulse_control, planning_horizon, quality_price_belief
```

Category fields:

```text
category_need, category_knowledge, replacement_urgency,
purchase_timeline, decision_role, preferred_channel,
price_ceiling, feature_priorities, brand_awareness, service_expectation
```

Narrative fields:

```text
short_summary, life_story_short, purchase_style, media_style,
risk_style, household_influence, category_decision_journal
```

Control fields:

```text
source_confidence, imputation_score, coherence_score,
duplicate_cluster_id, uncertainty_score, calibration_level,
generation_version, prompt_sensitivity_score, model_version_sensitivity,
bootstrap_interval_width
```

Interview choice fields:

```text
identity_snapshot, task_id, choice, interview_response, main_drivers,
main_barriers, rejected_alternatives, switch_conditions, answer_confidence,
isolation, generation_controls, quality_controls, diagnostics
```

`choice` is a discrete answer such as `focal_product`, `competitor`, or `none_or_delay`. Do not store person-level results only as scores or probabilities.

Interview control objects:

```json
{
  "isolation": {
    "context_scope": "individual",
    "conversation_id": "scenario_id:persona_id",
    "saw_other_answers": false,
    "saw_aggregate_results": false
  },
  "generation_controls": {
    "model": "model-name",
    "temperature": 0.2,
    "seed": "scenario_id:persona_id:task_id",
    "prompt_variant": "base",
    "schema_version": "choice_interview_v1"
  },
  "quality_controls": {
    "consistency_judge": "pass",
    "judge_reasons": [],
    "test_retest_status": "not_sampled",
    "prompt_sensitivity_status": "not_sampled"
  }
}
```

Require these controls for LLM-generated interview rows. For non-LLM respondent engines, store equivalent reproducibility and audit metadata.

HTE and segment labels:

```text
life_stage, household_type, price_ceiling_band, financial_stress,
category_need_intensity, replacement_urgency, decision_role,
price_sensitivity, premium_willingness, warranty_sensitivity,
review_dependency, brand_loyalty, feature_priority_cluster,
preferred_channel, digital_literacy, time_scarcity,
calibration_level, source_confidence, imputation_score
```

For the full HTE taxonomy and reporting schema, read `hte-segmentation.md`.

## Output Files

`personas_core.jsonl` is for computation. Keep it compact and structured.

`personas_narrative.jsonl` is for explanation. Link records by `persona_id`.

`personas_deep_casebook.jsonl` is for qualitative exploration. Use a small subset only.

`choice_results.jsonl` is for interviewed product answers. Each row must contain `persona_id`, `population_weight`, `choice`, `interview_response`, `main_drivers`, `main_barriers`, `switch_conditions`, and `answer_confidence`.

`choice_interview_validation.json` records schema pass rate, contamination warnings, isolation control coverage, and quality-control coverage.

`audit_report.json` is for trust. Include sources, fit, imputation, uncertainty, and limitations.

## HTE Label Object

Use this optional object when the user needs segment lift, CATE, uplift, targeting, or subgroup reporting:

```json
{
  "hte_labels": {
    "population": [],
    "capacity": [],
    "category_need": [],
    "decision_role": [],
    "price_value": [],
    "risk_trust": [],
    "brand_feature": [],
    "channel_media": [],
    "friction": [],
    "evidence": []
  }
}
```

Keep labels enumerable and stable. Do not generate unbounded free-text segment labels inside `personas_core.jsonl`.
