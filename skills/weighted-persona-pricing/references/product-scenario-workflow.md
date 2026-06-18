# Product Scenario Workflow

Use this when the user describes a country, category, focal product, price, brand, features, competitors, and asks who would choose the product, why, and why not.

## Natural Input

Accept inputs like:

```text
Romania smartphone.
My product: Brand A, 399 EUR, long battery, fast charge, 128GB, 2-year warranty.
Competitor: Samsung A series, 349 EUR, strong brand, better screen, 128GB, 1-year warranty.
Who chooses my product, how many, what kind of people are they, why choose, why not choose?
```

If product or competitor details are missing and the user wants real current specs/prices, research current sources before running the scenario. Treat prices, product specs, and competitor lists as time-sensitive.

## Normalize Input

Convert the user request to:

```json
{
  "country": "Romania",
  "category": "smartphone",
  "currency": "EUR",
  "target_population": "adult smartphone purchase decision makers",
  "focal_product": {
    "name": "Brand A model",
    "price": 399,
    "attributes": {
      "battery": "long",
      "charging": "fast",
      "storage": "128GB",
      "warranty": "2 years"
    }
  },
  "competitors": [
    {
      "name": "Samsung A series",
      "price": 349,
      "attributes": {
        "brand_strength": "high",
        "screen": "better",
        "storage": "128GB",
        "warranty": "1 year"
      }
    }
  ],
  "choice_options": ["focal_product", "competitor", "none_or_delay"],
  "depth_plan": "tiered",
  "respondent_mode": "three_tier_mixed",
  "quality_controls": {
    "isolation": "individual",
    "answer_confidence": "low_medium_high",
    "test_retest_sample": "5-10%",
    "prompt_sensitivity_variants": ["base", "tradeoff", "skeptical"],
    "consistency_judge": true
  }
}
```

## End-To-End Output Contract

Produce these output layers:

1. Person-level interview answers: one identity, one scenario, one natural answer, one parsed choice per respondent.
2. Market choice summary: weighted share, represented population, no-purchase rate, confidence intervals from discrete choices.
3. Segment lift table: who over-indexes and under-indexes for the focal product.
4. Reasons: structured drivers and barriers by segment, linked to respondent answers.
5. Sensitivity: price, seed, prompt, model, and calibration sensitivity by re-running answers.
6. Interview quality audit: schema pass rate, isolation coverage, answer confidence distribution, test-retest, prompt sensitivity, consistency judge.
7. Readable report: a human-facing summary with charts/tables if the environment supports them, otherwise clean markdown tables.
8. Casebook: representative deep stories for key segments, not for every persona.

## Required JSON Summary

```json
{
  "scenario": {
    "country": "Romania",
    "category": "smartphone",
    "focal_product": "Brand A model",
    "competitors": ["Samsung A series"]
  },
  "overall": {
    "focal_product": {
      "share": 0.31,
      "interval": [0.27, 0.35],
      "represented_people": 1240000
    },
    "competitor": {
      "share": 0.46,
      "interval": [0.42, 0.50]
    },
    "none_or_delay": {
      "share": 0.23,
      "interval": [0.20, 0.27]
    }
  },
  "calibration_level": "level_1",
  "respondent_mode": "three_tier_mixed",
  "choice_interview_validation": {
    "choice_record_contract_pass_rate": 0.99,
    "context_contamination_rate": 0.0,
    "consistency_judge_pass_rate": 0.97
  },
  "interpretation": "Simulated preference hypothesis; validate with human or behavioral data."
}
```

## Readable Report Shape

Use this order:

1. Decision headline: one sentence with the focal product share and main competitive problem.
2. Market result table: focal product vs competitor vs none.
3. Who chooses: top positive segment lifts.
4. Who rejects: top negative segment lifts and barriers.
5. Why they choose: drivers ranked by weighted contribution.
6. Why they do not choose: barriers ranked by weighted contribution.
7. Price sensitivity: base price, lower price, higher price, elasticity.
8. Representative people: 5 to 12 deep cases from the strongest segments.
9. Confidence and sensitivity: bootstrap interval, seed sensitivity, prompt sensitivity, test-retest, consistency judge, model/calibration level.
10. Audit notes: data sources, imputed fields, limitations, next real-world validation step.

## Reason Output

For each important segment:

```json
{
  "segment_id": "price_value:medium_price_sensitivity|risk_trust:high_warranty_sensitivity",
  "plain_label": "Warranty-sensitive value buyers",
  "population_share": 0.18,
  "focal_choice_rate": 0.44,
  "lift_vs_average": 0.13,
  "why_choose": [
    "2-year warranty reduces perceived risk",
    "Battery and fast charging map to daily-use pain points",
    "Price is still within the segment ceiling"
  ],
  "why_not_choose": [
    "Competitor brand trust is stronger",
    "Screen quality is a visible comparison point",
    "Resale value is uncertain"
  ],
  "message_angle": "Lead with battery, fast charging, and warranty proof; reduce brand-risk anxiety."
}
```

## Person-Level Choice Output

Every new `choice_results.jsonl` row should look like an interview response:

```json
{
  "persona_id": "RO-PHONE-000001",
  "population_weight": 120.4,
  "identity_snapshot": {
    "age_band": "35-44",
    "region": "Bucharest",
    "income_decile": 6,
    "phone_ecosystem": "android",
    "price_ceiling": 450
  },
  "choice": "competitor",
  "interview_response": "I would choose Samsung. Your phone is interesting, but I know Samsung better and the price difference matters this month.",
  "main_drivers": ["brand_trust", "lower_price"],
  "main_barriers": ["focal_brand_risk"],
  "switch_conditions": ["focal discount", "stronger warranty proof"],
  "answer_confidence": "medium",
  "isolation": {
    "context_scope": "individual",
    "saw_other_answers": false,
    "saw_aggregate_results": false
  },
  "generation_controls": {
    "temperature": 0.2,
    "seed": "scenario:RO-PHONE-000001",
    "prompt_variant": "base"
  },
  "quality_controls": {
    "consistency_judge": "pass",
    "test_retest_status": "not_sampled",
    "prompt_sensitivity_status": "not_sampled"
  }
}
```

Do not use a row that only contains `choice_probability` as the primary respondent output.

## Guardrails

- Do not present a single number without an interval.
- Do not turn the person-level layer into score tables. Each respondent needs a final `choice`.
- Do not let respondents see other respondents, aggregate shares, quotas, or target proportions.
- Do not use numeric fake-precision confidence for interview answers; use `low|medium|high`.
- Do not show only winning segments; include rejection segments and barriers.
- Do not treat narrative stories as segment definitions.
- Do not call descriptive segment lift causal HTE.
- Do not report current product specs or competitor prices without checking current sources when the user expects real-world current values.
