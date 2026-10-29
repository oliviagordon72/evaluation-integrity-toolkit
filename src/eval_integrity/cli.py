"""Command-line boundary. stdout is machine-readable JSON; failures return nonzero."""

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from .core import (
    IntegrityError,
    atomic_create,
    freeze,
    load_manifest,
    manifest_bytes,
    sha,
)
from .models import Generation
from .runner import run
from .verify import release, verify_bytes


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="eit", description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    make = commands.add_parser("freeze", help="freeze deterministic intent in a new file")
    make.add_argument("--root", type=Path, default=Path.cwd())
    make.add_argument("--dataset", required=True, help="relative JSONL path")
    make.add_argument("--model", default="mockllm/model")
    make.add_argument("--seed", type=int, default=42)
    make.add_argument("--count", type=int)
    make.add_argument("--epochs", type=int, default=1)
    make.add_argument("--temperature", type=float, default=0.0)
    make.add_argument("--max-tokens", type=int, default=32)
    make.add_argument("--artifact", action="append", default=[])
    make.add_argument("--out", type=Path, required=True)
    for name in ("run", "verify", "release"):
        command = commands.add_parser(name)
        command.add_argument("--root", type=Path, default=Path.cwd())
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument(
            "--expected-digest", required=True, help="digest pinned independently at freeze time"
        )
        if name == "run":
            command.add_argument(
                "--log-dir",
                type=Path,
                required=True,
                help="new directory, normally beneath .integrity/",
            )
        else:
            command.add_argument("--log", type=Path, required=True)
        if name == "release":
            command.add_argument("--out", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        root = args.root.resolve()
        if args.command == "freeze":
            manifest = freeze(
                root,
                args.dataset,
                args.model,
                args.seed,
                args.count,
                args.epochs,
                args.artifact,
                Generation(
                    temperature=args.temperature, max_tokens=args.max_tokens, seed=args.seed
                ),
            )
            data = manifest_bytes(manifest)
            atomic_create(args.out, data)
            report = {"manifest": str(args.out), "sha256": sha(data)}
        else:
            manifest = load_manifest(args.manifest, args.expected_digest)
            if args.command == "run":
                log = run(manifest, root, args.log_dir)
                report = verify_bytes(manifest, root, Path(log.location).read_bytes())
                report["log"] = log.location
            elif args.command == "verify":
                report = verify_bytes(manifest, root, args.log.read_bytes())
            else:
                report = release(manifest, root, args.log, args.out)
        print(json.dumps(report, sort_keys=True))
        return 0
    except IntegrityError as error:
        print(
            json.dumps({"passed": False, "category": error.category, "error": error.detail}),
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError, ValidationError) as error:
        print(
            json.dumps({"passed": False, "category": "EXECUTION", "error": str(error)}),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
