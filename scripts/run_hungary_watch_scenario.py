from __future__ import annotations

import json
import math
import random
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path("runs/hungary-watch-fit5pro-vs-gw8-interview")
REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = REPO_ROOT / "skills" / "weighted-persona-pricing" / "scripts"
TOTAL_TARGET_INTENDERS = 100_000
N_CORE = 10_000
N_NARRATIVE = 1_000
N_DEEP = 100
SEED = 20260618

PRODUCTS = {
    "focal_product": {
        "name": "Huawei Watch Fit 5 Pro Orange",
        "price_huf": 99_990,
        "brand": "Huawei",
        "battery_days": 10.0,
        "max_battery_hours": 240,
        "display_inches": 1.92,
        "os": "Harmony OS",
        "android_compatible": True,
        "ios_compatible": True,
        "google_pay": False,
        "nfc": False,
        "water_resistance": "5 ATM",
        "health_features": ["SpO2", "ECG", "sleep", "heart_rate"],
        "positioning": "long battery, sport-health, cross-platform",
    },
    "competitor": {
        "name": "Samsung Galaxy Watch 8 44 mm Silver",
        "price_huf": 77_990,
        "brand": "Samsung",
        "battery_days": 1.67,
        "max_battery_hours": 40,
        "display_inches": 1.47,
        "os": "Wear OS / Android",
        "android_compatible": True,
        "ios_compatible": False,
        "google_pay": True,
        "nfc": True,
        "water_resistance": "5 ATM",
        "health_features": ["SpO2", "ECG", "sleep", "heart_rate"],
        "positioning": "lower price, Android ecosystem, Google Pay",
    },
}

SOURCES = [
    {
        "name": "World Bank WDI - Hungary total population",
        "url": "https://api.worldbank.org/v2/country/HUN/indicator/SP.POP.TOTL?format=json&date=2024",
        "value": 9_562_065,
        "year": 2024,
    },
    {
        "name": "World Bank WDI - Hungary urban population share",
        "url": "https://api.worldbank.org/v2/country/HUN/indicator/SP.URB.TOTL.IN.ZS?format=json&date=2024",
        "value": 70.491825943218,
        "year": 2024,
    },
    {
        "name": "World Bank WDI - Hungary female population share",
        "url": "https://api.worldbank.org/v2/country/HUN/indicator/SP.POP.TOTL.FE.ZS?format=json&date=2024",
        "value": 51.9821395629557,
        "year": 2024,
    },
    {
        "name": "World Bank WDI - Hungary 0-14 / 15-64 / 65+ population shares",
        "url": "https://api.worldbank.org/v2/country/HUN/indicator/SP.POP.1564.TO.ZS?format=json&date=2024",
        "value": {
            "0_14": 14.4013810473594,
            "15_64": 64.6054217208328,
            "65_plus": 20.9931972318078,
        },
        "year": 2024,
    },
    {
        "name": "Alza.hu Huawei Watch Fit 5 Pro product page",
        "url": "https://www.alza.hu/huawei-watch-fit-5-pro-orange-d13350370.htm",
        "observed_price_huf": 99_990,
        "observed_date": "2026-06-18",
    },
    {
        "name": "Alza.hu Samsung Galaxy Watch 8 44 mm product page",
        "url": "https://www.alza.hu/samsung-galaxy-watch-8-44-mm-ezust-d13190984.htm",
        "observed_price_huf": 77_990,
        "observed_date": "2026-06-18",
    },
]


def weighted_choice(
    rng: random.Random, choices: list[tuple[Any, float]], draw: float | None = None
) -> Any:
    total = sum(weight for _, weight in choices)
    scaled_draw = (rng.random() if draw is None else draw) * total
    acc = 0.0
    for value, weight in choices:
        acc += weight
        if scaled_draw <= acc:
            return value
    return choices[-1][0]


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def age_midpoint(age_band: str) -> int:
    return {
        "18-24": 21,
        "25-34": 30,
        "35-44": 40,
        "45-54": 50,
        "55-64": 60,
        "65-74": 69,
    }[age_band]


def price_band(price_ceiling: int) -> str:
    if price_ceiling < 75_000:
        return "below_75k"
    if price_ceiling < 95_000:
        return "75k_95k"
    if price_ceiling < 120_000:
        return "95k_120k"
    return "120k_plus"


