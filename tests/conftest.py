import socket
import subprocess

import pytest

from eval_integrity.core import freeze
from eval_integrity.runner import run


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    """Real Inspect may use local IPC; no external provider or tokenizer requests."""
    original = socket.socket.connect

    def guarded(sock, address):
        if isinstance(address, tuple) and address[0] not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"external network forbidden in tests: {address}")
        return original(sock, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".gitignore").write_text(".integrity/\n")
    (root / "data.jsonl").write_text(
        '{"id":"one","input":"Say mock answer","target":"mock answer"}\n'
        '{"id":"two","input":"Repeat mock answer","target":"mock answer"}\n'
    )
    (root / "rubric.txt").write_text("Default match scorer.\n")
    for args in (
        ["init", "-q"],
        ["add", "."],
        [
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


@pytest.fixture
def manifest(repo):
    return freeze(repo, "data.jsonl", epochs=2, artifacts=["rubric.txt"])


@pytest.fixture
def completed(repo, manifest):
    return run(manifest, repo, repo / ".integrity" / "logs")
