COMPONENT := custom_components/yttv
VERSION := $(shell python3 -c "import json; print(json.load(open('$(COMPONENT)/manifest.json'))['version'])")

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

.PHONY: version
version: ## Print the manifest version
	@echo $(VERSION)

.PHONY: check
check: ## Validate JSON manifests and byte-compile the component
	@python3 -m json.tool $(COMPONENT)/manifest.json >/dev/null && echo "manifest.json ok"
	@python3 -m json.tool hacs.json >/dev/null && echo "hacs.json ok"
	@python3 -m compileall -q $(COMPONENT) && echo "compile ok"

.PHONY: release
release: check ## Tag the manifest version, publish a GitHub release (gh), then start the next patch version
	@git diff --quiet HEAD || { echo "working tree dirty — commit first"; exit 1; }
	@git rev-parse "v$(VERSION)" >/dev/null 2>&1 && { echo "tag v$(VERSION) already exists"; exit 1; } || true
	git push
	gh release create "v$(VERSION)" --title "v$(VERSION)" --generate-notes
	@git rev-parse -q --verify "refs/tags/v$(VERSION)" >/dev/null || git fetch origin tag "v$(VERSION)"
	@echo "released v$(VERSION)"
	@next=$$(echo $(VERSION) | awk -F. -v OFS=. '{$$NF += 1; print}'); \
		python3 -c "import re, sys; p = sys.argv[1]; s = open(p).read(); open(p, 'w').write(re.sub(r'(\"version\": \")[^\"]*', r'\g<1>' + sys.argv[2], s))" $(COMPONENT)/manifest.json "$$next"; \
		git commit -q -m "Start $$next" $(COMPONENT)/manifest.json; \
		echo "version is now $$next (committed, not pushed)"
