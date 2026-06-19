<div align="center">

# Synthetic Population and Silicon Sampling

_Census-weighted digital respondents for product choice, pricing, segment lift, and audited synthetic market research._

<p align="center">
  <img src="https://img.shields.io/badge/status-private%20research%20prototype-black" alt="Private research prototype">
  <img src="https://img.shields.io/badge/python-3.13-blue?logo=python&logoColor=white" alt="Python 3.13">
  <img src="https://img.shields.io/badge/respondents-isolated%20interviews-6f42c1" alt="Isolated interviews">
  <img src="https://img.shields.io/badge/output-JSONL%20%2B%20audit-green" alt="JSONL and audit outputs">
</p>

<p align="center">
  <a href="#what-it-does">What it does</a> |
  <a href="#how-it-works">How it works</a> |
  <a href="#get-started">Get started</a> |
  <a href="#proof">Proof</a> |
  <a href="#docs">Docs</a>
</p>

</div>

This repo packages agent skills and a runnable prototype for building weighted synthetic consumer panels where each digital respondent has an identity, answers a product scenario, and leaves an auditable trail from country data pack to persona to choice to segment lift.

Generated full panels live outside git in `runs/`. The repository keeps curated examples, summaries, and validation artifacts under `examples/` so each country/product run can be regenerated from the current scenario inputs.

AI agents / LLMs: read [`llms.txt`](llms.txt) for a compact map of the repository before using the skill.

## What It Does

- **Builds country data packs** - separates official margins, survey priors, imputed fields, missing tables, calibration levels, and IPF readiness.
- **Creates seed statistical cells** - turns an audited country pack plus explicit dimensions into a seed grid for raking.
- **Runs IPF/raking** - fits seed cells to supplied official or survey margin targets and writes weighted cells.
- **Samples persona skeletons** - uses deterministic largest-remainder allocation to convert weighted cells into exact-size `personas_core.jsonl` panels.
- **Expands soft traits** - initializes media, shopping, psychographic, and category priors with deterministic conditional rules, not LLM-generated stories.
- **Validates persona coherence** - checks ranges, traces, weights, duplicate IDs, and cross-field consistency before choice simulation.
- **Normalizes product scenarios** - turns raw A/B/C product descriptions into CBC-style finite choice sets with attributes, outside option, and audit metadata.
- **Runs deterministic choice baselines** - creates discrete choice rows from enriched personas and normalized scenarios before any LLM interview layer.
- **Runs full scenario pipelines** - wires the audited steps together from config and writes a manifest with step commands, outputs, and scientific boundaries.
- **Generates concise market reports** - summarizes audit status, weighted choice shares, uncertainty intervals, drivers, barriers, and limitations without copying row-level data.
- **Validates pipeline artifacts** - checks that required run outputs exist, JSON audits parse, critical pass flags are true, and reports stay compact.
- **Builds weighted synthetic panels** - separates hard demographics, inferred soft traits, narrative stories, and audit metadata.
- **Runs identity-first choice interviews** - each respondent outputs one discrete `choice`, a natural answer, drivers, barriers, and switch conditions.
- **Avoids score-table substitution** - probabilities and utility scores are diagnostics only; market share is aggregated from respondent choices.
- **Reports uncertainty** - bootstraps weighted choices and segment lift instead of presenting single-number claims.
- **Keeps claims auditable** - records source metadata, imputation limits, calibration level, validation outputs, and final acceptance checks.

## How It Works

```text
Country/product scenario
        |
        +-----------------------------+
        |                             |
        v                             v
Country pack: sources + constraints   Product scenario normalization
        |                             |
        v                             v
Seed statistical cells           normalized_choice_scenario.json
        |
        v
IPF/raking to official or survey margins
        |
        v
Weighted cells
        |
        v
Persona skeleton sampling
        |
        v
personas_core.jsonl
        |
        v
Deterministic soft-trait expansion
        |
        v
personas_enriched.jsonl
        |
        v
Persona coherence validation
        |
        v
Deterministic choice baseline
        |
        v
choice_results.jsonl
        |
        +--> validation: schema, isolation, confidence, contamination
        +--> bootstrap: intervals and segment lift
        +--> concise report: market_report.md / market_report.json
        +--> final acceptance: pipeline_artifact_validation.json
        +--> optional LLM interview explanation layer
```

