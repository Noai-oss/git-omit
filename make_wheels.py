from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class WheelTarget:
    name: str
    zig_target: str
    wheel_tag: str


TARGETS = (
    WheelTarget(
        name="windows-x86_64",
        zig_target="x86_64-windows",
        wheel_tag="py3-none-win_amd64",
    ),
    WheelTarget(
        name="macos-x86_64",
        zig_target="x86_64-macos.11.0",
        wheel_tag="py3-none-macosx_11_0_x86_64",
    ),
    WheelTarget(
        name="macos-aarch64",
        zig_target="aarch64-macos.11.0",
        wheel_tag="py3-none-macosx_11_0_arm64",
    ),
    WheelTarget(
        name="linux-x86_64",
        zig_target="x86_64-linux-gnu.2.17",
        wheel_tag="py3-none-manylinux_2_17_x86_64",
    ),
    WheelTarget(
        name="linux-aarch64",
        zig_target="aarch64-linux-gnu.2.17",
        wheel_tag="py3-none-manylinux_2_17_aarch64",
    ),
)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cross-compile git-omit and build platform wheels.",
    )
    parser.add_argument(
        "--target",
        action="append",
        choices=[target.name for target in TARGETS],
        help="Build only this named target; may be repeated. Defaults to all targets.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "dist",
        help="Directory for distributions (default: dist).",
    )
    parser.add_argument(
        "--sdist",
        action="store_true",
        help="Also build a source distribution.",
    )
    parser.add_argument(
        "--expected-version",
        help="Require pyproject.toml to use this version; a leading 'v' is ignored.",
    )
    return parser.parse_args(argv)


def read_project_version() -> str:
    in_project = False
    for raw_line in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            in_project = line == "[project]"
            continue
        if in_project and line.startswith("version"):
            _, value = line.split("=", 1)
            return value.strip().strip("\"'")
    raise RuntimeError("Could not read [project].version from pyproject.toml")


def select_targets(names: Iterable[str] | None) -> tuple[WheelTarget, ...]:
    if not names:
        return TARGETS
    selected = set(names)
    return tuple(target for target in TARGETS if target.name in selected)


def build_wheel(target: WheelTarget, out_dir: Path, version: str) -> Path:
    env = os.environ.copy()
    env["GIT_OMIT_ZIG_TARGET"] = target.zig_target
    env["GIT_OMIT_WHEEL_TAG"] = target.wheel_tag

    print(
        f"\n==> {target.name}: {target.zig_target} -> {target.wheel_tag}",
        flush=True,
    )
    subprocess.run(
        [
            "uv",
            "build",
            "--wheel",
            "--out-dir",
            str(out_dir),
            "--no-create-gitignore",
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )

    wheel = out_dir / f"git_omit-{version}-{target.wheel_tag}.whl"
    if not wheel.is_file():
        raise FileNotFoundError(f"Build did not produce the expected wheel: {wheel}")
    return wheel


def build_sdist(out_dir: Path) -> Path:
    print("\n==> source distribution", flush=True)
    subprocess.run(
        [
            "uv",
            "build",
            "--sdist",
            "--out-dir",
            str(out_dir),
            "--no-create-gitignore",
        ],
        cwd=ROOT,
        check=True,
    )
    archives = sorted(out_dir.glob("git_omit-*.tar.gz"))
    if len(archives) != 1:
        raise RuntimeError(
            f"Expected exactly one git-omit source distribution, found {archives}"
        )
    return archives[0]


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    version = read_project_version()

    if args.expected_version:
        expected = args.expected_version.removeprefix("v")
        if version != expected:
            raise RuntimeError(
                f"Tag version {expected!r} does not match pyproject.toml {version!r}"
            )

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    built = [
        build_wheel(target, out_dir, version)
        for target in select_targets(args.target)
    ]
    if args.sdist:
        built.append(build_sdist(out_dir))

    print("\nBuilt distributions:", flush=True)
    for path in built:
        print(f"  {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
