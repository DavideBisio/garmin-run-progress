# Dev, test and deploy tasks (see docs/deploy.md). Run `make help` for the list.
# Works with GNU make on Linux, macOS and Windows (Git Bash or any sh in PATH).

ifeq ($(OS),Windows_NT)
  PY      ?= python
  VENV_PY := .venv/Scripts/python.exe
else
  PY      ?= python3
  VENV_PY := .venv/bin/python
endif
NODE ?= node
PORT ?= 8000
ARGS ?=
VERSION ?=
DEPS := garminconnect curl_cffi ua-generator

# run the grabber and planner packages straight from src/ (python -m garmin_grab, -m garmin_plan)
export PYTHONPATH := src

# fail before the tests run, not after
ifneq ($(filter release,$(MAKECMDGOALS)),)
  ifeq ($(VERSION),)
    $(error usage: make release VERSION=v1.0.0)
  endif
endif

.DEFAULT_GOAL := help
.PHONY: help install upgrade grab rebuild plan-profile plan build dev serve test test-py test-js site-install site-dev site-build site-test deploy release clean

help: ## list the targets
	@$(PY) -c "import re; [print(f'  make {m[1]:<13} {m[2]}') for m in re.finditer(r'^([a-z-]+):.*?## (.*)$$', open('Makefile').read(), re.M)]"
	@echo "  Pass grabber options with ARGS, e.g. make grab ARGS=\"--since 2016-01-01\""

# ---------------------------------------------------------------- grabber
$(VENV_PY):
	$(PY) -m venv .venv
	$(VENV_PY) -m pip install --upgrade $(DEPS)

install: $(VENV_PY) ## create .venv and install the Garmin library

upgrade: $(VENV_PY) ## upgrade the Garmin library (when login starts failing)
	$(VENV_PY) -m pip install --upgrade $(DEPS)

grab: $(VENV_PY) ## fetch new runs and rebuild garmin_export/runs.json
	$(VENV_PY) -m garmin_grab $(ARGS)

rebuild: ## rebuild runs.json from local files, no network
	$(PY) -m garmin_grab --rebuild $(ARGS)

# ---------------------------------------------------------------- planner
plan-profile: ## print the runner profile (garmin_export/profile.toml + runs.json)
	$(PY) -m garmin_plan profile $(ARGS)

plan: ## write garmin_export/plan.json and plan.md from profile.toml's [week] (ARGS="--weeks 4")
	$(PY) -m garmin_plan plan $(ARGS)

# ---------------------------------------------------------------- page
build: ## build dist/garmin_grab.py and dist/index.html from src/
	$(PY) tools/build.py

dev: ## serve the unbuilt src/page on localhost:8000 (edit, then reload)
	$(PY) -m http.server $(PORT) --bind 127.0.0.1 --directory src/page

serve: build ## serve the built dist/ on localhost:8000
	$(PY) -m http.server $(PORT) --bind 127.0.0.1 --directory dist

# ---------------------------------------------------------------- project site (site/, Astro + site-kit)
site-install: ## install the site's dependencies (npm ci in site/)
	npm --prefix site ci

site-dev: ## serve the project site with live reload (run site-build once first for /app/)
	npm --prefix site run dev

site-build: build ## build the app, copy it to site/public/app, then build the site into site/dist
	npm --prefix site run app:copy
	npm --prefix site run build

site-test: ## check the built site/dist (run site-build first)
	$(NODE) --test tests/site.test.mjs

# ---------------------------------------------------------------- test & deploy
test: build test-py test-js ## build, then run all tests

test-py: ## grabber, planner and build unit tests
	$(PY) -m unittest discover -s tests

test-js: build ## page smoke tests on dist/ and metric parity vectors (Node 20.11+)
	$(NODE) --test tests/page.test.mjs tests/metrics.test.mjs

deploy: test ## test, then push; pushing main deploys the project site (pages.yml)
	git push

release: test ## tag and push VERSION (e.g. make release VERSION=v1.0.0); CI publishes the release
	git tag -a $(VERSION) -m "$(VERSION)"
	git push origin $(VERSION)

clean: ## remove dist/, site/dist/ and Python caches
	$(PY) -c "import pathlib, shutil; [shutil.rmtree(p) for p in [pathlib.Path('dist'), pathlib.Path('site/dist'), *pathlib.Path('.').rglob('__pycache__')] if p.exists() and '.venv' not in p.parts and 'node_modules' not in p.parts]"
