# Country Run Policy

This project is a country-level synthetic respondent panel generator. A run must regenerate its active respondent panel from country inputs.

## Hard rule

Do not treat a checked-in 10,000-person file, prior persona JSONL, prior choice JSONL, or old dashboard artifact as the population source.

Every country scenario starts from:

```text
country_pack
+ dimensions
+ margins
+ sample_size
+ product_scenario
```

Then the pipeline generates:

```text
seed_cells.jsonl
→ weighted_cells.jsonl
→ personas_core.jsonl
→ personas_enriched.jsonl
→ choice_results.jsonl
→ dashboard_data.json
```

## Why

A reusable fixed respondent file would turn the system into a static sample analyzer. The intended product is a repeatable country-run generator.

Changing the country should regenerate the panel because:

- population weights differ by country;
- required margins differ by country;
- country coverage and source quality differ;
- digital access, income, education, settlement, and employment structures differ;
- the 1,000 and 100 explanation layers must be derived from the active 10,000-person country run.

## Layer contract

| Layer | Source | Purpose |
|---|---|---|
| 10,000 | regenerated active country panel | weighted market estimation and segment filtering |
| 1,000 | selected from active country panel | medium-detail explanation and reason-code review |
| 100 | selected from active country panel or 1,000 explanation layer | compact persona case cards and qualitative examples |

The 1,000 and 100 layers are not separate population bases. They are derived views of the current run.

## Allowed config inputs

A scenario config may include:

- `country_pack`
- `dimensions`
- `margins` or `margins_inline`
- `sample_size`
- `product_scenario`
- `category`
- `category_price_index`
- `interview_engine`
- dashboard sample sizes and audit settings

## Disallowed config inputs

A scenario config should not include prior active-run artifacts as inputs, such as:

- `personas_enriched`
- `personas_core`
- `persona_file`
- `panel_path`
- `choice_results`
- `choice_results_file`

These are outputs of a run, not input population sources.

## Builder

Use the config builder to create a run config:

```powershell
python skills\weighted-persona-pricing\scripts\create_country_scenario_config.py `
  --country-pack skills\country-pack-builder\examples\RS_country_pack_v0_1.json `
  --product-scenario skills\weighted-persona-pricing\examples\smartwatch_product_scenario.json `
  --dimension region=Belgrade,Vojvodina `
  --dimension sex=male,female `
  --margins-json skills\weighted-persona-pricing\examples\serbia_smartwatch_margins.json `
  --sample-size 10000 `
  --output runs\configs\serbia_smartwatch_10000.json
```

## Validator

Use the dependency validator before accepting scenario configs:

```powershell
python scripts\validate_no_static_panel_dependency.py skills\weighted-persona-pricing\examples
```

Warnings for demo-size configs are acceptable. Errors indicate a config is not following the country-run contract.
