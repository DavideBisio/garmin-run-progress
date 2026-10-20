#!/usr/bin/env python3
"""
garmin_grab.py - incremental Garmin Connect running exporter.

Each run:
  1. logs in (saved tokens in ~/.garminconnect, so credentials/MFA only the first time)
  2. lists your activities newest-first and stops as soon as it reaches ones it already has
  3. downloads the GPX of every new run (originals kept in garmin_export/gpx/)
  4. fetches your daily resting heart rate (kept in garmin_export/rhr.json)
  5. rebuilds garmin_export/runs.json, the single file you upload to the analysis page

Setup (Python 3.12+):
    python3 -m venv .venv
    source .venv/bin/activate          # Windows: .venv\\Scripts\\activate
    pip install --upgrade garminconnect curl_cffi ua-generator

Usage:
    python garmin_grab.py                  # fetch new runs, rebuild runs.json
    python garmin_grab.py --since 2016-01-01
    python garmin_grab.py --rebuild        # only rebuild runs.json from local files
    python garmin_grab.py --full           # re-scan the whole activity list

The first run on ~10 years of data takes 1-2 hours (it pauses between
downloads to stay polite). It is safe to stop with Ctrl-C and run again:
finished files are kept and only missing ones are fetched.
"""

import argparse
import getpass
import json
import math
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

TOKENSTORE = os.path.expanduser(os.getenv("GARMINTOKENS", "~/.garminconnect"))
PAGE = 100
SAMPLE_EVERY_S = 10          # stream resolution stored in runs.json
NO_GPS_TYPES = ("treadmill", "indoor", "virtual")
RHR_CHUNK_DAYS = 364         # get_rhr_daily returns up to ~1 year per request
RHR_REFRESH_DAYS = 7         # re-fetch the last week: today's value settles later


# ---------------------------------------------------------------- helpers
def is_run(act):
    key = ((act.get("activityType") or {}).get("typeKey") or "").lower()
    return "run" in key


def type_key(act):
    return ((act.get("activityType") or {}).get("typeKey") or "").lower()


def has_gps(act):
    k = type_key(act)
    if any(t in k for t in NO_GPS_TYPES):
        return False
    if act.get("hasPolyline") is False:
        return False
    return True


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    tmp.replace(path)


# ---------------------------------------------------------------- garmin
def login():
    try:
        from garminconnect import Garmin
    except ImportError:
        sys.exit("Missing library. Run:  pip install --upgrade garminconnect curl_cffi ua-generator")

    try:
        g = Garmin()
        g.login(TOKENSTORE)
        print("Logged in with saved tokens.")
        return g
    except Exception:
        pass

    print("First login (tokens will be saved to %s)" % TOKENSTORE)
    email = os.getenv("GARMIN_EMAIL") or input("Garmin email: ").strip()
    password = getpass.getpass("Garmin password: ")
    g = Garmin(email, password, prompt_mfa=lambda: input("MFA code: ").strip())
    g.login(TOKENSTORE)
    print("Logged in.")
    return g


def with_retry(fn, *args, tries=4, **kwargs):
    for attempt in range(tries):
        try:
            return fn(*args, **kwargs)
        except KeyboardInterrupt:
            raise
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            wait = 60 if ("429" in msg or "Too Many" in msg) else 5 * (attempt + 1)
            if attempt == tries - 1:
                raise
            print(f"  ! {msg[:120]} - retrying in {wait}s")
            time.sleep(wait)


def list_new_activities(g, known, since, full):
    """Walk the activity list newest-first; stop at the first page that is all known."""
    found, seen = {}, set()
    start = 0
    while True:
        page = with_retry(g.get_activities, start, PAGE)
        if not page:
            break
        page_all_known = True
        reached_since = False
        for act in page:
            day = (act.get("startTimeLocal") or "")[:10]
            if since and day and day < since:
                reached_since = True
                continue
            aid = str(act.get("activityId"))
            seen.add(aid)
            if aid not in known:
                page_all_known = False
            if is_run(act):
                found[aid] = act
        print(f"  scanned {start + len(page)} activities, {len(found)} runs in this scan")
        if reached_since or (page_all_known and not full):
            break
        start += PAGE
        time.sleep(0.5)
    return found, seen


def download_gpx(g, aid):
    from garminconnect import Garmin
    return with_retry(g.download_activity, int(aid), dl_fmt=Garmin.ActivityDownloadFormat.GPX)


