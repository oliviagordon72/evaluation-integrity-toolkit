import io
import zipfile

import pytest
from hypothesis import given
from hypothesis import strategies as st

from eval_integrity.core import IntegrityError, parse_json, preflight, sha
from eval_integrity.verify import release, verify_bytes, verify_log


@pytest.mark.integration
def test_real_inspect_success_and_bundle(repo, manifest, completed):
    rows = preflight(manifest, repo)
    assert verify_log(manifest, rows, completed)["records"] == 4
    path = repo / ".integrity" / "release.zip"
    report = release(manifest, repo, __import__("pathlib").Path(completed.location), path)
    assert report["bundle_sha256"] == sha(path.read_bytes())
    with zipfile.ZipFile(path) as bundle:
        sums = parse_json(bundle.read("SHA256SUMS.json"))
        for name, expected in sums.items():
            assert sha(bundle.read(name)) == expected
        assert verify_bytes(manifest, repo, bundle.read("run.eval"))["passed"]


def mutate(log, case):
    binding = log.eval.metadata["integrity"]
    if case == "MANIFEST":
        binding["manifest_sha256"] = "0" * 64
    elif case == "DATASET":
        log.samples[0].input = "different prompt"
    elif case == "ARTIFACT":
        binding["toolkit_sha256"] = "0" * 64
    elif case == "GIT":
        binding["git_commit"] = "0" * 40
    elif case == "MODEL":
        log.eval.model = "other/model"
    elif case == "GENERATION":
        log.plan.config.temperature = 0.9
    elif case == "COVERAGE":
        log.samples.pop()
    elif case == "EXECUTION":
        log.status = "error"


@pytest.mark.integration
def test_all_eight_failure_categories(repo, manifest, completed):
    rows = preflight(manifest, repo)
    for category in (
        "MANIFEST",
        "DATASET",
        "ARTIFACT",
        "GIT",
        "MODEL",
        "GENERATION",
        "COVERAGE",
        "EXECUTION",
    ):
        changed = completed.model_copy(deep=True)
        mutate(changed, category)
        with pytest.raises(IntegrityError) as error:
            verify_log(manifest, rows, changed)
        assert error.value.category == category


@pytest.mark.integration
def test_event_level_model_and_config_changes(repo, manifest, completed):
    rows = preflight(manifest, repo)
    for field, value, category in (
        ("model", "other/model", "MODEL"),
        ("temperature", 0.75, "GENERATION"),
    ):
        changed = completed.model_copy(deep=True)
        event = next(e for e in changed.samples[0].events if e.event == "model")
        if field == "model":
            event.model = value
        else:
            event.config.temperature = value
        with pytest.raises(IntegrityError, match=category):
            verify_log(manifest, rows, changed)


@pytest.mark.integration
def test_native_abbreviated_revision_and_dirty_flag(repo, manifest, completed):
    from inspect_ai.log import EvalRevision

    rows = preflight(manifest, repo)
    changed = completed.model_copy(deep=True)
    changed.eval.revision = EvalRevision(
        type="git",
        origin="",
        commit=manifest.git_commit[:7],
        dirty=False,
    )
    assert verify_log(manifest, rows, changed)["passed"]
    for commit, dirty in (
        ("0" * 7, False),
        (manifest.git_commit[:7], True),
        (manifest.git_commit[:6], False),
    ):
        changed.eval.revision = EvalRevision(type="git", origin="", commit=commit, dirty=dirty)
        with pytest.raises(IntegrityError, match="GIT"):
            verify_log(manifest, rows, changed)


@pytest.mark.integration
def test_missing_score_and_duplicate_record(repo, manifest, completed):
    rows = preflight(manifest, repo)
    changed = completed.model_copy(deep=True)
    changed.samples[0].scores = {}
    with pytest.raises(IntegrityError, match="EXECUTION"):
        verify_log(manifest, rows, changed)
    changed = completed.model_copy(deep=True)
    changed.samples[0] = changed.samples[1]
    with pytest.raises(IntegrityError, match="COVERAGE"):
        verify_log(manifest, rows, changed)


@pytest.mark.integration
def test_submitted_prompt_and_solver_are_verified(repo, manifest, completed):
    rows = preflight(manifest, repo)
    changed = completed.model_copy(deep=True)
    event = next(e for e in changed.samples[0].events if e.event == "model")
    event.input[0].content = "unapproved input"
    with pytest.raises(IntegrityError, match="DATASET"):
        verify_log(manifest, rows, changed)
    changed = completed.model_copy(deep=True)
    changed.plan.steps[0].solver = "different_solver"
    with pytest.raises(IntegrityError, match="EXECUTION"):
        verify_log(manifest, rows, changed)


@pytest.mark.integration
def test_property_any_removed_or_duplicated_record_is_rejected(repo, manifest, completed):
    rows = preflight(manifest, repo)

    @given(st.integers(min_value=0, max_value=3), st.booleans())
    def check(index, duplicate):
        changed = completed.model_copy(deep=True)
        if duplicate:
            changed.samples.append(changed.samples[index])
        else:
            changed.samples.pop(index)
        with pytest.raises(IntegrityError, match="COVERAGE"):
            verify_log(manifest, rows, changed)

    check()


@pytest.mark.integration
def test_release_rejects_bad_log_without_creating_bundle(repo, manifest, completed):
    from pathlib import Path

    from inspect_ai.log import write_eval_log

    changed = completed.model_copy(deep=True)
    changed.samples.pop()
    bad_log = repo / ".integrity" / "bad.eval"
    write_eval_log(changed, str(bad_log))
    output = repo / ".integrity" / "blocked.zip"
    with pytest.raises(IntegrityError, match="COVERAGE"):
        release(manifest, repo, Path(bad_log), output)
    assert not output.exists()


@pytest.mark.integration
def test_release_refuses_existing_output(repo, manifest, completed):
    from pathlib import Path

    output = repo / ".integrity" / "already.zip"
    output.write_bytes(b"keep me")
    with pytest.raises(FileExistsError):
        release(manifest, repo, Path(completed.location), output)
    assert output.read_bytes() == b"keep me"


@given(st.binary(max_size=1000))
def test_arbitrary_bytes_are_not_eval_logs(data):
    # Test the actual Inspect reader used at the boundary. It must reject fuzzed bytes.
    from inspect_ai.log import read_eval_log

    with pytest.raises(Exception):
        read_eval_log(io.BytesIO(data))
