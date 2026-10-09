# git-omit

[English](README.md)

管理仅在本地忽略的 Git 文件。

## 安装

需要 Python 3.10 或更高版本，以及 Git。

```console
uv tool install git-omit
```

也可以安装到 Python 环境：

```console
pip install git-omit
git-omit --help
```

wheel 会将原生 `git-omit` 可执行文件直接安装到当前环境的命令目录。

提供 Windows x86-64、macOS x86-64/Arm64，以及基于 glibc 的 Linux x86-64/Arm64 wheel。

## 命令

| 命令 | 作用 |
| --- | --- |
| `git-omit hide <pattern>...` | 将模式加入 `.git/info/exclude` |
| `git-omit unhide <pattern>...` | 从 `.git/info/exclude` 移除指定模式 |
| `git-omit freeze <path>...` | 为已跟踪文件设置 `skip-worktree` |
| `git-omit unfreeze <path>...` | 清除 `skip-worktree` |
| `git-omit list` | 列出忽略模式和已冻结文件 |

通配符模式需加引号，避免被 shell 提前展开：

```console
git-omit hide '*.log'
```

## 开发与构建

安装 Zig 0.17.0 和 [uv](https://docs.astral.sh/uv/)：

```console
uv sync
uv run git-omit --help
```

运行测试并构建：

```console
zig build test
zig build -Doptimize=ReleaseSmall
```

将五个平台的 wheel 构建到 `dist/`：

```console
uv run python make_wheels.py
```

可用 `--target` 指定构建目标。脚本只生成 wheel，不生成源码包（sdist）。

在 Windows 上构建 Linux/macOS wheel 时，脚本会将包内可执行文件条目的权限设为 `0755`，因为 Windows 的 `chmod` 无法设置 Unix 执行权限。

## 发布

设置 `UV_PUBLISH_TOKEN`，确保 `pyproject.toml`、`build.zig.zon` 与命令参数中的版本一致，并提交所有修改：

```console
uv run python pypi_publish.py 0.0.4
```

脚本检查版本、工作区和本地及远程标签，构建并校验五个平台的 wheel，先上传 PyPI，成功后再创建并推送版本标签。
