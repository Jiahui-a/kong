"""打包 Windows 可执行文件（双击弹出操作界面）。

在 Windows 上执行：

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
DIST_NAME = "CasconSync"


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("未安装 PyInstaller，请先执行: pip install pyinstaller", file=sys.stderr)
        return 1

    if not SPEC.is_file():
        print(f"找不到打包配置: {SPEC}", file=sys.stderr)
        return 1

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        str(SPEC),
    ]
    print("执行:", " ".join(cmd))
    completed = subprocess.run(cmd, cwd=ROOT, check=False)
    if completed.returncode == 0:
        suffix = ".exe" if sys.platform.startswith("win") else ""
        print(f"打包完成: {ROOT / 'dist' / (DIST_NAME + suffix)}")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
