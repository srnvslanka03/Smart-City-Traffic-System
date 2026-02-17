import os
import sys
import threading
import uuid
import subprocess
import statistics
from typing import Dict, Any, List, Optional
import json
from urllib.parse import urlparse, unquote
from urllib.request import urlopen, Request

from flask import Flask, jsonify, request, render_template

from data_pipeline.loader import (
    CityRecord,
    build_index,
    load_city_records,
    normalize_key,
)


app = Flask(__name__)


class SimulationRun:
    def __init__(self, run_id: str, params: Dict[str, Any]):
        self.run_id = run_id
        self.params = params
        self.log_lines: List[str] = []
        self.status: str = "running"  # "running" | "finished" | "error"
        self.stats: Dict[str, Any] = {
            "phase": "",
            "lanes": {1: 0, 2: 0, 3: 0, 4: 0},
            "lane_details": {
                1: {"total": 0, "car": 0, "bus": 0, "truck": 0, "rickshaw": 0, "bike": 0},
                2: {"total": 0, "car": 0, "bus": 0, "truck": 0, "rickshaw": 0, "bike": 0},
                3: {"total": 0, "car": 0, "bus": 0, "truck": 0, "rickshaw": 0, "bike": 0},
                4: {"total": 0, "car": 0, "bus": 0, "truck": 0, "rickshaw": 0, "bike": 0},
            },
            "total_vehicles": 0,
            "total_time": 0,
            "throughput": 0.0,
            "traffic_density": 0,
            "average_wait": 0,
            "congestion_level": 0,
        }
        self.process: Optional[subprocess.Popen] = None

# Cities to exclude from City Insights listing/detail
EXCLUDED_CITIES = {"kochi", "nagpur", "salem"}


runs: Dict[str, SimulationRun] = {}
runs_lock = threading.Lock()

city_records: List[CityRecord] = load_city_records()
city_index: Dict[str, CityRecord] = build_index(city_records)


def _score_city(record: CityRecord) -> Dict[str, Any]:
    # Composite score favouring high delays, low peak speed and large population influence.
    delay_score = min(1.0, record.avg_delay_minutes / 45.0)
    speed_score = 1.0 - min(1.0, record.avg_peak_speed_kmph / 40.0)
    population_score = min(1.0, record.population_millions / 15.0)
    composite = round((delay_score * 0.45 + speed_score * 0.35 + population_score * 0.2) * 100, 1)

    priority_band = "Moderate"
    if composite >= 70:
        priority_band = "High"
    elif composite >= 45:
        priority_band = "Medium"

    return {
        "score": composite,
        "priority": priority_band,
        "rationale": [
            f"Average delay of {record.avg_delay_minutes:.0f} minutes",
            f"Peak speed around {record.avg_peak_speed_kmph:.0f} km/h",
            f"Population ~{record.population_millions:.1f}M",
        ],
    }


def _aggregate_home_metrics(records: List[CityRecord]) -> Dict[str, Any]:
    total = len(records)
    if not records:
        return {
            "density": 0,
            "avg_wait": 0,
            "travel_speed": 0,
            "city_count": 0,
            "priority_high_pct": 0,
            "priority_medium_pct": 0,
        }

    delays = [record.avg_delay_minutes for record in records]
    speeds = [record.avg_peak_speed_kmph for record in records]
    density = round(min(95.0, max(15.0, statistics.mean(delays) / 45.0 * 100.0)))
    avg_wait = round(statistics.mean(delays))
    travel_speed = round(statistics.mean(speeds), 1)

    priority_counts = {"High": 0, "Medium": 0, "Moderate": 0}
    for record in records:
        priority_counts[_score_city(record)["priority"]] += 1

    def pct(value: int) -> int:
        return round(value / total * 100) if total else 0

    return {
        "density": density,
        "avg_wait": avg_wait,
        "travel_speed": travel_speed,
        "city_count": total,
        "priority_high_pct": pct(priority_counts["High"]),
        "priority_medium_pct": pct(priority_counts["Medium"]),
        "priority_moderate_pct": pct(priority_counts["Moderate"]),
    }


home_metrics: Dict[str, Any] = _aggregate_home_metrics(city_records)


