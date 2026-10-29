import json

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from eval_integrity.core import (
    IntegrityError,
    atomic_create,
    canonical,
    freeze,
    load_manifest,
    manifest_bytes,
    parse_json,
    preflight,
    resolve,
    rows_from_bytes,
    sha,
)
from eval_integrity.models import Generation, Manifest


def test_freeze_is_byte_identical(repo):
    first = manifest_bytes(freeze(repo, "data.jsonl", artifacts=["rubric.txt"]))
    second = manifest_bytes(freeze(repo, "data.jsonl", artifacts=["rubric.txt"]))
    assert first == second


def test_subset_and_order_are_frozen(repo):
    full = freeze(repo, "data.jsonl", seed=17)
    subset = freeze(repo, "data.jsonl", seed=17, count=1)
    assert subset.sample_ids == full.sample_ids[:1]
    assert len(full.sample_ids) == 2


def test_pinned_digest_rejects_edit(repo, manifest):
    path = repo / ".integrity" / "manifest.json"
    data = manifest_bytes(manifest)
    atomic_create(path, data)
    assert load_manifest(path, sha(data)) == manifest
    changed = json.loads(data)
    changed["epochs"] = 3
    path.write_bytes(canonical(changed))
    with pytest.raises(IntegrityError, match="MANIFEST"):
        load_manifest(path, sha(data))


def test_strict_validation(manifest):
    for field, value in (
        ("unknown", 1),
        ("epochs", "2"),
        ("sample_ids", ["one", "one"]),
        ("provider", "wrong"),
        ("dataset", "../data.jsonl"),
    ):
        with pytest.raises(ValidationError):
            Manifest.model_validate({**manifest.model_dump(), field: value})
    with pytest.raises(ValidationError):
        Generation(temperature=float("nan"))


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', '{"x":{"y":1,"y":2}}'])
def test_duplicate_json_keys_rejected(text):
    with pytest.raises(ValueError, match="duplicate"):
        parse_json(text)


def test_duplicate_dataset_ids_rejected():
    row = b'{"id":"x","input":"q","target":"a"}\n'
    with pytest.raises(ValueError, match="unique"):
        rows_from_bytes(row + row)


def test_symlink_escape_rejected(repo, tmp_path):
    (tmp_path / "outside").write_text("secret")
    (repo / "link").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="escapes"):
        resolve(repo, "link")


def test_existing_freeze_never_overwritten(tmp_path):
    path = tmp_path / "frozen.json"
    atomic_create(path, b"original")
    with pytest.raises(FileExistsError):
        atomic_create(path, b"replacement")
    assert path.read_bytes() == b"original"


def test_dirty_git_rejected(repo, manifest):
    (repo / "untracked.txt").write_text("not committed")
    with pytest.raises(IntegrityError, match="GIT"):
        preflight(manifest, repo)


def test_dataset_hash_rechecked_even_when_git_ignores_file(repo, manifest):
    # Git alone is insufficient. An ignored source is still content-addressed.
    import subprocess

    subprocess.run(
        ["git", "-C", str(repo), "update-index", "--assume-unchanged", "data.jsonl"], check=True
    )
    (repo / "data.jsonl").write_text("changed")
    with pytest.raises(IntegrityError, match="DATASET"):
        preflight(manifest, repo)


def test_artifact_hash_rechecked(repo, manifest):
    import subprocess

    subprocess.run(
        ["git", "-C", str(repo), "update-index", "--assume-unchanged", "rubric.txt"], check=True
    )
    (repo / "rubric.txt").write_text("changed")
    with pytest.raises(IntegrityError, match="ARTIFACT"):
        preflight(manifest, repo)


json_scalars = st.one_of(st.none(), st.booleans(), st.integers(), st.text())


@given(st.dictionaries(st.text(), json_scalars))
def test_canonicalization_independent_of_key_insertion_order(value):
    assert canonical(value) == canonical(dict(reversed(list(value.items()))))


@given(st.binary(), st.binary(min_size=1))
def test_appended_content_changes_digest(original, suffix):
    assert sha(original) != sha(original + suffix)
