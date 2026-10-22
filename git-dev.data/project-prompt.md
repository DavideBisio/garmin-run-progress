# PLACEHOLDER: project-specific prompt

Read by every step before it starts. Describe project conventions, terminology and constraints here.

The four sections below are read individually, at the exact point each is needed, via
`handoff_manager.py prompt-section "<heading>"` — not just once at Setup. A section that is
deleted, or still holds only its `<placeholder>` lines, is treated as unset: every reader falls
back to the default noted under it. `Branching strategy` ships with real values, which are used
as written until you change them.

## Branching strategy
- source_branch: dev
- target_branch: main
- branch_pattern:
  - new feature: `feat/<iid>-<slug>`
  - fix to an existing feature: `fix/<iid>-<slug>`
  - else: `docs/<iid>-<slug>` or `chore/<iid>-<slug>`
- branching flow:
  1. always start from source_branch
  2. work on feat/fix/docs/chore branches cut from source_branch
  3. PR back to target_branch once work is done
  4. merge target_branch back into source_branch after the PR merges
- exception — training plan generator roadmap (issues #3–#13, see docs/roadmap/):
  all of these commit on one shared branch `feat/training-planner`, cut from source_branch,
  instead of per-issue branches. Do not open a merge request per issue; PRs to target_branch are
  opened per group: #3–#5 (foundation), #6–#10 (planner core), #11–#13 (adaptation + UI).
<!-- Default if this section is missing: source_branch=dev, target_branch=main, branch_pattern=fix/<iid>-<slug>. -->

## Issue labels
- enhancement: new feature or request → `feat/` branch
- bug: something isn't working → `fix/` branch
- documentation: docs-only change → `docs/` branch
- accessibility: barrier affecting people with disabilities (combine with enhancement/bug)
- question, duplicate, invalid, wontfix, good first issue, help wanted: triage only, not work types
<!-- Default if unchanged or missing: no special label handling beyond what each provider already assumes. -->

## Test commands
- unit (grabber, Python): `make test-py` (runs `python -m unittest discover -s tests` with PYTHONPATH=src)
- page smoke tests (Node 20.11+): `make test-js` (builds dist/ via tools/build.py, then `node --test tests/page.test.mjs`)
- full suite, as CI runs it: `make test`
<!-- Default if unchanged or missing: none assumed; git-dev-execute asks rather than guessing. -->

## Pre-PR checklist
- `make test` passes
- README.md / docs/ updated when user-facing behavior changes
- the issue's section in docs/roadmap/ updated to reflect what shipped
- no version bump: releases are tagged separately with `make release VERSION=vX.Y.Z`
<!-- Default if unchanged or missing: no extra checklist items beyond the merge request itself. -->