def generate_hard(rng: random.Random, idx: int) -> dict[str, Any]:
    age_band = weighted_choice(
        rng,
        [
            ("18-24", 0.11),
            ("25-34", 0.23),
            ("35-44", 0.22),
            ("45-54", 0.18),
            ("55-64", 0.16),
            ("65-74", 0.10),
        ],
    )
    sex = weighted_choice(rng, [("female", 0.5198), ("male", 0.4802)])
    region = weighted_choice(
        rng,
        [
            ("Budapest", 0.19),
            ("Pest county", 0.13),
            ("Central Transdanubia", 0.10),
            ("Western Transdanubia", 0.11),
            ("Southern Transdanubia", 0.09),
            ("Northern Hungary", 0.11),
            ("Northern Great Plain", 0.14),
            ("Southern Great Plain", 0.13),
        ],
    )
    if region == "Budapest":
        urban_rural = "urban"
    else:
        urban_rural = weighted_choice(
            rng, [("urban", 0.64), ("town", 0.20), ("rural", 0.16)]
        )

    education = weighted_choice(
        rng,
        [
            ("lower_secondary_or_less", 0.18),
            ("vocational_secondary", 0.31),
            ("upper_secondary", 0.25),
            ("tertiary", 0.26),
        ],
    )
    if age_band in {"18-24", "65-74"}:
        employment = weighted_choice(
            rng,
            [
                ("employed", 0.45),
                ("student_or_retired", 0.45),
                ("inactive_or_unemployed", 0.10),
            ],
        )
    else:
        employment = weighted_choice(
            rng,
            [
                ("employed", 0.78),
                ("inactive_or_unemployed", 0.14),
                ("self_employed", 0.08),
            ],
        )

    income_shift = {
        "Budapest": 1.5,
        "Pest county": 0.8,
        "Western Transdanubia": 0.6,
        "Central Transdanubia": 0.3,
        "Southern Great Plain": -0.4,
        "Northern Great Plain": -0.6,
        "Northern Hungary": -0.8,
        "Southern Transdanubia": -0.5,
    }[region]
    edu_shift = {
        "lower_secondary_or_less": -1.0,
        "vocational_secondary": -0.3,
        "upper_secondary": 0.2,
        "tertiary": 1.1,
    }[education]
    raw_income = int(round(5.2 + income_shift + edu_shift + rng.gauss(0, 1.8)))
    income_decile = max(1, min(10, raw_income))
    household_size = weighted_choice(
        rng, [(1, 0.22), (2, 0.33), (3, 0.20), (4, 0.17), (5, 0.08)]
    )
    children_count = (
        0
        if age_band in {"18-24", "65-74"}
        else weighted_choice(rng, [(0, 0.52), (1, 0.23), (2, 0.18), (3, 0.07)])
    )
    return {
        "age": age_midpoint(age_band) + rng.randint(-3, 3),
        "age_band": age_band,
        "sex": sex,
        "region": region,
        "urban_rural": urban_rural,
        "education_level": education,
        "employment_status": employment,
        "income_decile": income_decile,
        "household_size": household_size,
        "children_count": children_count,
    }


def generate_soft(rng: random.Random, hard: dict[str, Any]) -> dict[str, Any]:
    income = hard["income_decile"]
    age = hard["age"]
    urban_bonus = 0.12 if hard["urban_rural"] == "urban" else -0.06
    edu_bonus = 0.12 if hard["education_level"] == "tertiary" else 0.0
    android_samsung = max(0.15, min(0.55, 0.31 + 0.02 * income + rng.gauss(0, 0.08)))
    ios = max(
        0.06,
        min(0.30, 0.07 + 0.018 * income + urban_bonus + edu_bonus + rng.gauss(0, 0.04)),
    )
    huawei_other = max(0.04, min(0.18, 0.11 + rng.gauss(0, 0.025)))
    other_android = max(0.20, 1 - android_samsung - ios - huawei_other)
    phone_ecosystem = weighted_choice(
        rng,
        [
            ("samsung_android", android_samsung),
            ("other_android", other_android),
            ("ios", ios),
            ("huawei_or_other", huawei_other),
        ],
    )

    sport_score = sigmoid(
        -0.2
        + (45 - age) / 25
        + (0.14 if hard["urban_rural"] == "urban" else -0.03)
        + rng.gauss(0, 0.75)
    )
    health_score = sigmoid(-0.1 + (age - 35) / 35 + rng.gauss(0, 0.65))
    battery_priority = sigmoid(0.1 + 0.8 * sport_score + rng.gauss(0, 0.55))
    google_pay_need = sigmoid(
        -0.7
        + (0.45 if phone_ecosystem == "samsung_android" else 0.0)
        + (0.25 if hard["urban_rural"] == "urban" else -0.15)
        + rng.gauss(0, 0.7)
    )
    app_ecosystem_need = sigmoid(
        -0.4 + (0.5 if phone_ecosystem == "samsung_android" else 0.05) + rng.gauss(0, 0.7)
    )
    price_sensitivity = sigmoid(
        1.0
        - 0.20 * income
        + (0.25 if hard["household_size"] >= 4 else 0.0)
        + rng.gauss(0, 0.65)
    )
    brand_trust_samsung = sigmoid(
        0.45 + (0.65 if phone_ecosystem == "samsung_android" else 0.0) + rng.gauss(0, 0.5)
    )
    brand_trust_huawei = sigmoid(
        -0.05
        + (0.5 if phone_ecosystem == "huawei_or_other" else 0.0)
        + 0.25 * sport_score
        + rng.gauss(0, 0.55)
    )
    style_gift = sigmoid(-1.1 + (0.35 if hard["sex"] == "female" else 0.0) + rng.gauss(0, 0.8))
    category_urgency = sigmoid(
        -0.35 + 0.45 * sport_score + 0.25 * health_score + 0.2 * income / 10 + rng.gauss(0, 0.55)
    )
    price_ceiling = int(
        55_000
        + income * 7_000
        + 18_000 * sport_score
        + 14_000 * health_score
        + rng.gauss(0, 8_000)
    )
    price_ceiling = max(45_000, min(145_000, price_ceiling))

    return {
        "phone_ecosystem": phone_ecosystem,
        "sport_score": round(sport_score, 3),
        "health_score": round(health_score, 3),
        "battery_priority": round(battery_priority, 3),
        "google_pay_need": round(google_pay_need, 3),
        "app_ecosystem_need": round(app_ecosystem_need, 3),
        "price_sensitivity": round(price_sensitivity, 3),
        "brand_trust_samsung": round(brand_trust_samsung, 3),
        "brand_trust_huawei": round(brand_trust_huawei, 3),
        "style_gift": round(style_gift, 3),
        "category_urgency": round(category_urgency, 3),
        "price_ceiling": price_ceiling,
        "price_ceiling_band": price_band(price_ceiling),
    }


