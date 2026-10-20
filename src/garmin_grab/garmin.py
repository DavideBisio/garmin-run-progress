"""Garmin Connect: login, retries, activity list, GPX download."""
import getpass
import os
import sys
import time

from .activities import is_run
from .config import PAGE, TOKENSTORE


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