def update_rhr(g, path, first_day):
    """Fetch daily resting heart rate from first_day (or the last known day) to today."""
    rhr = load_json(path, {})
    if not hasattr(g, "get_rhr_daily"):
        print("  resting HR skipped: needs a newer library (pip install --upgrade garminconnect)")
        return
    if rhr:
        start = date.fromisoformat(max(rhr)) - timedelta(days=RHR_REFRESH_DAYS)
    elif first_day:
        start = date.fromisoformat(first_day)
    else:
        return
    end = date.today()
    while start <= end:
        stop = min(start + timedelta(days=RHR_CHUNK_DAYS - 1), end)
        try:
            rows = with_retry(g.get_rhr_daily, start.isoformat(), stop.isoformat())
        except Exception as e:  # noqa: BLE001
            print(f"  resting HR {start} to {stop} skipped: {str(e)[:100]}")
            rows = []
        for row in rows:
            if row.get("calendarDate") and isinstance(row.get("value"), (int, float)):
                rhr[row["calendarDate"]] = round(row["value"])
        start = stop + timedelta(days=1)
        time.sleep(0.5)
    save_json(path, rhr)
    print(f"  resting HR: {len(rhr)} days")


# ---------------------------------------------------------------- GPX -> stream
def _tag(el):
    return el.tag.rsplit("}", 1)[-1]


def _parse_time(s):
    s = s.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def haversine(lat1, lon1, lat2, lon2):
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def parse_gpx(data):
    """Return list of (t_epoch, lat, lon, ele|None, hr|None)."""
    root = ET.fromstring(data)
    pts = []
    for el in root.iter():
        if _tag(el) != "trkpt":
            continue
        try:
            lat, lon = float(el.get("lat")), float(el.get("lon"))
        except (TypeError, ValueError):
            continue
        t = ele = hr = None
        for c in el.iter():
            name = _tag(c)
            if not c.text:
                continue
            if name == "time":
                t = _parse_time(c.text)
            elif name == "ele":
                ele = float(c.text)
            elif name == "hr":
                hr = int(float(c.text))
        if t is not None:
            pts.append((t, lat, lon, ele, hr))
    pts.sort(key=lambda p: p[0])
    return pts


def to_stream(pts, summary_distance=None):
    """Cumulative distance on all points, then sample every SAMPLE_EVERY_S seconds."""
    if len(pts) < 2:
        return None
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + haversine(a[1], a[2], b[1], b[2]))
    total = cum[-1]
    scale = 1.0
    if summary_distance and total > 0:
        ratio = summary_distance / total
        if 0.85 < ratio < 1.15:          # align with Garmin's own distance
            scale = ratio
    t0 = pts[0][0]
    T, D, H, E = [], [], [], []
    last_t = None
    for i, p in enumerate(pts):
        if last_t is not None and p[0] - last_t < SAMPLE_EVERY_S and i != len(pts) - 1:
            continue
        last_t = p[0]
        T.append(int(round(p[0] - t0)))
        D.append(int(round(cum[i] * scale)))
        H.append(p[4] or 0)
        E.append(int(round(p[3] * 10)) if p[3] is not None else 0)
    return {"t": T, "d": D, "hr": H, "e": E}


# ---------------------------------------------------------------- build runs.json
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


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Incremental Garmin Connect running exporter")
    ap.add_argument("--out", default="garmin_export", help="output folder (default: garmin_export)")
    ap.add_argument("--since", help="ignore activities before YYYY-MM-DD")
    ap.add_argument("--full", action="store_true", help="re-scan the full activity list")
    ap.add_argument("--rebuild", action="store_true", help="no network: rebuild runs.json only")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between downloads")
    args = ap.parse_args()

    out = Path(args.out)
    (out / "gpx").mkdir(parents=True, exist_ok=True)
    acts_path = out / "activities.json"
    known_path = out / "seen_ids.json"
    acts = load_json(acts_path, {})
    known = set(load_json(known_path, []))

    if not args.rebuild:
        g = login()
        print("Scanning activity list...")
        new, seen = list_new_activities(g, known, args.since, args.full or not known)
        acts.update(new)
        save_json(acts_path, acts)
        # every listed id (runs and other sports) feeds the "stop at known page" rule
        known |= seen | set(acts.keys())
        save_json(known_path, sorted(known))

        todo = [aid for aid, a in acts.items()
                if has_gps(a) and not (out / "gpx" / f"{aid}.gpx").exists()]
        print(f"{len(todo)} GPX files to download")
        try:
            for n, aid in enumerate(todo, 1):
                try:
                    data = download_gpx(g, aid)
                except Exception as e:  # noqa: BLE001
                    print(f"  skip {aid}: {str(e)[:100]}")
                    continue
                (out / "gpx" / f"{aid}.gpx").write_bytes(data or b"")
                if n % 25 == 0 or n == len(todo):
                    print(f"  {n}/{len(todo)}")
                time.sleep(args.delay)
        except KeyboardInterrupt:
            print("\nStopped. Run again to continue where you left off.")

        print("Fetching resting heart rate...")
        days = [(a.get("startTimeLocal") or "")[:10] for a in acts.values()]
        first_day = args.since or min((d for d in days if d), default=None)
        try:
            update_rhr(g, out / "rhr.json", first_day)
        except KeyboardInterrupt:
            print("\nStopped. Resting HR will be fetched on the next run.")

    build_runs(out, acts)
    print(f"Done. Upload {out / 'runs.json'} to the analysis page.")


if __name__ == "__main__":
    main()
