# Interview-First Choice Simulation

Use this mode for product A/B, pricing, WTP, purchase intent, conjoint-style tasks, and competitor choice. The person-level output is a respondent answer, not a score table.

## Core Principle

Generate or load a persona identity first, show the same product scenario to that persona, ask for a natural choice answer, parse that answer into one final choice, then aggregate weighted choices.

Do not make `choice_probability` the default output. Probabilities, utilities, propensities, or scores may be used only as internal diagnostics, sampling aids, calibration priors, or consistency checks.

For isolation, generation controls, answer confidence, test-retest, prompt sensitivity, and consistency judging, read `interview-quality-controls.md`.

## Task Design

Always include a realistic no-purchase option unless the user explicitly asks for forced choice:

```json
{
  "task_id": "T-001",
  "context": "The consumer is considering a replacement smartwatch within 3 months.",
  "alternatives": [
    {
      "id": "focal_product",
      "brand": "Huawei",
      "model": "Watch Fit 5 Pro",
      "price": 99990,
      "currency": "HUF",
      "attributes": ["10-day battery", "Android+iOS compatibility", "sport-health tracking"]
    },
    {
      "id": "competitor",
      "brand": "Samsung",
      "model": "Galaxy Watch 8 44 mm",
      "price": 77990,
      "currency": "HUF",
      "attributes": ["lower price", "Google Pay", "Android ecosystem"]
    },
    {
      "id": "none_or_delay",
      "meaning": "Delay purchase or keep current watch"
    }
  ]
}
```

## Person-Level Contract

Every interviewed persona must produce:

```json
{
  "persona_id": "HU-WATCH-00001",
  "identity_snapshot": {
    "age": 34,
    "region": "Budapest",
    "income_decile": 7,
    "phone_ecosystem": "ios",
    "price_ceiling": 110000,
    "category_need": "fitness_outdoor_high"
  },
  "choice": "focal_product",
  "interview_response": "I would choose Huawei. It is more expensive, but I use an iPhone and care more about battery life for running than Google Pay.",
  "main_drivers": ["battery_life", "ios_compatibility", "fitness_tracking"],
  "main_barriers": ["higher_price"],
  "rejected_alternatives": {
    "competitor": "Samsung is cheaper, but Android and Google Pay do not matter enough to me.",
    "none_or_delay": "The purchase is useful enough for training that I would not delay."
  },
  "switch_conditions": ["Huawei above my comfort budget", "Samsung has better iOS compatibility"],
  "answer_confidence": "medium",
  "method": "identity_first_interview",
  "isolation": {
    "context_scope": "individual",
    "saw_other_answers": false,
    "saw_aggregate_results": false
  },
  "generation_controls": {
    "temperature": 0.2,
    "seed": "scenario_id:HU-WATCH-00001:T-001",
    "prompt_variant": "base"
  },
  "quality_controls": {
    "consistency_judge": "pass",
    "test_retest_status": "not_sampled",
    "prompt_sensitivity_status": "not_sampled"
  }
}
```

Use enumerable driver and barrier labels where possible. Keep the natural answer as text, but never aggregate by reading free text alone.

## Prompt Pattern

For an LLM respondent, use a strict JSON prompt:

```text
You are this synthetic consumer. The identity fields are fixed facts.
Read the product scenario and answer as this person, not as a market analyst.

Choose exactly one:
- focal_product
- competitor
- none_or_delay

First write one natural first-person answer.
Then structure the same answer into choice, main_drivers, main_barriers,
rejected_alternatives, and switch_conditions.

Do not output probabilities, utility scores, or rankings as the final answer.
Return strict JSON only.
```

For 10,000-person runs, avoid 10,000 long LLM calls. Use one of:

- LLM for 100 deep and 1,000 medium responses, then a validated deterministic respondent for 10,000 shallow responses.
- Batched structured-output calls with short answers only.
- Rule-based or statistical respondent for Level 0, clearly audited as synthetic assumptions.

If the user requests 10,000 independent LLM conversations, use one request per respondent or hard-delimited micro-batches with audit metadata. Do not run a single rolling conversation over many personas.

## Weighted Aggregation

Weighted share must count discrete choices:

```text
Share_A = sum_i(w_i * 1(choice_i = A)) / sum_i(w_i)
```

Segment lift:

```text
Lift_segment_A = Share_A(segment) - Share_A(total)
```

Price sensitivity must re-run the interview task on the same personas with changed prices:

```text
base task -> persona answer
focal price -10% -> same persona answers again
focal price +10% -> same persona answers again
competitor price changes -> same persona answers again
```

Report who switches, why they switch, and which switch conditions are triggered.

## Optional Diagnostics

Diagnostics may exist in separate fields or files, but they must not replace the answer:

```json
{
  "diagnostics": {
    "budget_conflict": false,
    "identity_answer_coherence": "pass",
    "model_prior_used": true,
    "latent_utility_not_reported_to_user": true
  }
}
```

Use diagnostics for:

- coherence checks
- sparse segment suppression
- calibration to real survey, click, or sales data
- prompt/model sensitivity
- identifying personas that need manual review

Do not show diagnostics as respondent answers. Report diagnostics in audit files.

## Preference Heterogeneity Models

Choose the model according to evidence:

| Evidence | Model family | Person-level output | Aggregate output |
|---|---|---|---|
| Synthetic panel with one scenario | Identity-first interview | one discrete choice | descriptive segment lift |
| Repeated synthetic tasks per persona | Interview plus mixed-logit/HB-MNL diagnostics | repeated choices | preference heterogeneity labels |
| Human CBC/DCE data | HB-MNL, mixed logit, latent class MNL | observed choice tasks | partworths, WTP, preference segments |
| Treatment/control outcome data | Causal forest, meta-learner, uplift model | observed outcomes | causal HTE/uplift |

Do not call a descriptive segment lift causal HTE unless treatment assignment, counterfactual design, or calibrated causal assumptions support it.

## Confidence Intervals

For weighted interview results, bootstrap over records:

```bash
python scripts/bootstrap_choice_intervals.py choice_results.jsonl \
  --segment-field hte_labels.price_value \
  --segment-field hte_labels.risk_trust \
  --segment-field hte_labels.category_need
```

The script accepts preferred discrete `choice` records and legacy probability records. Prefer discrete records for new runs.

Before bootstrapping, validate the interview contract:

```bash
python scripts/validate_choice_interviews.py choice_results.jsonl --audit choice_interview_validation.json
```

For LLM-generated respondent batches:

```bash
python scripts/validate_choice_interviews.py choice_results.jsonl --require-controls --strict
```

## Red Flags

Stop and revise if:

- `choice_results.jsonl` has probabilities but no `choice`.
- 1,000 medium records contain only scores and no natural answer.
- The report says "people chose" when the pipeline only averaged probabilities.
- Sensitivity analysis changes prices but does not re-run persona answers.
- Segment stories are written after aggregation but are not linked to actual persona IDs.
- Multiple respondents share one rolling context without isolation metadata.
- Respondents mention aggregate shares, quotas, or other respondents in their answers.
- `answer_confidence` uses fake precision instead of `low|medium|high`.
