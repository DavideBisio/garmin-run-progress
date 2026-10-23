"""Daily HRV status and training readiness (optional: skipped when the library lacks the call).

hrv.json is {date: status} ("BALANCED", "UNBALANCED", "LOW", ...), fetched in ranges like resting
HR; readiness.json is {date: {level, score}}, one request a day, so the first fetch and any long
gap stop at the last READINESS_FIRST_DAYS days. The response shapes are parsed defensively: a
missing field leaves the day out (HRV) or null (readiness), never an error.
"""
import time
from datetime import date, timedelta

from .config import HRV_CHUNK_DAYS, READINESS_FIRST_DAYS, WELLNESS_REFRESH_DAYS
from .garmin import with_retry
from .storage import load_json, save_json

UPGRADE_HINT = "needs a newer library (pip install --upgrade garminconnect)"


def hrv_statuses(resp):
    """{date: status} from an HRV response: {"hrvSummaries": [...]}, {"hrvSummary": {...}} or a list
    of summaries, each {"calendarDate", "status"}; anything else is skipped."""
    if isinstance(resp, dict):
        rows = resp.get("hrvSummaries")
        if rows is None:
            rows = [resp.get("hrvSummary", resp)]
    else:
        rows = resp
    out = {}
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and isinstance(row.get("calendarDate"), str) and isinstance(row.get("status"), str):
            out[row["calendarDate"][:10]] = row["status"]
    return out


def readiness_entry(resp):
    """{level, score} of a training readiness response (a list of the day's readings, the morning
    one preferred, or one dict); None without a level or a score."""
    rows = resp if isinstance(resp, list) else [resp]
    rows = [r for r in rows if isinstance(r, dict)
            and (isinstance(r.get("level"), str) or isinstance(r.get("score"), (int, float)))]
    if not rows:
        return None
    row = next((r for r in rows if r.get("inputContext") == "AFTER_WAKEUP_RESET"), rows[0])
    level, score = row.get("level"), row.get("score")
    return {"level": level if isinstance(level, str) else None,
            "score": round(score) if isinstance(score, (int, float)) and not isinstance(score, bool) else None}


def wellness_start(known, first_day):
    """The first day to fetch: the last known day minus the refresh window, else first_day; None
    when there is nothing to start from."""
    if known:
        return date.fromisoformat(max(known)) - timedelta(days=WELLNESS_REFRESH_DAYS)
    return date.fromisoformat(first_day) if first_day else None


def update_hrv(g, path, first_day):
    """Fetch HRV status in HRV_CHUNK_DAYS ranges from first_day (or the last known day) to today."""
    if not hasattr(g, "get_hrv_data_range"):
        print(f"  HRV status skipped: {UPGRADE_HINT}")
        return
    hrv = load_json(path, {})
    start = wellness_start(hrv, first_day)
    if start is None:
        return
    end = date.today()
    while start <= end:
        stop = min(start + timedelta(days=HRV_CHUNK_DAYS - 1), end)
        try:
            hrv.update(hrv_statuses(with_retry(g.get_hrv_data_range, start.isoformat(), stop.isoformat())))
        except Exception as e:  # noqa: BLE001
            print(f"  HRV status {start} to {stop} skipped: {str(e)[:100]}")
        start = stop + timedelta(days=1)
        time.sleep(0.5)
    save_json(path, hrv)
    print(f"  HRV status: {len(hrv)} days")


def update_readiness(g, path, first_day):
    """Fetch training readiness one day at a time, at most the last READINESS_FIRST_DAYS days."""
    if not hasattr(g, "get_training_readiness"):
        print(f"  training readiness skipped: {UPGRADE_HINT}")
        return
    ready = load_json(path, {})
    start = wellness_start(ready, first_day)
    if start is None:
        return
    end = date.today()
    start = max(start, end - timedelta(days=READINESS_FIRST_DAYS - 1))
    while start <= end:
        try:
            entry = readiness_entry(with_retry(g.get_training_readiness, start.isoformat()))
        except Exception as e:  # noqa: BLE001
            print(f"  training readiness {start} skipped: {str(e)[:100]}")
            entry = None
        if entry:
            ready[start.isoformat()] = entry
        start += timedelta(days=1)
        time.sleep(0.5)
    save_json(path, ready)
    print(f"  training readiness: {len(ready)} days")


def update_wellness(g, out, first_day):
    """HRV status into out/hrv.json and training readiness into out/readiness.json, each skipped on
    its own (with a hint) when the client lacks its method."""
    update_hrv(g, out / "hrv.json", first_day)
    update_readiness(g, out / "readiness.json", first_day)
