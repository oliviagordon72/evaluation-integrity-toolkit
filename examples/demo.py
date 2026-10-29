"""Run an offline evaluation, release it, then demonstrate a blocked release."""

import json
import subprocess
import sys
import uuid
from pathlib import Path

from inspect_ai.log import read_eval_log, write_eval_log


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    destination = root / ".integrity" / f"demo-{uuid.uuid4().hex[:8]}"
    destination.mkdir(parents=True)

    def cli(*arguments: str, success: bool = True) -> dict:
        result = subprocess.run(
            [sys.executable, "-m", "eval_integrity", *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if (result.returncode == 0) != success:
            raise RuntimeError(result.stdout + result.stderr)
        return json.loads(result.stdout if success else result.stderr)

    manifest_path = destination / "manifest.json"
    frozen = cli(
        "freeze",
        "--dataset",
        "examples/dataset.jsonl",
        "--epochs",
        "2",
        "--artifact",
        "examples/rubric.txt",
        "--out",
        str(manifest_path),
    )
    shared = ("--manifest", str(manifest_path), "--expected-digest", frozen["sha256"])
    completed = cli("run", *shared, "--log-dir", str(destination / "logs"))
    released = cli(
        "release", *shared, "--log", completed["log"], "--out", str(destination / "release.zip")
    )

    changed = read_eval_log(completed["log"])
    changed.samples.pop()
    altered_path = destination / "missing-sample.eval"
    write_eval_log(changed, str(altered_path))
    failure = cli(
        "release",
        *shared,
        "--log",
        str(altered_path),
        "--out",
        str(destination / "blocked.zip"),
        success=False,
    )
    assert failure["category"] == "COVERAGE" and not (destination / "blocked.zip").exists()
    summary = {
        "released": released,
        "blocked": failure,
        "note": "Real Inspect run, mock responses, no provider API calls",
    }
    (destination / "demo-result.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
