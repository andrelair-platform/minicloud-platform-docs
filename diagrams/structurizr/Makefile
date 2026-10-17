# C4 System Design as code — Structurizr DSL → PlantUML → clean SVG.
# Both tools run via Docker (no local Java). Output → the Docusaurus static tree.

OUT := ../../static/img/c4
DSL := workspace.dsl

.DEFAULT_GOAL := c4

.PHONY: c4 validate clean
validate: ## Validate the DSL only
	docker run --rm -v "$(CURDIR)":/w -w /w structurizr/structurizr validate -workspace $(DSL)

c4: ## Export the DSL to PlantUML, render clean SVGs, copy to static/img/c4/
	rm -rf build && mkdir -p build "$(OUT)"
	docker run --rm -v "$(CURDIR)":/w -w /w structurizr/structurizr export -workspace $(DSL) -format plantuml -output build
	docker run --rm -v "$(CURDIR)/build":/w plantuml/plantuml -tsvg "/w/*.puml"
	cp build/*.svg "$(OUT)/"
	@echo "C4 SVGs → $(OUT)/ :"; ls "$(OUT)"

clean: ## Remove the build dir
	rm -rf build
