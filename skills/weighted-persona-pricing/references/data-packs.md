# Data Packs

## Country Statistical Data Pack

A synthetic panel is only credible when every hard variable and calibration source is traceable. If no data pack exists, produce a data acquisition plan instead of a calibrated panel.

Example country pack:

```text
serbia/
  census_region_age_sex.csv
  census_education_age_sex.csv
  household_size_region.csv
  employment_status_age_sex.csv
  income_decile_region.csv
  urban_rural_region.csv
  ict_usage_age_education.csv
  media_usage_survey.csv
  consumer_expenditure_category.csv
  metadata.json
```

## Source Metadata

Every file needs metadata:

```json
{
  "source_name": "Statistical Office of the Republic of Serbia",
  "source_url": "https://example.org",
  "year": 2022,
  "coverage": "Serbia excluding Kosovo and Metohija",
  "variables": ["region", "age_band", "sex"],
  "license": "unknown",
  "last_checked": "2026-06-18",
  "notes": []
}
```

## Required Hard Variables

Start with:

```text
region
age_band
sex
education_level
household_size
employment_status
income_decile or income_band
urban_rural
```

Optional but valuable:

```text
marital_status
children_count
housing_tenure
occupation_group
industry
internet_frequency
consumer_expenditure_category
media_usage
```

## IPF/Raking Inputs

Most countries will not provide the full joint distribution. Use marginal constraints such as:

```text
P(region)
P(age, sex)
P(education | age, sex)
P(household_size | region)
P(employment | age, sex)
P(urban_rural | region)
P(income_decile | region)
```

Record which constraints are official, which are survey-derived, and which are imputed.

## Higher-Order Interactions

Do not stop at first-order margins when the business question depends on interactions. Track the strongest available controls for:

```text
region x age x sex
region x education
region x income
age x household_size
income x household_size
education x internet_frequency
region x urban_rural x income
```

If these interactions are missing, choose one:

1. Mark them as unobserved and keep HTE labels coarse.
2. Use multilevel calibration or MRP-style shrinkage if survey data exists.
3. Use conditional imputation with an explicit uncertainty penalty.

Never present high-order segment lift as stable when the data pack only supports low-order margins.

## Calibration Levels

| Level | Name | Meaning |
|---|---|---|
| Level 0 | Census-calibrated | Hard demographics and household structure only |
| Level 1 | Survey-calibrated | Adds media, internet, expenditure, or consumer survey data |
| Level 2 | Behavior-calibrated | Adds sales, click, ad, panel, or experiment benchmarks |
| Level 3 | Client-calibrated | Calibrated to client-owned historical data |

Always state the level in the final report.