# Default enrichment for landmark and (optionally) image attribution
DEFAULT_CITY_META: Dict[str, Dict[str, str]] = {
    # Metros and major cities
    "delhi": {
        "landmark_name": "India Gate",
        "landmark_url": "https://en.wikipedia.org/wiki/India_Gate",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/India_Gate-Delhi_India11.JPG",
        "image_credit": "Wikimedia Commons contributors (CC BY-SA)",
        "image_source": "https://commons.wikimedia.org/wiki/File:India_Gate-Delhi_India11.JPG",
    },
    "delhi ncr": {
        "landmark_name": "India Gate",
        "landmark_url": "https://en.wikipedia.org/wiki/India_Gate",
    },
    "mumbai": {
        "landmark_name": "Gateway of India",
        "landmark_url": "https://en.wikipedia.org/wiki/Gateway_of_India",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Marine_Drive.JPG",
        "image_credit": "Wikimedia Commons contributors (CC BY-SA)",
        "image_source": "https://commons.wikimedia.org/wiki/File:Marine_Drive.JPG",
    },
    "bengaluru": {
        "landmark_name": "Vidhana Soudha",
        "landmark_url": "https://en.wikipedia.org/wiki/Vidhana_Soudha",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Vidhana_Soudha_,_the_State_Legistlature_of_Karnataka,_Bengaluru,_India.jpg",
        "image_credit": "Wikimedia Commons contributors (CC BY-SA)",
        "image_source": "https://commons.wikimedia.org/wiki/File:Vidhana_Soudha_,_the_State_Legistlature_of_Karnataka,_Bengaluru,_India.jpg",
    },
    "chennai": {
        "landmark_name": "Marina Beach",
        "landmark_url": "https://en.wikipedia.org/wiki/Marina_Beach",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Marina_Beach,%20Chennai%20101.JPG",
        "image_credit": "Wikimedia Commons contributors (CC BY-SA)",
        "image_source": "https://commons.wikimedia.org/wiki/File:Marina_Beach,_Chennai_101.JPG",
    },
    "hyderabad": {
        "landmark_name": "Charminar",
        "landmark_url": "https://en.wikipedia.org/wiki/Charminar",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Charminar,%20Hyderabad.JPG",
        "image_credit": "Wikimedia Commons contributors (CC BY-SA)",
        "image_source": "https://commons.wikimedia.org/wiki/File:Charminar,_Hyderabad.JPG",
    },
    "pune": {
        "landmark_name": "Shaniwar Wada",
        "landmark_url": "https://en.wikipedia.org/wiki/Shaniwar_Wada",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/The_entrance_of_Shaniwar_Wada..JPG",
        "image_credit": "Wikimedia Commons contributors (CC BY-SA)",
        "image_source": "https://commons.wikimedia.org/wiki/File:The_entrance_of_Shaniwar_Wada..JPG",
    },
    "jaipur": {
        "landmark_name": "Hawa Mahal",
        "landmark_url": "https://en.wikipedia.org/wiki/Hawa_Mahal",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Hawa%20mahal%20the%20great%20windy%20palace.JPG",
        "image_credit": "Wikimedia Commons contributors (CC BY-SA)",
        "image_source": "https://commons.wikimedia.org/wiki/File:Hawa_mahal_the_great_windy_palace.JPG",
    },
    "ahmedabad": {
        "landmark_name": "Sabarmati Riverfront",
        "landmark_url": "https://en.wikipedia.org/wiki/Sabarmati_Riverfront",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Sabarmati%20river%20front.JPG",
        "image_credit": "Wikimedia Commons contributors (CC BY-SA)",
        "image_source": "https://commons.wikimedia.org/wiki/File:Sabarmati_river_front.JPG",
    },
    "kolkata": {
        "landmark_name": "Howrah Bridge",
        "landmark_url": "https://en.wikipedia.org/wiki/Howrah_Bridge",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Howrah%20Bridge%20from%20Babu%20ghat.JPG",
        "image_credit": "Wikimedia Commons contributors (CC BY-SA)",
        "image_source": "https://commons.wikimedia.org/wiki/File:Howrah_Bridge_from_Babu_ghat.JPG",
    },
    "nagpur": {
        "landmark_name": "Deekshabhoomi",
        "landmark_url": "https://en.wikipedia.org/wiki/Deekshabhoomi",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Deekshabhoomi%20Stupa%20Nagpur.jpg",
        "image_credit": "Wikimedia Commons contributors (CC BY-SA)",
        "image_source": "https://commons.wikimedia.org/wiki/File:Deekshabhoomi_Stupa_Nagpur.jpg",
    },
    "kochi": {
        "landmark_name": "Chinese fishing nets (Fort Kochi)",
        "landmark_url": "https://en.wikipedia.org/wiki/Chinese_fishing_nets",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Chinese%20nets,%20Kochi,%20India.jpg",
        "image_credit": "Wikimedia Commons contributors (CC BY-SA)",
        "image_source": "https://commons.wikimedia.org/wiki/File:Chinese_nets,_Kochi,_India.jpg",
    },
    "udaipur": {
        "landmark_name": "City Palace, Udaipur",
        "landmark_url": "https://en.wikipedia.org/wiki/City_Palace,_Udaipur",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Night_View_of_City_Palace_udaipur.JPG",
        "image_credit": "Wikimedia Commons contributors (CC BY-SA)",
        "image_source": "https://commons.wikimedia.org/wiki/File:Night_View_of_City_Palace_udaipur.JPG",
    },
    "surat": {
        "landmark_name": "Surat Castle",
        "landmark_url": "https://en.wikipedia.org/wiki/Surat_Castle",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Kavi_Narmad_Central_Library_surat.JPG",
        "image_credit": "Wikimedia Commons contributors (CC BY-SA)",
        "image_source": "https://commons.wikimedia.org/wiki/File:Kavi_Narmad_Central_Library_surat.JPG",
    },
    "lucknow": {
        "landmark_name": "Bara Imambara",
        "landmark_url": "https://en.wikipedia.org/wiki/Bara_Imambara",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Naubat_Khana_at_Bara_Imambara_Lucknow.jpg",
        "image_credit": "Wikimedia Commons contributors (CC BY-SA)",
        "image_source": "https://commons.wikimedia.org/wiki/File:Naubat_Khana_at_Bara_Imambara_Lucknow.jpg",
    },
    "kanpur": {"landmark_name": "JK Temple", "landmark_url": "https://en.wikipedia.org/wiki/J._K._Temple"},
    "indore": {
        "landmark_name": "Rajwada",
        "landmark_url": "https://en.wikipedia.org/wiki/Rajwada,_Indore",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Wide_Angle_view_of_Indore_Rajwada_at_night.jpg",
        "image_credit": "Wikimedia Commons contributors (CC BY-SA)",
        "image_source": "https://commons.wikimedia.org/wiki/File:Wide_Angle_view_of_Indore_Rajwada_at_night.jpg",
    },
    "coimbatore": {"landmark_name": "Marudamalai Temple", "landmark_url": "https://en.wikipedia.org/wiki/Marudamalai"},
    "visakhapatnam": {"landmark_name": "RK Beach", "landmark_url": "https://en.wikipedia.org/wiki/RK_Beach"},
    "vizag": {"landmark_name": "RK Beach", "landmark_url": "https://en.wikipedia.org/wiki/RK_Beach"},
    "guwahati": {"landmark_name": "Kamakhya Temple", "landmark_url": "https://en.wikipedia.org/wiki/Kamakhya_Temple"},
    "varanasi": {"landmark_name": "Dashashwamedh Ghat", "landmark_url": "https://en.wikipedia.org/wiki/Dashashwamedh_Ghat"},
    "madurai": {"landmark_name": "Meenakshi Temple", "landmark_url": "https://en.wikipedia.org/wiki/Meenakshi_Temple"},
    "panaji": {"landmark_name": "Our Lady of the Immaculate Conception Church", "landmark_url": "https://en.wikipedia.org/wiki/Our_Lady_of_the_Immaculate_Conception_Church,_Goa"},
    "silvassa": {"landmark_name": "Hirwa Van Garden", "landmark_url": "https://en.wikipedia.org/wiki/Silvassa"},
    "jamshedpur": {"landmark_name": "Jubilee Park", "landmark_url": "https://en.wikipedia.org/wiki/Jubilee_Park,_Jamshedpur"},
    "bhubaneswar": {"landmark_name": "Lingaraja Temple", "landmark_url": "https://en.wikipedia.org/wiki/Lingaraja_Temple"},
    "dehradun": {"landmark_name": "Clock Tower", "landmark_url": "https://en.wikipedia.org/wiki/Dehradun"},
    "shimla": {"landmark_name": "The Ridge, Shimla", "landmark_url": "https://en.wikipedia.org/wiki/Shimla"},
    "thrissur": {"landmark_name": "Vadakkunnathan Temple", "landmark_url": "https://en.wikipedia.org/wiki/Vadakkunnathan_Temple"},
    "nashik": {"landmark_name": "Trimbakeshwar Temple", "landmark_url": "https://en.wikipedia.org/wiki/Trimbakeshwar_Shiva_Temple"},
    "ranchi": {"landmark_name": "Dassam Falls", "landmark_url": "https://en.wikipedia.org/wiki/Dassam_Falls"},
    "agartala": {"landmark_name": "Ujjayanta Palace", "landmark_url": "https://en.wikipedia.org/wiki/Ujjayanta_Palace"},
    "patna": {"landmark_name": "Golghar", "landmark_url": "https://en.wikipedia.org/wiki/Golghar"},
    "noida": {"landmark_name": "Okhla Bird Sanctuary", "landmark_url": "https://en.wikipedia.org/wiki/Okhla_Bird_Sanctuary"},
    "gurugram": {"landmark_name": "Cyber Hub", "landmark_url": "https://en.wikipedia.org/wiki/Gurgaon"},
    "ghaziabad": {"landmark_name": "ISKCON Ghaziabad", "landmark_url": "https://en.wikipedia.org/wiki/Ghaziabad,_Uttar_Pradesh"},
    "thane": {"landmark_name": "Upvan Lake", "landmark_url": "https://en.wikipedia.org/wiki/Upvan_Lake"},
    "navi mumbai": {"landmark_name": "Nerul Balaji Temple", "landmark_url": "https://en.wikipedia.org/wiki/Nerul"},
    "bhopal": {"landmark_name": "Upper Lake (Bhojtal)", "landmark_url": "https://en.wikipedia.org/wiki/Bhojtal"},
    "vadodara": {"landmark_name": "Laxmi Vilas Palace", "landmark_url": "https://en.wikipedia.org/wiki/Laxmi_Vilas_Palace"},
    "ludhiana": {"landmark_name": "Rakh Bagh Park", "landmark_url": "https://en.wikipedia.org/wiki/Ludhiana"},
    "amritsar": {"landmark_name": "Golden Temple", "landmark_url": "https://en.wikipedia.org/wiki/Golden_Temple"},
    "bhilai-durg": {"landmark_name": "Maitri Bagh", "landmark_url": "https://en.wikipedia.org/wiki/Maitri_Bagh"},
    "raipur": {"landmark_name": "Vivekananda Sarovar", "landmark_url": "https://en.wikipedia.org/wiki/Raipur"},
    "chandigarh": {"landmark_name": "Rock Garden of Chandigarh", "landmark_url": "https://en.wikipedia.org/wiki/Rock_Garden_of_Chandigarh"},
    # Additional cities to ensure Wikipedia photo enrichment
    "salem": {
        "landmark_name": "Sugavaneshwarar Temple",
        "landmark_url": "https://en.wikipedia.org/wiki/Sugavaneshwarar_Temple",
        "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Salem_junction_panorama.jpg",
        "image_credit": "Wikimedia Commons contributors (CC BY-SA)",
        "image_source": "https://commons.wikimedia.org/wiki/File:Salem_junction_panorama.jpg",
    },
    "gwalior": {"landmark_name": "Gwalior Fort", "landmark_url": "https://en.wikipedia.org/wiki/Gwalior_Fort"},
    "aurangabad": {"landmark_name": "Bibi Ka Maqbara", "landmark_url": "https://en.wikipedia.org/wiki/Bibi_Ka_Maqbara"},
    "vijayawada": {"landmark_name": "Prakasam Barrage", "landmark_url": "https://en.wikipedia.org/wiki/Prakasam_Barrage"},
    "meerut": {"landmark_name": "Augarnath Temple", "landmark_url": "https://en.wikipedia.org/wiki/Augarnath_Temple"},
    "tirupati": {"landmark_name": "Tirumala Venkateswara Temple", "landmark_url": "https://en.wikipedia.org/wiki/Venkateswara_Temple,_Tirumala"},
    "faridabad": {"landmark_name": "Surajkund", "landmark_url": "https://en.wikipedia.org/wiki/Surajkund"},
    "prayagraj": {"landmark_name": "Sangam, Prayagraj", "landmark_url": "https://en.wikipedia.org/wiki/Triveni_Sangam"},
    "dhanbad": {"landmark_name": "Jharia Coalfield", "landmark_url": "https://en.wikipedia.org/wiki/Jharia_coalfield"},
    "asansol": {"landmark_name": "Churulia (Tagore's birthplace region)", "landmark_url": "https://en.wikipedia.org/wiki/Asansol"},
    "rajkot": {"landmark_name": "Kaba Gandhi No Delo", "landmark_url": "https://en.wikipedia.org/wiki/Kaba_Gandhi_No_Delo"},
    "warangal": {"landmark_name": "Thousand Pillar Temple", "landmark_url": "https://en.wikipedia.org/wiki/Thousand_Pillar_Temple"},
    "mangaluru": {"landmark_name": "Panambur Beach", "landmark_url": "https://en.wikipedia.org/wiki/Panambur_Beach"},
    "mysuru": {"landmark_name": "Mysore Palace", "landmark_url": "https://en.wikipedia.org/wiki/Mysore_Palace"},
    "guntur": {"landmark_name": "Uppalapadu Bird Sanctuary", "landmark_url": "https://en.wikipedia.org/wiki/Uppalapadu_Bird_Sanctuary"},
    "tiruchirappalli": {"landmark_name": "Rockfort", "landmark_url": "https://en.wikipedia.org/wiki/Tiruchirappalli_Rock_Fort"},
}


