# Working on this project in Codex

Read README.md and docs/design.md before changing behavior.

Keep the manifest strict and deterministic. No timestamps, generated run IDs, or absolute
paths belong in it. Keep --expected-digest mandatory for run, verify, and release.
The digest must come from freeze-time approval, not from recomputing a changed manifest.

Use Inspect's public log APIs. Check real model events and sample/epoch multiplicity.
Never replace the actual Inspect mock-provider integration tests with fabricated JSON.
Preserve all eight error categories and their negative tests.
Keep the default path free of paid APIs, credentials, and external network calls.
When extending task semantics, version the adapter and manifest schema as needed.
Do not silently accept new solver, scorer, provider-routing, or generation options.

Run `ruff check .`, `ruff format --check .`, and `pytest -q` after code changes.
Run `python -m build` for packaging changes and `python examples/demo.py` from a clean
committed repository for lifecycle changes. Generated outputs belong under .integrity/.
Do not hide failed assertions by weakening the verifier.
