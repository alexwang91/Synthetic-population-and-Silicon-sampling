---
name: country-pack-builder
description: Use when the user needs to build, audit, or plan country statistical data packs for census-weighted synthetic populations, silicon samples, weighted persona panels, IPF/raking inputs, source metadata, calibration levels, missing-table reports, or country coverage checks before persona generation or pricing simulation.
---

# Country Pack Builder

## Overview

Build machine-readable country statistical data packs before generating synthetic respondents. Use official statistics to decide which hard constraints exist, what can be fitted, what must be imputed, and what claims the downstream panel may make.

This skill is the data-foundation layer for `weighted-persona-pricing`. It does not generate personas, product choices, market shares, or narrative stories.

## Core Boundary

A country pack is not a synthetic population. It is the audited input layer used to create one.

Use this skill to produce:

```text
country_packs/<ISO2>/
  metadata.json
  sources.json
  constraints.json
  tables/
  audit/
```

If official tables are missing, produce a source plan and gap report. Do not pretend the pack is census-calibrated.

## First Decision

Classify the request before acting:

| User needs | Mode | Output |
|---|---|---|
| New country support | Country pack skeleton | `metadata.json`, `sources.json`, `constraints.json`, missing table list |
| Source discovery | Source mapping | official source priority, table URLs, extraction plan |
| Data extraction plan | Table plan | required CSV names, grains, variables, expected sources |
| Existing pack audit | Pack validation | source coverage, missing fields, calibration level, warnings |
| Cross-country rollout | Coverage matrix | country status: empty/source_mapped/anchor_ready/ipf_ready/calibrated_ready |
| Downstream panel readiness | IPF readiness audit | whether weighted skeleton generation is allowed |

## Evidence Rules

- Use national statistical offices and official census portals before international aggregators.
- Use Eurostat, OECD, World Bank, UN, ILO, ITU, DHS/MICS only as fallback or harmonisation sources unless they are the strongest source for that variable.
- Use commercial or public web sources only for category and product context. Never use them for hard population weights.
- Keep official margins, survey margins, derived margins, imputed priors, and unavailable constraints separate.
- Do not let LLM-generated narratives, stereotypes, or product assumptions fill hard demographic tables.
- Do not include sensitive attributes for discriminatory pricing. If such attributes are statistically relevant for representativeness, restrict them to aggregate calibration and audit notes.

## Required Hard Variables

A country pack should support these variables before it is considered useful for weighted persona generation:

```text
region
age_band
sex
urban_rural or settlement_type
education_level
household_size
employment_status
income_band or income_decile
internet_frequency or digital_access_level
```

Optional but valuable variables:

```text
marital_status
children_count
migration_status
birthplace_region
housing_tenure
occupation_group
industry
consumer_expenditure_category
e_commerce_usage
media_usage
language or ethnicity only when legally and ethically appropriate
```

## Calibration Levels

| Level | Name | Meaning |
|---|---|---|
| Level 0 | Census-calibrated | Hard demographics and household structure only |
| Level 1 | Survey-calibrated | Adds ICT, media, expenditure, or consumer survey data |
| Level 2 | Behavior-calibrated | Adds sales, clicks, search, panel, or observed product behavior |
| Level 3 | Client-calibrated | Calibrated with client-owned historical data |

A pack may have partial anchors without being ready for Level 0. Total population and sex anchors alone do not permit a census-calibrated synthetic panel.

## Recommended Workflow

1. Define country identity: country name, ISO2, ISO3, population year, target population, and coverage scope.
2. Identify national statistical office and census portal.
3. List required tables, grains, variables, and source metadata.
4. Extract anchor values only when the source is known and traceable.
5. Classify each constraint as `official_margin`, `survey_margin`, `derived_margin`, `imputed_prior`, or `unavailable`.
6. Assign each constraint `use_in_ipf: true|false`.
7. Mark missing tables and high-imputation fields.
8. Run `validate_country_pack.py` on the JSON output.
9. Produce a build status: `empty`, `source_mapped`, `anchor_ready`, `ipf_ready`, or `calibrated_ready`.
10. Hand off only `ipf_ready` or stronger packs to weighted skeleton generation.