def _extract_wikipedia_title(url: str) -> Optional[str]:
    try:
        if not url:
            return None
        parsed = urlparse(url)
        if "wikipedia.org" not in parsed.netloc:
            return None
        path = parsed.path
        if not path:
            return None
        if path.startswith("/wiki/"):
            title = path[len("/wiki/"):]
            return unquote(title)
        return None
    except Exception:
        return None


def _fetch_wikipedia_image(title: str) -> Optional[str]:
    try:
        if not title:
            return None
        api = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
        req = Request(api, headers={"User-Agent": "CityInsights/1.0"})
        with urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        if not isinstance(data, dict):
            return None
        if "originalimage" in data and isinstance(data["originalimage"], dict):
            src = data["originalimage"].get("source")
            if src:
                return src
        if "thumbnail" in data and isinstance(data["thumbnail"], dict):
            src = data["thumbnail"].get("source")
            if src:
                return src
        return None
    except Exception:
        return None


_WIKI_IMAGE_CACHE: Dict[str, str] = {}

def _warm_wiki_image_cache() -> None:
    names: List[str] = []
    try:
        for r in city_records:
            names.append(r.city.strip().lower())
        for k in DEFAULT_CITY_META.keys():
            names.append(k.strip().lower())
        seen = set()
        for name in names:
            if not name or name in seen:
                continue
            seen.add(name)
            meta = DEFAULT_CITY_META.get(name, {})
            if meta.get("image_url"):
                _WIKI_IMAGE_CACHE[name] = meta["image_url"]
                continue
            landmark_url = meta.get("landmark_url", "")
            title = _extract_wikipedia_title(landmark_url)
            if not title:
                continue
            img = _fetch_wikipedia_image(title)
            if img:
                _WIKI_IMAGE_CACHE[name] = img
    except Exception:
        pass


