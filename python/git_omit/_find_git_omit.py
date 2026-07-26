from __future__ import annotations

import os
import shutil
import site
import sysconfig
from pathlib import Path
from typing import Iterator, Set


class GitOmitNotFound(FileNotFoundError):
    """Raised when the Python module cannot locate the native executable."""


def _script_name() -> str:
    executable_suffix = sysconfig.get_config_var("EXE")
    if not isinstance(executable_suffix, str):
        executable_suffix = ".exe" if os.name == "nt" else ""
    return f"git-omit{executable_suffix}"


def _candidate_script_dirs() -> Iterator[Path]:
    scripts = sysconfig.get_path("scripts")
    if scripts:
        yield Path(scripts)

    if site.ENABLE_USER_SITE:
        try:
            preferred_scheme = sysconfig.get_preferred_scheme("user")
        except AttributeError:
            preferred_scheme = "nt_user" if os.name == "nt" else "posix_user"

        user_scripts = sysconfig.get_path("scripts", scheme=preferred_scheme)
        if user_scripts:
            yield Path(user_scripts)

    package_dir = Path(__file__).resolve().parent
    yield package_dir.parent / ("Scripts" if os.name == "nt" else "bin")

    for parent in package_dir.parents:
        if parent.name.lower() not in {"site-packages", "dist-packages"}:
            continue

        if os.name == "nt":
            yield parent.parent.parent / "Scripts"
        else:
            yield parent.parent.parent / "bin"
        break


def find_git_omit_bin() -> str:
    """Return the installed native git-omit executable."""

    override = os.environ.get("GIT_OMIT_BINARY")
    if override:
        binary = Path(override).expanduser()
        if binary.is_file():
            return str(binary)
        raise GitOmitNotFound(
            f"GIT_OMIT_BINARY does not point to a file: {binary}"
        )

    script_name = _script_name()
    checked: Set[Path] = set()
    for directory in _candidate_script_dirs():
        binary = directory / script_name
        if binary in checked:
            continue
        checked.add(binary)
        if binary.is_file():
            return str(binary)

    binary_on_path = shutil.which(script_name)
    if binary_on_path:
        return binary_on_path

    locations = ", ".join(str(path) for path in checked)
    raise GitOmitNotFound(
        f"Could not find {script_name}. Checked: {locations}. "
        "Reinstall the platform wheel or set GIT_OMIT_BINARY."
    )
