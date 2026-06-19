# React Dashboard

Premium React dashboard for `dashboard_data.json`.

This app is a presentation layer only. It does not generate personas, choices, market shares, or LLM responses. It reads a single `dashboard_data.json` artifact and renders country-panel structure, weighted choice shares, segment exploration, drivers/barriers, audit diagnostics, and deep case cards.

## Run locally

```powershell
cd skills\weighted-persona-pricing\dashboard-react
npm install
npm run dev
```

Open the dev server URL shown by Vite.

Without a `data` query parameter, the dashboard uses embedded demo data.

## Load a real run

After running a scenario pipeline, pass the dashboard artifact path:

```text
http://localhost:5173/?data=../../../runs/<run_id>/dashboard_data.json
```

Example:

```text
http://localhost:5173/?data=../../../runs/serbia_smartwatch_pipeline_demo/dashboard_data.json
```

The Vite config allows reading from the repository root during local development.

## Sections

1. **Hero overview** - run status, engine, respondent count, weighted population, 10k/1k/100 layers.
2. **Weighted choice shares** - focal product, competitor, and none/delay with intervals when available.
3. **Product scenario** - alternatives, prices, outside option, normalized attributes.
4. **Country panel distribution** - weighted population distributions and synthetic respondent support.
5. **Synthetic archetypes** - compact representative profiles and archetype-level choice shares.
6. **Segment explorer** - filter by available dimensions and inspect segment-level weighted shares.
7. **Drivers / barriers** - aggregated reason codes and segment snapshots.
8. **Quality and audit trail** - method settings, calibration level, prompt/order metadata, warnings.
9. **Deep case cards** - compact qualitative cards from the 100-person interpretation layer.

## Data boundary

The dashboard should not read:

- `personas_enriched.jsonl`
- `choice_results.jsonl`
- all row-level LLM responses
- raw country pack source tables

Those remain audit artifacts. The dashboard should read only `dashboard_data.json`.

## Production note

The first version intentionally avoids a backend. For product deployment, keep the same data contract and serve validated `dashboard_data.json` artifacts through a controlled endpoint.
