from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from datetime import datetime
from typing import Dict, Iterable, List, Optional

import requests

from .loader import (
    DATA_FILE,
    CityRecord,
    build_index,
    load_city_records,
    normalize_key,
    write_city_records,
)

LOGGER = logging.getLogger(__name__)

DATA_GOV_IN_API_BASE = "https://api.data.gov.in/resource/"
DATA_GOV_IN_DEFAULT_LIMIT = 200

# Configuration for potential public datasets. These IDs can be swapped with
# production-ready resources when credentials are available.
DATA_GOV_IN_SOURCES: List[Dict[str, str]] = [
    {
        "name": "Sample Smart City traffic feed",
        "resource_id": "275fe0cc-d790-4f75-9a7a-b6fa8a1b9e35",
        "city_field": "city",
        "state_field": "state",
        "delay_field": "avg_delay_minutes",
        "speed_field": "avg_speed_kmph",
        "population_field": "population_millions",
        "issues_field": "key_issues",
        "actions_field": "recommended_actions",
        "classification_field": "classification",
    }
]


def _safe_float(value: object, fallback: float = 0.0) -> float:
    try:
        if value is None:
            return fallback
        return float(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def _safe_list(value: object) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        parts = [segment.strip() for segment in value.replace(";", ",").split(",")]
        return [segment for segment in parts if segment]
    return []


def _normalise_city_record(payload: Dict[str, object]) -> Optional[CityRecord]:
    city = str(payload.get("city", "")).strip()
    if not city:
        return None

    state = str(payload.get("state", "")).strip() or "Unknown"
    classification = str(payload.get("classification", "unknown")) or "unknown"
    population = _safe_float(payload.get("population_millions"), fallback=0.0)
    speed = _safe_float(payload.get("avg_peak_speed_kmph"), fallback=0.0)
    delay = _safe_float(payload.get("avg_delay_minutes"), fallback=0.0)
    issues = _safe_list(payload.get("key_issues"))
    actions = _safe_list(payload.get("recommended_actions"))

    return CityRecord(
        city=city.title(),
        state=state.title(),
        classification=classification.lower(),
        population_millions=population,
        avg_peak_speed_kmph=speed,
        avg_delay_minutes=delay,
        vehicle_mix=payload.get("vehicle_mix", {}) or {},
        issues=issues,
        recommended_actions=actions,
    )


def _fetch_data_gov_in_dataset(config: Dict[str, str]) -> List[CityRecord]:
    api_key = os.getenv("DATA_GOV_IN_API_KEY")
    if not api_key:
        LOGGER.info("DATA_GOV_IN_API_KEY not set; skipping %s", config["name"])
        return []

    resource_id = config["resource_id"]
    params = {
        "api-key": api_key,
        "format": "json",
        "limit": str(DATA_GOV_IN_DEFAULT_LIMIT),
    }

    url = f"{DATA_GOV_IN_API_BASE}{resource_id}"
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:  # broad catch so we can continue gracefully
        LOGGER.warning("Failed to pull %s: %s", config["name"], exc)
        return []

    records = []
    for item in data.get("records", []):
        mapped_payload = {
            "city": item.get(config.get("city_field", "city"), ""),
            "state": item.get(config.get("state_field", "state"), ""),
            "classification": item.get(config.get("classification_field", "classification"), ""),
            "population_millions": item.get(config.get("population_field", "population_millions"), 0),
            "avg_peak_speed_kmph": item.get(config.get("speed_field", "avg_speed_kmph"), 0),
            "avg_delay_minutes": item.get(config.get("delay_field", "avg_delay_minutes"), 0),
            "key_issues": item.get(config.get("issues_field", "key_issues"), []),
            "recommended_actions": item.get(config.get("actions_field", "recommended_actions"), []),
        }
        record = _normalise_city_record(mapped_payload)
        if record:
            records.append(record)

    LOGGER.info("Fetched %d records from %s", len(records), config["name"])
    return records


def _merge_records(primary: List[CityRecord], supplements: Iterable[CityRecord]) -> List[CityRecord]:
    merged = build_index(primary)
    for record in supplements:
        key = normalize_key(record.city)
        merged[key] = record
    return list(merged.values())


def refresh_city_dataset(include_baseline: bool = True, write_file: bool = True) -> Dict[str, object]:
    baseline: List[CityRecord] = load_city_records(DATA_FILE if include_baseline else None)
    merged_records = list(baseline)
    source_counts: Dict[str, int] = {}

    for source in DATA_GOV_IN_SOURCES:
        results = _fetch_data_gov_in_dataset(source)
        if results:
            merged_records = _merge_records(merged_records, results)
        source_counts[source["name"]] = len(results)

    if write_file:
        write_city_records(merged_records)

    snapshot = {
        "written_records": len(merged_records),
        "source_counts": source_counts,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    LOGGER.info("City dataset refresh summary: %s", snapshot)
    return snapshot


def save_snapshot(path: os.PathLike[str]) -> None:
    records = load_city_records()
    with open(path, "w", encoding="utf-8") as handle:
        json.dump([asdict(record) for record in records], handle, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    summary = refresh_city_dataset()
    print(json.dumps(summary, indent=2))
