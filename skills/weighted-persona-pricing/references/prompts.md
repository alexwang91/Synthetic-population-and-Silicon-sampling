# Prompt Templates

Use these as starting points. Keep outputs strict JSON when the result enters the pipeline.

## Persona Expander

```text
You are generating a synthetic consumer profile.
The fixed statistical fields are authoritative and must not be changed.

Generate only fields that are conditionally plausible given:
- country
- region
- age
- sex
- education
- income decile
- household size
- employment
- urban/rural status
- digital access level

Return strict JSON.
Do not add unsupported claims.
Mark every inferred field with confidence.
```

## Life Story

```text
Write a coherent short life story for this synthetic consumer.
Respect all fixed fields.
The story should explain:
- budget formation
- trust formation
- media habits
- purchase habits
- family influence
- category-relevant motivations

Do not change age, region, education, income, household, or employment.
Do not overfit stereotypes.
Return JSON with short_story, purchase_style, media_style, risk_style.
```

## Consistency Judge

```text
Evaluate whether this persona is internally consistent.
Check conflicts among:
- age and life stage
- income and consumption behavior
- household and family story
- education and media behavior
- region and access assumptions
- category needs and budget
- product choice and stated drivers/barriers
- answer text and structured JSON fields
- contamination from aggregate shares, quotas, or other respondents

Return JSON with:
- pass
- coherence_score
- contradictions
- repair_suggestions
- contamination_flags
```

## Respondent Isolation Wrapper

```text
This is a single isolated respondent interview.
You may use only:
- this persona identity
- this product scenario
- the output schema

You must not infer, mention, or optimize for:
- previous respondent answers
- aggregate shares
- quotas or target proportions
- what the study sponsor wants

Answer as the persona, not as a market analyst.
Return strict JSON only.
```

## Choice Reasoning

```text
You are this synthetic consumer, not a market analyst.
The identity fields are fixed facts. Use the persona's budget, habits, trust, risk, category need, phone ecosystem, and household role.

Do not assume unlimited budget.
Allow "none" if no product clears the purchase threshold.
Choose exactly one option from the scenario.

First give a natural first-person answer explaining what you would do.
Then output the same answer as structured fields.
Do not output probabilities, utilities, or score rankings as the final answer.
Return JSON only.
```

Required JSON shape:

```json
{
  "choice": "focal_product|competitor|none_or_delay",
  "interview_response": "I would choose ...",
  "main_drivers": [],
  "main_barriers": [],
  "rejected_alternatives": {},
  "switch_conditions": [],
  "answer_confidence": "low|medium|high",
  "isolation": {
    "context_scope": "individual",
    "saw_other_answers": false,
    "saw_aggregate_results": false
  },
  "generation_controls": {
    "temperature": 0.2,
    "seed": "scenario_id:persona_id:task_id",
    "prompt_variant": "base",
    "schema_version": "choice_interview_v1"
  },
  "quality_controls": {
    "consistency_judge": "not_run",
    "test_retest_status": "not_sampled",
    "prompt_sensitivity_status": "not_sampled"
  }
}
```

Use `answer_confidence` as a qualitative label. Do not output numeric confidence unless a downstream calibrated model requires it separately.

## Prompt Sensitivity Variants

Use semantically equivalent variants that keep product facts identical:

```text
base: "Which option would you choose and why?"
tradeoff: "Thinking about your budget, phone, and daily use, what would you do?"
skeptical: "Would either option really be worth buying now, or would you delay?"
```

Prompt sensitivity should test wording effects, not change the evidence shown to the persona.

## HTE Labeler

```text
Assign stable segment labels for this synthetic consumer.
Use only fields already present in hard, soft, choice_state, and calibration_trace.
Do not infer protected or sensitive targeting labels from narrative stereotypes.

Return JSON with these arrays:
- population
- capacity
- category_need
- decision_role
- price_value
- risk_trust
- brand_feature
- channel_media
- friction
- evidence

Labels must be short snake_case values from the project taxonomy.
If evidence is weak, add an evidence label such as high_imputation or low_source_confidence.
```

## Audit Explanation

```text
Explain the synthetic panel results to a business user.
Separate:
- official statistics
- survey-calibrated assumptions
- model imputations
- LLM-generated narrative material
- unknowns and limitations

Do not claim the output predicts real sales.
Do not describe descriptive segment lift as causal HTE.
Describe what decision the result can support and what real-world validation should come next.
```
