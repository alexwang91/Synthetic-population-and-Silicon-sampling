# React Dashboard Data Contract

The React dashboard consumes exactly one artifact: `dashboard_data.json`.

It should not fetch or parse row-level panel files, row-level answer files, or raw model response files. The dashboard is a read-only presentation layer for aggregate planning output.

## Required media-planner sections

| Section | Required | Used for |
|---|---:|---|
| `input_brief` | yes | Country, audience, category/product, budget, and currency. |
| `workflow_steps` | yes | Five visible run stages: audience panel, channel candidates, simulation, budget allocation, recommendations. |
| `channel_plan` | yes | Candidate channels, funnel role, method field, creative angle, fit reason, and reach quality. |
| `channel_results` | yes | Aggregate channel estimates: reach, conversions, CAC, ROAS, ROI, interval, drivers, and risks. |
| `budget_recommendation` | yes | Priority ranking, budget amount, percent, rationale, execution advice, and risk. |
| `run_history` | yes | Aggregate run steps and status metadata. |
| `run` | recommended | Run id, status, version, and creation time. |
| `method` | recommended | Planning mode, calibration boundary, and LLM dependency. |
| `quality` | recommended | Audit cards for the aggregate artifacts. |
| `artifacts` | optional | Provenance drawer links. |

## Example shape

```json
{
  "input_brief": {
    "country": "Hungary",
    "audience": "cycling enthusiasts",
    "category": "smartwatch",
    "budget": 100000,
    "currency": "EUR"
  },
  "workflow_steps": [
    { "step_id": "audience_panel", "status": "passed" },
    { "step_id": "channel_candidates", "status": "passed" },
    { "step_id": "simulation", "status": "passed" },
    { "step_id": "budget_allocation", "status": "passed" },
    { "step_id": "recommendations", "status": "passed" }
  ],
  "channel_plan": { "channels": [] },
  "channel_results": { "channel_results": [] },
  "budget_recommendation": { "recommended_budget_split": [] },
  "run_history": { "steps": [] }
}
```

## Non-goals

The React app must not:

- generate respondents;
- run statistical fitting;
- run channel simulation;
- call an LLM;
- recompute ROI, ROAS, CAC, or budget split from row-level files;
- use checked-in large respondent files as the source for display.

## Loading modes

1. Embedded demo data when no query parameter is provided.
2. `?data=<relative-or-absolute-url>` for local development.
3. Upload a local `dashboard_data.json` file in the browser.

Example:

```text
http://localhost:5173/?data=../../../runs/hungary_cycling_smartwatch_demo/dashboard_data.json
```

## Interpretation boundary

ROI, ROAS, CAC, reach, conversions, and budget split are planning estimates. They are not observed platform results, sales, survey, clickstream, or experiment data. Decision-grade use requires holdouts, live campaign data, and calibration.
