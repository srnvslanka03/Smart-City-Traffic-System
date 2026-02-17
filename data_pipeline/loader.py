from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Any, Dict, List

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_FILE = DATA_DIR / "traffic_sample.json"
LATEST_DATA_FILE = DATA_DIR / "traffic_latest.json"


@dataclass
class CityRecord:
    city: str
    state: str
    classification: str
    population_millions: float
    avg_peak_speed_kmph: float
    avg_delay_minutes: float
    vehicle_mix: Dict[str, float]
    issues: List[str]
    recommended_actions: List[str]
    image_url: str = ""
    image_credit: str = ""
    image_source: str = ""
    landmark_name: str = ""
    landmark_url: str = ""

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "CityRecord":
        return cls(
            city=payload.get("city", ""),
            state=payload.get("state", ""),
            classification=payload.get("classification", "unknown"),
            population_millions=float(payload.get("population_millions", 0.0)),
            avg_peak_speed_kmph=float(payload.get("avg_peak_speed_kmph", 0.0)),
            avg_delay_minutes=float(payload.get("avg_delay_minutes", 0.0)),
            vehicle_mix=dict(payload.get("vehicle_mix", {})),
            issues=list(payload.get("issues", [])),
            recommended_actions=list(payload.get("recommended_actions", [])),
            image_url=payload.get("image_url", ""),
            image_credit=payload.get("image_credit", ""),
            image_source=payload.get("image_source", ""),
            landmark_name=payload.get("landmark_name", ""),
            landmark_url=payload.get("landmark_url", ""),
        )


def load_city_records(data_path: pathlib.Path | None = None) -> List[CityRecord]:
    candidate_paths = []
    if data_path:
        candidate_paths.append(data_path)
    else:
        candidate_paths.extend([LATEST_DATA_FILE, DATA_FILE])

    for path in candidate_paths:
        if path and path.exists():
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return [CityRecord.from_dict(item) for item in payload]

    return []


def build_index(records: List[CityRecord]) -> Dict[str, CityRecord]:
    return {normalize_key(record.city): record for record in records}


def normalize_key(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


def write_city_records(records: List[CityRecord], path: pathlib.Path | None = None) -> None:
    target = path or LATEST_DATA_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    serialisable = [record.__dict__ for record in records]
    with target.open("w", encoding="utf-8") as handle:
        json.dump(serialisable, handle, ensure_ascii=False, indent=2)