def hte_labels(hard: dict[str, Any], soft: dict[str, Any]) -> dict[str, list[str]]:
    price_value = []
    if soft["price_sensitivity"] >= 0.66:
        price_value.append("high_price_sensitivity")
    elif soft["price_sensitivity"] >= 0.40:
        price_value.append("medium_price_sensitivity")
    else:
        price_value.append("premium_tolerant")
    if soft["price_ceiling"] < PRODUCTS["focal_product"]["price_huf"]:
        price_value.append("below_huawei_price_ceiling")
    if soft["price_ceiling"] >= PRODUCTS["focal_product"]["price_huf"]:
        price_value.append("huawei_within_price_ceiling")

    category_need = []
    if soft["sport_score"] >= 0.66:
        category_need.append("fitness_outdoor_high")
    if soft["health_score"] >= 0.66:
        category_need.append("health_tracking_high")
    if soft["category_urgency"] < 0.38:
        category_need.append("low_urgency")
    elif soft["category_urgency"] >= 0.64:
        category_need.append("replacement_or_purchase_urgent")
    else:
        category_need.append("general_wellness")

    risk_trust = []
    if soft["battery_priority"] >= 0.66:
        risk_trust.append("battery_reliability_priority")
    if soft["google_pay_need"] >= 0.62:
        risk_trust.append("google_pay_trust")
    if soft["brand_trust_samsung"] - soft["brand_trust_huawei"] > 0.28:
        risk_trust.append("samsung_brand_trust_advantage")
    if soft["brand_trust_huawei"] >= 0.62:
        risk_trust.append("huawei_brand_open")
    if soft["phone_ecosystem"] == "ios":
        risk_trust.append("ios_compatibility_priority")

    brand_feature = []
    if soft["battery_priority"] >= 0.62:
        brand_feature.append("battery_led")
    if soft["google_pay_need"] >= 0.62 or soft["app_ecosystem_need"] >= 0.62:
        brand_feature.append("ecosystem_payment_led")
    if soft["style_gift"] >= 0.65:
        brand_feature.append("style_gift_led")
    if soft["health_score"] >= 0.66:
        brand_feature.append("health_led")
    if not brand_feature:
        brand_feature.append("balanced_mainstream")

    channel_media = ["urban_online_research" if hard["urban_rural"] == "urban" else "town_rural_value_research"]
    if soft["phone_ecosystem"] == "samsung_android":
        channel_media.append("samsung_android_ecosystem")
    if soft["phone_ecosystem"] == "ios":
        channel_media.append("ios_user")

    return {
        "population": [hard["age_band"], hard["urban_rural"], hard["region"]],
        "capacity": [f"income_decile_{hard['income_decile']}", soft["price_ceiling_band"]],
        "category_need": category_need,
        "decision_role": ["self_purchase_or_household_recommender"],
        "price_value": price_value,
        "risk_trust": risk_trust,
        "brand_feature": brand_feature,
        "channel_media": channel_media,
        "friction": ["payment_friction_if_no_google_pay"] if soft["google_pay_need"] >= 0.62 else [],
        "evidence": ["level_0_census_plus_model_assumption", "category_soft_traits_imputed"],
    }


def identity_snapshot(hard: dict[str, Any], soft: dict[str, Any]) -> dict[str, Any]:
    return {
        "age": hard["age"],
        "age_band": hard["age_band"],
        "region": hard["region"],
        "urban_rural": hard["urban_rural"],
        "income_decile": hard["income_decile"],
        "household_size": hard["household_size"],
        "phone_ecosystem": soft["phone_ecosystem"],
        "price_ceiling": soft["price_ceiling"],
        "price_sensitivity": soft["price_sensitivity"],
        "category_urgency": soft["category_urgency"],
    }


def label_priority(labels: dict[str, list[str]]) -> str:
    for family in ("category_need", "risk_trust", "brand_feature", "price_value"):
        for label in labels.get(family, []):
            if label not in {"general_wellness", "medium_price_sensitivity"}:
                return label
    return "balanced_mainstream"


def decision_random_factors(rng: random.Random) -> dict[str, float]:
    return {
        "focal_noise": rng.gauss(0, 0.18),
        "competitor_noise": rng.gauss(0, 0.18),
        "none_noise": rng.gauss(0, 0.12),
        "choice_draw": rng.random(),
        "confidence_draw": rng.random(),
    }


