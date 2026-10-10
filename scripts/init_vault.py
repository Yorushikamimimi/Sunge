#!/usr/bin/env python3
"""Create the default private archive after checking its Git boundary."""

from pathlib import Path
import subprocess
import sys


FILES = ("AGENTS.md", "START_HERE.md", "PROFILE.md", "CURRENT.md")


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True
    )


def initialize(root: Path) -> str:
    root = root.resolve()
    top = git(root, "rev-parse", "--show-toplevel")
    if top.returncode or Path(top.stdout.strip()).resolve() != root:
        raise ValueError("请先在 Sunge 根目录建立或克隆 Git 仓库；尚未写入档案。")

    vault = root / "local-vault"
    if vault.is_symlink() or (vault.exists() and not vault.is_dir()):
        raise ValueError("local-vault 必须是本项目中的普通目录，不能是链接或文件。")

    for name in (*FILES, "logs/isolation-probe.md"):
        target = vault / name
        if git(root, "check-ignore", "--no-index", "--quiet", str(target)).returncode:
            raise ValueError("私人目录忽略检查未通过，尚未写入档案。")
    tracked = git(root, "ls-files", "-z", "--", "local-vault")
    if tracked.returncode or tracked.stdout:
        raise ValueError("私人目录已有被跟踪文件或检查失败，尚未写入档案。")

    if vault.exists() and any(vault.iterdir()):
        if all((vault / name).is_file() and not (vault / name).is_symlink() for name in FILES):
            return "入口已经存在；未修改任何已有档案。"
        raise ValueError("本地目录已有内容但入口不完整，请核对后恢复；未覆盖或补写。")

    # Read and validate every public template before the first private write.
    contents = {}
    for name in FILES:
        template = root / "templates" / "vault" / name
        if template.is_symlink() or not template.is_file():
            raise ValueError("空白模板缺失或不是普通文件，尚未写入档案。")
        contents[name] = template.read_text(encoding="utf-8")

    vault.mkdir(mode=0o700, exist_ok=True)
    for name, content in contents.items():
        target = vault / name
        # Exclusive creation also protects against a file appearing after checks.
        with target.open("x", encoding="utf-8") as stream:
            target.chmod(0o600)
            stream.write(content)
    return "已建立 local-vault/ 的空白入口；尚未生成生活记录。"


def main() -> int:
    if len(sys.argv) != 1:
        print("本版只初始化仓库内的 local-vault/，不接受外部目录参数。", file=sys.stderr)
        return 1
    try:
        print(initialize(Path(__file__).resolve().parents[1]))
    except (ValueError, OSError) as exc:
        print(f"初始化停止：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
