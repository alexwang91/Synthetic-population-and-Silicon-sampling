# LLM Choice Risk Controls

This reference translates recent LLM survey and synthetic-respondent risks into concrete pipeline controls.

## Why these controls exist

Recent LLM survey-methodology work highlights three recurring risks:

1. **Prompt and option sensitivity** - small wording or answer-option changes can change model responses.
2. **Selection / order / recency bias** - LLMs may favor options because of their presented position or token form, not the respondent's simulated preference.
3. **Variance compression and weak subgroup differentiation** - synthetic respondents may produce distributions that are too smooth, too similar across subgroups, or insufficiently varied compared with real respondents.

These risks do not invalidate the original product design. They define the controls needed to make all-persona LLM short interviews auditable.

## Control map

| Risk | Control | Implementation |
|---|---|---|
| Prompt sensitivity | Record prompt version and prompt variant. Use compact, neutral/tradeoff prompt templates. | `run_llm_choice_interviews.py --prompt-variant neutral|tradeoff` |
| Option-order / recency bias | Do not define choice labels by presentation position. Use canonical labels and optional counterbalanced presentation order. | `canonical_choice_label`, `choice_label_map`, `--order-policy canonical|reverse|rotate` |
| Wrong label returned by LLM | Normalize response using `chosen_alternative_id` and prompt-level `choice_label_map`. Record `choice_remap_count`. | `run_llm_choice_interviews.py normalize-responses` |
| Variance compression | Check choice entropy, dominant choice share, confidence distribution, and reason-code variety. | `validate_llm_choice_quality.py` |
| Weak subgroup differentiation | Compare weighted choice shares by region, sex, income, education, settlement, employment, or configured fields. | `validate_llm_choice_quality.py --subgroup-fields ...` |
| Context leakage | Explicit isolation instructions and validation fields. | `validate_choice_interviews.py --require-controls` |
| Over-summarization | Store row-level outputs in JSONL and summarize only aggregate artifacts. | `token-and-scaling-policy.md` |

## Variance compression

Variance means the spread of responses across synthetic respondents. In this project, useful variance appears as:

- different personas choose different products;
- not every respondent has the same reason;
- confidence levels are not all identical;
- price-sensitive, high-income, rural, urban, digitally intense, or risk-averse respondents can behave differently when the product scenario makes that plausible.

A synthetic panel with low variance may look stable but is often less useful. If every persona chooses the same product for the same generic reason, the model is not acting like a differentiated respondent panel.

## Subgroup differentiation

Subgroup differentiation means that important segments can show different weighted choice patterns.

Examples:

- high-income respondents may tolerate a higher price;
- low-income respondents may select `none_or_delay` more often;
- more digitally intense respondents may value apps/ecosystem features more;
- risk-averse respondents may react more to warranty or brand trust.

This is not a requirement that every subgroup must differ. Some products genuinely have broad appeal. The risk is when all subgroups always look identical, because then the synthetic panel has lost the heterogeneity that segmentation and pricing analysis require.

## Product choice prompt design

A product choice prompt should:

1. present a finite choice set;
2. include an outside option when purchase deferral is realistic;
3. use structured attributes, not raw marketing copy alone;
4. define canonical choice labels independently of display order;
5. instruct the respondent not to use other respondents, aggregate shares, quotas, or target proportions;
6. require strict JSON output;
7. collect drivers, barriers, switch conditions, and confidence;
8. keep the respondent answer short enough for 10,000-person operation.

## Required downstream checks

For LLM-generated choice rows, run:

```powershell
python skills\weighted-persona-pricing\scripts\validate_choice_interviews.py `
  runs\<run_id>\choice_results.jsonl `
  --audit runs\<run_id>\choice_interview_validation.json `
  --require-controls

python skills\weighted-persona-pricing\scripts\validate_llm_choice_quality.py `
  runs\<run_id>\personas_enriched.jsonl `
  runs\<run_id>\choice_results.jsonl `
  --audit runs\<run_id>\llm_choice_quality_audit.json
```

The first validator checks row integrity and isolation. The second checks methodological risk patterns.
