.PHONY: all venv run test test-only clean

# Bootstrap / engine targets are no-ops here: the "engine" is pure Python
# (see DECISIONS.md). Kept as a convention so `make all` still means
# "everything you need to play" on a fresh clone.
all: venv

venv: .venv/bin/python
.venv/bin/python:
	python3 -m venv .venv
	.venv/bin/pip install -e .

run: venv
	.venv/bin/python play.py

# Full QA suite.
test: venv
	.venv/bin/python -m tests.qa

# Subset by pattern. Usage: make test-only PAT=merge
test-only: venv
	.venv/bin/python -m tests.qa $(PAT)

clean:
	rm -rf .venv *.egg-info tests/out/*.svg tests/out/*.png
