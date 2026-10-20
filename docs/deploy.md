# Deploy

Two independent pieces: the grabber runs on your computer; the page is a static file that can be opened locally or hosted anywhere.

## 1. Grabber

### Install

Python 3.12 or later is required.

```bash
git clone https://github.com/DavideBisio/garmin-run-progress
cd garmin-run-progress
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade garminconnect curl_cffi ua-generator
```

On Debian/Ubuntu the venv is mandatory (the system Python is externally managed).

### First run

```bash
python garmin_grab.py
```

Enter your Garmin email, password and MFA code when asked. Tokens are saved to `~/.garminconnect/garmin_tokens.json` (mode 0600). Expect 1–2 hours for ten years of runs; Ctrl-C is safe at any point.

To avoid typing the email each time, set `GARMIN_EMAIL`. The password is always prompted and never stored.

### Scheduling updates

Once tokens exist, later runs are non-interactive and take seconds. Schedule a daily run if you like.

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

### Upgrading the Garmin library

Garmin changes its login from time to time. When the grabber starts failing at login:

```bash
pip install --upgrade garminconnect curl_cffi ua-generator
```

If that doesn't help, check the [python-garminconnect issues](https://github.com/cyberjunky/python-garminconnect/issues).

## 2. Analysis page

The page is one static file with no build step. It loads fonts from Google Fonts and Chart.js from cdnjs, so it needs internet access to display charts.

### Option A: open locally

Double-click `index.html`, or drag it into a browser. Everything works from `file://`.

### Option B: GitHub Pages

1. On GitHub: **Settings → Pages**.
2. **Source:** Deploy from a branch. **Branch:** `main`, folder `/ (root)`. Save.
3. After a minute the page is at `https://davidebisio.github.io/garmin-run-progress/`.

Visitors load their own `runs.json`; nothing is uploaded to GitHub, and the data stays in each visitor's browser.

`docs/` is plain Markdown. GitHub renders it in the repository view; it is not part of the Pages site unless you choose `/docs` as the Pages folder (don't, or `index.html` won't be served).

### Option C: any static host

Copy `index.html` to Netlify, Cloudflare Pages, an S3 bucket or any web server. No server-side code or configuration is needed.

If the host sets a strict Content-Security-Policy, allow:

```text
script-src  'unsafe-inline' https://cdnjs.cloudflare.com
style-src   'unsafe-inline' https://fonts.googleapis.com
font-src    https://fonts.gstatic.com
```

### Option D: claude.ai artifact

The same page can be published as a private claude.ai artifact. There, the `downloads` capability enables the "Download grabber (.zip)" button (see [grabber-download](features/grabber-download.md)). Elsewhere that button stays hidden.

## Releasing a change

`index.html` embeds a copy of `garmin_grab.py`. After editing the script:

```bash
python tools/embed_grabber.py          # copy the script into index.html
python tools/embed_grabber.py --check  # verify (exit code 1 if out of date)
git add garmin_grab.py index.html
git commit -m "..."
git push
```

GitHub Pages redeploys automatically on push.

If you change the [runs.json format](runs-json-format.md) incompatibly, bump `format` to `garmin-runs/2` and tell users to run `python garmin_grab.py --rebuild` (delete `garmin_export/cache/` first if the stream encoding changed).