_warm_wiki_image_cache()


def _record_to_payload(record: CityRecord) -> Dict[str, Any]:
    suitability = _score_city(record)
    # Enrich with defaults where fields are missing
    meta = DEFAULT_CITY_META.get(record.city.strip().lower(), {})
    image_url = getattr(record, "image_url", "") or meta.get("image_url", "") or _WIKI_IMAGE_CACHE.get(record.city.strip().lower(), "")
    image_credit = getattr(record, "image_credit", "") or meta.get("image_credit", "")
    image_source = getattr(record, "image_source", "") or meta.get("image_source", "")
    landmark_name = getattr(record, "landmark_name", "") or meta.get("landmark_name", "")
    landmark_url = getattr(record, "landmark_url", "") or meta.get("landmark_url", "")

    return {
        "city": record.city,
        "state": record.state,
        "classification": record.classification,
        "population_millions": record.population_millions,
        "avg_peak_speed_kmph": record.avg_peak_speed_kmph,
        "avg_delay_minutes": record.avg_delay_minutes,
        "vehicle_mix": record.vehicle_mix,
        "issues": record.issues,
        "recommended_actions": record.recommended_actions,
        "image_url": image_url,
        "image_credit": image_credit,
        "image_source": image_source,
        "landmark_name": landmark_name,
        "landmark_url": landmark_url,
        "suitability": suitability,
    }


