"""Build runs.json from activities.json, the GPX files and rhr.json."""
import xml.etree.ElementTree as ET
from datetime import datetime

from .activities import type_key
from .config import SAMPLE_EVERY_S
from .gpx import parse_gpx, to_stream
from .storage import load_json, save_json


def summary_fields(act):
    def num(k):
        v = act.get(k)
        return round(v, 2) if isinstance(v, (int, float)) else None

    zones = [round(act.get(f"hrTimeInZone_{z}") or 0) for z in range(1, 6)]
    return {
        "id": act.get("activityId"),
        "date": act.get("startTimeLocal"),
        "name": act.get("activityName"),
        "type": type_key(act),
        "dist": num("distance"),
        "dur": num("duration"),
        "moving": num("movingDuration"),
        "elev": num("elevationGain"),
        "avgHr": num("averageHR"),
        "maxHr": num("maxHR"),
        "vo2": num("vO2MaxValue"),
        "cad": num("averageRunningCadenceInStepsPerMinute"),
        "stride": num("avgStrideLength"),
        "te": num("aerobicTrainingEffect"),
        "teAn": num("anaerobicTrainingEffect"),
        "hrz": zones if any(zones) else None,
    }


def build_runs(out, acts):
    gpx_dir = out / "gpx"
    cache_dir = out / "cache"
    cache_dir.mkdir(exist_ok=True)
    runs = []
    for aid, act in sorted(acts.items(), key=lambda kv: kv[1].get("startTimeLocal") or ""):
        rec = summary_fields(act)
        gpx = gpx_dir / f"{aid}.gpx"
        cache = cache_dir / f"{aid}.json"
        stream = None
        if cache.exists() and gpx.exists() and cache.stat().st_mtime >= gpx.stat().st_mtime:
            stream = load_json(cache, None)
        elif gpx.exists() and gpx.stat().st_size > 0:
            try:
                stream = to_stream(parse_gpx(gpx.read_bytes()), rec["dist"])
            except ET.ParseError:
                stream = None
            save_json(cache, stream)
        if stream:
            rec.update(stream)
        runs.append(rec)
    payload = {
        "format": "garmin-runs/1",
        "generated": datetime.now().isoformat(timespec="seconds"),
        "sampleEvery": SAMPLE_EVERY_S,
        "runs": runs,
        "rhr": sorted(load_json(out / "rhr.json", {}).items()),
    }
    save_json(out / "runs.json", payload)
    with_stream = sum(1 for r in runs if "t" in r)
    size = (out / "runs.json").stat().st_size / 1e6
    print(f"runs.json: {len(runs)} runs ({with_stream} with GPS/HR stream), "
          f"{len(payload['rhr'])} resting HR days, {size:.1f} MB")
