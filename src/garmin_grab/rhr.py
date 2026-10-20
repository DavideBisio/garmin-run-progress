"""Daily resting heart rate."""
import time
from datetime import date, timedelta

from .config import RHR_CHUNK_DAYS, RHR_REFRESH_DAYS
from .garmin import with_retry
from .storage import load_json, save_json


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
