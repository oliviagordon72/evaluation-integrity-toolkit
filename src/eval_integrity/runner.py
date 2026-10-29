"""The narrow, versioned Inspect task adapter; no arbitrary task code is loaded."""

import os
from contextlib import contextmanager
from pathlib import Path

from inspect_ai import Task, eval
from inspect_ai.dataset import Sample
from inspect_ai.log import EvalLog
from inspect_ai.model import GenerateConfig, ModelOutput, ModelUsage
from inspect_ai.scorer import match
from inspect_ai.solver import generate

from .core import IntegrityError, binding, preflight
from .models import Manifest, Row


@contextmanager
def working_directory(root: Path):
    # Inspect records Git provenance relative to the task execution directory.
    # This adapter is synchronous; do not call it concurrently from multiple threads.
    previous = Path.cwd()
    os.chdir(root)
    try:
        yield
    finally:
        os.chdir(previous)


def task_for(manifest: Manifest, rows: list[Row]) -> Task:
    return Task(
        dataset=[Sample(id=r.id, input=r.input, target=r.target) for r in rows],
        solver=generate(),
        scorer=match(),
        name=manifest.task,
        version=1,
        config=GenerateConfig(**manifest.generation.model_dump()),
    )


def run(manifest: Manifest, root: Path, log_dir: Path) -> EvalLog:
    rows = preflight(manifest, root)
    log_dir = log_dir.resolve()
    log_dir.mkdir(parents=True, exist_ok=False)
    model_args = {}
    if manifest.provider == "mockllm":
        # Explicit usage avoids tokenizer downloads, making this path fully offline.
        output = ModelOutput.from_content(model="mockllm", content="mock answer")
        output.usage = ModelUsage(input_tokens=1, output_tokens=1, total_tokens=2)
        # Inspect adds timing/context data to responses. Each call needs its own object.
        model_args = {
            "custom_outputs": [
                output.model_copy(deep=True) for _ in range(len(rows) * manifest.epochs)
            ]
        }
    with working_directory(root):
        logs = eval(
            task_for(manifest, rows),
            model=manifest.model,
            model_args=model_args,
            epochs=manifest.epochs,
            metadata={"integrity": binding(manifest)},
            log_dir=str(log_dir),
            log_format="eval",
            display="none",
            log_samples=True,
            fail_on_error=True,
            sandbox_cleanup=True,
        )
    if len(logs) != 1:
        raise IntegrityError("EXECUTION", "expected exactly one Inspect log")
    # Verification (including another preflight) is performed by the CLI before success.
    return logs[0]
