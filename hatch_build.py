import os
import subprocess
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from packaging.tags import sys_tags


class CustomBuildHook(BuildHookInterface):
    """Build Zig and put the executable in the wheel's scripts directory."""

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        zig_target = os.environ.get("GIT_OMIT_ZIG_TARGET")
        command = ["zig", "build", "-Doptimize=ReleaseSmall"]
        if zig_target:
            command.append(f"-Dtarget={zig_target}")

        subprocess.run(command, cwd=self.root, check=True)

        target_is_windows = "windows" in zig_target if zig_target else os.name == "nt"
        binary_name = "git-omit.exe" if target_is_windows else "git-omit"
        binary = Path(self.root, "zig-out", "bin", binary_name)
        if not binary.is_file():
            raise FileNotFoundError(
                f"Zig did not produce the expected binary: {binary}"
            )
        if binary.suffix != ".exe":
            binary.chmod(binary.stat().st_mode | 0o111)

        wheel_tag = os.environ.get("GIT_OMIT_WHEEL_TAG") or (
            f"py3-none-{next(iter(sys_tags())).platform}"
        )

        build_data["pure_python"] = False
        build_data["tag"] = wheel_tag

        source = binary.relative_to(Path(self.root)).as_posix()
        build_data.setdefault("shared_scripts", {})[source] = binary.name
