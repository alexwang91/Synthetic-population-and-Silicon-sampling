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

This repo packages an agent skill and a runnable prototype for building weighted synthetic consumer panels where each digital respondent has an identity, answers a product scenario, and leaves an auditable trail from persona to choice to segment lift.

AI agents / LLMs: read [`llms.txt`](llms.txt) for a compact map of the repository before using the skill.

## What It Does

- **Builds weighted synthetic panels** - separates hard demographics, inferred soft traits, narrative stories, and audit metadata.
- **Runs identity-first choice interviews** - each respondent outputs one discrete `choice`, a natural answer, drivers, barriers, and switch conditions.
- **Avoids score-table substitution** - probabilities and utility scores are diagnostics only; market share is aggregated from respondent choices.
- **Supports three depth tiers** - 10,000 shallow records for statistics, 1,000 medium interviews for reason distribution, and 100 deep cases for story work.
- **Checks isolation and contamination** - validates that respondent rows do not leak aggregate shares, quotas, or other respondents into the answer.
- **Reports uncertainty** - bootstraps weighted choices and segment lift instead of presenting single-number claims.
- **Keeps claims auditable** - records source metadata, imputation limits, calibration level, and validation outputs.

## How It Works

```text
Country/product scenario
        |
        v
Statistical skeletons + weights
        |
        v
Soft-trait expansion with documented assumptions
        |
        v
Isolated respondent interviews
        |
        v
choice_results.jsonl
        |
        +--> validation: schema, isolation, confidence, contamination
        +--> bootstrap: intervals and segment lift
        +--> report: readable market story and audit notes
```

The important boundary: respondents answer as people; statistics aggregate after the answers. No respondent sees the target share, previous answers, or the sponsor's desired result.

## Get Started

The prototype uses only the Python standard library.

```powershell
# Validate the choice interview contract
python tests\test_choice_interview_validator.py
python tests\test_interview_choice_contract.py

# Validate the current Hungary smartwatch example output
python skills\weighted-persona-pricing\scripts\validate_choice_interviews.py `
  runs\hungary-watch-fit5pro-vs-gw8-interview\choice_results.jsonl `
  --audit runs\hungary-watch-fit5pro-vs-gw8-interview\choice_interview_validation.json

# Reproduce the example run when needed
python scripts\run_hungary_watch_scenario.py
```

Use the skill from an agent:

```text
Use $weighted-persona-pricing to evaluate a country/category/product/competitor scenario with isolated synthetic respondents, segment lift, confidence intervals, and audit notes.
```

## Proof

The included Hungary smartwatch scenario is a Level 0 synthetic interview run. It is a method demonstration, not a real sales forecast.

| Check | Current artifact | Result |
|---|---|---:|
| Core panel size | `personas_core.jsonl` | 10,000 records |
| Choice interviews | `choice_results.jsonl` | 10,000 rows |
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

## Repository Map

| Path | Purpose |
|---|---|
| [`skills/weighted-persona-pricing/SKILL.md`](skills/weighted-persona-pricing/SKILL.md) | Main Codex skill entrypoint |
| [`skills/weighted-persona-pricing/references/interview-quality-controls.md`](skills/weighted-persona-pricing/references/interview-quality-controls.md) | Isolation, seed/temperature, schema, confidence, test-retest, prompt sensitivity, judge rules |
| [`skills/weighted-persona-pricing/references/choice-simulation.md`](skills/weighted-persona-pricing/references/choice-simulation.md) | Interview-first product choice workflow |
| [`skills/weighted-persona-pricing/scripts/validate_choice_interviews.py`](skills/weighted-persona-pricing/scripts/validate_choice_interviews.py) | Choice-row schema and contamination validator |
| [`skills/weighted-persona-pricing/scripts/bootstrap_choice_intervals.py`](skills/weighted-persona-pricing/scripts/bootstrap_choice_intervals.py) | Weighted bootstrap intervals and segment lift |
| [`scripts/run_hungary_watch_scenario.py`](scripts/run_hungary_watch_scenario.py) | End-to-end runnable demo scenario |
| [`runs/hungary-watch-fit5pro-vs-gw8-interview/`](runs/hungary-watch-fit5pro-vs-gw8-interview/) | Example output, reports, validation, audit files |
| [`tests/`](tests/) | Lightweight unittest checks for the interview contract |

## Compatibility

| Surface | Status | Notes |
|---|:---:|---|
| Codex local skills | Ready | Copy or reference `skills/weighted-persona-pricing` |
| Windows PowerShell | Tested locally | Current workspace uses Windows paths |
| Python | Ready | Standard-library scripts; tested with Python 3.13 |
| GitHub README showcase style | Used | Structure follows an evidence-first showcase pattern |
| Real market calibration | Not included | Add survey, sales, click, search, or CBC data for higher calibration levels |

## When To Use / When To Skip

**Great fit if you...**

- need a structured first pass before commissioning human research
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
| [Skill entrypoint](skills/weighted-persona-pricing/SKILL.md) | [Method routing](skills/weighted-persona-pricing/references/methodology-map.md) |
| [Product scenario workflow](skills/weighted-persona-pricing/references/product-scenario-workflow.md) | [Country data packs](skills/weighted-persona-pricing/references/data-packs.md) |
| [Interview quality controls](skills/weighted-persona-pricing/references/interview-quality-controls.md) | [Validation](skills/weighted-persona-pricing/references/validation.md) |
| [Persona schema](skills/weighted-persona-pricing/references/persona-schema.md) | [HTE segmentation](skills/weighted-persona-pricing/references/hte-segmentation.md) |

## Compared To

| Approach | What it gives you | Main limitation |
|---|---|---|
| **This repo** | Weighted synthetic respondents, isolated interviews, intervals, audit files | Synthetic assumptions still need real-world calibration |
| One-shot persona prompt | Fast qualitative ideas | No stable weights, no isolation audit, weak reproducibility |
| Score-only simulator | Easy aggregation | Respondents are reduced to utilities instead of answers |
| Human survey / CBC | Observed respondent data | Slower and more expensive, but needed for calibrated decisions |

## Status

Private research prototype. Use it for hypothesis screening and workflow development before real survey, sales, click, or experiment calibration.

## Acknowledgement

README structure follows the evidence-first style of [`alexwang91/writing-showcase-readmes`](https://github.com/alexwang91/writing-showcase-readmes): attractive where supported, explicit where evidence is missing.
