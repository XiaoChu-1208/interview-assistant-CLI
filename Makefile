.PHONY: help install dev clean lint test build check release-test release tag

PY ?= python3
PKG := interview_assistant
DIST := dist

help:
	@echo "Targets:"
	@echo "  install        pip install . (runtime only)"
	@echo "  dev            pip install -e .[all] + dev tools"
	@echo "  clean          remove dist/, build/, *.egg-info, __pycache__"
	@echo "  lint           ruff + a quick syntax sweep"
	@echo "  test           pytest tests/"
	@echo "  build          python -m build  (sdist + wheel into dist/)"
	@echo "  check          twine check dist/*"
	@echo "  release-test   upload to TestPyPI (requires ~/.pypirc or token)"
	@echo "  release        push current tag — GitHub Actions handles PyPI upload"
	@echo "  tag VERSION=x.y.z   create + push a signed git tag (vx.y.z)"

install:
	$(PY) -m pip install .

dev:
	$(PY) -m pip install -e ".[all]" build twine ruff pytest

clean:
	rm -rf $(DIST) build *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
	find . -type d -name .ruff_cache -prune -exec rm -rf {} +

lint:
	@command -v ruff >/dev/null && ruff check src/ tests/ || echo "(ruff not installed; skipping)"
	$(PY) -m compileall -q src/

test:
	$(PY) -m pytest -q tests/

build: clean
	$(PY) -m build
	@echo
	@echo "Built artifacts:"
	@ls -lh $(DIST)/

check: build
	$(PY) -m twine check $(DIST)/*
	@echo
	@echo "Inspecting wheel contents (skills + templates + locales must be present):"
	@$(PY) -c "import zipfile,glob; w=glob.glob('$(DIST)/*.whl')[0]; \
		names=zipfile.ZipFile(w).namelist(); \
		assert any('_bundled/skills/interview-knowledge-format/SKILL.md' in n for n in names), 'missing knowledge-format skill'; \
		assert any('_bundled/skills/homophone-detector/SKILL.md' in n for n in names), 'missing homophone-detector skill'; \
		assert any('_bundled/templates/knowledge.starter.md' in n for n in names), 'missing starter template'; \
		assert any('locales/zh-CN.yaml' in n for n in names), 'missing zh-CN locale'; \
		assert any('locales/en.yaml' in n for n in names), 'missing en locale'; \
		print('  OK — wheel contains skills, templates, and locales')"

release-test: check
	$(PY) -m twine upload --repository testpypi $(DIST)/*

tag:
	@test -n "$(VERSION)" || (echo "usage: make tag VERSION=0.1.1" && exit 1)
	@echo "Tagging v$(VERSION)…"
	git tag -a "v$(VERSION)" -m "Release v$(VERSION)"
	git push origin "v$(VERSION)"
	@echo
	@echo "Done. Watch the publish workflow at:"
	@echo "  https://github.com/XiaoChu-1208/interview-assistant-CLI/actions"

release:
	@echo "Releases are produced by GitHub Actions on tag push."
	@echo "Run:  make tag VERSION=0.1.0"
