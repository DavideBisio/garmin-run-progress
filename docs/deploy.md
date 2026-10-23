# Deploy

Two independent pieces: the grabber runs on your computer; the page is a static file that can be opened locally or hosted anywhere.

Both are built from `src/` by `tools/build.py` and are not committed. Get them from:

| Where | `garmin_grab.py` | `index.html` |
|---|---|---|
| Latest [GitHub Release](https://github.com/DavideBisio/garmin-run-progress/releases/latest) | [download](https://github.com/DavideBisio/garmin-run-progress/releases/latest/download/garmin_grab.py) | [download](https://github.com/DavideBisio/garmin-run-progress/releases/latest/download/index.html) |
| GitHub Pages | "Copy script" on the page | `https://davidebisio.github.io/garmin-run-progress/app/` (the project site and docs are at `https://davidebisio.github.io/garmin-run-progress/`) |
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

The page is one static file with everything inlined, including Chart.js and the site-kit tokens. It makes no third-party requests (no CDN, no web fonts), so it works offline, opened from disk. `tools/build.py` fails if a remote script, stylesheet or font sneaks back in.

### Option A: open locally

Download `index.html` from the latest release (or `make build` in a clone and open `dist/index.html`), then double-click it or drag it into a browser. Everything works from `file://`, offline. Only the bar's link to the project site (`../`) leads nowhere there.

### Option B: GitHub Pages

GitHub Pages serves the project site: an Astro + [site-kit](https://github.com/DavideBisio/site-kit) landing page and the repo's own `docs/` at `https://davidebisio.github.io/garmin-run-progress/`, with the app at `https://davidebisio.github.io/garmin-run-progress/app/`. The [Pages workflow](https://github.com/DavideBisio/garmin-run-progress/blob/main/.github/workflows/pages.yml) calls site-kit's reusable `deploy-pages.yml` on every push to `main`: it runs `python tools/build.py`, copies `dist/index.html` to `site/public/app/` (`npm --prefix site run app:copy`), builds `site/` and deploys it. The [CI workflow](https://github.com/DavideBisio/garmin-run-progress/blob/main/.github/workflows/ci.yml) only tests, and builds the site to catch breakage before `main`. One-time setup:

1. On GitHub: **Settings → Pages**.
2. **Source:** GitHub Actions.
3. Push to `main` (or run the Pages workflow by hand). After a minute the site is up.

Visitors load their own `runs.json`; nothing is uploaded to GitHub, and the data stays in each visitor's browser.

To work on the site locally (Node 22.23.4+): `make site-install` once, then `make site-build` (app, copy, `astro build` into `site/dist/`) and `make site-test`, or `make site-dev` for a live preview. The docs pages are the Markdown files in `docs/` as they are; links between them are rewritten to the built pages, so link other repo files with absolute GitHub URLs.

### Upgrading site-kit

site-kit is pinned by commit SHA, with a `# v0.1.2` comment, in `site/package.json` and `.github/workflows/pages.yml`; change both together. The app carries two verbatim copies from the kit: `src/page/vendor/tokens.css` and `src/page/js/site-bar.js`. Re-copy them together from the same kit version and update the version in their header comments.

Chart.js is vendored at `src/page/vendor/chart.umd.min.js` with its MIT license header. Its version lives in one place, `CHART_VERSION` in `tools/build.py`; the build checks the file's header against it. To upgrade, replace the file with the new `chart.umd.min.js`, keep the license header, and bump `CHART_VERSION`.

### Option C: any static host

Copy `index.html` (from a release or `dist/`) to Netlify, Cloudflare Pages, an S3 bucket or any web server. No server-side code or configuration is needed.

If the host sets a strict Content-Security-Policy, the page needs no third-party origins, only its inline code:

```text
script-src  'unsafe-inline'
style-src   'unsafe-inline'
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
make deploy                       # test, git push; CI tests again, pages.yml deploys main
make release VERSION=v1.2.0       # tag and push; CI publishes the release
```

Without `make`: `python tools/build.py`, `python -m unittest discover -s tests` and `node --test tests/page.test.mjs` (the site: `npm --prefix site ci`, `npm --prefix site run app:copy`, `npm --prefix site run build`, `node --test tests/site.test.mjs`); release with `git tag -a v1.2.0 -m v1.2.0 && git push origin v1.2.0`.

| Workflow | Trigger | Does |
|---|---|---|
| [`ci.yml`](https://github.com/DavideBisio/garmin-run-progress/blob/main/.github/workflows/ci.yml) | every push and pull request | `make test`, then `make site-build site-test` |
| [`pages.yml`](https://github.com/DavideBisio/garmin-run-progress/blob/main/.github/workflows/pages.yml) | a push to `main` | site-kit's `deploy-pages.yml`: builds the app and the site, deploys it to Pages |
| [`release.yml`](https://github.com/DavideBisio/garmin-run-progress/blob/main/.github/workflows/release.yml) | a pushed `v*` tag | `make test`, then a GitHub Release with `garmin_grab.py` and `index.html` attached, notes pointing to the app (`/app/`) and the site (`/`), and generated notes |

The page's "Download garmin_grab.py" button and the install commands above point at `releases/latest`, so they serve the grabber from the newest release, not from `main`. Cut a release after changing the grabber.

If you change the [runs.json format](runs-json-format.md) incompatibly, bump `format` to `garmin-runs/2` and tell users to run `python garmin_grab.py --rebuild` (delete `garmin_export/cache/` first if the stream encoding changed).
