"""Command line: list, download, fetch resting HR, rebuild runs.json."""
import argparse
import time
from pathlib import Path

from .activities import has_gps
from .export import build_runs
from .garmin import download_gpx, list_new_activities, login
from .rhr import update_rhr
from .storage import load_json, save_json


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
