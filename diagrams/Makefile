# Diagram-as-code for the minicloud platform (mingrammer `diagrams` + Graphviz).
# Generated images land in ../static/img/architecture/ so Docusaurus serves them.

VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip
SRC  := src

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

$(VENV): requirements.txt ## Create the venv + install deps
	python3 -m venv $(VENV)
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements.txt

.PHONY: install
install: $(VENV) ## Install Python deps (needs system Graphviz: brew install graphviz)
	@$(PY) -c "from importlib.metadata import version; print('diagrams', version('diagrams'))"
	@command -v dot >/dev/null || { echo 'ERROR: Graphviz "dot" not found — run: brew install graphviz'; exit 1; }

.PHONY: generate
generate: install ## Render every diagram in src/ (each *.py that isn't _private) + self-contain the SVGs
	@for f in $(SRC)/[!_]*.py; do echo ">> $$f"; $(PY) "$$f"; done
	@echo ">> inlining icons so the SVGs open standalone"; $(PY) embed-svg-images.py
	@echo "Images written to ../static/img/architecture/"

.PHONY: check
check: install ## Local same-environment drift check: fail if images differ from source
	@$(MAKE) --no-print-directory generate
	@git diff --quiet -- ../static/img/architecture || { \
	  echo 'ERROR: generated diagrams are out of date — run "make generate" and commit.'; exit 1; }

.PHONY: clean
clean: ## Remove generated images
	rm -f ../static/img/architecture/*.png ../static/img/architecture/*.svg

.PHONY: distclean
distclean: clean ## Also remove the venv
	rm -rf $(VENV)