def _search_records(query: Optional[str]) -> List[CityRecord]:
    if not query:
        return sorted(city_records, key=lambda r: (-r.avg_delay_minutes, r.city))

    needle = query.strip().lower()
    matches: List[CityRecord] = []
    for record in city_records:
        haystack = f"{record.city.lower()} {record.state.lower()} {record.classification.lower()}"
        if needle in haystack:
            matches.append(record)
    return matches[:50]


def _parse_stats_from_line(run: SimulationRun, line: str) -> None:
    line = line.strip()
    if not line:
        return

    # Current phase from signal status lines
    # Only capture GREEN or YELLOW lines to avoid overwriting with trailing RED lines
    if "GREEN TS" in line or "YELLOW TS" in line:
        run.stats["phase"] = line

    if line.startswith("LANE_STATS"):
        try:
            parts = line.split()[1:]
            data = {}
            for part in parts:
                key, value = part.split("=")
                data[key] = value
            lane_idx = int(data.get("lane", "0"))
            if lane_idx:
                total = int(data.get("total", "0"))
                lane_details = {
                    "total": total,
                    "car": int(data.get("car", "0")),
                    "bus": int(data.get("bus", "0")),
                    "truck": int(data.get("truck", "0")),
                    "rickshaw": int(data.get("rickshaw", "0")),
                    "bike": int(data.get("bike", "0")),
                }
                run.stats["lanes"][lane_idx] = total
                run.stats["lane_details"][lane_idx] = lane_details
        except Exception:
            pass

    # Lane totals
    if line.startswith("Lane ") and "Total:" in line:
        # Example: 'Lane 1: Total: 38'
        try:
            parts = line.split(":")
            lane_part = parts[0].strip()  # "Lane 1"
            total_part = parts[2].strip() if len(parts) > 2 else ""
            lane_num = int(lane_part.split()[1])
            total_val = int(total_part)
            run.stats["lanes"][lane_num] = total_val
        except Exception:
            pass

    # Total vehicles
    if line.startswith("Total vehicles passed"):
        try:
            val_str = line.split(":")[1].strip()
            run.stats["total_vehicles"] = int(float(val_str))
        except Exception:
            pass

    # Total time
    if line.startswith("Total time passed"):
        try:
            val_str = line.split(":")[1].strip()
            run.stats["total_time"] = int(float(val_str))
        except Exception:
            pass
        _update_summary_metrics(run)

    # Throughput
    if line.startswith("No. of vehicles passed per unit time"):
        try:
            val_str = line.split(":")[1].strip()
            run.stats["throughput"] = float(val_str)
        except Exception:
            pass
        _update_summary_metrics(run)

    if line.startswith("SUMMARY"):
        try:
            parts = line.split()[1:]
            data = {}
            for part in parts:
                key, value = part.split("=")
                data[key] = value
            if "total" in data:
                run.stats["total_vehicles"] = int(float(data["total"]))
            if "time" in data:
                run.stats["total_time"] = int(float(data["time"]))
            if "throughput" in data:
                run.stats["throughput"] = float(data["throughput"])
        except Exception:
            pass
        _update_summary_metrics(run)

    if line.startswith("SIMULATION_COMPLETE"):
        run.status = "finished"


