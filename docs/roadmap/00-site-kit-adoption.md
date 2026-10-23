# 00 · Project site and shared look with site-kit

Adopt [site-kit](https://github.com/DavideBisio/site-kit), the shared design system and Pages plumbing extracted from davidebisio.github.io. Use the same plumbing as [claude-code-workflow](https://github.com/DavideBisio/claude-code-workflow) (`site/`, `pages.yml`, `project.json`).

## Requirements

- **Project site at `davidebisio.github.io/garmin-run-progress/`:**
  - an Astro + site-kit landing page;
  - docs that publish the repo's own Markdown in place: `docs/`, `docs/features/` and `docs/roadmap/`, so the site never drifts from the repo.
- **The app moves to `/garmin-run-progress/app/`.** It is still the single-file `index.html` from `tools/build.py`, copied into the site at build time. The root becomes the landing page, with an "Open the app" button.
- **Deploy:** `.github/workflows/pages.yml` calls site-kit's reusable `deploy-pages.yml`, pinned by commit SHA:
  - `site-kit` **v0.1.2**, `ef6ed2586d40a45e27228d4734d5a2abe58575d2`;
  - `python-version: "3.12"`;
  - `prebuild: python tools/build.py && npm --prefix site run app:copy`.
  - `ci.yml` keeps the tests and loses its Pages deploy job.
- **`project.json`** lists the project on the hub: name, tagline, repo, URL, status, tags and order.
- **Shared look in the app:**
  - **`<site-bar>`** at the top: project name, link to the hub, repo link and theme switch. The theme is shared with every `*.github.io` project site through `localStorage.theme`.
  - The app's own tokens (`--bg`, `--surface`, `--ink`, `--muted`, `--line`, `--accent`, `--good`, `--bad`, …) alias the kit's `--sk-*` tokens, in light and dark.
  - Fonts follow the kit's stack: Inter if present, otherwise the system UI font. **Google Fonts are removed.**
  - The **data-viz colors** (`--accent-2`, `--accent-3`, zones `--z1…--z5`) are re-derived from the brand palette and checked for contrast and color-vision distinguishability in both themes.
- **No third-party requests:** Chart.js 4.4.1 is **vendored** in the repo and inlined by `tools/build.py`. The page then works offline and makes no CDN or font requests. The charts look the same: same version, same config.
- **The release keeps working:** the `index.html` attached to a GitHub Release still works on its own, opened from disk.

## Implementation

Repo layout after this section:

```text
site/                         Astro site (site-kit init --python 3.12 --app-build … --app-dist dist)
  astro.config.mjs            base '/garmin-run-progress', siteKit({ title, repo, nav: Overview · Docs · App })
  package.json                @davidebisio/site-kit pinned to the v0.1.2 SHA; app:copy script (dist → public/app)
  src/content.config.ts       docs collection: base '../docs', pattern ['**/*.md']
  src/lib/docs.ts             sidebar groups and order: Overview · Features · Roadmap
  src/pages/index.astro       landing page
  src/pages/docs/…            docs index and [...slug] (from the template)
.github/workflows/pages.yml   uses DavideBisio/site-kit/.github/workflows/deploy-pages.yml@ef6ed25… # v0.1.2
project.json                  hub listing
src/page/js/site-bar.js       copied from site-kit src/elements/site-bar.js (v0.1.2), inlined by build.py
src/page/vendor/chart.umd.min.js  Chart.js 4.4.1 (license header kept), inlined by build.py
src/page/vendor/tokens.css   copied from site-kit src/styles/tokens.css (v0.1.2), inlined by build.py
```

Landing page (`site/src/pages/index.astro`), built from kit components:

```text
╭─ site-kit header: Davide Bisio / Run Progress Lab      Overview  Docs  App  ◐ ─╮
│                                                                              │
│  Run Progress Lab                                                    (Hero)  │
│  Measure how your running fitness changed over the years, then plan          │
│  what comes next, from your own Garmin data.                                 │
│  [Open the app]  [Read the docs]  [View source]                              │
│                                                                              │
│  What it shows                                              (FeatureGrid)    │
│  ┌ Pace at the same HR ┐ ┌ Best efforts as VDOT ┐ ┌ Training load & zones ┐  │
│  ┌ Resting HR          ┐ ┌ Aerobic decoupling   ┐ ┌ Planning (roadmap)    ┐  │
│                                                                              │
│  How it works                                                     (Steps)    │
│  1 Download garmin_grab.py   $ curl -fLO …/releases/latest/download/…        │
│  2 Run it                    $ python garmin_grab.py                         │
│  3 Drop runs.json on the app                                                 │
│                                                                              │
│  ▌Your data stays on your computer                    (Callout tone=privacy) │
│  ▌The grabber talks only to Garmin; the app runs in your browser.            │
╰─ site-kit footer ────────────────────────────────────────────────────────────╯
```

The app at `/app/`, with the shared bar above its own header (and above the tabs once 02 is done):

```text
╭─ <site-bar>: Davide Bisio / Run Progress Lab              Docs  Source  ◐ ──╮
│ Run Progress Lab                                  ● Your data · 412 runs     │
│ ┃ Data ┃   Analysis      Planning                       (tabs, section 02)   │
│ …                                                                            │
```

- **`tools/build.py`:**
  - inlines `vendor/chart.umd.min.js` in place of the cdnjs `<script>` tag;
  - fails if any `http(s)://` script or stylesheet remains in the built page, apart from links (`<a href>`);
  - `site-bar.js` is an ordinary entry in the `js/` script list and is inlined with the rest. It goes first, so the bar renders before the charts.
- **`styles.css`:** `:root { --bg: var(--sk-bg); --ink: var(--sk-ink); … }`, with the kit's `tokens.css` contents inlined at build time. The app's dark block keeps only the data-viz overrides. Theme switching already reacts to `data-theme` through `boot.js`.
- **Links:**
  - `<site-bar home="../" repo="https://github.com/DavideBisio/garmin-run-progress" wide>` with a `Docs` link to `../docs/`;
  - README, `docs/deploy.md` and the release notes point to `/app/` for the app and `/` for the site.
- **Makefile:**
  - `site-install` (`npm --prefix site ci`);
  - `site-dev` (`astro dev`);
  - `site-build`, which builds the app, copies it, then runs `astro build`;
  - `serve` stays as it is for the app alone.
- **Docs links:** the kit rewrites relative `.md` links but not other files. The relative links to `../.github/workflows/ci.yml` and `release.yml` in `docs/deploy.md` become absolute GitHub URLs.

## Testing strategy

- **CI (`ci.yml`, unchanged trigger):** the existing Python and Node tests, plus `npm --prefix site ci && make site-build`. This catches a broken site on a branch, before `main` deploys it.
- **Page tests (`tests/page.test.mjs`):**
  - the built page has no external `<script src>` or stylesheet `<link>`;
  - `Chart` is defined by the inlined bundle;
  - `site-bar` is defined exactly once;
  - the existing "loads every js file exactly once" test includes `site-bar.js`.
- **Build test:** `tools/build.py` fails on a page that still references cdnjs or Google Fonts.
- **Site build assertions**, after `make site-build`:
  - `site/dist/app/index.html` exists;
  - `site/dist/docs/features/resting-heart-rate/index.html` and `site/dist/docs/roadmap/index.html` exist;
  - no `href` in the built HTML points to a `.md` file or to `/garmin-run-progress/../`.
- **Manual:**
  - light and dark: switch on the hub, then open the app. It follows, and the reverse also works;
  - chart colors are distinguishable in both themes;
  - the release `index.html` opened from disk: charts render offline, and the bar's home link is the only broken-looking thing;
  - 360 px width.

## Completion checklist

- [ ] **Settings → Pages → Source** is already "GitHub Actions" (switched earlier). Confirm that `pages.yml` and the removed `ci.yml` deploy job don't both run in the same push, because the `pages` concurrency group would cancel one.
- [x] Pin site-kit by **SHA** in both `package.json` and `pages.yml`, with `# v0.1.2` comments. A tag can be moved. claude-code-workflow is still on v0.1.1: note it, but don't change it here.
- [x] Old links: `davidebisio.github.io/garmin-run-progress/` now shows the landing page. The page's own "Download garmin_grab.py" link points at the release, so nothing it depends on moves. Search the repo for `github.io/garmin-run-progress/` and update every one.
- [x] The kit's `tokens.css` is copied with its version in a comment. Upgrading site-kit means re-copying it together with `site-bar.js`, so write this in `docs/deploy.md`.
- [x] Chart.js: keep its MIT license header in the vendored file and in the inlined bundle. Record the version in one place that `build.py` and the docs both read.
- [x] Choose the data-viz palette with the dataviz guidance (validated categorical and sequential ramps). Zones Z1–Z5 stay a single-hue sequential ramp, now in a brand hue, and 01's legend uses the same tokens.
- [ ] `docs/README.md` becomes the docs index page. Check that its table links render as pages, and that the roadmap group lists 00–10 in order.
- [ ] `project.json` `tagline` matches the landing page lede. The hub's `loadProjects([...])` list gets `garmin-run-progress`, in the hub repo, as a follow-up outside this repo.
