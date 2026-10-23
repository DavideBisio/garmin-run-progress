# 02 · Three-tab page layout: Data, Analysis, Planning

## Requirements

- One app, three tabs, under the shared `<site-bar>` from 00 and a header that is always visible (title, short lede, data status chip):
  - **Data:**
    1. Get the grabber.
    2. Load your runs.
    3. **Your heart rate**, new: the max and resting HR inputs move here from Training, with their hint and a preview of the HRR zone table from 01. They're shared by Analysis and Planning.
  - **Analysis:** everything in today's step 3, unchanged: filters, KPIs, fitness charts, year table and the Training group.
  - **Planning:** for now, an empty state that explains how to create a plan (`make plan`, then `make grab` so it's included in `runs.json`). Section 10 fills it.
- **Default tab:**
  1. a URL hash (`#data`, `#analysis`, `#planning`) always wins;
  2. otherwise Analysis if saved data was restored from this browser;
  3. otherwise Data, on a first visit.
- Loading a file successfully switches to **Analysis**.
- Back and forward step through tabs, through the URL hash.
- **Example data:** the status chip says "Example data · Load yours", and it links to the Data tab.
- **Accessibility:** the WAI-ARIA tabs pattern: `tablist`, `tab`, `tabpanel`, arrow keys, Home and End, and a visible focus.
- **Mobile:** the tab bar is full width and sticky under the header, with no horizontal scroll at 360 px.

## Implementation

Desktop:

```text
╭──────────────────────────────────────────────────────────────────────────╮
│ Run Progress Lab                                  ● Your data · 412 runs │
│ Measure how your running fitness changed, and plan what comes next.      │
├──────────────────────────────────────────────────────────────────────────┤
│ ┃ Data ┃   Analysis      Planning                                        │
├━━━━━━━━┷─────────────────────────────────────────────────────────────────┤
│ (1) Get the grabber                                                      │
│     [Download garmin_grab.py] [Copy script] [View on GitHub]             │
│     Set up once / Run whenever you want an update  (code blocks)         │
│ (2) Load your runs                                                       │
│     ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐                          │
│       Drop runs.json here, or click to choose                            │
│     └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘                          │
│     [x] Remember in this browser   [Forget my data]                      │
│ (3) Your heart rate                                                      │
│     Max [202] / resting [50] bpm   Filled in from your data: …           │
│     Z1 <141 · Z2 141–156 · Z3 156–172 · Z4 172–187 · Z5 187+             │
╰──────────────────────────────────────────────────────────────────────────╯
```

```text
├──────────────────────────────────────────────────────────────────────────┤
│   Data    ┃ Analysis ┃    Planning                                       │
├━━━━━━━━━━━┷━━━━━━━━━━┷───────────────────────────────────────────────────┤
│ HR band [140]–[150]  Months [All year ▾]  [x] Exclude trail runs         │
│ [KPI] [KPI] [KPI] [KPI]                                                  │
│ Pace at the same heart rate ……………………………………………………………… (chart)            │
│ Best efforts as VDOT (chart)          │ Volume (chart)                   │
│ … resting HR, decoupling, cadence/stride, Training Effect, year table …  │
│ ── Training ──────────────────────────────────────────────────────────── │
│ [KPI] [KPI] [KPI]   load · load ratio · zones · weekly km · consistency  │
╰──────────────────────────────────────────────────────────────────────────╯
```

```text
├──────────────────────────────────────────────────────────────────────────┤
│   Data      Analysis   ┃ Planning ┃                                      │
├━━━━━━━━━━━━━━━━━━━━━━━━┷━━━━━━━━━━┷─────────────────────────────────────┤
│                         No plan in this file                             │
│   Plans are made on your computer, next to the grabber:                  │
│     make plan        write garmin_export/plan.md and plan.json           │
│     make push        put the workouts on your Garmin calendar            │
│     make grab        include the plan in runs.json, then load it in Data │
│                       [See the plan docs on GitHub]                      │
╰──────────────────────────────────────────────────────────────────────────╯
```

Mobile (360 px):

```text
┌────────────────────────────────┐
│ Run Progress Lab   ● 412 runs  │
├──────────┬──────────┬──────────┤  ← sticky
│   Data   │ Analysis │ Planning │
├──────────┴──────────┴──────────┤
│ panels stack in one column     │
└────────────────────────────────┘
```

- **`src/page/index.html`:**
  - the three `<section class="step">` blocks become `<div role="tablist">` plus three `<section role="tabpanel" id="tab-data|tab-analysis|tab-planning">`;
  - the max and resting HR `.controls` block moves into the Data tab;
  - all element ids stay as they are, so `state.js`, `training.js` and the tests keep working.
- **New `src/page/js/tabs.js`**, loaded after `training.js` and before `boot.js`:
  - `showTab(name, push)`: toggles `hidden` and `aria-selected`, updates `location.hash`, and resizes the visible panel's charts;
  - handles `hashchange` and the arrow keys;
  - `setData` calls `showTab("analysis")` after a user load, but not for the example data.
- **Charts in hidden panels:** Chart.js measures a `display: none` canvas as 0 × 0. `showTab` calls `charts[id].resize()` for the charts in the panel it shows. As an alternative, `render` defers creating the charts of a hidden panel until it's first shown.
- **CSS:** tab bar styles use the app tokens, which alias site-kit's `--sk-*` after 00, and follow the dark theme. On mobile, `position: sticky` sits under the header. The site bar scrolls away; only the tab bar sticks.
- **Text:**
  - the lede is shorter;
  - "load yours in step 2" becomes "load yours in Data";
  - step numbers restart inside the Data tab.
- **Docs:** update the page code map in `docs/architecture.md` (new `tabs.js`), the README screenshots and the section names in `docs/features/*.md`.

## Testing strategy

- **Node page tests:**
  - `tabs.js` is loaded exactly once, before `boot.js`;
  - the built page has three tabpanels and exactly one without `hidden` after boot;
  - `#planning` in the hash selects Planning;
  - a user `setData` switches to Analysis, while the example boot does not.
  - The DOM stub needs `location`, `history` and `addEventListener` on `window`. `tabs.js` must also survive their absence.
- **Existing tests** (all sections render, old `runs.json`, unbuilt `make dev` scripts) pass unchanged.
- **Manual:**
  - each tab in light and dark mode;
  - every chart has the right size after switching tabs and after resizing the window while on another tab;
  - keyboard only: Tab into the tab list, then arrow keys, Enter and focus moves;
  - 360 px width;
  - the back button;
  - reloading on `#planning`.

## Completion checklist

- [ ] No chart is drawn at 0 × 0: open Analysis for the first time after loading data while Data was showing.
- [x] The Data tab's "Your heart rate" is now the **only** place to set max and resting HR. The Training group's hint links to it instead of duplicating the inputs.
- [ ] Theme changes re-render the charts in hidden tabs too. They stay correct when you switch to them.
- [x] Deep links to old anchors (`#s1`, `#s2`, `#s3`) still land on the right tab.
- [ ] The built single-file `index.html` still works when opened from disk (`file://`). Hash navigation needs no server.
- [x] `tools/build.py` picks up `tabs.js` from the script tag list, and `tests/page.test.mjs` "loads every js file exactly once" passes.

The README has no screenshots, so there were none to update. The unchecked items above, and the manual checks under Testing strategy, need a browser.
