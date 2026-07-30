"""打包 Windows 可执行文件（双击弹出操作界面）。

在 Windows 上、于 cascon-database-sync 目录执行：

    pip install -r requirements.txt
    pip install pyinstaller
    python scripts/build_exe.py

生成文件：dist/CasconSync.exe
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "CasconSync.spec"
ENTRY = ROOT / "run_gui.py"
DIST_NAME = "CasconSync"


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("未安装 PyInstaller，请先执行: pip install pyinstaller", file=sys.stderr)
        return 1

    if not ENTRY.is_file():
        print(f"找不到入口脚本: {ENTRY}", file=sys.stderr)
        return 1

    # 优先用相对路径的 CLI 参数打包，避免 .spec 被写成某台机器绝对路径。
    # 若存在便携 .spec，则使用它（含 hiddenimports）。
    if SPEC.is_file():
        cmd = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(SPEC.name),
        ]
    else:
        cmd = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--windowed",
            "--name",
            DIST_NAME,
            "--paths",
            ".",
            str(ENTRY.relative_to(ROOT)),
        ]

    print("执行:", " ".join(cmd))
    print("工作目录:", ROOT)
    completed = subprocess.run(cmd, cwd=ROOT, check=False)
    if completed.returncode == 0:
        suffix = ".exe" if sys.platform.startswith("win") else ""
        print(f"打包完成: {ROOT / 'dist' / (DIST_NAME + suffix)}")
        print("请勿把 PyInstaller 回写后的绝对路径 .spec 提交到仓库。")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
