"""图形操作界面：选择 database / 源目录 / 输出目录并执行同步。"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from .cli import _write_json_report, format_report
from .database import load_database
from .sync import sync_projects


def validate_sync_inputs(
    database: str | Path,
    sources: list[str | Path],
    output: str | Path,
) -> list[str]:
    """校验界面输入，返回错误信息列表（空列表表示通过）。"""
    errors: list[str] = []

    database_path = Path(str(database).strip()) if database else Path()
    if not str(database).strip():
        errors.append("请选择 database.xlsx 文件")
    elif not database_path.is_file():
        errors.append(f"找不到 database 文件: {database_path}")

    cleaned_sources = [Path(str(item).strip()) for item in sources if str(item).strip()]
    if not cleaned_sources:
        errors.append("请至少添加一个 Cascon 源目录")
    else:
        for source in cleaned_sources:
            if not source.is_dir():
                errors.append(f"找不到源目录: {source}")

    output_path = Path(str(output).strip()) if output else Path()
    if not str(output).strip():
        errors.append("请选择公盘输出目录")
    elif output_path.exists() and not output_path.is_dir():
        errors.append(f"输出路径不是目录: {output_path}")

    return errors


class CasconSyncApp:
    """Cascon 同步工具主窗口。"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Cascon 芯片测试文件夹同步")
        self.root.minsize(720, 560)
        self.root.geometry("860x640")

        self.database_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.json_report_var = tk.StringVar()
        self.dry_run_var = tk.BooleanVar(value=True)
        self.overwrite_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="请选择输入路径后开始同步")

        self._busy = False
        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 6}
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(main, text="Cascon 芯片测试文件夹同步", font=("Segoe UI", 14, "bold"))
        title.pack(anchor=tk.W, pady=(0, 8))

        hint = ttk.Label(
            main,
            text="选择 database.xlsx、Cascon 源目录与公盘输出目录。默认开启预览模式，确认无误后再取消勾选正式复制。",
            wraplength=780,
        )
        hint.pack(anchor=tk.W, pady=(0, 10))

        form = ttk.Frame(main)
        form.pack(fill=tk.X)

        # database.xlsx
        row0 = ttk.Frame(form)
        row0.pack(fill=tk.X, **pad)
        ttk.Label(row0, text="database.xlsx", width=16).pack(side=tk.LEFT)
        ttk.Entry(row0, textvariable=self.database_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Button(row0, text="浏览…", command=self._browse_database, width=10).pack(side=tk.RIGHT)

        # source folders
        source_frame = ttk.LabelFrame(form, text="Cascon 源目录（可添加多个工作区或项目文件夹）", padding=8)
        source_frame.pack(fill=tk.BOTH, expand=False, **pad)

        list_row = ttk.Frame(source_frame)
        list_row.pack(fill=tk.BOTH, expand=True)
        self.source_list = tk.Listbox(list_row, height=5, exportselection=False)
        self.source_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(list_row, orient=tk.VERTICAL, command=self.source_list.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.source_list.configure(yscrollcommand=scroll.set)

        source_btns = ttk.Frame(source_frame)
        source_btns.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(source_btns, text="添加目录…", command=self._add_source).pack(side=tk.LEFT)
        ttk.Button(source_btns, text="移除选中", command=self._remove_source).pack(side=tk.LEFT, padx=8)

        # output
        row_out = ttk.Frame(form)
        row_out.pack(fill=tk.X, **pad)
        ttk.Label(row_out, text="公盘输出目录", width=16).pack(side=tk.LEFT)
        ttk.Entry(row_out, textvariable=self.output_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Button(row_out, text="浏览…", command=self._browse_output, width=10).pack(side=tk.RIGHT)

        # optional json report
        row_json = ttk.Frame(form)
        row_json.pack(fill=tk.X, **pad)
        ttk.Label(row_json, text="JSON 报告（可选）", width=16).pack(side=tk.LEFT)
        ttk.Entry(row_json, textvariable=self.json_report_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Button(row_json, text="浏览…", command=self._browse_json_report, width=10).pack(side=tk.RIGHT)

        # options
        options = ttk.Frame(form)
        options.pack(fill=tk.X, **pad)
        ttk.Checkbutton(options, text="预览模式（不实际复制）", variable=self.dry_run_var).pack(side=tk.LEFT)
        ttk.Checkbutton(options, text="目标已存在时覆盖", variable=self.overwrite_var).pack(side=tk.LEFT, padx=16)

        # actions
        actions = ttk.Frame(form)
        actions.pack(fill=tk.X, **pad)
        self.run_button = ttk.Button(actions, text="开始同步", command=self._on_run)
        self.run_button.pack(side=tk.LEFT)
        ttk.Button(actions, text="清空日志", command=self._clear_log).pack(side=tk.LEFT, padx=8)
        ttk.Label(actions, textvariable=self.status_var).pack(side=tk.LEFT, padx=12)

        # log
        log_frame = ttk.LabelFrame(main, text="运行日志", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.log_text = tk.Text(log_frame, wrap=tk.WORD, height=18, state=tk.DISABLED)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=log_scroll.set)

    def _browse_database(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 database.xlsx",
            filetypes=[
                ("Excel 文件", "*.xlsx"),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            self.database_var.set(path)

    def _add_source(self) -> None:
        path = filedialog.askdirectory(title="选择 Cascon 工作区或项目目录")
        if not path:
            return
        existing = set(self.source_list.get(0, tk.END))
        if path not in existing:
            self.source_list.insert(tk.END, path)

    def _remove_source(self) -> None:
        selection = list(self.source_list.curselection())
        for index in reversed(selection):
            self.source_list.delete(index)

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="选择公盘 database 输出目录")
        if path:
            self.output_var.set(path)

    def _browse_json_report(self) -> None:
        path = filedialog.asksaveasfilename(
            title="选择 JSON 报告保存位置",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if path:
            self.json_report_var.set(path)

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text.rstrip() + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.run_button.configure(state=state)
        self.status_var.set("正在同步…" if busy else "就绪")

    def _on_run(self) -> None:
        if self._busy:
            return

        sources = list(self.source_list.get(0, tk.END))
        errors = validate_sync_inputs(self.database_var.get(), sources, self.output_var.get())
        if errors:
            messagebox.showerror("输入有误", "\n".join(errors))
            return

        database = Path(self.database_var.get().strip())
        source_paths = [Path(item) for item in sources]
        output = Path(self.output_var.get().strip())
        dry_run = bool(self.dry_run_var.get())
        overwrite = bool(self.overwrite_var.get())
        json_report = self.json_report_var.get().strip()

        if not dry_run:
            confirmed = messagebox.askyesno(
                "确认正式同步",
                "当前未勾选预览模式，将实际复制文件到公盘输出目录。\n是否继续？",
            )
            if not confirmed:
                return

        self._set_busy(True)
        self._append_log("-" * 60)
        mode = "预览" if dry_run else "正式同步"
        self._append_log(f"开始{mode}…")
        self._append_log(f"database: {database}")
        for source in source_paths:
            self._append_log(f"source: {source}")
        self._append_log(f"output: {output}")

        def worker() -> None:
            try:
                database_obj = load_database(database)
                report = sync_projects(
                    source_paths=source_paths,
                    database=database_obj,
                    dest_root=output,
                    dry_run=dry_run,
                    overwrite=overwrite,
                )
                text = format_report(report)
                if json_report:
                    _write_json_report(report, Path(json_report))
                    text += f"\nJSON 报告已写入: {json_report}"
                exit_code = 1 if report.errors else 0
                self.root.after(0, lambda: self._on_done(text, exit_code, None))
            except Exception as exc:  # noqa: BLE001 - surface any sync failure in UI
                self.root.after(0, lambda: self._on_done("", 1, exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_done(self, report_text: str, exit_code: int, error: BaseException | None) -> None:
        self._set_busy(False)
        if error is not None:
            self.status_var.set("同步失败")
            self._append_log(f"错误: {error}")
            messagebox.showerror("同步失败", str(error))
            return

        self._append_log(report_text)
        if exit_code == 0:
            self.status_var.set("同步完成")
            messagebox.showinfo("完成", "同步已完成，详情见运行日志。")
        else:
            self.status_var.set("同步完成（有错误）")
            messagebox.showwarning("完成（有错误）", "同步结束但存在错误，请查看运行日志。")


def run_app(root_factory: Callable[[], tk.Tk] | None = None) -> int:
    """启动 GUI。返回进程退出码。"""
    factory = root_factory or tk.Tk
    root = factory()
    CasconSyncApp(root)
    root.mainloop()
    return 0


def main() -> int:
    """GUI 入口。"""
    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