The same flow can be run from a single config with `run_scenario_pipeline.py`, which preserves all intermediate files and writes `manifest.json` for provenance.

The important boundary: respondents answer as people; statistics aggregate after the answers. No respondent sees the target share, previous answers, or the sponsor's desired result.

## Get Started

The prototype uses only the Python standard library.

```powershell
# Run the full deterministic Serbia smartwatch demo pipeline from config.
# This emits manifest.json, choice_results.jsonl, bootstrap_intervals.json, market_report.md, market_report.json, and pipeline_artifact_validation.json.
python skills\weighted-persona-pricing\scripts\run_scenario_pipeline.py `
  skills\weighted-persona-pricing\examples\serbia_smartwatch_pipeline_config.json `
  --output-root runs

# Regenerate the concise report from an existing run manifest
python skills\weighted-persona-pricing\scripts\generate_market_report.py `
  runs\serbia_smartwatch_pipeline_demo\manifest.json

# Validate a completed run folder before treating it as deliverable
python skills\weighted-persona-pricing\scripts\validate_pipeline_artifacts.py `
  runs\serbia_smartwatch_pipeline_demo\manifest.json `
  --audit runs\serbia_smartwatch_pipeline_demo\pipeline_artifact_validation.json

# Build a generic country-pack skeleton
python skills\country-pack-builder\scripts\build_country_pack.py `
  --country-name Serbia --iso2 RS --iso3 SRB --population-year 2022 `
  --nso-name "Statistical Office of the Republic of Serbia" `
  --nso-url "https://www.stat.gov.rs/" `
  --total-population 6647003 --male-count 3231978 --female-count 3415025 `
  --output country_packs\RS\metadata.json

# Validate the country-pack builder example
python skills\country-pack-builder\scripts\validate_country_pack.py `
  skills\country-pack-builder\examples\RS_country_pack_v0_1.json

# Create demo seed cells from explicit dimensions
python skills\country-pack-builder\scripts\country_pack_to_cells.py `
  skills\country-pack-builder\examples\RS_country_pack_v0_1.json `
  --dimension region=Belgrade,Vojvodina `
  --dimension sex=male,female `
  --output runs\serbia-demo\seed_cells.jsonl

# Fit seed cells to a margin JSON file
python skills\country-pack-builder\scripts\run_ipf.py `
  runs\serbia-demo\seed_cells.jsonl `
  runs\serbia-demo\margins.json `
  --output runs\serbia-demo\weighted_cells.jsonl `
  --audit runs\serbia-demo\ipf_audit.json

# Sample exact-size hard persona skeletons from weighted cells
python skills\country-pack-builder\scripts\sample_persona_skeletons.py `
  runs\serbia-demo\weighted_cells.jsonl `
  --sample-size 1000 `
  --output runs\serbia-demo\personas_core.jsonl `
  --audit runs\serbia-demo\persona_sampling_audit.json

# Expand deterministic soft traits for pricing simulation readiness
python skills\weighted-persona-pricing\scripts\expand_soft_traits.py `
  runs\serbia-demo\personas_core.jsonl `
  --category smartwatch `
  --category-price-index 0.7 `
  --output runs\serbia-demo\personas_enriched.jsonl `
  --audit runs\serbia-demo\soft_trait_audit.json

# Validate enriched persona coherence before choice simulation
python skills\weighted-persona-pricing\scripts\validate_persona_coherence.py `
  runs\serbia-demo\personas_enriched.jsonl `
  --audit runs\serbia-demo\persona_coherence_audit.json

# Normalize a product scenario into a CBC-style choice set
python skills\weighted-persona-pricing\scripts\product_scenario_normalizer.py `
  skills\weighted-persona-pricing\examples\smartwatch_product_scenario.json `
  --output runs\serbia-demo\normalized_choice_scenario.json `
  --audit runs\serbia-demo\product_scenario_audit.json

