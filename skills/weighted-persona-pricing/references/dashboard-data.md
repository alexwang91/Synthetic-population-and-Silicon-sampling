# Dashboard Data

`dashboard_data.json` is the structured input layer for future HTML or app dashboards.

It is not a new model and does not create choices. It consolidates existing pipeline artifacts into one front-end-friendly JSON file.

## Purpose

The dashboard should show both:

1. market results, such as weighted choice shares and intervals; and
2. method quality, such as interview engine, prompt/order settings, LLM warnings, subgroup diagnostics, and artifact validation status.

This prevents dashboards from displaying synthetic respondent outputs as if they were observed consumer data.

## Generator

```powershell
python skills\weighted-persona-pricing\scripts\generate_dashboard_data.py `
  runs\<run_id>\manifest.json `
  --output runs\<run_id>\dashboard_data.json
```

The full scenario pipeline generates this file automatically when `generate_dashboard_data` is true.

## Top-level sections

| Section | Purpose |
|---|---|
| `run` | Run ID, pipeline status, pipeline version, creation time. |
| `method` | Interview engine, calibration level, prompt/order settings, risk controls, limitations. |
| `inputs` | Scenario inputs copied from the manifest. |
| `product_scenario` | Normalized product choice-set summary. |
| `results` | Choice shares, intervals, confidence counts, top drivers, top barriers. |
| `quality` | Audit cards, LLM risk summary, row validation, artifact validation. |
| `artifacts` | Links/paths to retained JSON, JSONL, and report files. |

## Method boundary

Dashboard data should read aggregate artifacts and compact diagnostics.

It should not copy or render all row-level persona or interview records by default.

For LLM runs, the dashboard should display:

- `interview_engine`
- `prompt_version`
- `prompt_variant`
- `order_policy`
- LLM quality warnings
- subgroup differentiation diagnostics
- possible position/order-bias warnings
- calibration level

## Recommended UI panels

1. **Executive result** - weighted choice shares and bootstrap intervals.
2. **Choice task** - alternatives, prices, outside option, key normalized attributes.
3. **Method card** - interview engine, prompt/order settings, calibration level.
4. **Quality card** - IPF, persona coherence, product scenario, choice rows, LLM quality, artifact validation.
5. **Drivers and barriers** - top weighted reason codes.
6. **Subgroup diagnostics** - subgroup share differences and warnings.
7. **Artifacts** - downloadable source files for audit.

## Interpretation

Warnings in `quality.llm_risk_summary` are diagnostic signals. They do not automatically mean the result is wrong.

Examples:

- A dominant product share may indicate real product dominance or LLM response collapse.
- Low subgroup differentiation may indicate a broadly appealing product or over-smoothed synthetic responses.
- Position-bias warnings indicate that a counterbalanced or canonical-order sensitivity run may be needed.
