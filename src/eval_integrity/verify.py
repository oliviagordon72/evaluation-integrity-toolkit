"""Fail closed against native Inspect evidence, with eight stable failure codes."""

import io
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from inspect_ai.log import EvalLog, read_eval_log

from .core import (
    IntegrityError,
    atomic_create,
    binding,
    canonical,
    manifest_bytes,
    preflight,
    sha,
)
from .models import Manifest, Row


def require(condition: bool, category: str, detail: str) -> None:
    if not condition:
        raise IntegrityError(category, detail)


def verify_log(manifest: Manifest, rows: list[Row], log: EvalLog) -> dict[str, Any]:
    require(log.status == "success" and log.error is None, "EXECUTION", "run not successful")
    require(
        log.eval.task == manifest.task and log.eval.task_version == 1,
        "EXECUTION",
        "task identity/version mismatch",
    )
    metadata = log.eval.metadata or {}
    recorded = metadata.get("integrity", {})
    require(isinstance(recorded, dict), "EXECUTION", "missing provenance binding")
    expected = binding(manifest)
    for field, category in (
        ("manifest_sha256", "MANIFEST"),
        ("dataset_sha256", "DATASET"),
        ("artifacts", "ARTIFACT"),
        ("toolkit_sha256", "ARTIFACT"),
        ("git_commit", "GIT"),
        ("versions", "EXECUTION"),
    ):
        require(recorded.get(field) == expected[field], category, f"binding differs: {field}")
    # Some programmatic Tasks have no native revision. The wrapper always binds its
    # independently checked clean HEAD; compare native provenance whenever present.
    if log.eval.revision is not None:
        revision = log.eval.revision
        # Inspect records git's abbreviated commit; local HEAD is checked in full.
        require(
            7 <= len(revision.commit) <= len(manifest.git_commit)
            and all(c in "0123456789abcdef" for c in revision.commit)
            and manifest.git_commit.startswith(revision.commit)
            and revision.dirty is False,
            "GIT",
            "logged Git mismatch or dirty checkout",
        )
    require(
        log.eval.packages.get("inspect_ai") == manifest.versions["inspect-ai"],
        "EXECUTION",
        "Inspect version mismatch",
    )
    require(log.eval.model == manifest.model, "MODEL", "logged provider/model differs")
    require(
        log.eval.model.partition("/")[0] == manifest.provider, "MODEL", "logged provider differs"
    )
    require(
        not log.eval.model_base_url and not log.eval.model_roles,
        "MODEL",
        "custom routing and model roles are outside this adapter",
    )
    require(log.plan is not None, "EXECUTION", "missing execution plan")
    require(
        len(log.plan.steps) == 1
        and log.plan.steps[0].solver == "generate"
        and log.plan.steps[0].params == {"tool_calls": "loop"},
        "EXECUTION",
        "solver plan differs",
    )
    require(
        log.eval.scorers is not None
        and len(log.eval.scorers) == 1
        and log.eval.scorers[0].name == "match"
        and log.eval.scorers[0].options == {},
        "EXECUTION",
        "scorer differs",
    )
    require(
        log.eval.config.log_samples is True and log.eval.config.fail_on_error is True,
        "EXECUTION",
        "sample logging or failure policy differs",
    )
    if manifest.provider != "mockllm":
        require(not log.eval.model_args, "MODEL", "unexpected provider arguments")
    generation = manifest.generation.model_dump()
    require(
        log.plan.config.model_dump(exclude_none=True) == generation,
        "GENERATION",
        "plan generation config differs",
    )
    require(
        not log.eval.model_generate_config.model_dump(exclude_none=True),
        "GENERATION",
        "unexpected model-level config",
    )
    require(log.eval.config.epochs == manifest.epochs, "COVERAGE", "epoch count differs")
    require(log.eval.dataset.samples == len(rows), "COVERAGE", "dataset size differs")
    require(
        log.eval.dataset.sample_ids == manifest.sample_ids,
        "COVERAGE",
        "selected sample order differs",
    )
    require(log.samples is not None, "COVERAGE", "missing sample records")
    actual = Counter((s.id, s.epoch) for s in log.samples)
    expected_coverage = Counter(
        (r.id, epoch) for r in rows for epoch in range(1, manifest.epochs + 1)
    )
    require(actual == expected_coverage, "COVERAGE", "missing, extra, or repeated sample/epoch")
    by_id = {r.id: r for r in rows}
    for sample in log.samples:
        require(
            sample.error is None and sample.invalidation is None and sample.limit is None,
            "EXECUTION",
            f"sample {sample.id} errored, invalidated, or hit a limit",
        )
        row = by_id[sample.id]
        require(
            sample.input == row.input and sample.target == row.target,
            "DATASET",
            f"sample content changed: {sample.id}",
        )
        require(
            bool(sample.scores) and "match" in sample.scores,
            "EXECUTION",
            f"missing score: {sample.id}",
        )
        events = [event for event in sample.events if event.event == "model"]
        require(len(events) == 1, "EXECUTION", "expected one model call per sample")
        for event in events:
            require(
                len(event.input) == 1
                and event.input[0].role == "user"
                and event.input[0].content == row.input,
                "DATASET",
                "submitted model input differs from frozen prompt",
            )
            require(not event.tools, "EXECUTION", "unexpected tools in text-only task")
            require(event.model == manifest.model, "MODEL", "model call routed differently")
            require(
                event.config.model_dump(exclude_none=True) == generation,
                "GENERATION",
                "model call generation config differs",
            )
            require(
                event.output is not None and bool(event.output.choices),
                "EXECUTION",
                "missing model response",
            )
            require(
                sample.output.model_dump() == event.output.model_dump(),
                "EXECUTION",
                "sample response differs from model event response",
            )
    return {
        "passed": True,
        "manifest_sha256": sha(manifest_bytes(manifest)),
        "samples": len(rows),
        "epochs": manifest.epochs,
        "records": sum(actual.values()),
        "categories_checked": 8,
    }


def verify_bytes(manifest: Manifest, root: Path, data: bytes) -> dict[str, Any]:
    rows = preflight(manifest, root)
    try:
        # Read the exact byte snapshot that release will embed, avoiding a log reread race.
        log = read_eval_log(io.BytesIO(data))
    except Exception as error:
        raise IntegrityError("EXECUTION", f"unreadable Inspect log: {error}") from error
    return verify_log(manifest, rows, log)


def release(manifest: Manifest, root: Path, log_path: Path, output: Path) -> dict[str, Any]:
    data = log_path.read_bytes()
    report = verify_bytes(manifest, root, data)
    files = {
        "manifest.json": manifest_bytes(manifest),
        "run.eval": data,
        "verification.json": canonical(report),
    }
    files["SHA256SUMS.json"] = canonical({name: sha(value) for name, value in files.items()})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, value)
    atomic_create(output, buffer.getvalue())
    return {**report, "bundle": str(output), "bundle_sha256": sha(buffer.getvalue())}