# Run deterministic discrete-choice baseline
python skills\weighted-persona-pricing\scripts\run_choice_model.py `
  runs\serbia-demo\personas_enriched.jsonl `
  runs\serbia-demo\normalized_choice_scenario.json `
  --output runs\serbia-demo\choice_results.jsonl `
  --audit runs\serbia-demo\choice_model_audit.json

# Validate generated choice rows
python skills\weighted-persona-pricing\scripts\validate_choice_interviews.py `
  runs\serbia-demo\choice_results.jsonl `
  --audit runs\serbia-demo\choice_interview_validation.json `
  --require-controls

# Run country-pack, enrichment, scenario, choice, pipeline, report, and acceptance unit tests
python tests\test_country_pack_builder.py
python tests\test_country_pack_ipf_pipeline.py
python tests\test_sample_persona_skeletons.py
python tests\test_expand_soft_traits.py
python tests\test_validate_persona_coherence.py
python tests\test_product_scenario_normalizer.py
python tests\test_run_choice_model.py
python tests\test_run_scenario_pipeline.py
python tests\test_validate_pipeline_artifacts.py

# Validate the existing interview contract tests
python tests\test_choice_interview_validator.py
python tests\test_interview_choice_contract.py

# Validate the curated Hungary smartwatch example sample
python skills\weighted-persona-pricing\scripts\validate_choice_interviews.py `
  examples\hungary-watch-fit5pro-vs-gw8-interview\samples\choice_results_sample_100.jsonl

