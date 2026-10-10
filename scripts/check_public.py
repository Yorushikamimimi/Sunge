#!/usr/bin/env python3
"""Check the explicit publication set without opening private directories."""

from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit


PUBLIC_FILES = (
    ".gitignore", "LICENSE", "README.md", "AGENTS.md", "CURRENT_PROGRESS.md",
    "assistant/PROTOCOL.md",
    "templates/vault/AGENTS.md", "templates/vault/START_HERE.md",
    "templates/vault/PROFILE.md", "templates/vault/CURRENT.md",
    "templates/monthly-log.md",
    "examples/SCENARIO.md", "examples/fictional-vault/AGENTS.md",
    "examples/fictional-vault/START_HERE.md", "examples/fictional-vault/PROFILE.md",
    "examples/fictional-vault/CURRENT.md", "examples/fictional-vault/logs/2026-10.md",
    "materials/interview-summary.md", "materials/SOURCES.md",
    "scripts/init_vault.py", "scripts/check_public.py", "tests/test_safety.py",
)
PRIVATE_DIRS = ("local-vault", "materials/local", ".local-checks")
BLOCKED = {
    "个人绝对路径": r"/" + r"(?:Users|home)/|[A-Za-z]:\\(?:Users|Documents)\\",
    "私人档案链接": "Personal" + "_Archive|" + "obsidian" + "://",
    "个人共读身份": r"\b" + "Ti" + "an" + r"\b|恒" + "生交付岗|CURRENT_" + "JOB_SEARCH",
    "邮箱或凭据": r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|gh[pousr]_\w{20,}|sk-\w{20,}",
}


def content_findings(content: str) -> list[str]:
    return [label for label, pattern in BLOCKED.items() if re.search(pattern, content)]


def inspect(root: Path) -> list[str]:
    root = root.resolve()
    errors = []
    allowed = set(PUBLIC_FILES)
    for args in (("ls-files", "-z"), ("ls-files", "--others", "--exclude-standard", "-z")):
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
        if result.returncode:
            errors.append("Git 文件清单检查失败")
            continue
        for name in filter(None, result.stdout.split("\0")):
            if name not in allowed:
                # Do not print possibly private file names or content.
                errors.append("发现公开清单之外的跟踪或未忽略文件；请在本机核对 Git 状态")
    for directory in PRIVATE_DIRS:
        probe = f"{directory}/isolation-probe.md"
        check = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "--no-index", "--quiet", probe],
            capture_output=True,
        )
        if check.returncode:
            errors.append(f"忽略规则未保护 {directory}/")

    for name in PUBLIC_FILES:
        path = root / name
        if path.is_symlink() or root not in path.resolve().parents or not path.is_file():
            errors.append(f"公开文件缺失、越界或为链接：{name}")
            continue
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            errors.append(f"公开文件为空：{name}")
        for label in content_findings(content):
            errors.append(f"{name}：检测到{label}，请人工检查（不输出匹配内容）")
        if path.suffix == ".md":
            if content.count("```") % 2:
                errors.append(f"代码围栏不成对：{name}")
            for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", content):
                target = target.strip().strip("<>")
                parts = urlsplit(target)
                if parts.scheme in ("https", "http"):
                    continue
                if parts.scheme or target.startswith("/"):
                    errors.append(f"本地链接格式不可公开：{name}")
                    continue
                if not parts.path:
                    continue
                linked = (path.parent / unquote(parts.path)).resolve()
                try:
                    relative = linked.relative_to(root).as_posix()
                except ValueError:
                    errors.append(f"相对链接越界：{name}")
                    continue
                if relative not in allowed or not linked.is_file():
                    errors.append(f"相对链接不在公开清单或目标不存在：{name}")
    return sorted(set(errors))


def main() -> int:
    errors = inspect(Path(__file__).resolve().parents[1])
    if errors:
        print("公开检查未通过：\n" + "\n".join(f"- {error}" for error in errors))
        return 1
    print(f"公开检查通过：{len(PUBLIC_FILES)} 个清单文件；私人目录未跟踪，常见泄露标记与相对链接检查通过。")
    print("限制：外部链接需实际访问；仍须人工核对语义隐私与第三方权利。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
