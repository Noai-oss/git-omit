from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from packaging.tags import sys_tags


class CustomBuildHook(BuildHookInterface):
    """Build Zig and put the executable in the wheel's scripts directory."""

    def initialize(self, version: str, build_data: Dict[str, Any]) -> None:
        zig_target = os.environ.get("GIT_OMIT_ZIG_TARGET")
        command = ["zig", "build", "-Doptimize=ReleaseSmall"]
        if zig_target:
            command.append(f"-Dtarget={zig_target}")

        subprocess.run(command, cwd=self.root, check=True)

        binary = self._find_binary(zig_target)
        if binary.suffix != ".exe":
            executable_bits = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            binary.chmod(binary.stat().st_mode | executable_bits)

        wheel_tag = os.environ.get("GIT_OMIT_WHEEL_TAG")
        if wheel_tag is None:
            platform_tag = next(iter(sys_tags())).platform
            wheel_tag = f"py3-none-{platform_tag}"
        elif not wheel_tag.startswith("py3-none-"):
            raise ValueError(
                "GIT_OMIT_WHEEL_TAG must look like "
                "'py3-none-manylinux_2_17_x86_64'"
            )

        build_data["pure_python"] = False
        build_data["tag"] = wheel_tag

        shared_scripts = build_data.setdefault("shared_scripts", {})
        if not isinstance(shared_scripts, dict):
            raise TypeError("Hatch build data contains an invalid shared_scripts value")

        source = binary.relative_to(Path(self.root)).as_posix()
        shared_scripts[source] = binary.name

    def _find_binary(self, zig_target: Optional[str]) -> Path:
        binary_name = os.environ.get("GIT_OMIT_BINARY_NAME")
        if binary_name is None:
            target_is_windows = zig_target is not None and "windows" in zig_target
            has_exe_suffix = target_is_windows or (zig_target is None and os.name == "nt")
            binary_name = "git-omit.exe" if has_exe_suffix else "git-omit"

        binary = Path(self.root, "zig-out", "bin", binary_name)
        if not binary.is_file():
            raise FileNotFoundError(
                f"Zig build did not produce the expected executable: {binary}"
            )
        return binary
