# Recreate and understand the project with Codex

This repository is already implemented. Use the prompts below to understand it,
rebuild individual pieces in a separate branch, or extend it while preserving the
contract. Complete and inspect one phase before moving to the next.

## 1. Learn the failure model

> Read AGENTS.md, README.md, and docs/design.md. Explain the path from dataset to release
> in plain language. Map each of the eight failure codes to the exact check and a test.
> Explain what a separately pinned manifest digest protects and what it cannot protect.
> Do not change files yet.

You should be able to explain why a successful Inspect status is insufficient, why
counts alone miss duplicate samples, and why a checksum stored beside a mutable file
does not establish independent trust.

## 2. Rebuild deterministic manifests

> On a new branch, implement the manifest layer from the documented contract. Use
> strict Pydantic models, canonical JSON, SHA-256, explicit string sample IDs, deterministic
> subset ranking, epochs, provider/model, generation settings, clean Git revision,
> dataset/artifact hashes, toolkit source hash, and runtime versions. Require an external
> expected digest when loading a frozen manifest. Reject duplicate JSON keys and unsafe
> paths. Verify two identical freezes produce identical bytes.

Review `models.py` and `core.py`. Change one row, seed, generation setting, and artifact
separately. Predict which frozen fields will change before you run the commands.

## 3. Follow execution into Inspect

> Walk through runner.py and show where Inspect receives the frozen sample order,
> generation settings, epochs, and provenance. Keep the text_match_v1 adapter narrow.
> Run it through Inspect's mockllm provider with explicit mock token usage so it needs
> no tokenizer downloads. Inspect the resulting .eval log using read_eval_log().

Do not replace Inspect with a hand-written JSON log. Inspect generates real native
headers, sample records, scores, events, and serialized logs in the offline path.

## 4. Exercise the eight rejection categories

> Run the integration suite. For each error category, show the deliberately altered
> evidence and why verification rejects it. Confirm planned settings AND per-event
> settings are checked. Confirm each expected (sample ID, epoch) occurs exactly once.
> Add one meaningful negative case if an actual missing check is found.

Read `test_verification.py`. Follow `COVERAGE`, `MODEL`, and `GENERATION` first; these
illustrate the main ideas without requiring knowledge of the whole codebase.

## 5. Understand property tests and export

> Explain what Hypothesis generates in this repository, how shrinking helps find
> counterexamples, and which tests exercise real Inspect. Run the CLI end to end with
> external network connections blocked. Explain how release verifies one snapshot and
> prevents an existing output file from being overwritten.

Make sure you can distinguish unit tests, generated-input property tests, integration
tests, and CLI subprocess tests. A checksum law alone does not validate the pipeline;
the integration and negative-release tests supply the behavioral evidence.

## 6. Make one useful extension

> Add a new versioned task adapter that reads an explicitly hashed prompt template.
> Freeze its path and exact-byte hash. Add positive tests and negative tests for changing
> the template, submitting a different rendered prompt, and changing the scorer config.
> Preserve the old adapter's behavior and all eight failure categories. Update the
> schema only if the new contract needs it. Run the required checks.

Other useful follow-ups: bind a full environment lock digest, create a benchmark of
seeded integrity failures, or enforce the gate in a protected release workflow.
Only connect a real provider after reviewing the small run's settings and cost.

## Interview explanation

Be prepared to demonstrate:

- How a manifest represents intended execution, while a log is observed evidence.
- Why stable IDs plus epochs require multiset comparison.
- Why provider/model strings cannot attest to remote weights.
- Why temperature zero and a seed do not guarantee identical model answers.
- How a run can finish successfully yet contain the wrong settings or coverage.
- How mock-provider tests exercise the real framework without paid calls.
- Why a local export gate needs external enforcement to control a hosted release.

Describe only features you have run and understand. The supplied code supports the
technical claims for a small text-only evaluation workflow; do not claim production
attestation, verified upstream model routing, or hosted CI success without that work.