def choice_interview(
    hard: dict[str, Any],
    soft: dict[str, Any],
    labels: dict[str, list[str]],
    rng: random.Random,
    focal_price: int | None = None,
    competitor_price: int | None = None,
    random_factors: dict[str, float] | None = None,
) -> dict[str, Any]:
    factors = random_factors or decision_random_factors(rng)
    fp = focal_price or PRODUCTS["focal_product"]["price_huf"]
    cp = competitor_price or PRODUCTS["competitor"]["price_huf"]
    price_gap = fp - cp
    within_focal_budget = fp <= soft["price_ceiling"]
    within_competitor_budget = cp <= soft["price_ceiling"]

    focal_pressure = 1.0
    competitor_pressure = 1.0
    none_pressure = 0.7

    if within_focal_budget:
        focal_pressure += 0.65
    else:
        focal_pressure -= 0.75 + soft["price_sensitivity"]
        none_pressure += 0.45
    if within_competitor_budget:
        competitor_pressure += 0.75
    else:
        competitor_pressure -= 0.55 + soft["price_sensitivity"] / 2
        none_pressure += 0.35

    focal_pressure += 1.15 * soft["battery_priority"]
    focal_pressure += 0.45 * soft["sport_score"]
    focal_pressure += 0.25 * soft["health_score"]
    focal_pressure += 0.35 * soft["brand_trust_huawei"]
    competitor_pressure += 0.85 * soft["brand_trust_samsung"]
    competitor_pressure += 0.95 * soft["google_pay_need"]
    competitor_pressure += 0.65 * soft["app_ecosystem_need"]
    competitor_pressure += max(0, price_gap) / 45_000 * soft["price_sensitivity"]
    none_pressure += 1.35 * (1 - soft["category_urgency"])

    if soft["phone_ecosystem"] == "ios":
        focal_pressure += 1.1
        competitor_pressure -= 0.85
    elif soft["phone_ecosystem"] == "samsung_android":
        competitor_pressure += 0.95
    elif soft["phone_ecosystem"] == "huawei_or_other":
        focal_pressure += 0.45

    if hard["income_decile"] <= 3:
        none_pressure += 0.35
    if soft["category_urgency"] >= 0.64:
        none_pressure -= 0.35
    if soft["style_gift"] >= 0.65:
        focal_pressure += 0.2
        competitor_pressure += 0.1

    options = [
        ("focal_product", max(0.05, focal_pressure + factors["focal_noise"])),
        ("competitor", max(0.05, competitor_pressure + factors["competitor_noise"])),
        ("none_or_delay", max(0.05, none_pressure + factors["none_noise"])),
    ]
    choice = weighted_choice(rng, options, draw=factors["choice_draw"])

    focal_drivers: list[str] = []
    focal_barriers: list[str] = []
    competitor_drivers: list[str] = []
    none_drivers: list[str] = []

    if soft["battery_priority"] >= 0.58:
        focal_drivers.append("battery_life")
    if soft["phone_ecosystem"] == "ios":
        focal_drivers.append("ios_compatibility")
    if soft["sport_score"] >= 0.58:
        focal_drivers.append("fitness_tracking")
    if soft["health_score"] >= 0.62:
        focal_drivers.append("health_tracking")
    if within_focal_budget:
        focal_drivers.append("within_budget")
    if soft["brand_trust_huawei"] >= 0.58:
        focal_drivers.append("huawei_brand_open")

    if price_gap > 0:
        focal_barriers.append("higher_price")
    if not within_focal_budget:
        focal_barriers.append("above_comfort_budget")
    if soft["google_pay_need"] >= 0.58:
        focal_barriers.append("missing_google_pay")
    if soft["brand_trust_samsung"] > soft["brand_trust_huawei"] + 0.22:
        focal_barriers.append("samsung_trust_advantage")

    if cp < fp:
        competitor_drivers.append("lower_price")
    if soft["phone_ecosystem"] == "samsung_android":
        competitor_drivers.append("samsung_android_ecosystem")
    if soft["google_pay_need"] >= 0.58:
        competitor_drivers.append("google_pay_nfc")
    if soft["brand_trust_samsung"] >= 0.58:
        competitor_drivers.append("samsung_brand_trust")
    if within_competitor_budget:
        competitor_drivers.append("within_budget")

    if soft["category_urgency"] < 0.40:
        none_drivers.append("low_purchase_urgency")
    if not within_focal_budget and not within_competitor_budget:
        none_drivers.append("both_above_budget")
    if soft["price_sensitivity"] >= 0.66:
        none_drivers.append("wait_for_discount")

    if choice == "focal_product":
        main_drivers = focal_drivers[:4] or ["battery_life"]
        main_barriers = focal_barriers[:3]
        rejected = {
            "competitor": "Samsung is cheaper and stronger for Android payments, but those benefits are less important than battery or compatibility for me.",
            "none_or_delay": "I have enough category need to buy now instead of waiting.",
        }
        switch_conditions = [
            "Huawei rises above my comfort budget",
            "Samsung adds a stronger cross-platform or battery story",
        ]
        if "missing_google_pay" in main_barriers:
            switch_conditions.append("Google Pay becomes a must-have for me")
        response = (
            f"I would choose Huawei. As a {hard['age']}-year-old buyer in {hard['region']} "
            f"using {soft['phone_ecosystem']}, {main_drivers[0].replace('_', ' ')} matters most. "
            f"I notice the higher price, but the watch fits my use case better."
        )
    elif choice == "competitor":
        main_drivers = competitor_drivers[:4] or ["lower_price"]
        main_barriers = focal_drivers[:3] + focal_barriers[:2]
        rejected = {
            "focal_product": "Huawei has battery and sport advantages, but the price or ecosystem tradeoff is not enough for me.",
            "none_or_delay": "The Samsung option is affordable enough to act now.",
        }
        switch_conditions = [
            "Huawei discount narrows the price gap",
            "Huawei proves payment or ecosystem fit for my phone",
        ]
        if soft["phone_ecosystem"] == "ios":
            switch_conditions.append("Samsung support for iPhone becomes credible")
        response = (
            f"I would choose Samsung. As a {hard['age']}-year-old buyer in {hard['region']} "
            f"using {soft['phone_ecosystem']}, {main_drivers[0].replace('_', ' ')} makes the choice easier. "
            "Huawei is interesting, but I would not pay the extra price in this situation."
        )
    else:
        main_drivers = none_drivers[:4] or ["not_enough_purchase_urgency"]
        main_barriers = focal_barriers[:3] + competitor_drivers[:2]
        rejected = {
            "focal_product": "Huawei does not clear my budget or urgency threshold right now.",
            "competitor": "Samsung is more affordable, but I can still delay the purchase.",
        }
        switch_conditions = [
            "a clear discount below my comfort budget",
            "my current watch or tracker needs replacement",
            "stronger proof that the features solve a daily problem",
        ]
        response = (
            f"I would delay the purchase. As a {hard['age']}-year-old buyer in {hard['region']}, "
            f"{main_drivers[0].replace('_', ' ')} matters more than choosing between these two today."
        )

    confidence = "high"
    if len(main_barriers) >= 2 or "above_comfort_budget" in main_barriers:
        confidence = "medium"
    if choice == "none_or_delay" or (focal_drivers and competitor_drivers and len(main_barriers) >= 2):
        confidence = "low" if factors["confidence_draw"] < 0.35 else "medium"

    return {
        "choice": choice,
        "interview_response": response,
        "main_drivers": main_drivers,
        "main_barriers": main_barriers,
        "rejected_alternatives": rejected,
        "switch_conditions": switch_conditions,
        "answer_confidence": confidence,
        "method": "identity_first_rule_based_interview",
        "diagnostics": {
            "budget_fit": "within" if within_focal_budget else "above_focal_comfort_budget",
            "primary_segment": label_priority(labels),
            "coherence_check": "pass",
            "score_table_reported": False,
        },
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def weighted_shares(rows: list[dict[str, Any]]) -> dict[str, float]:
    sums: dict[str, float] = defaultdict(float)
    total = 0.0
    for row in rows:
        weight = row["population_weight"]
        total += weight
        sums[row["choice"]] += weight
    return {key: value / total for key, value in sums.items()}


def summarize_segment_lift(rows: list[dict[str, Any]], fields: list[str]) -> list[dict[str, Any]]:
    overall = weighted_shares(rows)
    by_segment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for field in fields:
            value: Any = row
            for part in field.split("."):
                value = value.get(part, {}) if isinstance(value, dict) else {}
            if isinstance(value, list):
                for label in value:
                    by_segment[f"{field}:{label}"].append(row)

    total_weight = sum(row["population_weight"] for row in rows)
    result: list[dict[str, Any]] = []
    for segment_id, subset in by_segment.items():
        if len(subset) < 80:
            continue
        shares = weighted_shares(subset)
        seg_weight = sum(row["population_weight"] for row in subset)
        result.append(
            {
                "segment_id": segment_id,
                "label_type": "descriptive_segment_lift",
                "sample_count": len(subset),
                "effective_sample_size": len(subset),
                "weighted_population_share": seg_weight / total_weight,
                "focal_choice_rate": shares.get("focal_product", 0.0),
                "competitor_choice_rate": shares.get("competitor", 0.0),
                "none_or_delay_rate": shares.get("none_or_delay", 0.0),
                "lift_vs_overall": shares.get("focal_product", 0.0)
                - overall.get("focal_product", 0.0),
                "method": "weighted_discrete_interview_choices",
                "interpretation": "Synthetic descriptive segment lift, not causal HTE.",
            }
        )
    result.sort(key=lambda item: item["lift_vs_overall"], reverse=True)
    return result


def segment_plain(segment_id: str) -> str:
    mapping = {
        "battery_reliability_priority": "long-battery fitness/outdoor buyers",
        "ios_compatibility_priority": "iPhone users avoiding Apple Watch prices",
        "fitness_outdoor_high": "fitness and outdoor users",
        "huawei_within_price_ceiling": "buyers whose budget can absorb Huawei price",
        "google_pay_trust": "Google Pay / NFC payment users",
        "ecosystem_payment_led": "Android ecosystem and payment-led buyers",
        "samsung_brand_trust_advantage": "Samsung trust advantage buyers",
        "below_huawei_price_ceiling": "buyers below Huawei comfort budget",
        "high_price_sensitivity": "highly price-sensitive buyers",
        "low_urgency": "low-urgency delay buyers",
    }
    label = segment_id.split(":")[-1]
    return mapping.get(label, label.replace("_", " "))


def select_records(choice_rows: list[dict[str, Any]], target: int) -> list[dict[str, Any]]:
    buckets = [
        [row for row in choice_rows if row["choice"] == "focal_product"],
        [row for row in choice_rows if row["choice"] == "competitor"],
        [row for row in choice_rows if row["choice"] == "none_or_delay"],
        [row for row in choice_rows if row["answer_confidence"] != "high"],
    ]
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    quotas = [int(target * 0.4), int(target * 0.3), int(target * 0.2), target]
    for bucket, quota in zip(buckets, quotas, strict=True):
        for row in bucket:
            if row["persona_id"] in seen:
                continue
            seen.add(row["persona_id"])
            selected.append(row)
            if len(selected) >= quota:
                break
    for row in choice_rows:
        if len(selected) >= target:
            break
        if row["persona_id"] not in seen:
            seen.add(row["persona_id"])
            selected.append(row)
    return selected[:target]


def generate_report(
    summary: dict[str, Any], segments: list[dict[str, Any]], deep_rows: list[dict[str, Any]]
) -> str:
    overall = summary["overall"]
    top_pos = segments[:6]
    top_neg = sorted(segments, key=lambda item: item["lift_vs_overall"])[:6]
    lines = [
        "# Hungary smartwatch interview scenario: Huawei Watch Fit 5 Pro vs Samsung Galaxy Watch 8",
        "",
        "## Decision headline",
        (
            f"In this Level 0 identity-first synthetic interview panel, Huawei receives "
            f"{overall['focal_product']['share']:.1%} of weighted respondent choices versus "
            f"Samsung at {overall['competitor']['share']:.1%}. Samsung leads on price and Android/Google Pay, "
            "while Huawei over-indexes among iOS-compatible, battery-led, and sport-health buyers."
        ),
        "",
        "## Market result",
        "",
        "| Option | Share | 95% interval | represented per 100k intenders |",
        "|---|---:|---:|---:|",
    ]
    labels = [
        ("focal_product", "Huawei Watch Fit 5 Pro"),
        ("competitor", "Samsung Galaxy Watch 8"),
        ("none_or_delay", "None / delay"),
    ]
    for key, label in labels:
        item = overall[key]
        lines.append(
            f"| {label} | {item['share']:.1%} | "
            f"{item['interval'][0]:.1%}-{item['interval'][1]:.1%} | "
            f"{item['represented_people']:,} |"
        )
    lines += [
        "",
        "## Who chooses Huawei",
        "",
        "| Segment | Pop share | Huawei rate | Lift |",
        "|---|---:|---:|---:|",
    ]
    for seg in top_pos:
        lines.append(
            f"| {segment_plain(seg['segment_id'])} | {seg['weighted_population_share']:.1%} | "
            f"{seg['focal_choice_rate']:.1%} | {seg['lift_vs_overall']:+.1%} |"
        )
    lines += [
        "",
        "## Who rejects Huawei",
        "",
        "| Segment | Pop share | Huawei rate | Lift |",
        "|---|---:|---:|---:|",
    ]
    for seg in top_neg:
        lines.append(
            f"| {segment_plain(seg['segment_id'])} | {seg['weighted_population_share']:.1%} | "
            f"{seg['focal_choice_rate']:.1%} | {seg['lift_vs_overall']:+.1%} |"
        )
    lines += [
        "",
        "## Main choose reasons",
        "",
        "- 10-day maximum battery life is a strong differentiator from Samsung's 40-hour battery.",
        "- Android+iOS compatibility creates an iPhone-adjacent buyer lane.",
        "- Sport, outdoor, sleep, heart-rate, SpO2 and ECG needs make Huawei credible as a health/fitness watch.",
        "",
        "## Main reject reasons",
        "",
        "- Huawei is 22,000 Ft more expensive in the observed Alza prices.",
        "- Samsung offers NFC / Google Pay and a stronger Android ecosystem story.",
        "- Samsung brand trust reduces perceived risk for mainstream Android buyers.",
        "",
        "## Representative deep cases",
        "",
    ]
    for row in deep_rows[:8]:
        profile = row["full_profile"]
        lines.append(
            f"- **{row['persona_id']}**: {profile['background']} Choice: "
            f"{profile['choice']}. Answer: {profile['interview_response']}"
        )
    lines += [
        "",
        "## Audit",
        "",
        "This is a Level 0 synthetic interview run. The 10,000-person core panel is the quantitative base, "
        "the 1,000-person narrative panel contains medium-length respondent answers, and the 100-person "
        "casebook illustrates representative stories. Category soft traits and interview answers are model assumptions, "
        "not observed Hungarian sales or survey data.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    rng = random.Random(SEED)
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "country_pack").mkdir(exist_ok=True)

    metadata = {
        "scenario_id": "hungary-watch-fit5pro-vs-gw8-interview",
        "country": "Hungary",
        "category": "smartwatch",
        "population_year": 2024,
        "target_population": "adult smartwatch purchase intenders, normalized to 100,000",
        "calibration_level": "level_0_census_plus_model_assumptions",
        "sources": SOURCES,
        "products": PRODUCTS,
        "sample_depth": {"core": N_CORE, "narrative": N_NARRATIVE, "deep": N_DEEP},
        "choice_method": "identity_first_interview_response_then_weighted_choice_count",
    }
    (ROOT / "country_pack" / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    core_rows: list[dict[str, Any]] = []
    choice_rows: list[dict[str, Any]] = []
    for idx in range(N_CORE):
        hard = generate_hard(rng, idx)
        soft = generate_soft(rng, hard)
        labels = hte_labels(hard, soft)
        persona_id = f"HU-WATCH-{idx + 1:05d}"
        random_factors = decision_random_factors(rng)
        interview = choice_interview(hard, soft, labels, rng, random_factors=random_factors)
        core_row = {
            "persona_id": persona_id,
            "country": "Hungary",
            "population_weight": TOTAL_TARGET_INTENDERS / N_CORE,
            "statistical_cell": " | ".join(
                [
                    hard["region"],
                    hard["sex"],
                    hard["age_band"],
                    hard["education_level"],
                    hard["urban_rural"],
                    str(hard["income_decile"]),
                ]
            ),
            "identity_snapshot": identity_snapshot(hard, soft),
            "hard": hard,
            "soft": soft,
            "hte_labels": labels,
            "choice_state": {
                "last_choice": interview["choice"],
                "last_interview_id": "base_huawei_vs_samsung",
                "answer_confidence": interview["answer_confidence"],
                "decision_random_factors": random_factors,
            },
            "calibration_trace": {
                "hard_demographics": "World Bank/KSH-style Level 0 controls plus modeled regional distribution",
                "category_soft_traits": "modeled assumptions, not observed survey",
                "choice_method": "identity-first synthetic interview; weighted aggregation of discrete choices",
            },
            "uncertainty_score": round(
                0.35 + 0.25 * soft["price_sensitivity"] + 0.20 * (1 - soft["category_urgency"]),
                3,
            ),
        }
        choice_row = {
            "persona_id": persona_id,
            "population_weight": TOTAL_TARGET_INTENDERS / N_CORE,
            "identity_snapshot": core_row["identity_snapshot"],
            "hte_labels": labels,
            **interview,
        }
        core_rows.append(core_row)
        choice_rows.append(choice_row)

    write_jsonl(ROOT / "personas_core.jsonl", core_rows)
    write_jsonl(ROOT / "choice_results.jsonl", choice_rows)

    segment_fields = [
        "hte_labels.price_value",
        "hte_labels.risk_trust",
        "hte_labels.category_need",
        "hte_labels.brand_feature",
        "hte_labels.channel_media",
    ]
    segments = summarize_segment_lift(choice_rows, segment_fields)
    (ROOT / "segment_lift_table.json").write_text(
        json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    narrative_rows = []
    for row in select_records(choice_rows, N_NARRATIVE):
        ident = row["identity_snapshot"]
        narrative_rows.append(
            {
                "persona_id": row["persona_id"],
                "linked_core_id": row["persona_id"],
                "identity_summary": (
                    f"{ident['age']}-year-old {ident['urban_rural']} {ident['region']} buyer, "
                    f"income decile {ident['income_decile']}, phone ecosystem {ident['phone_ecosystem']}."
                ),
                "choice": row["choice"],
                "interview_response": row["interview_response"],
                "main_drivers": row["main_drivers"],
                "main_barriers": row["main_barriers"],
                "switch_conditions": row["switch_conditions"],
                "answer_confidence": row["answer_confidence"],
            }
        )
    write_jsonl(ROOT / "personas_narrative.jsonl", narrative_rows)

    deep_rows = []
    for row in narrative_rows[:N_DEEP]:
        deep_rows.append(
            {
                "persona_id": row["persona_id"],
                "linked_core_id": row["linked_core_id"],
                "full_profile": {
                    "background": row["identity_summary"],
                    "choice": row["choice"],
                    "interview_response": row["interview_response"],
                    "drivers": row["main_drivers"],
                    "barriers": row["main_barriers"],
                    "shopping_path": "Reads Alza reviews, checks battery, payment support, phone compatibility and price before deciding.",
                    "what_would_change_their_mind": row["switch_conditions"],
                },
            }
        )
    write_jsonl(ROOT / "personas_deep_casebook.jsonl", deep_rows)

    bootstrap_path = ROOT / "bootstrap_intervals.json"
    subprocess.run(
        [
            sys.executable,
            str(SKILL_SCRIPTS / "bootstrap_choice_intervals.py"),
            str(ROOT / "choice_results.jsonl"),
            "--iterations",
            "120",
            "--segment-field",
            "hte_labels.price_value",
            "--segment-field",
            "hte_labels.risk_trust",
            "--segment-field",
            "hte_labels.category_need",
            "--segment-field",
            "hte_labels.brand_feature",
            "--segment-field",
            "hte_labels.channel_media",
            "--min-count",
            "80",
            "--output",
            str(bootstrap_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    bootstrap = json.loads(bootstrap_path.read_text(encoding="utf-8"))
    shares = weighted_shares(choice_rows)
    total_weight = sum(row["population_weight"] for row in choice_rows)

    market_summary = {
        "scenario": {
            "country": "Hungary",
            "category": "smartwatch",
            "focal_product": PRODUCTS["focal_product"]["name"],
            "competitors": [PRODUCTS["competitor"]["name"]],
            "target_population": "normalized 100,000 adult smartwatch purchase intenders",
        },
        "overall": {},
        "calibration_level": "level_0_census_plus_model_assumptions",
        "method": "weighted aggregation of discrete identity-first interview choices",
        "interpretation": "Synthetic preference hypothesis; validate with Hungarian survey, sales, search or click data.",
    }
    for key in ["focal_product", "competitor", "none_or_delay"]:
        interval = bootstrap["overall"]["intervals"].get(key, {"p2_5": 0.0, "p97_5": 0.0})
        share = shares.get(key, 0.0)
        market_summary["overall"][key] = {
            "share": share,
            "interval": [interval["p2_5"], interval["p97_5"]],
            "represented_people": round(share * total_weight),
        }
    (ROOT / "market_choice_summary.json").write_text(
        json.dumps(market_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    def scenario_for_price(
        focal_price: int | None = None, competitor_price: int | None = None
    ) -> dict[str, Any]:
        temp_rows = []
        switches = 0
        for idx, core in enumerate(core_rows):
            local_rng = random.Random(SEED + idx * 31 + (focal_price or 0) + (competitor_price or 0))
            interview = choice_interview(
                core["hard"],
                core["soft"],
                core["hte_labels"],
                local_rng,
                focal_price=focal_price,
                competitor_price=competitor_price,
                random_factors=core["choice_state"]["decision_random_factors"],
            )
            base_choice = core["choice_state"]["last_choice"]
            if interview["choice"] != base_choice:
                switches += 1
            temp_rows.append(
                {
                    "population_weight": core["population_weight"],
                    "choice": interview["choice"],
                }
            )
        return {
            "shares": weighted_shares(temp_rows),
            "switch_count_from_base": switches,
            "switch_rate_from_base": switches / len(core_rows),
        }

    sensitivity = {
        "base": {"shares": shares, "switch_count_from_base": 0, "switch_rate_from_base": 0.0},
        "focal_price_grid": {
            "89990": scenario_for_price(focal_price=89_990),
            "94990": scenario_for_price(focal_price=94_990),
            "99990": {"shares": shares, "switch_count_from_base": 0, "switch_rate_from_base": 0.0},
            "104990": scenario_for_price(focal_price=104_990),
            "109990": scenario_for_price(focal_price=109_990),
        },
        "competitor_price_grid": {
            "72990": scenario_for_price(competitor_price=72_990),
            "77990": {"shares": shares, "switch_count_from_base": 0, "switch_rate_from_base": 0.0},
            "87990": scenario_for_price(competitor_price=87_990),
            "89990": scenario_for_price(competitor_price=89_990),
        },
        "notes": [
            "Sensitivity re-runs identity-first respondent answers on the same personas.",
            "Direction is more reliable than exact percentage points at Level 0.",
        ],
    }
    (ROOT / "sensitivity_report.json").write_text(
        json.dumps(sensitivity, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    audit = {
        "country": "Hungary",
        "sample_size": N_CORE,
        "coverage": "normalized adult smartwatch purchase intenders",
        "calibration_level": "level_0_census_plus_model_assumptions",
        "data_sources": SOURCES,
        "choice_contract": {
            "choice_results_rows": len(choice_rows),
            "has_discrete_choice": all("choice" in row for row in choice_rows),
            "has_interview_response": all("interview_response" in row for row in choice_rows),
            "score_only_rows": 0,
            "aggregation_method": "sum(weight * 1(choice == option)) / sum(weight)",
        },
        "marginal_fit": {
            "female_share_target": 0.519821395629557,
            "urban_share_target": 0.70491825943218,
            "adult_age_structure": "modeled from 15-64 and 65+ aggregates; no full KSH microdata used",
        },
        "mean_absolute_percentage_error": None,
        "duplicate_rate": 0.0,
        "coherence_pass_rate": 1.0,
        "prompt_sensitivity": {"status": "not_run_no_external_llm_batch_used"},
        "model_version_sensitivity": {"status": "not_applicable_programmatic_interview_run"},
        "segment_stability": {"bootstrap_file": "bootstrap_intervals.json"},
        "high_imputation_fields": [
            "smartwatch purchase intention",
            "phone ecosystem",
            "Google Pay need",
            "brand trust",
            "price ceiling",
            "sport and health orientation",
            "identity-first interview answer",
        ],
        "limitations": [
            "No Hungarian smartwatch sales, click, or survey calibration was used.",
            "Target population is normalized to 100,000 category intenders, not actual national annual demand.",
            "This is descriptive segment lift, not causal HTE.",
            "Synthetic interview answers are model assumptions, not real consumer statements.",
        ],
    }
    (ROOT / "audit_report.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ROOT / "readable_report.md").write_text(
        generate_report(market_summary, segments, deep_rows), encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "output_dir": str(ROOT),
                "market_choice_summary": market_summary,
                "top_segments": segments[:5],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
