ACP_SRC := $(HOME)/.emacs.d/elpaca/sources/acp
TEST_FILE := $(CURDIR)/tests/mock-acp-integration-test.el

.PHONY: build
build: ## Initialize submodules and sync Python dependencies
	git submodule update --init --recursive
	uv sync

.PHONY: test-integration
test-integration: ## Run the ACP integration tests via ERT
	@emacs -Q --batch \
		-L "$(ACP_SRC)" \
		-L "$(dir $(TEST_FILE))" \
		-l "$(TEST_FILE)" \
		--eval "(ert-run-tests-batch-and-exit t)"

.PHONY: help
help:
	@awk -F '## ' '/^[A-Za-z_-]+:.*##/ { target = $$1; sub(/:.*/, "", target); printf "\033[36m%-20s\033[0m %s\n", target, $$2 }' $(MAKEFILE_LIST)

.DEFAULT_GOAL := help
