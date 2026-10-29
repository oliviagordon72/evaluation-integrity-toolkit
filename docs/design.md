# Design and trust boundaries

## Data flow

1. Freeze reads a clean Git revision, JSONL dataset, optional declared artifacts,
   installed toolkit Python sources, and Python/Inspect/Pydantic/toolkit versions.
2. Selection ranks samples by SHA-256 of canonical `[selection_seed, sample_id]`.
   Intent uses canonical UTF-8 JSON, sorted object keys, and no timestamps or run IDs.
3. The operator pins the manifest digest separately. Every later CLI command requires
   that expected digest and validates the strict schema.
4. Run rechecks local inputs, constructs the fixed task from those verified bytes,
   attaches provenance metadata, and delegates to Inspect's public `eval()` API.
5. Verify uses Inspect's public `read_eval_log()` API, checks native header fields,
   execution plan, sample coverage/content, scores, and model event settings.
6. Release reads one byte snapshot of the log, verifies that snapshot, and embeds
   those exact bytes in a bundle. An exclusive atomic link publishes the finished ZIP.

## Evidence and limitations

The threat model is accidental drift, missing coverage, stale configurations,
misrouted model names, and incomplete or mixed-up results. A separately pinned digest
also detects an edited manifest when the operator still has the original digest.
It is not remote execution attestation or protection against an operator who can
fabricate all log fields, alter the verifier, and replace the approval digest.

The wrapper checks actual clean HEAD before and after running and again at release.
It records that revision in the run's EvalSpec metadata. For programmatic
Tasks, Inspect may omit native `eval.revision`; when native revision exists, the
verifier checks its clean flag and full or abbreviated commit against the frozen
revision too. Metadata alone is not treated as evidence of sample coverage
or generation settings: those checks read native samples and model events.

Provider identity means the configured Inspect `provider/model` name, both in the
header and in every model event. It cannot prove which weights a remote provider
actually served or prevent an upstream alias from moving. Custom base URLs and extra
model roles are rejected by this adapter. Credentials and upstream routing can still
be environment-dependent. Auditing external gateway routing needs a separate adapter.

Declared artifacts are exact-byte input dependencies such as rubrics and configuration
files. The toolkit's own source digest binds the fixed task implementation. The
manifest records Python and direct runtime package versions, not the entire operating
system, dependency graph, GPU, or hardware state. The supplied constraints file helps
reproduce the tested dependency graph. For production use, bind a container digest or
fully hashed environment lock and preserve a trusted execution record.

Current verification also requires the original files and frozen Git checkout to be
available. Release ZIPs contain evidence and checksums, not a copy of the dataset or
every artifact. Reviewers need the source checkout to rerun full verification.

The local export gate applies when callers use `eit release`. Protecting an external
release requires that destination's workflow and permissions to enforce the gate.
No publishing, signing service, transparency log, or protected GitHub release is
configured here.

## Operating assumptions

Run commands synchronously in an isolated, clean checkout. The adapter temporarily
changes the process working directory and is not thread-safe. Preflight checks do not
defend against a concurrent hostile process changing inputs between reads. A trusted
read-only checkout/container is the appropriate stronger boundary.

The manifest and release writer publishes complete bytes with `os.link`, refusing
existing names. Use a local filesystem supporting hard links, such as WSL's Linux
filesystem. A network share that does not support hard links is outside the tested
storage configuration. File publication is atomic; full crash-durable directory
fsync semantics are not claimed.

Logs and release ZIPs are held in memory. This implementation targets small text
evaluations. Large logs should use streaming APIs plus immutable snapshots and limits.
Treat untrusted logs as data requiring resource limits, not as safe unlimited uploads.

## Files to read

| File | Responsibility |
| --- | --- |
| `models.py` | Pydantic contracts and safe paths |
| `core.py` | Canonical serialization, hashes, selection, Git, preflight |
| `runner.py` | Fixed Inspect task and mock-provider execution |
| `verify.py` | Eight-category gate and verified bundle export |
| `cli.py` | Commands, required digest, JSON output, exit status |

## Extending the contract

Add a new versioned adapter for multi-turn tasks, tools, model graders, and model roles.
Freeze scorer and solver options explicitly. Bind every prompt/template/tool file.
Require expected model routes and generation config for every role and model event.
Specify coverage and retry semantics before accepting partial or resumed runs.
Add negative tests before widening accepted log shapes.
