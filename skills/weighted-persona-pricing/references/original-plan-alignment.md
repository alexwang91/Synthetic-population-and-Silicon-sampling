# Original Plan Alignment

This reference keeps the implementation anchored to the original product design.
New methods from synthetic population research, conjoint/discrete-choice practice, and LLM survey simulation are allowed only when they support this design. They must not replace it.

## Original product definition

The system is a census-weighted synthetic respondent panel for market research and pricing simulation.

The intended flow is:

```text
country official statistics / survey margins
→ weighted synthetic population cells
→ 10,000 representative, distinguishable digital respondents
→ each respondent has population_weight
→ each respondent has hard traits, soft traits, and optionally story/personality
→ each respondent independently answers the same product choice task
→ each answer is a discrete choice with reasons
→ market share is weighted aggregation over all respondent choices
```

The phrase "representative digital respondent" means:

- not arbitrary roleplay
- not unweighted persona fiction
- not random character generation
- not score-only utility rows
- a synthetic respondent whose record has a traceable statistical origin and `population_weight`

## Alignment table

| Current module | Alignment with original plan | Status | Boundary |
|---|---|---|---|
| `country-pack-builder` | Directly supports the original plan by grounding each country in official/survey constraints before persona generation. | core | Must not invent hard demographics. |
| `validate_country_pack.py` | Supports the original plan by blocking unsupported census-calibration claims. | core QA | Structural/audit validation only. |
| `country_pack_to_cells.py` | Supports the original plan by creating seed statistical cells before persona sampling. | core | Seed cells are not final people. |
| `run_ipf.py` | Supports the original plan by fitting cells to margin targets. | core | Requires valid official/survey/explicit margins. |
| `sample_persona_skeletons.py` | Supports the original plan by converting weighted cells into exact-size respondent skeletons. | core | Produces hard skeletons only, not finished respondents. |
| `expand_soft_traits.py` | Supports the original plan by adding structured inferred traits before interviews. | core, but inferred | Soft traits are priors, not observed facts. |
| narrative/personality layer | Required for the original product vision, but not fully implemented yet. | missing / next | Should enrich respondent identity without changing weights or hard traits. |
| `validate_persona_coherence.py` | Supports the original plan by checking that enriched respondents are usable before interview. | core QA | Warnings do not necessarily invalidate a respondent. |
| `product_scenario_normalizer.py` | Supports the original plan by giving every respondent the same finite product choice task. | core | Does not predict choice. |
| `run_choice_model.py` | Useful as baseline, smoke test, and comparison model. | auxiliary, not final simulator | Must not be treated as replacement for LLM respondent interviews. |
| `run_llm_choice_interviews.py run-batch` | This is the main intended synthetic respondent simulator: it calls a live LLM (or deterministic mock) per persona and writes discrete choice rows. | implemented | Each respondent independently returns a discrete choice and reason; aggregation still counts weighted choices. |
| `validate_choice_interviews.py` | Supports the original plan by enforcing row-level discrete choice output and isolation controls. | core QA | Should validate both rule-based baseline rows and LLM interview rows. |
| `bootstrap_choice_intervals.py` | Supports the original plan by estimating uncertainty over weighted choices. | core statistics | Does not create choices. |
| `generate_market_report.py` | Supports delivery/reporting. | presentation | Must summarize aggregates and avoid copying all row-level records. |
| `validate_pipeline_artifacts.py` | Supports acceptance/QA. | QA | Checks deliverability, not truth of market forecast. |
| `run_scenario_pipeline.py` | Supports orchestration. | workflow | Must not add new model assumptions or silently replace LLM interviews. |

## Correct choice-engine hierarchy

The system should distinguish between baseline choice generation and intended LLM respondent interviews.

| Engine | Coverage | Role |
|---|---:|---|
| `rule_based_baseline` | all personas | Development baseline, CI smoke test, sanity comparison, cheap preview. |
| `llm_short_all` | all personas | Main synthetic respondent mode: every representative respondent independently answers the product choice task. |
| `llm_short_all_plus_deep_sample` | all personas for short choice; selected respondents for deep interviews | Recommended commercial mode when both aggregate choice and richer explanations are needed. |
| `calibrated` | all personas | Decision-grade direction only when survey/CBC/sales/clickstream/experiment calibration exists. |

## Non-negotiable rules

1. Every respondent used in market-share aggregation must have `population_weight`.
2. Every respondent in the selected analysis universe should produce a discrete `choice`.
3. In the intended product mode, all 10,000 representative respondents can be asked through an LLM short interview.
4. Rule-based choice is allowed only as baseline/comparison/development mode.
5. Market share must be computed by weighted aggregation over respondent-level choices.
6. Narrative/personality can enrich a respondent but must not modify hard statistical variables or weights.
7. Reports and dashboards should read aggregate artifacts; they should not paste 10,000 row-level interviews into a single LLM prompt.
8. LLM interview rows must preserve isolation: no previous answers, no aggregate shares, no quotas, no target proportions.

## Methods that strengthen the original plan

These methods are additions that support the original plan:

- synthetic population / microsimulation: creates representative weighted respondents
- IPF/raking: fits population cells to margins
- largest-remainder allocation: converts weighted cells to exact-size respondent panels
- conjoint / discrete-choice design: structures the product choice task
- LLM virtual respondents: produces respondent-level answers and reasons
- bootstrap uncertainty: summarizes uncertainty over weighted choices
- provenance / manifest tracking: keeps the pipeline auditable

They are not allowed to replace the original architecture with a score-only simulator.

## Implementation status

The deterministic choice baseline (`run_choice_model.py`) remains, but its role is explicitly demoted from "main simulator" to "baseline/comparison".

The intended synthetic respondent simulator is implemented in `run_llm_choice_interviews.py`:

- `export-prompts` reads `personas_enriched.jsonl` and `normalized_choice_scenario.json` and writes one isolated prompt per persona.
- `run-batch` calls a live LLM (`--provider anthropic`) or a deterministic offline mock (`--provider mock`) over those prompts and writes `choice_results.jsonl` in the schema `validate_choice_interviews.py` expects.
- `normalize-responses` ingests an externally generated batch response file into the same schema.

`run_scenario_pipeline.py` runs this in-pipeline when `interview_engine: "llm_short_all"` and `llm_call_mode: "run_batch"`. See `references/llm-batch-runner.md`.

Remaining next steps: real survey/CBC/sales/clickstream calibration (move beyond Level 0), a fitted discrete-choice estimator so utility coefficients come from data rather than hand-set values, the narrative/personality enrichment layer, and a causal-HTE path.
