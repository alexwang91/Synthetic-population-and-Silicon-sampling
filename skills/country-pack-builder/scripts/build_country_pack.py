#!/usr/bin/env python3
"""Build a generic country pack skeleton.

The script creates a structurally valid country pack from user-supplied country
identity and optional anchor values. It does not fetch official data. Use it to
initialize a pack, then attach official tables and run validation.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

DEFAULT_REQUIRED_TABLES = [
    {
        "file_name": "census_population_total_sex.csv",
        "grain": "country x sex",
        "variables": ["country", "sex", "population_count", "population_share"],
        "required_for_level": "level_0_census",
        "comments": "Use for total population and sex reconciliation."
    },
    {
        "file_name": "census_region_age_sex.csv",
        "grain": "region x age_band x sex",
        "variables": ["region", "age_band", "sex", "population_count"],
        "required_for_level": "level_0_census",
        "comments": "Core IPF/raking constraint. Do not replace with LLM-generated shares."
    },
    {
        "file_name": "census_education_age_sex_region.csv",
        "grain": "region x age_band x sex x education_level",
        "variables": ["region", "age_band", "sex", "education_level", "population_count"],
        "required_for_level": "level_0_census",
        "comments": "Use for educational attainment calibration. Align age base before combining with all-age tables."
    },
    {
        "file_name": "household_size_region.csv",
        "grain": "region x household_size",
        "variables": ["region", "household_size", "household_count", "average_household_size"],
        "required_for_level": "level_0_census",
        "comments": "Use for household role, family burden, and purchase-decision context."
    },
    {
        "file_name": "employment_status_age_sex.csv",
        "grain": "age_band x sex x employment_status",
        "variables": ["age_band", "sex", "employment_status", "count_or_share"],
        "required_for_level": "level_0_census",
        "comments": "Required for budget pressure, time scarcity, and category need."
    },
    {
        "file_name": "income_band_region.csv",
        "grain": "region x income_band",
        "variables": ["region", "income_band", "income_decile", "household_or_person_count", "year"],
        "required_for_level": "level_1_survey",
        "comments": "If unavailable, use a clearly marked prior and apply uncertainty penalty."
    },
    {
        "file_name": "settlement_type_region.csv",
        "grain": "region x settlement_type",
        "variables": ["region", "settlement_type", "urban_rural", "population_count"],
        "required_for_level": "level_0_census",
        "comments": "Controls channel access, digital behavior, logistics, and household context."
    },
    {
        "file_name": "ict_usage_individuals.csv",
        "grain": "country x year x ict_indicator",
        "variables": ["year", "indicator", "value", "population_base", "internet_frequency", "digital_access_level"],
        "required_for_level": "level_1_survey",
        "comments": "Use as a conditional prior for soft traits unless aligned to census bands."
    },
]

DEFAULT_OPTIONAL_TABLES = [
    {
        "file_name": "marital_status_age_sex.csv",
        "grain": "age_band x sex x marital_status",
        "variables": ["age_band", "sex", "marital_status", "population_count"],
        "required_for_level": "level_0_census",
        "comments": "Improves family decision-role modeling."
    },
    {
        "file_name": "consumer_expenditure_category.csv",
        "grain": "household x expenditure_category",
        "variables": ["year", "expenditure_category", "value", "household_type"],
        "required_for_level": "level_1_survey",
        "comments": "Useful for category-level affordability and price-sensitivity priors."
    },
    {
        "file_name": "ecommerce_usage_age_education.csv",
        "grain": "age_band x education_level x ecommerce_indicator",
        "variables": ["age_band", "education_level", "indicator", "value", "population_base"],
        "required_for_level": "level_1_survey",
        "comments": "Useful for channel and digital-purchase priors."
    },
]


def normalise_iso2(value: str) -> str:
    value = value.strip().upper()
    if len(value) != 2:
        raise ValueError("iso2 must be a two-letter code")
    return value


def normalise_iso3(value: str) -> str:
    value = value.strip().upper()
    if len(value) != 3:
        raise ValueError("iso3 must be a three-letter code")
    return value


def table_entry(
    template: dict[str, Any],
    *,
    source_name: str,
    source_url: str,
    population_year: int | str,
    expected: bool,
) -> dict[str, Any]:
    status = "needs_source_table" if expected else "unavailable"
    official = "official_expected" if expected else "unavailable"
    return {
        **template,
        "source_name": source_name,
        "source_url": source_url or "TODO_OFFICIAL_SOURCE_URL",
        "source_year": population_year,
        "coverage_note": "TODO: add exact coverage note from official source metadata.",
        "official_or_imputed": official,
        "missing_status": status,
    }


def constraint(
    country_code: str,
    name: str,
    variable_set: list[str],
    *,
    source: str,
    year: int | str,
    values_available: bool = False,
    ctype: str = "unavailable",
    geography_level: str = "unknown",
    population_base: str = "to be determined",
    confidence: str = "medium",
    use_in_ipf: bool = False,
    warning: str | None = None,
) -> dict[str, Any]:
    return {
        "constraint_id": f"{country_code}_{name}",
        "type": ctype,
        "variable_set": variable_set,
        "values_available": values_available,
        "geography_level": geography_level,
        "population_base": population_base,
        "year": year,
        "source": source,
        "confidence": confidence,
        "use_in_ipf": use_in_ipf,
        "warning_if_used": warning,
    }


def build_pack(args: argparse.Namespace) -> dict[str, Any]:
    iso2 = normalise_iso2(args.iso2)
    iso3 = normalise_iso3(args.iso3)
    source_name = args.nso_name or f"{args.country_name} national statistical office"
    source_url = args.nso_url or "TODO_OFFICIAL_SOURCE_URL"
    census_portal = args.census_url or source_url

    anchors: dict[str, Any] = {}
    constraints: list[dict[str, Any]] = []

    total_available = args.total_population is not None
    if total_available:
        anchors["population_total"] = {
            "value": args.total_population,
            "year": args.population_year,
            "confidence": "high" if args.total_population_source else "medium",
        }

    if args.male_count is not None and args.female_count is not None:
        total = args.male_count + args.female_count
        anchors["sex_distribution"] = {
            "male_count": args.male_count,
            "male_share": args.male_count / total if total else None,
            "female_count": args.female_count,
            "female_share": args.female_count / total if total else None,
            "confidence": "high",
        }
        sex_available = True
    else:
        sex_available = False

    constraints.append(
        constraint(
            iso2,
            "TOTAL_POP",
            ["country"],
            source=args.total_population_source or source_name,
            year=args.population_year,
            values_available=total_available,
            ctype="official_margin" if total_available else "unavailable",
            geography_level="country",
            population_base="all residents",
            confidence="high" if total_available else "medium",
            use_in_ipf=total_available,
            warning=None if total_available else "Attach official total population before reconciliation.",
        )
    )
    constraints.append(
        constraint(
            iso2,
            "SEX",
            ["sex"],
            source=source_name,
            year=args.population_year,
            values_available=sex_available,
            ctype="official_margin" if sex_available else "unavailable",
            geography_level="country",
            population_base="all residents",
            confidence="high" if sex_available else "medium",
            use_in_ipf=sex_available,
            warning=None if sex_available else "Attach official sex distribution before claiming sex-calibrated panel.",
        )
    )

    required_constraints = [
        ("REGION_AGE_SEX", ["region", "age_band", "sex"], "region", "all residents"),
        ("EDUCATION", ["education_level"], "country or region", "adult or 15+ population"),
        ("HOUSEHOLD_SIZE", ["household_size"], "country or region", "private households"),
        ("EMPLOYMENT_AGE_SEX", ["employment_status", "age_band", "sex"], "country or region", "working-age or adult population"),
        ("INCOME_REGION", ["income_band", "income_decile", "region"], "country or region", "household or person"),
        ("SETTLEMENT_TYPE_REGION", ["region", "settlement_type", "urban_rural"], "region or municipality", "all residents"),
        ("ICT_USAGE", ["internet_frequency", "digital_access_level"], "country", "individuals in survey scope"),
    ]
    for name, variables, geography, base in required_constraints:
        constraints.append(
            constraint(
                iso2,
                name,
                variables,
                source=source_name,
                year=args.population_year,
                geography_level=geography,
                population_base=base,
                warning=f"Attach official or survey-derived {name.lower()} table before using this as a calibrated constraint.",
            )
        )

    source_priority = [
        {
            "rank": 1,
            "source_type": "national_statistical_office",
            "source_name": source_name,
            "source_url": source_url,
            "use_for": ["population", "sex", "education", "households", "labour", "income", "ICT"],
        },
        {
            "rank": 2,
            "source_type": "official_census_portal",
            "source_name": f"{args.country_name} official census portal",
            "source_url": census_portal,
            "use_for": ["census tables", "regional tables", "municipality tables", "households"],
        },
        {
            "rank": 3,
            "source_type": "international_statistical_sources",
            "source_name": "World Bank / Eurostat / OECD / UN / ILO / ITU",
            "source_url": "https://data.worldbank.org/",
            "use_for": ["fallback indicators", "cross-country harmonisation"],
        },
        {
            "rank": 4,
            "source_type": "category_or_product_sources",
            "source_name": "retail/product pages and market reports",
            "source_url": "TODO_CATEGORY_CONTEXT_SOURCE_URL",
            "use_for": ["product facts only", "category context only", "never hard population weights"],
        },
    ]

    required_tables = [
        table_entry(t, source_name=source_name, source_url=source_url, population_year=args.population_year, expected=True)
        for t in DEFAULT_REQUIRED_TABLES
    ]
    optional_tables = [
        table_entry(t, source_name=source_name, source_url=source_url, population_year=args.population_year, expected=True)
        for t in DEFAULT_OPTIONAL_TABLES
    ]

    status = "anchor_ready" if (total_available or sex_available) else "source_mapped"

    return {
        "country_identity": {
            "country_name": args.country_name,
            "iso2": iso2,
            "iso3": iso3,
            "pack_version": args.pack_version,
            "population_year": args.population_year,
            "preferred_language": args.preferred_language,
            "local_languages": args.local_language,
            "currency": args.currency,
            "build_date": args.build_date or date.today().isoformat(),
        },
        "coverage_scope": {
            "target_population": args.target_population,
            "base_population_reference": {
                "value": args.total_population,
                "year": args.population_year,
                "source_name": args.total_population_source or source_name,
                "source_url": source_url,
                "coverage_note": args.coverage_note or "TODO: add exact national statistical coverage note.",
            },
            "use_case": args.intended_use_case,
        },
        "source_priority": source_priority,
        "required_tables": required_tables,
        "optional_tables": optional_tables,
        "extracted_anchor_values": anchors,
        "statistical_constraints": constraints,
        "imputation_policy": {
            "allowed_fields": [
                {
                    "field": "price_sensitivity",
                    "imputation_allowed": True,
                    "recommended_method": "conditional model using income, household_size, employment, region, and category price",
                    "uncertainty_penalty": "high",
                    "allowed_reporting_language": "model-inferred price sensitivity",
                },
                {
                    "field": "media_usage",
                    "imputation_allowed": True,
                    "recommended_method": "conditional model using ICT survey, age, education, and settlement type",
                    "uncertainty_penalty": "medium",
                    "allowed_reporting_language": "survey-conditioned media prior",
                },
                {
                    "field": "narrative_life_story",
                    "imputation_allowed": True,
                    "recommended_method": "narrative-only generation constrained by hard variables",
                    "uncertainty_penalty": "high",
                    "allowed_reporting_language": "illustrative narrative detail only",
                },
            ],
            "forbidden_behavior": [
                "Do not let LLM-generated stories modify population_weight.",
                "Do not use narrative-only fields as statistical constraints.",
                "Do not report high-order segment lift if only low-order margins are fitted.",
            ],
        },
        "quality_checks": {
            "required_before_panel_generation": [
                "total_population_reconciliation",
                "sex_distribution_fit",
                "region_distribution_fit",
                "age_sex_fit",
                "education_fit",
                "household_size_fit",
                "urban_rural_fit_if_available",
                "source_metadata_completeness",
                "missing_table_report",
            ],
            "required_before_pricing_report": [
                "choice_record_contract_validation",
                "weighted_bootstrap_intervals",
                "segment_effective_sample_size_check",
                "high_imputation_field_report",
                "calibration_level_disclosure",
            ],
        },
        "build_status": {
            "status": status,
            "current_calibration_level": "level_0_partial" if status == "anchor_ready" else "none",
            "can_generate_demo_panel": True,
            "can_claim_census_calibrated_panel": False,
            "reason_census_claim_not_ready": [
                "required official margins are not yet attached",
                "region x age x sex table not yet validated",
                "marginal fit report not yet computed",
            ],
        },
        "next_actions": [
            "Replace TODO source URLs with official table URLs.",
            "Attach region x age x sex table.",
            "Attach education, household, employment, income, settlement, and ICT tables.",
            "Run validate_country_pack.py and fix structural warnings.",
            "Run IPF/raking only after required margins are attached.",
            "Generate weighted skeletons only as a demo until IPF readiness is reached.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-name", required=True)
    parser.add_argument("--iso2", required=True)
    parser.add_argument("--iso3", required=True)
    parser.add_argument("--population-year", required=True)
    parser.add_argument("--target-population", default="adult_purchase_decision_makers")
    parser.add_argument("--intended-use-case", default="pricing_simulation")
    parser.add_argument("--preferred-language", default="en")
    parser.add_argument("--local-language", action="append", default=[])
    parser.add_argument("--currency", default="")
    parser.add_argument("--pack-version", default="0.1.0")
    parser.add_argument("--build-date", default="")
    parser.add_argument("--nso-name", default="")
    parser.add_argument("--nso-url", default="")
    parser.add_argument("--census-url", default="")
    parser.add_argument("--coverage-note", default="")
    parser.add_argument("--total-population", type=int)
    parser.add_argument("--total-population-source", default="")
    parser.add_argument("--male-count", type=int)
    parser.add_argument("--female-count", type=int)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack = build_pack(args)
    text = json.dumps(pack, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