# Reproduce the full 10,000-person run locally when needed.
# Output goes to runs/, which is intentionally gitignored.
python scripts\run_hungary_watch_scenario.py
```

Use the skills from an agent:

```text
Use $country-pack-builder to build or audit a country statistical data pack before panel generation.
Use $weighted-persona-pricing to evaluate a country/category/product/competitor scenario with isolated synthetic respondents, segment lift, confidence intervals, audit notes, concise report, and final artifact validation.
```

## Proof

The included Hungary smartwatch scenario is a Level 0 synthetic interview example. It is a method demonstration, not a real sales forecast. The full 10,000-person panel is generated locally; this repository keeps samples and summary artifacts.

| Check | Current artifact | Result |
|---|---|---:|
| Core panel sample | `samples/personas_core_sample_100.jsonl` | 100 example records |
| Choice interview sample | `samples/choice_results_sample_100.jsonl` | 100 example rows |
| Choice contract validation | `choice_interview_validation.json` | 100% pass rate |
| Answer confidence distribution | `choice_interview_validation.json` | high 1,783 / medium 5,363 / low 2,854 |
| Bootstrap intervals | `bootstrap_intervals.json` | generated |
| Segment lift table | `segment_lift_table.json` | generated |

Example market summary from the included run:

| Option | Weighted share | 95% interval | Per 100k normalized intenders |
|---|---:|---:|---:|
| Huawei Watch Fit 5 Pro | 35.3% | 34.5%-36.1% | 35,270 |
| Samsung Galaxy Watch 8 | 45.2% | 44.3%-46.1% | 45,190 |
| None / delay | 19.5% | 18.9%-20.2% | 19,540 |

The audit explicitly marks this as `level_0_census_plus_model_assumptions`: no Hungarian smartwatch sales, clickstream, or survey calibration is included.

## Data Policy

- `examples/` contains small samples, summaries, and audit evidence that make the method inspectable.
- `runs/` contains generated full panels and is ignored by git.
- Full `personas_core.jsonl`, `choice_results.jsonl`, and narrative JSONL files should be regenerated per country, category, product, competitor set, and calibration level.
- If a full run must be shared, publish it as a separate artifact or controlled dataset, not as normal source history.

## Repository Map

| Path | Purpose |
|---|---|
| [`skills/country-pack-builder/SKILL.md`](skills/country-pack-builder/SKILL.md) | Country statistical data pack skill entrypoint |
| [`skills/country-pack-builder/prompts/build_country_pack.md`](skills/country-pack-builder/prompts/build_country_pack.md) | Reusable country pack generation prompt |
| [`skills/country-pack-builder/schemas/country_pack.schema.json`](skills/country-pack-builder/schemas/country_pack.schema.json) | JSON schema for combined country pack files |
| [`skills/country-pack-builder/scripts/build_country_pack.py`](skills/country-pack-builder/scripts/build_country_pack.py) | Generic country pack skeleton generator |
| [`skills/country-pack-builder/scripts/validate_country_pack.py`](skills/country-pack-builder/scripts/validate_country_pack.py) | Country pack structure and audit-readiness validator |
| [`skills/country-pack-builder/scripts/country_pack_to_cells.py`](skills/country-pack-builder/scripts/country_pack_to_cells.py) | Seed statistical cell generator |
| [`skills/country-pack-builder/scripts/run_ipf.py`](skills/country-pack-builder/scripts/run_ipf.py) | Iterative proportional fitting / raking over seed cells |
| [`skills/country-pack-builder/scripts/sample_persona_skeletons.py`](skills/country-pack-builder/scripts/sample_persona_skeletons.py) | Exact-size weighted persona skeleton sampler |
| [`skills/country-pack-builder/examples/RS_country_pack_v0_1.json`](skills/country-pack-builder/examples/RS_country_pack_v0_1.json) | Serbia anchor-ready example pack |
| [`skills/weighted-persona-pricing/SKILL.md`](skills/weighted-persona-pricing/SKILL.md) | Weighted persona pricing skill entrypoint |
| [`skills/weighted-persona-pricing/scripts/expand_soft_traits.py`](skills/weighted-persona-pricing/scripts/expand_soft_traits.py) | Deterministic soft-trait expansion for pricing-readiness |
| [`skills/weighted-persona-pricing/scripts/validate_persona_coherence.py`](skills/weighted-persona-pricing/scripts/validate_persona_coherence.py) | Persona-level coherence and consistency validator |
| [`skills/weighted-persona-pricing/scripts/product_scenario_normalizer.py`](skills/weighted-persona-pricing/scripts/product_scenario_normalizer.py) | CBC-style product scenario normalizer |
| [`skills/weighted-persona-pricing/scripts/run_choice_model.py`](skills/weighted-persona-pricing/scripts/run_choice_model.py) | Deterministic rule-based random-utility choice baseline |
| [`skills/weighted-persona-pricing/scripts/run_scenario_pipeline.py`](skills/weighted-persona-pricing/scripts/run_scenario_pipeline.py) | End-to-end deterministic scenario pipeline runner |
| [`skills/weighted-persona-pricing/scripts/generate_market_report.py`](skills/weighted-persona-pricing/scripts/generate_market_report.py) | Concise market report generator from pipeline manifest |
| [`skills/weighted-persona-pricing/scripts/validate_pipeline_artifacts.py`](skills/weighted-persona-pricing/scripts/validate_pipeline_artifacts.py) | Final run-folder acceptance validator |
| [`skills/weighted-persona-pricing/examples/smartwatch_product_scenario.json`](skills/weighted-persona-pricing/examples/smartwatch_product_scenario.json) | Example A/B smartwatch scenario |
| [`skills/weighted-persona-pricing/examples/serbia_smartwatch_pipeline_config.json`](skills/weighted-persona-pricing/examples/serbia_smartwatch_pipeline_config.json) | Example full pipeline config |
| [`skills/weighted-persona-pricing/references/interview-quality-controls.md`](skills/weighted-persona-pricing/references/interview-quality-controls.md) | Isolation, seed/temperature, schema, confidence, test-retest, prompt sensitivity, judge rules |
| [`skills/weighted-persona-pricing/references/choice-simulation.md`](skills/weighted-persona-pricing/references/choice-simulation.md) | Interview-first product choice workflow |
| [`skills/weighted-persona-pricing/scripts/validate_choice_interviews.py`](skills/weighted-persona-pricing/scripts/validate_choice_interviews.py) | Choice-row schema and contamination validator |
| [`skills/weighted-persona-pricing/scripts/bootstrap_choice_intervals.py`](skills/weighted-persona-pricing/scripts/bootstrap_choice_intervals.py) | Weighted bootstrap intervals and segment lift |
| [`scripts/run_hungary_watch_scenario.py`](scripts/run_hungary_watch_scenario.py) | End-to-end runnable demo scenario |
| [`examples/hungary-watch-fit5pro-vs-gw8-interview/`](examples/hungary-watch-fit5pro-vs-gw8-interview/) | Curated sample output, reports, validation, audit files |
| `runs/` | Local generated full panels; ignored by git |
| [`tests/`](tests/) | Lightweight unittest checks for the interview contract |

## Compatibility

| Surface | Status | Notes |
|---|:---:|---|
| Codex local skills | Ready | Copy or reference `skills/country-pack-builder` and `skills/weighted-persona-pricing` |
| Windows PowerShell | Tested locally | Current workspace uses Windows paths |
| Python | Ready | Standard-library scripts; tested with Python 3.13 |
| GitHub README showcase style | Used | Structure follows an evidence-first showcase pattern |
| Real market calibration | Not included | Add survey, sales, click, search, or CBC data for higher calibration levels |

## When To Use / When To Skip

**Great fit if you...**

- need a structured first pass before commissioning human research
- need country-source audit before synthetic panel generation
- want to compare products by country, segment, price, and reason
- care about confidence intervals, segment lift, and auditability
- need digital respondents that do not share context or target quotas

**Skip it if you...**

- need a legally defensible forecast from observed consumer behavior
- want individual-level targeting for sensitive or protected groups
- only need a quick qualitative brainstorm
- cannot tolerate synthetic assumptions in the decision process

## Docs

| Start here | Go deeper |
|---|---|
| [Country pack builder](skills/country-pack-builder/SKILL.md) | [Country pack prompt](skills/country-pack-builder/prompts/build_country_pack.md) |
| [Skill entrypoint](skills/weighted-persona-pricing/SKILL.md) | [Method routing](skills/weighted-persona-pricing/references/methodology-map.md) |
| [Product scenario workflow](skills/weighted-persona-pricing/references/product-scenario-workflow.md) | [Country data packs](skills/weighted-persona-pricing/references/data-packs.md) |
| [Interview quality controls](skills/weighted-persona-pricing/references/interview-quality-controls.md) | [Validation](skills/weighted-persona-pricing/references/validation.md) |
| [Persona schema](skills/weighted-persona-pricing/references/persona-schema.md) | [HTE segmentation](skills/weighted-persona-pricing/references/hte-segmentation.md) |

## Compared To

| Approach | What it gives you | Main limitation |
|---|---|---|
| **This repo** | Country-pack audit, weighted synthetic respondents, isolated interviews, intervals, audit files | Synthetic assumptions still need real-world calibration |
| One-shot persona prompt | Fast qualitative ideas | No stable weights, no isolation audit, weak reproducibility |
| Score-only simulator | Easy aggregation | Respondents are reduced to utilities instead of answers |
| Human survey / CBC | Observed respondent data | Slower and more expensive, but needed for calibrated decisions |

## Status

Private research prototype. Use it for hypothesis screening and workflow development before real survey, sales, click, or experiment calibration.

## Acknowledgement

README structure follows the evidence-first style of [`alexwang91/writing-showcase-readmes`](https://github.com/alexwang91/writing-showcase-readmes): attractive where supported, explicit where evidence is missing.
