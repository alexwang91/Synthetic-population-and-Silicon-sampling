# HTE Segmentation

Use this file for segment lift, heterogeneous treatment effects, CATE, uplift, and targeting labels.

## Naming Discipline

Do not use `HTE` as a generic synonym for subgroup differences.

| Label type | Meaning | Required evidence |
|---|---|---|
| Descriptive segment lift | A weighted subgroup differs from the total in simulated choice share or WTP | Weighted panel and uncertainty checks |
| Preference heterogeneity | People differ in estimated partworths, coefficients, or latent preference classes | Repeated choice tasks or calibrated simulated choice history |
| Behavioral lift | Segment differs against observed sales, click, conversion, or survey benchmark | External behavior or survey calibration |
| Causal HTE/CATE | Treatment effect differs by covariates | Experiment, quasi-experiment, or defensible observational causal design |
| Uplift targeting label | Segment is predicted to respond incrementally to a treatment | Treatment/control data or calibrated uplift model |

## Expanded Label Families

Use labels from multiple families, not only demographics.

### 1. Population And Life Stage

```text
age_band
life_stage
household_type
children_count
elderly_dependents
marital_status
housing_tenure
urban_rural
region
commute_pattern
```

### 2. Socioeconomic Capacity

```text
income_decile
disposable_income_band
price_ceiling_band
savings_orientation
credit_access
financial_stress
employment_stability
occupation_group
education_level
```

### 3. Category Need And Timing

```text
category_need_intensity
replacement_urgency
purchase_timeline
ownership_status
current_solution_satisfaction
pain_point_severity
usage_frequency
seasonality_exposure
```

### 4. Decision Role And Household Dynamics

```text
primary_decider
primary_researcher
budget_holder
spouse_influence
child_influence
parent_influence
expert_friend_influence
joint_decision_complexity
```

### 5. Price And Value Psychology

```text
price_sensitivity
discount_responsiveness
promotion_skepticism
value_for_money_orientation
premium_willingness
loss_aversion
budget_rule_strictness
mental_accounting_category
```

### 6. Risk, Trust, And Proof

```text
risk_aversion
warranty_sensitivity
return_policy_sensitivity
review_dependency
expert_review_trust
word_of_mouth_trust
brand_trust
new_brand_resistance
service_failure_fear
```

### 7. Brand And Feature Preference

```text
brand_loyalty
brand_awareness
feature_priority_cluster
quality_price_belief
innovation_openness
design_sensitivity
sustainability_preference
local_brand_preference
```

### 8. Channel And Media Behavior

```text
preferred_channel
offline_store_reliance
online_purchase_frequency
marketplace_trust
social_media_influence
youtube_review_usage
forum_usage
news_portal_usage
influencer_trust
retailer_app_usage
```

### 9. Friction And Accessibility

```text
delivery_speed_need
installation_need
after_sales_access
payment_method_constraint
language_access
digital_literacy
transport_access
time_scarcity
```

### 10. Model And Evidence Controls

```text
calibration_level
source_confidence
imputation_score
uncertainty_score
coherence_score
duplicate_cluster_id
prompt_sensitivity_score
model_version_sensitivity
bootstrap_interval_width
```

## Default HTE Label Object

Add an optional `hte_labels` object to each core persona:

```json
{
  "hte_labels": {
    "population": ["urban", "age_35_44", "household_with_children"],
    "capacity": ["income_decile_7_10", "medium_high_savings"],
    "category_need": ["replacement_urgent", "high_usage_frequency"],
    "decision_role": ["primary_researcher", "shared_budget_holder"],
    "price_value": ["medium_price_sensitivity", "warranty_tradeoff_positive"],
    "risk_trust": ["high_review_dependency", "high_warranty_sensitivity"],
    "brand_feature": ["feature_led", "moderate_brand_loyalty"],
    "channel_media": ["online_research_offline_purchase"],
    "friction": ["delivery_speed_sensitive"],
    "evidence": ["level_1_survey_calibrated", "medium_imputation"]
  }
}
```

## Segment Output Schema

When reporting segment lift or HTE:

```json
{
  "segment_id": "price_value:high_price_sensitivity|capacity:income_decile_1_4",
  "label_type": "descriptive_segment_lift",
  "segment_definition": {
    "price_sensitivity": "high",
    "income_decile": "1-4"
  },
  "weighted_population_share": 0.18,
  "outcome": "choice_share_A",
  "overall_estimate": 0.46,
  "segment_estimate": 0.53,
  "lift": 0.07,
  "interval": [0.03, 0.11],
  "sample_count": 842,
  "effective_sample_size": 511,
  "calibration_level": "level_1",
  "method": "weighted_simulation_bootstrap",
  "interpretation": "Hypothesis for validation, not a causal effect."
}
```

## Segment Discovery Rules

1. Start with theory-driven labels from product economics: price, risk, proof, timing, budget, channel, and decision role.
2. Add data-driven labels only after checking support size and stability.
3. Require minimum weighted population share, minimum unweighted count, and minimum effective sample size.
4. Collapse or suppress sparse segments instead of reporting noisy micro-targets.
5. Report whether labels are stable across random seeds, prompt variants, and model versions.
6. For causal HTE, split discovery and estimation samples or use honest forests/cross-fitting.

## Recommended Segment Families By Product Question

| Product question | Segment families to prioritize |
|---|---|
| Price increase | price_value, capacity, category_need, risk_trust |
| Premium tier | premium_willingness, brand_feature, capacity, proof/trust |
| Warranty or service bundle | risk_trust, service_failure_fear, after_sales_access |
| Online vs offline channel | channel_media, digital_literacy, transport_access, time_scarcity |
| New brand entry | brand_trust, new_brand_resistance, review_dependency, social proof |
| Promotion planning | discount_responsiveness, promotion_skepticism, timing, uplift labels |
| Feature prioritization | feature_priority_cluster, category_knowledge, usage_frequency |

## Red Flags

- Segment label is just a stereotype with no measured or modeled field.
- Segment has high lift but tiny effective sample size.
- Segment is based on a protected or sensitive attribute and used for discriminatory pricing.
- Synthetic-only segment is described as a causal target.
- Lift disappears across seeds or prompt variants.
