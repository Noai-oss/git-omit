# Portions derived from Ruff: https://github.com/astral-sh/ruff/tree/main/python/ruff
# Copyright (c) 2022 Charles Marsh
# SPDX-License-Identifier: MIT

import os
import sys

from git_omit import find_git_omit_bin


def _run() -> None:
    git_omit = find_git_omit_bin()

    if sys.platform == "win32":
        import subprocess

        try:
            completed_process = subprocess.run([git_omit, *sys.argv[1:]], check=False)
        except KeyboardInterrupt:
            sys.exit(2)

        sys.exit(completed_process.returncode)
    else:
        os.execvp(git_omit, [git_omit, *sys.argv[1:]])


if __name__ == "__main__":
    _run()
