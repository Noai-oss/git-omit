"""Exercise an installed native CLI in a disposable Git repository."""
import subprocess
import sys
import tempfile
from pathlib import Path

cli = str(Path(sys.argv[1]).resolve())


def run(*args: str, cwd: Path | None = None, check: bool = True):
    return subprocess.run(args, cwd=cwd, check=check, capture_output=True, text=True)


assert "Usage: git-omit" in run(cli, "--help").stdout
assert run(cli, "--version").stdout.startswith("git-omit ")

with tempfile.TemporaryDirectory() as directory:
    repo = Path(directory)
    run("git", "init", "--quiet", cwd=repo)
    run("git", "config", "core.autocrlf", "false", cwd=repo)
    tracked = repo / "tracked file.txt"
    tracked.write_text("original\n", encoding="utf-8")
    run("git", "add", "--", tracked.name, cwd=repo)

    (repo / "local.log").write_text("local\n", encoding="utf-8")
    run(cli, "hide", "*.log", cwd=repo)
    assert run("git", "check-ignore", "local.log", cwd=repo).stdout.strip() == "local.log"
    assert "hide\t*.log" in run(cli, "list", cwd=repo).stdout.splitlines()

    run(cli, "freeze", tracked.name, cwd=repo)
    assert run("git", "ls-files", "-v", "--", tracked.name, cwd=repo).stdout.startswith("S ")
    assert f"freeze\t{tracked.name}" in run(cli, "list", cwd=repo).stdout.splitlines()
    tracked.write_text("changed\n", encoding="utf-8")
    assert not run("git", "diff", "--name-only", cwd=repo).stdout

    run(cli, "unfreeze", tracked.name, cwd=repo)
    assert run("git", "diff", "--name-only", cwd=repo).stdout.strip() == tracked.name
    assert f"freeze\t{tracked.name}" not in run(cli, "list", cwd=repo).stdout.splitlines()

    run(cli, "unhide", "*.log", cwd=repo)
    assert run("git", "check-ignore", "local.log", cwd=repo, check=False).returncode == 1
    assert "hide\t*.log" not in run(cli, "list", cwd=repo).stdout.splitlines()

print("Installed git-omit passed all command checks.")
