"""Strict schemas for intent. Unknown fields fail closed."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Row(StrictModel):
    id: str = Field(min_length=1)
    input: str = Field(min_length=1)
    target: str = Field(min_length=1)


class Generation(StrictModel):
    temperature: float = Field(default=0.0, ge=0, le=2, allow_inf_nan=False)
    max_tokens: int = Field(default=32, ge=1)
    seed: int = Field(default=42, ge=0)


class Manifest(StrictModel):
    schema_version: Literal[1] = 1
    task: Literal["text_match_v1"] = "text_match_v1"
    dataset: str
    dataset_sha256: str
    sample_ids: list[str] = Field(min_length=1)
    selection_seed: int = Field(ge=0)
    epochs: int = Field(ge=1, le=100)
    model: str
    provider: str
    generation: Generation
    git_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    artifacts: dict[str, str]
    toolkit_sha256: str
    versions: dict[str, str]

    @field_validator("dataset")
    @classmethod
    def safe_dataset(cls, value: str) -> str:
        return safe_path(value)

    @field_validator("artifacts")
    @classmethod
    def safe_artifacts(cls, value: dict[str, str]) -> dict[str, str]:
        for path, digest in value.items():
            safe_path(path)
            valid_digest(digest)
        return value

    @field_validator("dataset_sha256", "toolkit_sha256")
    @classmethod
    def digests(cls, value: str) -> str:
        return valid_digest(value)

    @model_validator(mode="after")
    def consistent(self) -> "Manifest":
        if len(self.sample_ids) != len(set(self.sample_ids)):
            raise ValueError("sample IDs must be unique")
        prefix, separator, name = self.model.partition("/")
        if not separator or not name or prefix != self.provider:
            raise ValueError("model must be provider/model and match provider")
        return self


def valid_digest(value: str) -> str:
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("expected lowercase SHA-256")
    return value


def safe_path(value: str) -> str:
    from pathlib import PurePosixPath

    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or ":" in value
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
        or value == "."
    ):
        raise ValueError("expected normalized relative POSIX file path")
    return value
