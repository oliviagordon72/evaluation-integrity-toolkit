import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.e2e
def test_zero_api_cli_lifecycle_and_negative_release(repo):
    # A sitecustomize guard also blocks external sockets in CLI subprocesses.
    guard = repo / ".integrity" / "guard"
    guard.mkdir(parents=True)
    (guard / "sitecustomize.py").write_text(
        "import socket\n"
        "original = socket.socket.connect\n"
        "def connect(self, address):\n"
        "    if isinstance(address, tuple) and address[0] not in "
        "('127.0.0.1', '::1', 'localhost'):\n"
        "        raise RuntimeError('external network forbidden')\n"
        "    return original(self, address)\n"
        "socket.socket.connect = connect\n"
        "socket.socket.connect_ex = connect\n"
    )
    env = {k: v for k, v in os.environ.items() if not k.endswith(("API_KEY", "AUTH_TOKEN"))}
    env["PYTHONPATH"] = str(guard)

    def cli(*args, success=True):
        result = subprocess.run(
            [sys.executable, "-m", "eval_integrity", *args],
            cwd=repo,
            env=env,
            text=True,
            capture_output=True,
            timeout=60,
        )
        assert (result.returncode == 0) == success, result.stdout + result.stderr
        return json.loads(result.stdout if success else result.stderr)

    manifest = repo / ".integrity" / "manifest.json"
    frozen = cli(
        "freeze",
        "--dataset",
        "data.jsonl",
        "--artifact",
        "rubric.txt",
        "--epochs",
        "2",
        "--out",
        str(manifest),
    )
    shared = ("--manifest", str(manifest), "--expected-digest", frozen["sha256"])
    result = cli("run", *shared, "--log-dir", str(repo / ".integrity" / "logs"))
    assert result["records"] == 4
    assert cli("verify", *shared, "--log", result["log"])["passed"]
    output = repo / ".integrity" / "bundle.zip"
    assert cli("release", *shared, "--log", result["log"], "--out", str(output))["passed"]
    # Valid syntax with a forged model name must still fail against the trusted digest.
    changed = json.loads(manifest.read_text())
    changed["model"] = "mockllm/other"
    manifest.write_text(json.dumps(changed))
    blocked = repo / ".integrity" / "blocked.zip"
    failure = cli("release", *shared, "--log", result["log"], "--out", str(blocked), success=False)
    assert failure["category"] == "MANIFEST"
    assert not Path(blocked).exists()
