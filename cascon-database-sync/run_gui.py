"""CasconSync 图形界面启动入口（供 PyInstaller / 双击 exe 使用）。

使用绝对导入，避免作为脚本入口时出现
「attempted relative import with no known parent package」。
"""

from __future__ import annotations

from cascon_sync.gui import main


if __name__ == "__main__":
    raise SystemExit(main())
