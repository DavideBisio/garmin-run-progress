# Deploy

Two independent pieces: the grabber runs on your computer; the page is a static file that can be opened locally or hosted anywhere.

Both are built from `src/` by `tools/build.py` and are not committed. Get them from:

| Where | `garmin_grab.py` | `index.html` |
|---|---|---|
| Latest [GitHub Release](https://github.com/DavideBisio/garmin-run-progress/releases/latest) | [download](https://github.com/DavideBisio/garmin-run-progress/releases/latest/download/garmin_grab.py) | [download](https://github.com/DavideBisio/garmin-run-progress/releases/latest/download/index.html) |
| GitHub Pages | "Copy script" on the page | `https://davidebisio.github.io/garmin-run-progress/` |
| A clone | `make build` → `dist/garmin_grab.py`, or run it unbundled with `make grab` | `make build` → `dist/index.html` |

## 1. Grabber

### Install

Python 3.12 or later is required. Put `garmin_grab.py` in a folder of its own (your data is written next to it, in `garmin_export/`):

```bash
mkdir garmin-run-progress && cd garmin-run-progress
curl -fLO https://github.com/DavideBisio/garmin-run-progress/releases/latest/download/garmin_grab.py
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade garminconnect curl_cffi ua-generator
```

On Debian/Ubuntu the venv is mandatory (the system Python is externally managed).

From a clone, `make install` creates the venv and installs the library.

### First run

```bash
python garmin_grab.py              # from a clone: make grab
```

Enter your Garmin email, password and MFA code when asked. Tokens are saved to `~/.garminconnect/garmin_tokens.json` (mode 0600). Expect 1–2 hours for ten years of runs; Ctrl-C is safe at any point.

To avoid typing the email each time, set `GARMIN_EMAIL`. The password is always prompted and never stored.

### Scheduling updates

Once tokens exist, later runs are non-interactive and take seconds. Schedule a daily run if you like. The examples use the folder where you saved `garmin_grab.py`.

In a clone, schedule `make grab` instead: it runs the grabber straight from `src/`, so `git pull` keeps it up to date. For example, `17 6 * * * cd /path/to/clone && make grab >> grab.log 2>&1`. For launchd and Task Scheduler, run `make` with the argument `grab`. Don't schedule `dist/garmin_grab.py`: `make clean` deletes it and it goes stale after a pull. Jobs set up in a clone before the code moved to `src/` ran `garmin_grab.py` from the repo root. That file is gone, so switch them to `make grab`.

**Linux / macOS (cron)** — `crontab -e`:

```cron
# every day at 06:17
17 6 * * * cd /path/to/garmin-run-progress && .venv/bin/python garmin_grab.py >> grab.log 2>&1
```

**macOS (launchd)** — save as `~/Library/LaunchAgents/local.garmin-run-progress.plist`, then `launchctl load` it:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>local.garmin-run-progress</string>
  <key>WorkingDirectory</key><string>/path/to/garmin-run-progress</string>
  <key>ProgramArguments</key><array>
    <string>/path/to/garmin-run-progress/.venv/bin/python</string>
    <string>garmin_grab.py</string>
  </array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>17</integer></dict>
  <key>StandardOutPath</key><string>/path/to/garmin-run-progress/grab.log</string>
  <key>StandardErrorPath</key><string>/path/to/garmin-run-progress/grab.log</string>
</dict></plist>
```

**Windows (Task Scheduler)** — in PowerShell:

```powershell
$dir = "C:\path\to\garmin-run-progress"
$action  = New-ScheduledTaskAction -Execute "$dir\.venv\Scripts\python.exe" -Argument "garmin_grab.py" -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -Daily -At 6:17am
Register-ScheduledTask -TaskName "Garmin run progress" -Action $action -Trigger $trigger
```

If a scheduled run ever needs credentials again (revoked token), it will wait for input and fail. Run it once by hand to log in again.

### Upgrading

Garmin changes its login from time to time. When the grabber starts failing at login:

```bash
pip install --upgrade garminconnect curl_cffi ua-generator     # from a clone: make upgrade
```

If that doesn't help, download the latest `garmin_grab.py` and check the [python-garminconnect issues](https://github.com/cyberjunky/python-garminconnect/issues).

## 2. Analysis page

The page is one static file. It loads fonts from Google Fonts and Chart.js from cdnjs, so it needs internet access to display charts.

### Option A: open locally

Download `index.html` from the latest release (or `make build` in a clone and open `dist/index.html`), then double-click it or drag it into a browser. Everything works from `file://`.

### Option B: GitHub Pages

The [CI workflow](../.github/workflows/ci.yml) builds and tests every push and deploys `dist/` from `main`. One-time setup:

1. On GitHub: **Settings → Pages**.
2. **Source:** GitHub Actions.
3. Push to `main` (or run the CI workflow by hand). After a minute the page is at `https://davidebisio.github.io/garmin-run-progress/`.

The site contains `index.html` and `garmin_grab.py`. Visitors load their own `runs.json`; nothing is uploaded to GitHub, and the data stays in each visitor's browser.

### Option C: any static host

Copy `index.html` (from a release or `dist/`) to Netlify, Cloudflare Pages, an S3 bucket or any web server. No server-side code or configuration is needed.

If the host sets a strict Content-Security-Policy, allow:

```text
script-src  'unsafe-inline' https://cdnjs.cloudflare.com
style-src   'unsafe-inline' https://fonts.googleapis.com
font-src    https://fonts.gstatic.com
```

### Option D: claude.ai artifact

The same page can be published as a private claude.ai artifact. There, the `downloads` capability enables the "Download grabber (.zip)" button (see [grabber-download](features/grabber-download.md)). Elsewhere that button stays hidden.

## Releasing a change

Edit the sources in `src/` (see [Source layout and build](architecture.md#source-layout-and-build)), then:

```bash
make dev                          # serve src/page on localhost:8000 while you edit the page
make test                         # build dist/, run all tests
git add src tools tests docs      # name paths: never `git add -A` in a folder with your data
git commit -m "..."
make deploy                       # test, git push; CI tests again and deploys main to Pages
make release VERSION=v1.2.0       # tag and push; CI publishes the release
```

Without `make`: `python tools/build.py`, `python -m unittest discover -s tests` and `node --test tests/page.test.mjs`; release with `git tag -a v1.2.0 -m v1.2.0 && git push origin v1.2.0`.

| Workflow | Trigger | Does |
|---|---|---|
| [`ci.yml`](../.github/workflows/ci.yml) | every push and pull request | `make test`; on `main` also deploys `dist/` to Pages |
| [`release.yml`](../.github/workflows/release.yml) | a pushed `v*` tag | `make test`, then a GitHub Release with `garmin_grab.py` and `index.html` attached and generated notes |

The page's "Download garmin_grab.py" button and the install commands above point at `releases/latest`, so they serve the grabber from the newest release, not from `main`. Cut a release after changing the grabber.

If you change the [runs.json format](runs-json-format.md) incompatibly, bump `format` to `garmin-runs/2` and tell users to run `python garmin_grab.py --rebuild` (delete `garmin_export/cache/` first if the stream encoding changed).
