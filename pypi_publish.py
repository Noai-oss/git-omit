import os
import re
import shutil
import subprocess
import sys

from make_wheels import ROOT, read_project_version


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(2)


if len(sys.argv) != 2 or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", sys.argv[1]):
    fail(f"usage: {sys.argv[0]} x.y.z")

version = sys.argv[1]
project_version = read_project_version()
zon = (ROOT / "build.zig.zon").read_text(encoding="utf-8")
match = re.search(r'^\s*\.version\s*=\s*"([^"]+)"\s*,', zon, re.MULTILINE)
if match is None:
    fail("Could not read .version from build.zig.zon")
zig_version = match.group(1)
if version != project_version or version != zig_version:
    fail(
        f"Version mismatch: argument={version}, pyproject.toml={project_version}, "
        f"build.zig.zon={zig_version}"
    )
if not os.getenv("UV_PUBLISH_TOKEN"):
    fail("UV_PUBLISH_TOKEN is not set")

dist = ROOT / "dist"
tag = f"v{version}"

shutil.rmtree(dist, ignore_errors=True)
subprocess.run(
    [sys.executable, "make_wheels.py", "--sdist"],
    cwd=ROOT,
    check=True,
)
subprocess.run(["uvx", "twine", "check", *dist.iterdir()], cwd=ROOT, check=True)
subprocess.run(["git", "tag", "-a", tag, "-m", tag], cwd=ROOT, check=True)
subprocess.run(["git", "push", "origin", tag], cwd=ROOT, check=True)
subprocess.run(["uv", "publish"], cwd=ROOT, check=True)
