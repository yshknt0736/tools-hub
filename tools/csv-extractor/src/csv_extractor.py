"""
CSV高速抽出ツール（軽量版・依存ゼロ）
Python 標準ライブラリのみで動作。GB 超のファイルもストリーミングで処理。
"""

import csv
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# 巨大なセルにも対応できるよう上限を引き上げる
csv.field_size_limit(min(sys.maxsize, 2_147_483_647))


def parse_row_ranges(text: str):
    """
    "1-1000, 2001, 3000-5000" -> 0始まりインデックスの set
    空文字列 -> None (全行)
    """
    text = text.strip()
    if not text:
        return None

    indices: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            indices.update(range(int(lo) - 1, int(hi)))
        else:
            indices.add(int(part) - 1)
    return indices


def sniff_dialect(path: str, encoding: str):
    """区切り文字（, / タブ）を推定。失敗時はカンマ。"""
    with open(path, "r", encoding=encoding, newline="", errors="replace") as f:
        sample = f.read(8192)
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        return csv.excel


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CSV 高速抽出ツール（軽量版）")
        self.geometry("960x720")
        self.minsize(700, 500)

        self._path: str | None = None
        self._dialect = csv.excel
        self._columns: list[str] = []
        self._col_vars: dict[int, tk.BooleanVar] = {}
        self._skip_lines: int = 1  # データ開始までに読み飛ばす行数（空行 + ヘッダー）
        self._encoding = tk.StringVar(value="utf-8-sig")
        self._cancel = threading.Event()

        self._build_ui()

    # ------------------------------------------------------------------ UI --

    def _build_ui(self):
        # ── ファイル選択 ──────────────────────────────────────────────────
        f = ttk.LabelFrame(self, text="ファイル選択", padding=8)
        f.pack(fill="x", padx=8, pady=4)

        self._file_var = tk.StringVar()
        ttk.Entry(f, textvariable=self._file_var, width=55).pack(side="left", fill="x", expand=True)
        ttk.Button(f, text="開く…", command=self._open_file).pack(side="left", padx=4)

        ttk.Label(f, text="文字コード:").pack(side="left", padx=(12, 2))
        ttk.Combobox(f, textvariable=self._encoding, width=11,
                     values=["utf-8-sig", "utf-8", "shift_jis", "cp932", "euc_jp", "latin1"]
                     ).pack(side="left")

        self._info_label = ttk.Label(f, text="")
        self._info_label.pack(side="left", padx=10)

        # ── 列選択 ───────────────────────────────────────────────────────
        cf = ttk.LabelFrame(self, text="列の選択", padding=6)
        cf.pack(fill="both", expand=False, padx=8, pady=4)

        btn_row = ttk.Frame(cf)
        btn_row.pack(fill="x", pady=(0, 4))
        ttk.Button(btn_row, text="全選択", command=self._select_all).pack(side="left")
        ttk.Button(btn_row, text="全解除", command=self._deselect_all).pack(side="left", padx=4)

        canvas = tk.Canvas(cf, height=160, highlightthickness=0)
        vsb = ttk.Scrollbar(cf, orient="vertical", command=canvas.yview)
        hsb = ttk.Scrollbar(cf, orient="horizontal", command=canvas.xview)
        self._col_inner = ttk.Frame(canvas)
        self._col_inner.bind("<Configure>",
            lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self._col_inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        canvas.pack(fill="both", expand=True)

        # ── 行選択 ───────────────────────────────────────────────────────
        rf = ttk.LabelFrame(self, text="行の選択", padding=8)
        rf.pack(fill="x", padx=8, pady=4)

        ttk.Label(rf, text="行番号・範囲（例: 1-1000, 2001, 3000-5000）").pack(anchor="w")
        self._row_var = tk.StringVar()
        ttk.Entry(rf, textvariable=self._row_var, width=60).pack(anchor="w", fill="x")
        ttk.Label(rf, text="空欄 = 全行。行番号は 1 始まり（ヘッダー行を除いたデータ行）。",
                  foreground="gray").pack(anchor="w")

        # ── アクション ───────────────────────────────────────────────────
        af = ttk.Frame(self)
        af.pack(fill="x", padx=8, pady=4)
        ttk.Button(af, text="プレビュー（先頭 100 行）", command=self._preview).pack(side="left")
        ttk.Button(af, text="CSV に書き出し…", command=self._export).pack(side="left", padx=8)
        self._progress = ttk.Progressbar(af, mode="indeterminate", length=200)
        self._progress.pack(side="left")
        self._status = ttk.Label(af, text="")
        self._status.pack(side="right")

        # ── プレビューテーブル ────────────────────────────────────────────
        pf = ttk.LabelFrame(self, text="プレビュー", padding=4)
        pf.pack(fill="both", expand=True, padx=8, pady=4)

        self._tree = ttk.Treeview(pf, show="headings")
        ty = ttk.Scrollbar(pf, orient="vertical", command=self._tree.yview)
        tx = ttk.Scrollbar(pf, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=ty.set, xscrollcommand=tx.set)
        ty.pack(side="right", fill="y")
        tx.pack(side="bottom", fill="x")
        self._tree.pack(fill="both", expand=True)

    # ---------------------------------------------------------------- ファイル読み込み --

    def _open_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("CSV / TSV", "*.csv *.tsv *.txt"), ("すべて", "*.*")])
        if not path:
            return
        self._file_var.set(path)
        self._path = path
        self._set_status("ヘッダー読み込み中…", busy=True)
        threading.Thread(target=self._load_header_thread, daemon=True).start()

    def _load_header_thread(self):
        try:
            enc = self._encoding.get()
            dialect = sniff_dialect(self._path, enc)
            with open(self._path, "r", encoding=enc, newline="", errors="replace") as f:
                reader = csv.reader(f, dialect)
                # 先頭の空行（完全な空行・全セル空白）を読み飛ばしてヘッダーを探す
                skip = 0
                header: list[str] = []
                for row in reader:
                    if any(cell.strip() for cell in row):
                        header = row
                        break
                    skip += 1
            self._dialect = dialect
            self._columns = header
            self._skip_lines = skip + 1  # 空行 + ヘッダー行
            self.after(0, lambda: self._on_header_loaded(skip))
            # 総行数は重いので別途バックグラウンドで数える
            threading.Thread(target=self._count_rows_thread, args=(enc,), daemon=True).start()
        except Exception as e:
            self.after(0, lambda: self._on_error(str(e)))

    def _count_rows_thread(self, enc: str):
        try:
            n = 0
            with open(self._path, "r", encoding=enc, newline="", errors="replace") as f:
                for _ in f:
                    n += 1
            n = max(0, n - self._skip_lines)  # 空行 + ヘッダー行を除外（概算）
            self.after(0, lambda: self._info_label.config(
                text=f"データ行数: 約 {n:,}  列数: {len(self._columns)}"))
        except Exception:
            pass

    def _on_header_loaded(self, skipped: int = 0):
        self._set_status("", busy=False)
        if not self._columns:
            self._info_label.config(text="ヘッダーが見つかりません（空ファイル？）")
            return
        note = f"（先頭 {skipped} 空行を無視）" if skipped else ""
        self._info_label.config(text=f"列数: {len(self._columns)}（行数を計算中…）{note}")

        for w in self._col_inner.winfo_children():
            w.destroy()
        self._col_vars.clear()

        COLS_PER_ROW = 4
        # 列は名前ではなく位置（インデックス）で管理：空ヘッダーや重複名でも壊れない
        for i, col in enumerate(self._columns):
            var = tk.BooleanVar(value=True)
            self._col_vars[i] = var
            label = col if col.strip() else f"(列{i + 1})"
            ttk.Checkbutton(self._col_inner, text=label, variable=var).grid(
                row=i // COLS_PER_ROW, column=i % COLS_PER_ROW, sticky="w", padx=6, pady=1)

    # ---------------------------------------------------------------- 抽出コア --

    def _selected_indices(self) -> list[int]:
        sel = [i for i in range(len(self._columns)) if self._col_vars[i].get()]
        if not sel:
            raise ValueError("列を 1 つ以上選択してください。")
        return sel

    def _iter_rows(self, col_idx: list[int], row_set, limit: int | None):
        """条件に合う行を逐次 yield（ストリーミング）。先頭はヘッダー。"""
        enc = self._encoding.get()
        yield [self._columns[i] for i in col_idx]  # ヘッダー

        emitted = 0
        with open(self._path, "r", encoding=enc, newline="", errors="replace") as f:
            reader = csv.reader(f, self._dialect)
            for _ in range(self._skip_lines):  # 先頭空行 + ヘッダー行を読み飛ばす
                next(reader, None)
            for data_idx, row in enumerate(reader):
                if self._cancel.is_set():
                    break
                if row_set is not None and data_idx not in row_set:
                    continue
                yield [row[i] if i < len(row) else "" for i in col_idx]
                emitted += 1
                if limit is not None and emitted >= limit:
                    break

    # ---------------------------------------------------------------- プレビュー --

    def _preview(self):
        if not self._path:
            messagebox.showwarning("警告", "ファイルを開いてください。")
            return
        self._set_status("プレビュー生成中…", busy=True)
        threading.Thread(target=self._preview_thread, daemon=True).start()

    def _preview_thread(self):
        try:
            col_idx = self._selected_indices()
            row_set = parse_row_ranges(self._row_var.get())
            rows = list(self._iter_rows(col_idx, row_set, limit=100))
            self.after(0, lambda: self._show_preview(rows))
        except Exception as e:
            self.after(0, lambda: self._on_error(str(e)))

    def _show_preview(self, rows: list[list[str]]):
        header, data = rows[0], rows[1:]
        self._set_status(f"プレビュー: {len(data):,} 行", busy=False)
        self._tree.delete(*self._tree.get_children())
        self._tree.configure(columns=header)
        for c in header:
            self._tree.heading(c, text=c)
            self._tree.column(c, width=110, minwidth=60)
        for row in data:
            self._tree.insert("", "end", values=row)

    # ---------------------------------------------------------------- 書き出し --

    def _export(self):
        if not self._path:
            messagebox.showwarning("警告", "ファイルを開いてください。")
            return
        out = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("すべて", "*.*")])
        if not out:
            return
        self._cancel.clear()
        self._set_status("書き出し中…", busy=True)
        threading.Thread(target=self._export_thread, args=(out,), daemon=True).start()

    def _export_thread(self, out_path: str):
        try:
            col_idx = self._selected_indices()
            row_set = parse_row_ranges(self._row_var.get())
            count = 0
            with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                for i, row in enumerate(self._iter_rows(col_idx, row_set, limit=None)):
                    writer.writerow(row)
                    if i > 0:
                        count += 1
                        if count % 100_000 == 0:
                            self.after(0, lambda c=count: self._status.config(
                                text=f"書き出し中… {c:,} 行"))
            self.after(0, lambda: self._on_export_done(out_path, count))
        except Exception as e:
            self.after(0, lambda: self._on_error(str(e)))

    def _on_export_done(self, path: str, count: int):
        self._set_status("書き出し完了 ✓", busy=False)
        messagebox.showinfo("完了", f"{count:,} 行を保存しました:\n{path}")

    # ---------------------------------------------------------------- ヘルパー --

    def _set_status(self, msg: str, *, busy: bool):
        self._status.config(text=msg)
        if busy:
            self._progress.start(12)
        else:
            self._progress.stop()

    def _on_error(self, msg: str):
        self._set_status("エラー", busy=False)
        messagebox.showerror("エラー", msg)

    def _select_all(self):
        for v in self._col_vars.values():
            v.set(True)

    def _deselect_all(self):
        for v in self._col_vars.values():
            v.set(False)


if __name__ == "__main__":
    App().mainloop()
