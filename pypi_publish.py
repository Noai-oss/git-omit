import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Sequence

from make_wheels import ROOT, TARGETS, read_project_metadata


def parse_version(value: str) -> str:
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        raise argparse.ArgumentTypeError("must use the x.y.z format")
    return value


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build and publish all platform wheels to PyPI.",
    )
    parser.add_argument(
        "version",
        type=parse_version,
        help="Release version in x.y.z format.",
    )
    return parser.parse_args(argv)


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def run_command(
    command: Sequence[str],
    *,
    check: bool = True,
    capture_output: bool = False,
    text: bool = False,
) -> subprocess.CompletedProcess[str]:
    # Use the host platform's quoting rules so the logged command can be
    # copied into a terminal and run manually when a release step fails.
    command_text = (
        subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command)
    )
    print(f"==> {command_text}", flush=True)
    return subprocess.run(
        command,
        cwd=ROOT,
        check=check,
        capture_output=capture_output,
        text=text,
    )


def read_zig_version() -> str:
    zon = (ROOT / "build.zig.zon").read_text(encoding="utf-8")
    match = re.search(r'^\s*\.version\s*=\s*"([^"]+)"\s*,', zon, re.MULTILINE)
    if match is None:
        fail("Could not read .version from build.zig.zon")
    return match.group(1)


def ensure_clean_worktree() -> None:
    result = run_command(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
    )
    if result.stdout:
        fail("Git worktree is not clean")


def ensure_tag_is_new(tag: str) -> None:
    result = run_command(
        ["git", "rev-parse", "--quiet", "--verify", f"refs/tags/{tag}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        fail(
            f"Git tag already exists: {tag}\n"
            "If it is safe to recreate this tag, remove it with:\n"
            f"  git tag --delete {tag}\n"
            f"  git push origin --delete {tag}  # if already pushed"
        )
    if result.returncode != 1:
        fail(result.stderr.strip() or f"Could not check Git tag: {tag}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    _, project_version = read_project_metadata()
    zig_version = read_zig_version()

    if args.version != project_version or args.version != zig_version:
        fail(
            f"Version mismatch: argument={args.version}, "
            f"pyproject.toml={project_version}, build.zig.zon={zig_version}"
        )
    if not os.getenv("UV_PUBLISH_TOKEN"):
        fail("UV_PUBLISH_TOKEN is not set")

    ensure_clean_worktree()
    tag = f"v{args.version}"
    ensure_tag_is_new(tag)

    dist = ROOT / "dist"
    if dist.exists():
        shutil.rmtree(dist)

    run_command([sys.executable, "make_wheels.py"])

    wheels = sorted(dist.glob("*.whl"))
    if len(wheels) != len(TARGETS):
        fail(f"Expected {len(TARGETS)} wheels, found {len(wheels)}")

    run_command(["uvx", "twine", "check", *(str(wheel) for wheel in wheels)])

    # Push the tag before the irreversible PyPI upload. The push also
    # catches an existing remote tag without requiring a separate fetch/check.
    run_command(["git", "tag", "-a", tag, "-m", tag])
    run_command(["git", "push", "origin", tag])
    run_command(["uv", "publish", *(str(wheel) for wheel in wheels)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