def _update_summary_metrics(run: SimulationRun) -> None:
    total_time = run.stats.get("total_time", 0)
    total_vehicles = run.stats.get("total_vehicles", 0)
    if total_vehicles > 0:
        avg_wait = max(0, total_time / total_vehicles)
    else:
        avg_wait = 0
    run.stats["average_wait"] = round(avg_wait, 2)

    sim_time = run.params.get("sim_time", 120) or 1
    theoretical_capacity = sim_time * 4
    if theoretical_capacity <= 0:
        theoretical_capacity = 1
    density_ratio = min(1.0, total_vehicles / theoretical_capacity)
    run.stats["traffic_density"] = round(density_ratio * 100, 1)
    run.stats["congestion_level"] = run.stats["traffic_density"]


def _run_simulation_subprocess(run: SimulationRun) -> None:
    """Background thread target: run simulation.py and capture output."""
    try:
        project_root = os.path.dirname(os.path.abspath(__file__))

        env = os.environ.copy()
        env["SIM_TIME"] = str(run.params.get("sim_time", 120))
        env["MIN_GREEN_TIME"] = str(run.params.get("min_green", 10))
        env["MAX_GREEN_TIME"] = str(run.params.get("max_green", 60))
        env.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        if not env.get("DISPLAY") and os.name != "nt":
            env.setdefault("SDL_VIDEODRIVER", "dummy")
            env.setdefault("SDL_AUDIODRIVER", "dummy")

        python_executable = sys.executable or "python"

        run.process = subprocess.Popen(
            [python_executable, "simulation.py"],
            cwd=project_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        assert run.process.stdout is not None

        for line in run.process.stdout:
            with runs_lock:
                run.log_lines.append(line.rstrip("\n"))
                _parse_stats_from_line(run, line)

        run.process.wait()
        with runs_lock:
            if run.status == "stopped":
                run.log_lines.append("[system] simulation halted by user")
            else:
                if run.process.returncode == 0:
                    run.status = "finished"
                else:
                    run.status = "error"
            run.process = None
    except Exception as exc:  # pragma: no cover - debug aid
        with runs_lock:
            run.log_lines.append(f"[backend error] {exc}")
            run.status = "error"


@app.route("/")
def home():
    return render_template("home.html", home_metrics=home_metrics)


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/awareness")
def awareness():
    return render_template("awareness.html")


@app.route("/cities")
def cities():
    return render_template("cities.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/resources")
def resources():
    return render_template("resources.html")


@app.route("/api/cities", methods=["GET"])
def api_cities():
    query = request.args.get("q", "").strip()
    records = _search_records(query)
    records = [r for r in records if r.city.strip().lower() not in EXCLUDED_CITIES]
    payload = [_record_to_payload(record) for record in records]
    return jsonify({"count": len(payload), "items": payload})


@app.route("/api/cities/<slug>", methods=["GET"])
def api_city_detail(slug: str):
    key = normalize_key(slug)
    record = city_index.get(key)
    if not record:
        # allow matching on raw city names if slug not found
        record = city_index.get(normalize_key(slug.replace("-", " ")))
    if not record:
        return jsonify({"error": "city not found"}), 404
    if record.city.strip().lower() in EXCLUDED_CITIES:
        return jsonify({"error": "city not available"}), 404
    return jsonify(_record_to_payload(record))


@app.route("/api/run", methods=["POST"])
def api_run():
    payload = request.get_json(force=True, silent=True) or {}
    sim_time = int(payload.get("sim_time", 120))
    min_green = int(payload.get("min_green", 10))
    max_green = int(payload.get("max_green", 60))

    run_id = str(uuid.uuid4())
    run = SimulationRun(
        run_id,
        {"sim_time": sim_time, "min_green": min_green, "max_green": max_green},
    )

    with runs_lock:
        runs[run_id] = run

    thread = threading.Thread(target=_run_simulation_subprocess, args=(run,))
    thread.daemon = True
    thread.start()

    return jsonify({"run_id": run_id, "status": run.status})


@app.route("/api/status/<run_id>", methods=["GET"])
def api_status(run_id: str):
    with runs_lock:
        run = runs.get(run_id)
        if not run:
            return jsonify({"error": "run not found"}), 404

        # Return last 300 log lines to avoid huge payloads
        log_tail = run.log_lines[-300:]

        return jsonify(
            {
                "run_id": run.run_id,
                "status": run.status,
                "params": run.params,
                "log": log_tail,
                "stats": run.stats,
            }
        )


@app.route("/api/stop/<run_id>", methods=["POST"])
def api_stop(run_id: str):
    with runs_lock:
        run = runs.get(run_id)
        if not run:
            return jsonify({"error": "run not found"}), 404

        proc = run.process
        if proc and proc.poll() is None:
            run.log_lines.append("[system] stop requested by user")
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        run.status = "stopped"
        run.process = None

    return jsonify({"run_id": run_id, "status": "stopped"})


if __name__ == "__main__":
    # For local development. In production use a proper WSGI server.
    app.run(host="0.0.0.0", port=5000, debug=True)


