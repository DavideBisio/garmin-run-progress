# Incremental grabber

File: `garmin_grab.py` — `login`, `with_retry`, `list_new_activities`, `download_gpx`, `update_rhr`, `main`.

After the GPX downloads, `update_rhr` fetches daily resting heart rate; see [resting heart rate](resting-heart-rate.md).

## Login

```text
Garmin().login(TOKENSTORE)            # try saved tokens
  └─ fails → ask email (or $GARMIN_EMAIL), password (getpass), MFA via prompt_mfa
           → Garmin(email, password, prompt_mfa=...).login(TOKENSTORE)
```

- `TOKENSTORE` is `~/.garminconnect`, overridable with `$GARMINTOKENS`.
- python-garminconnect ≥ 0.3 stores `garmin_tokens.json` there and refreshes tokens automatically, so credentials are only asked again if the refresh token is revoked or expires.
- The password is never written to disk or read from an environment variable.

## Incremental listing

Garmin returns activities newest-first via `get_activities(start, limit)`. The grabber pages through them 100 at a time.

```text
for each page:
    for each activity:
        skip if older than --since
        add id to `seen`
        if id not in known  → page is not fully known
        if it is a run      → remember its summary
    stop if: page empty, OR --since reached, OR (page fully known AND not --full)
```

`known` is loaded from `garmin_export/seen_ids.json` and contains every activity id ever listed, **including other sports**. That is what makes the stop rule work: if only run ids were tracked, a page with a bike ride would never look "fully known" and every run would rescan the whole history.

The first run (empty `known`) always does a full scan. `--full` forces one later, which is useful after deleting `seen_ids.json` or to pick up activities you edited from another sport into a run.

State is saved right after listing, before downloads start:

- `activities.json`: id → full Garmin summary for every run
- `seen_ids.json`: sorted list of every listed id

### What counts as a run

`is_run`: `activityType.typeKey` contains `run` (running, trail_running, treadmill_running, track_running, street_running, indoor_running, virtual_run, ultra_run…).

`has_gps`: false for type keys containing `treadmill`, `indoor` or `virtual`, or when Garmin says `hasPolyline: false`. These runs keep their summary (volume, VO2max) but no GPX is requested.

## GPX download

```text
todo = runs with GPS whose garmin_export/gpx/<id>.gpx does not exist
for each: download_activity(id, dl_fmt=GPX) → write file → sleep --delay (default 1 s)
```

Because the to-do list is derived from files on disk, any interruption is recoverable: Ctrl-C prints a message and the next run downloads only the missing files. An individual failed download is logged and skipped; it will be retried on the next run.

## Retries

`with_retry` wraps every network call: up to 4 attempts, waiting 5, 10, 15 s, or 60 s when the error mentions `429` / `Too Many`. `KeyboardInterrupt` is never swallowed.

## Timing

About 2 s per run (request plus delay). 2,500 runs ≈ 1.5 hours the first time. Later runs list one page, download a handful of files and rebuild `runs.json` from cache in a few seconds.

## Atomic writes

`save_json` writes to `<file>.tmp` and renames it, so an interrupted run never leaves a half-written JSON file.
