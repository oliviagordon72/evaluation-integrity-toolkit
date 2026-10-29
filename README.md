# Evaluation Integrity Toolkit

An installable Python CLI that freezes evaluation intent, runs a real Inspect AI task,
checks the resulting native log, and exports a bundle only after verification passes.
The included demonstration runs without provider credentials or API calls.

## Start here

Use Python 3.12 and Git. On your Windows machine, these commands work in WSL Ubuntu.
Extract the project, open its folder in VS Code, and run:

```bash
cd evaluation-integrity
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements.lock -e '.[dev]'
git init
git add .
git commit -m "Add evaluation integrity toolkit"
pytest -q
python examples/demo.py
```

Git may ask you to configure your name and email before the first commit. If you are
already using a Git repository, commit the project there and run commands from its root.
The demo expects this project directory itself to be the Git root. Do not nest it inside
another repository without adjusting the dataset paths and demo root.

The demo freezes three samples across two epochs, calls Inspect's `mockllm` provider,
releases a verified ZIP, removes one logged sample, and proves that the second release
fails with `COVERAGE`. Outputs go under `.integrity/demo-*/`.

## What the CLI does

| Command | Result |
| --- | --- |
| `eit freeze` | Strict manifest with deterministic selection, explicit settings, hashes, Git revision, and runtime versions |
| `eit run` | Preflight checks, actual Inspect execution, and post-run verification |
| `eit verify` | Independent verification of an existing native Inspect log |
| `eit release` | Verification followed by an atomic ZIP export; failures create no bundle |

All four commands also work as `python -m eval_integrity ...`.
Success writes JSON to stdout. Integrity failures write JSON to stderr and exit 1.
Invalid arguments, file errors, or invalid command settings exit nonzero.
New manifests, log directories, and release bundles refuse to overwrite existing paths.

## Manual walkthrough

Keep your working tree clean. Generated files should stay in the ignored `.integrity/`
directory. The manifest is not committed after freeze, because a new commit would change
the revision it binds.

```bash
eit freeze --dataset examples/dataset.jsonl --model mockllm/model \
  --seed 42 --epochs 2 --artifact examples/rubric.txt \
  --out .integrity/manifest.json
```

Copy the returned `sha256` into `APPROVED_DIGEST` below. Preserve it separately from the
manifest, for example in a review record or protected CI configuration. Recomputing the
digest from whatever manifest currently exists defeats this check.

```bash
export APPROVED_DIGEST='paste-the-freeze-output-sha256-here'

eit run --manifest .integrity/manifest.json \
  --expected-digest "$APPROVED_DIGEST" --log-dir .integrity/run-1
```

Copy the `log` path printed by `run`:

```bash
export RUN_LOG='paste-the-log-path-here'

eit verify --manifest .integrity/manifest.json \
  --expected-digest "$APPROVED_DIGEST" --log "$RUN_LOG"

eit release --manifest .integrity/manifest.json \
  --expected-digest "$APPROVED_DIGEST" --log "$RUN_LOG" \
  --out .integrity/release.zip
```

The ZIP contains `manifest.json`, the exact verified `run.eval` bytes,
`verification.json`, and `SHA256SUMS.json`. The command also returns a digest of the
whole ZIP. This is a local export gate. It does not publish to GitHub or prevent someone
from manually copying an unverified log elsewhere.

## Eight failure categories

| Code | Examples rejected |
| --- | --- |
| `MANIFEST` | Changed manifest, untrusted digest, mismatched run binding |
| `DATASET` | Changed dataset bytes, logged target/input, or submitted model prompt |
| `ARTIFACT` | Changed declared artifact bytes or installed toolkit source |
| `GIT` | Dirty repository, changed HEAD, inconsistent recorded revision |
| `MODEL` | Wrong provider/model string, changed per-call model, unsupported routing |
| `GENERATION` | Changed planned or per-call settings, unexpected generation overrides |
| `COVERAGE` | Missing, duplicate, extra, or wrong-epoch samples; changed selection |
| `EXECUTION` | Incomplete/failed logs, sample errors, missing scores, changed solver/scorer, runtime drift |

The verifier stops at the first detected failure. If several things change together,
the reported category depends on check order. The test suite isolates each category.

## Dataset and task contract

Each JSONL row has exactly three string fields: `id`, `input`, and `target`.
IDs must be unique. Unknown fields, duplicate JSON object keys, empty datasets, and
escaping file paths are rejected. The manifest hashes the exact dataset bytes, so
even a whitespace edit requires a new freeze.

The versioned `text_match_v1` adapter selects samples by SHA-256 ranking of `[seed, id]`,
uses one `generate()` call per sample, and scores with Inspect's default `match()` scorer.
`--count` selects a deterministic subset. `--epochs` repeats each selected ID.
The verifier checks the exact multiset of `(id, epoch)` pairs, not merely total counts.
The full dataset hash still changes if input row order changes.

The default generation settings are `temperature=0.0`, `max_tokens=32`, and `seed=42`.
Selection seed and generation seed use the same CLI `--seed`. The schema records them
separately. Generation options unsupported by a real provider may cause a run to fail.
Deterministic manifests do not imply deterministic model responses.

Mock mode deliberately returns `mock answer` with explicit token usage to avoid
tokenizer downloads. It tests infrastructure, not model quality. Integrity checks do
not impose a minimum benchmark score.

## Tests and CI

```bash
ruff check .
ruff format --check .
pytest -q
python -m build
```

Unit tests cover schemas, hashing, selection, Git state, and file boundaries.
Hypothesis checks canonicalization and coverage mutations and sends arbitrary bytes
to the Inspect log reader. Integration tests run the real Inspect engine and then
alter native log objects. The CLI test performs freeze, run, verify, release, and a
rejected release in subprocesses without provider keys.

Tests block external socket connections, including in CLI subprocesses. Loopback IPC
is allowed. Dependency installation still needs package downloads. The mock evaluation
itself needs neither network access nor provider credentials.

The included GitHub Actions workflow installs the package, lints it, runs the full
suite, builds distributions, and runs the offline demo. It runs after you push this
repository to GitHub; hosted CI has not been executed as part of delivering this ZIP.
`requirements.lock` pins the dependency set used for local validation on Linux/Python
3.12. It is a constraints file, not a cryptographically verified lockfile.

## Continue building with Codex

Open this folder in Codex and start with `docs/codex-build-guide.md`. It contains
incremental prompts for learning and extending each layer. `AGENTS.md` preserves the
integrity invariants during changes. Read `docs/design.md` for the trust model.

This is a working starter implementation of the resume project. It intentionally
supports one text-only task adapter, one model role, and three explicit generation
settings. Larger agentic evaluations require versioned adapters and additional checks.
The real-provider path is wired through Inspect but has not been tested with a paid API.

## Primary references

- [Inspect log files and public log API](https://inspect.aisi.org.uk/eval-logs.html)
- [Inspect log schema](https://inspect.aisi.org.uk/reference/inspect_ai.log.html)
- [Inspect model providers](https://inspect.aisi.org.uk/providers.html)
- [Pydantic models](https://docs.pydantic.dev/latest/concepts/models/)
- [Hypothesis documentation](https://hypothesis.readthedocs.io/en/latest/)
