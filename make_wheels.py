import argparse
import os
import re
import stat
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Sequence
from pathlib import Path

# Python 3.10 使用开发依赖 tomli，3.11 起使用内置 tomllib。
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent
CLI_NAME = "git-omit"
CLI_NAME_UPPER = CLI_NAME.replace("-", "_").upper()


TARGETS = {
    "x86_64-windows": "py3-none-win_amd64",
    "x86_64-macos.11.0": "py3-none-macosx_11_0_x86_64",
    "aarch64-macos.11.0": "py3-none-macosx_11_0_arm64",
    "x86_64-linux-gnu.2.17": "py3-none-manylinux_2_17_x86_64",
    "aarch64-linux-gnu.2.17": "py3-none-manylinux_2_17_aarch64",
}


def _make_wheel_script_executable(wheel: Path) -> None:
    script_suffix = f".data/scripts/{CLI_NAME}"

    # zipfile 未提供直接更新已有条目元数据的接口，因此重建 wheel 后替换。
    with tempfile.NamedTemporaryFile(
        dir=wheel.parent,
        prefix=f".{wheel.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)

    try:
        with zipfile.ZipFile(wheel) as source:
            matches = [
                info for info in source.infolist() if info.filename.endswith(script_suffix)
            ]
            if len(matches) != 1:
                raise RuntimeError(
                    f"Expected exactly one {CLI_NAME} script in {wheel}, found {len(matches)}"
                )

            script_info = matches[0]
            if (script_info.external_attr >> 16) & 0o111 == 0o111:
                return

            with zipfile.ZipFile(temporary_path, "w") as destination:
                for info in source.infolist():
                    if info.filename == script_info.filename:
                        # 3 表示 Unix；高 16 位保存文件类型和权限，低 16 位保留。
                        info.create_system = 3
                        info.external_attr = ((stat.S_IFREG | 0o755) << 16) | (
                            info.external_attr & 0xFFFF
                        )
                    destination.writestr(info, source.read(info))

        temporary_path.replace(wheel)
    finally:
        temporary_path.unlink(missing_ok=True)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"Cross-compile {CLI_NAME} and build platform wheels.",
    )
    parser.add_argument(
        "--target",
        action="append",
        choices=TARGETS,
        help="Build only this Zig target; may be repeated. Defaults to all targets.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "dist",
        help="Directory for distributions (default: dist).",
    )
    return parser.parse_args(argv)


def read_project_metadata() -> tuple[str, str]:
    try:
        with (ROOT / "pyproject.toml").open("rb") as file:
            project = tomllib.load(file)["project"]
        return project["name"], project["version"]
    except KeyError as error:
        raise RuntimeError(
            "Could not read [project].name and version from pyproject.toml"
        ) from error


def build_wheel(
    zig_target: str,
    wheel_tag: str,
    out_dir: Path,
    distribution_name: str,
    version: str,
) -> Path:
    env = os.environ.copy()
    env[f"{CLI_NAME_UPPER}_ZIG_TARGET"] = zig_target
    env[f"{CLI_NAME_UPPER}_WHEEL_TAG"] = wheel_tag

    print(
        f"\n==> {zig_target} -> {wheel_tag}",
        flush=True,
    )
    subprocess.run(
        [
            "uv",
            "build",
            "--wheel",
            "--out-dir",
            str(out_dir),
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )

    # wheel 包名需转小写，并将连续的 -、_、. 替换为一个下划线。
    # https://packaging.python.org/en/latest/specifications/binary-distribution-format/#escaping-and-unicode
    wheel_name = re.sub(r"[-_.]+", "_", distribution_name).lower()
    wheel = out_dir / f"{wheel_name}-{version}-{wheel_tag}.whl"
    if not wheel.is_file():
        raise FileNotFoundError(f"Build did not produce the expected wheel: {wheel}")

    # Windows 上的 chmod 无法设置 Unix 执行权限。
    # 为 Linux/macOS 构建时，将 wheel 内可执行文件条目的权限设为 0755。
    if os.name == "nt" and "windows" not in zig_target:
        _make_wheel_script_executable(wheel)

    return wheel


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    distribution_name, version = read_project_metadata()

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 按 TARGETS 顺序筛选目标；未指定时构建全部目标。
    selected = set(args.target or ())
    targets = (
        (zig_target, wheel_tag)
        for zig_target, wheel_tag in TARGETS.items()
        if not selected or zig_target in selected
    )
    built = [
        build_wheel(zig_target, wheel_tag, out_dir, distribution_name, version)
        for zig_target, wheel_tag in targets
    ]

    print("\nBuilt distributions:", flush=True)
    for path in built:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