## Expected Inputs

```json
{
  "country_name": "Serbia",
  "iso2": "RS",
  "iso3": "SRB",
  "target_population": "adult_purchase_decision_makers",
  "population_year": 2022,
  "intended_use_case": "pricing_simulation",
  "preferred_language": "en",
  "calibration_level_requested": "level_0_census"
}
```

## Expected Outputs

For planning or source discovery:

```text
country_pack_plan.md
missing_tables.json
source_priority.json
```

For a real pack:

```text
metadata.json
sources.json
constraints.json
tables/*.csv
audit/source_coverage_report.json
audit/missing_tables.json
audit/marginal_fit_report.json
```

For compact examples or early-stage work, one combined JSON file is acceptable:

```text
examples/RS_country_pack_v0_1.json
```

## Minimum Combined JSON Contract

A combined country pack JSON must include:

```json
{
  "country_identity": {},
  "coverage_scope": {},
  "source_priority": [],
  "required_tables": [],
  "optional_tables": [],
  "extracted_anchor_values": {},
  "statistical_constraints": [],
  "imputation_policy": {},
  "quality_checks": {},
  "build_status": {},
  "next_actions": []
}
```

## Table Contract

Every required or optional table entry should include:

```json
{
  "file_name": "census_region_age_sex.csv",
  "grain": "region x age_band x sex",
  "variables": ["region", "age_band", "sex", "population_count"],
  "source_name": "National Statistical Office",
  "source_url": "https://...",
  "source_year": 2022,
  "coverage_note": "...",
  "official_or_imputed": "official|official_expected|survey|derived|imputed|unavailable",
  "required_for_level": "level_0_census",
  "missing_status": "available|anchor_values_available|needs_download_from_database|needs_source_table|unavailable",
  "comments": "..."
}
```

## Constraint Contract

Every statistical constraint should include:

```json
{
  "constraint_id": "RS_SEX_2022",
  "type": "official_margin|survey_margin|derived_margin|imputed_prior|unavailable",
  "variable_set": ["sex"],
  "values_available": true,
  "geography_level": "country",
  "population_base": "all residents",
  "year": 2022,
  "source": "SORS Census 2022",
  "confidence": "high|medium|low",
  "use_in_ipf": true,
  "warning_if_used": null
}
```

## Build Status Rules

Use exactly one status:

| Status | Meaning |
|---|---|
| `empty` | Only country identity exists |
| `source_mapped` | Official source locations are known, but tables are not attached |
| `anchor_ready` | Some traceable anchor values exist, but IPF inputs are incomplete |
| `ipf_ready` | Required margins are attached enough to generate weighted skeletons |
| `calibrated_ready` | Survey, behavior, or client calibration exists beyond hard census constraints |

Set `can_generate_demo_panel` separately from `can_claim_census_calibrated_panel`.

## Validation Command

```bash
python skills/country-pack-builder/scripts/validate_country_pack.py skills/country-pack-builder/examples/RS_country_pack_v0_1.json --audit country_pack_validation.json
```

The validator checks structure and metadata completeness. It does not verify every external statistic. A human or source extractor must still confirm downloaded tables and values.

## Handoff To Weighted Persona Pricing

Only hand off a pack to `weighted-persona-pricing` when:

- required tables are present or explicitly marked as acceptable priors,
- the build status is `ipf_ready` or stronger, or the downstream run is explicitly marked as a demo,
- missing high-order interactions are documented,
- source metadata is complete enough to audit,
- sensitive variables have usage restrictions.

If the pack is only `anchor_ready`, downstream output must say `partial country pack` or `demo panel`, not `census-calibrated panel`.
