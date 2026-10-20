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
