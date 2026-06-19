# React Dashboard Data Contract

The React dashboard consumes exactly one artifact: `dashboard_data.json`.

It should not fetch or parse row-level persona files, row-level choice files, or raw LLM response files.

## Required sections

| Section | Required | Used for |
|---|---:|---|
| `run` | yes | Hero metadata and status. |
| `method` | yes | Engine, calibration, prompt/order settings, method boundary. |
| `country_panel` | yes | Country and weighted panel overview. |
| `results` | yes | Weighted choice shares, intervals, top drivers/barriers. |
| `product_scenario` | yes | Choice set, products, outside option. |
| `quality` | yes | Audit cards and LLM risk diagnostics. |
| `artifacts` | optional | Artifact drawer / provenance links. |
| `filter_options` | recommended | Segment Explorer controls. |
| `segment_choice_cube` | recommended | Segment-level weighted choice shares. |
| `reason_cube` | recommended | Segment and choice reason summaries. |
| `archetypes` | recommended | Representative synthetic profiles. |
| `sample_layers` | recommended | 10k / 1k / 100 layer summary and deep case cards. |

## Non-goals

The React app must not:

- generate personas;
- run IPF/raking;
- run choice simulation;
- call an LLM;
- recompute market shares from row-level files;
- use a checked-in 10k persona file as a population source.

## Loading modes

1. Embedded demo data when no query parameter is provided.
2. `?data=<relative-or-absolute-url>` for local development.

Example:

```text
http://localhost:5173/?data=../../../runs/serbia_smartwatch_pipeline_demo/dashboard_data.json
```

## Interpretation boundary

Dashboard values are synthetic respondent simulation outputs. They are not observed sales, survey, clickstream, or experiment data. Decision-grade claims require external calibration.
