# Postcodejager — common local tasks. Run `make help` for the list.
PY := .venv/bin/python

.DEFAULT_GOAL := help
.PHONY: help install fetch fetch-basemap run test

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Create the venv and install the app with dev deps
	python3 -m venv .venv
	$(PY) -m pip install -e ".[dev]"

fetch: ## Download the CBS PC4 boundaries into data/
	$(PY) scripts/fetch_pc4.py

fetch-basemap: ## Extract the NL Protomaps basemap into data/ (needs the pmtiles CLI + a PLANET_URL)
	$(PY) scripts/fetch_basemap.py $(PLANET_URL)

run: ## Run the app locally at http://localhost:8000
	$(PY) -m postcodejager

test: ## Run the test suite
	$(PY) -m pytest
