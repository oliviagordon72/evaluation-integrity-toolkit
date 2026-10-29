"""Manifest generation, content addressing, and local provenance checks."""

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .models import Generation, Manifest, Row, safe_path

CATEGORIES = (
    "MANIFEST",
    "DATASET",
    "ARTIFACT",
    "GIT",
    "MODEL",
    "GENERATION",
    "COVERAGE",
    "EXECUTION",
)


class IntegrityError(Exception):
    def __init__(self, category: str, detail: str):
        self.category = category
        self.detail = detail
        super().__init__(f"{category}: {detail}")


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_json(data: str | bytes) -> Any:
    return json.loads(data, object_pairs_hook=no_duplicates)


def resolve(root: Path, relative: str) -> Path:
    safe_path(relative)
    path = root.joinpath(relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes repository: {relative}")
    return path


def rows_from_bytes(data: bytes) -> list[Row]:
    rows = [
        Row.model_validate(parse_json(line))
        for line in data.decode("utf-8").splitlines()
        if line.strip()
    ]
    if not rows or len({r.id for r in rows}) != len(rows):
        raise ValueError("dataset must be nonempty with unique string IDs")
    return rows


def git_commit(root: Path) -> str:
    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], stderr=subprocess.PIPE, text=True
        ).strip()

    try:
        if Path(git("rev-parse", "--show-toplevel")).resolve() != root.resolve():
            raise ValueError("--root must be the Git repository root")
        if git("status", "--porcelain", "--untracked-files=all"):
            raise ValueError("repository must be clean, including untracked files")
        return git("rev-parse", "HEAD")
    except (ValueError, subprocess.CalledProcessError) as error:
        raise IntegrityError("GIT", str(error)) from error


def versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        **{
            name: importlib.metadata.version(name)
            for name in ("inspect-ai", "pydantic", "evaluation-integrity-toolkit")
        },
    }


def toolkit_hash() -> str:
    package = Path(__file__).parent
    return sha(canonical({p.name: sha(p.read_bytes()) for p in sorted(package.glob("*.py"))}))


def atomic_create(path: Path, data: bytes) -> None:
    """Publish completed bytes atomically and refuse to overwrite an existing name."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        os.unlink(temporary)


def freeze(
    root: Path,
    dataset: str,
    model: str = "mockllm/model",
    seed: int = 42,
    count: int | None = None,
    epochs: int = 1,
    artifacts: list[str] | None = None,
    generation: Generation | None = None,
) -> Manifest:
    commit = git_commit(root)
    try:
        data = resolve(root, dataset).read_bytes()
        rows = rows_from_bytes(data)
    except (OSError, ValueError) as error:
        raise IntegrityError("DATASET", str(error)) from error
    # Hash-ranking avoids dependency on global RNG state or input row order for selection.
    ordered = sorted(rows, key=lambda row: (sha(canonical([seed, row.id])), row.id))
    if count is not None and not 1 <= count <= len(rows):
        raise IntegrityError("COVERAGE", "count must be between 1 and dataset size")
    try:
        hashes = {p: sha(resolve(root, p).read_bytes()) for p in sorted(set(artifacts or []))}
    except (OSError, ValueError) as error:
        raise IntegrityError("ARTIFACT", str(error)) from error
    return Manifest(
        dataset=dataset,
        dataset_sha256=sha(data),
        sample_ids=[r.id for r in ordered[:count]],
        selection_seed=seed,
        epochs=epochs,
        model=model,
        provider=model.partition("/")[0],
        generation=generation or Generation(seed=seed),
        git_commit=commit,
        artifacts=hashes,
        toolkit_sha256=toolkit_hash(),
        versions=versions(),
    )


def manifest_bytes(manifest: Manifest) -> bytes:
    return canonical(manifest.model_dump())


def load_manifest(path: Path, expected_digest: str) -> Manifest:
    try:
        raw = parse_json(path.read_bytes())
        if sha(canonical(raw)) != expected_digest:
            raise ValueError("manifest differs from independently pinned digest")
        return Manifest.model_validate(raw)
    except (OSError, ValueError) as error:
        raise IntegrityError("MANIFEST", str(error)) from error


def preflight(manifest: Manifest, root: Path) -> list[Row]:
    if git_commit(root) != manifest.git_commit:
        raise IntegrityError("GIT", "HEAD differs from frozen revision")
    if versions() != manifest.versions:
        raise IntegrityError("EXECUTION", "Python or dependency versions changed")
    if toolkit_hash() != manifest.toolkit_sha256:
        raise IntegrityError("ARTIFACT", "toolkit source changed")
    for path, expected in manifest.artifacts.items():
        try:
            if sha(resolve(root, path).read_bytes()) != expected:
                raise ValueError(f"artifact changed: {path}")
        except (OSError, ValueError) as error:
            raise IntegrityError("ARTIFACT", str(error)) from error
    try:
        data = resolve(root, manifest.dataset).read_bytes()
        if sha(data) != manifest.dataset_sha256:
            raise ValueError("dataset bytes changed")
        rows = {row.id: row for row in rows_from_bytes(data)}
        return [rows[sample_id] for sample_id in manifest.sample_ids]
    except (OSError, ValueError, KeyError) as error:
        raise IntegrityError("DATASET", str(error)) from error


def binding(manifest: Manifest) -> dict[str, Any]:
    return {
        "manifest_sha256": sha(manifest_bytes(manifest)),
        "git_commit": manifest.git_commit,
        "dataset_sha256": manifest.dataset_sha256,
        "artifacts": manifest.artifacts,
        "toolkit_sha256": manifest.toolkit_sha256,
        "versions": manifest.versions,
    }
