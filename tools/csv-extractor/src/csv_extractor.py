"""
CSV高速抽出ツール（軽量版・依存ゼロ）
Python 標準ライブラリのみで動作。GB 超のファイルもストリーミングで処理。
"""

import csv
import os
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# 巨大なセルにも対応できるよう上限を引き上げる
csv.field_size_limit(min(sys.maxsize, 2_147_483_647))


def parse_row_ranges(text: str):
    """
    "1-1000, 2001, 3000-5000" -> 0始まりの閉区間リスト。
    巨大範囲でも行番号ごとのsetを作らない。
    空文字列 -> None (全行)
    """
    text = text.strip()
    if not text:
        return None

    ranges: list[tuple[int, int]] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            raise ValueError("行範囲に空の項目があります。例: 1-100, 201")
        bounds = part.split("-")
        if len(bounds) > 2 or not all(bound.strip().isdigit() for bound in bounds):
            raise ValueError(f"行範囲の形式が不正です: {part}")
        lo = int(bounds[0])
        hi = int(bounds[-1])
        if lo < 1 or hi < lo:
            raise ValueError(f"行範囲は1以上の昇順で指定してください: {part}")
        ranges.append((lo - 1, hi - 1))
    ranges.sort()
    merged: list[list[int]] = []
    for lo, hi in ranges:
        if merged and lo <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return [tuple(item) for item in merged]


def row_selected(index: int, ranges) -> bool:
    if ranges is None:
        return True
    # 区間の数は通常少ない。巨大CSVでもメモリ使用量は一定。
    return any(lo <= index <= hi for lo, hi in ranges)


def sniff_dialect(path: str, encoding: str):
    """区切り文字（, / タブ）を推定。失敗時はカンマ。"""
    with open(path, "r", encoding=encoding, newline="") as f:
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
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TLabelframe", padding=8)
        style.configure("TLabelframe.Label", font=("Yu Gothic UI", 10, "bold"))

        self._path: str | None = None
        self._dialect = csv.excel
        self._columns: list[str] = []
        self._col_vars: dict[int, tk.BooleanVar] = {}
        self._skip_lines: int = 1  # データ開始までに読み飛ばす行数（空行 + ヘッダー）
        self._encoding = tk.StringVar(value="utf-8-sig")
        self._cancel = threading.Event()
        self._load_generation = 0
        self._working = False

        self._build_ui()

    # ------------------------------------------------------------------ UI --

    def _build_ui(self):
        # ── ファイル選択 ──────────────────────────────────────────────────
        f = ttk.LabelFrame(self, text="ファイル選択", padding=8)
        f.pack(fill="x", padx=8, pady=4)

        self._file_var = tk.StringVar()
        ttk.Entry(f, textvariable=self._file_var, width=55, state="readonly").pack(side="left", fill="x", expand=True)
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
        self._preview_btn = ttk.Button(af, text="プレビュー（先頭 100 行）", command=self._preview)
        self._preview_btn.pack(side="left")
        self._export_btn = ttk.Button(af, text="CSV に書き出し…", command=self._export)
        self._export_btn.pack(side="left", padx=8)
        self._cancel_btn = ttk.Button(af, text="中止", command=self._cancel.set, state="disabled")
        self._cancel_btn.pack(side="left")
        self._progress = ttk.Progressbar(af, mode="indeterminate", length=200)
        self._progress.pack(side="left")
        self._status = ttk.Label(af, text="")
        self._status.pack(side="right")

        # ── 列の位置で分割 ───────────────────────────────────────────────
        sf = ttk.LabelFrame(self, text="列の位置で分割（指定列の手前で2つに分ける）", padding=8)
        sf.pack(fill="x", padx=8, pady=4)
        ttk.Label(sf, text="後半の先頭にする列:").pack(side="left")
        self._split_col = ttk.Combobox(sf, width=28, state="readonly")
        self._split_col.pack(side="left", padx=6)
        self._split_btn = ttk.Button(sf, text="フォルダに分割出力…", command=self._split_export)
        self._split_btn.pack(side="left", padx=6)
        self._split_hint = ttk.Label(sf, text="", foreground="gray")
        self._split_hint.pack(side="left", padx=6)
        self._split_col.bind("<<ComboboxSelected>>", lambda _: self._update_split_hint())

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
        self._load_generation += 1
        generation = self._load_generation
        enc = self._encoding.get()
        self._file_var.set(path)
        self._path = None
        self._columns = []
        self._set_status("ヘッダー読み込み中…", busy=True)
        threading.Thread(target=self._load_header_thread, args=(path, enc, generation), daemon=True).start()

    def _load_header_thread(self, path: str, enc: str, generation: int):
        try:
            dialect = sniff_dialect(path, enc)
            with open(path, "r", encoding=enc, newline="") as f:
                reader = csv.reader(f, dialect)
                # 先頭の空行（完全な空行・全セル空白）を読み飛ばしてヘッダーを探す
                skip = 0
                header: list[str] = []
                for row in reader:
                    if any(cell.strip() for cell in row):
                        header = row
                        break
                    skip += 1
            self.after(0, lambda: self._on_header_loaded(path, enc, dialect, header, skip, generation))
            # 総行数は重いので別途バックグラウンドで数える
            threading.Thread(target=self._count_rows_thread,
                             args=(path, enc, dialect, skip + 1, generation), daemon=True).start()
        except Exception as e:
            msg = str(e)
            self.after(0, lambda: self._on_error(msg) if generation == self._load_generation else None)

    def _count_rows_thread(self, path: str, enc: str, dialect, skip_lines: int, generation: int):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                reader = csv.reader(f, dialect)
                for _ in range(skip_lines):
                    next(reader, None)
                n = sum(1 for _ in reader)
            self.after(0, lambda: self._info_label.config(
                text=f"データ行数: {n:,}  列数: {len(self._columns)}")
                if generation == self._load_generation else None)
        except Exception:
            pass

    def _on_header_loaded(self, path, enc, dialect, header, skipped, generation):
        if generation != self._load_generation:
            return
        self._path = path
        self._dialect = dialect
        self._columns = header
        self._skip_lines = skipped + 1
        self._source_encoding = enc
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

        # 分割位置リスト（重複名でも一意になるよう "位置: 名前" 形式）
        # 先頭列を境界にすると前半が空になるため、2列目以降を候補にする
        choices = [f"{i + 1}: {c if c.strip() else f'(列{i + 1})'}"
                   for i, c in enumerate(self._columns) if i >= 1]
        self._split_col["values"] = choices
        if choices:
            self._split_col.current(0)
        self._update_split_hint()

    def _update_split_hint(self):
        """選択中の分割位置に応じて、前半／後半の列範囲を表示する。"""
        sel = self._split_col.get()
        if not sel or not self._columns:
            self._split_hint.config(text="")
            return
        key = int(sel.split(":", 1)[0]) - 1
        cols = [c if c.strip() else f"(列{i + 1})" for i, c in enumerate(self._columns)]
        left = f"{cols[0]}〜{cols[key - 1]}" if key >= 1 else "（なし）"
        right = f"{cols[key]}〜{cols[-1]}"
        self._split_hint.config(text=f"前半: {left}  ／  後半: {right}")

    # ---------------------------------------------------------------- 抽出コア --

    def _selected_indices(self) -> list[int]:
        sel = [i for i in range(len(self._columns)) if self._col_vars[i].get()]
        if not sel:
            raise ValueError("列を 1 つ以上選択してください。")
        return sel

    def _iter_rows(self, col_idx: list[int], row_ranges, limit: int | None,
                   path: str, enc: str, dialect, skip_lines: int, columns: list[str]):
        """条件に合う行を逐次 yield（ストリーミング）。先頭はヘッダー。"""
        yield [columns[i] for i in col_idx]  # ヘッダー

        emitted = 0
        with open(path, "r", encoding=enc, newline="") as f:
            reader = csv.reader(f, dialect)
            for _ in range(skip_lines):  # 先頭空行 + ヘッダー行を読み飛ばす
                next(reader, None)
            for data_idx, row in enumerate(reader):
                if self._cancel.is_set():
                    break
                if not row_selected(data_idx, row_ranges):
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
        if self._working:
            return
        try:
            col_idx = self._selected_indices()
            row_ranges = parse_row_ranges(self._row_var.get())
        except ValueError as e:
            messagebox.showwarning("入力を確認", str(e))
            return
        self._cancel.clear()
        job = (self._path, self._source_encoding, self._dialect,
               self._skip_lines, self._columns[:])
        self._set_status("プレビュー生成中…", busy=True)
        threading.Thread(target=self._preview_thread,
                         args=(col_idx, row_ranges, job), daemon=True).start()

    def _preview_thread(self, col_idx, row_ranges, job):
        try:
            rows = list(self._iter_rows(col_idx, row_ranges, 100, *job))
            self.after(0, lambda: self._show_preview(rows))
        except Exception as e:
            msg = str(e)
            self.after(0, lambda: self._on_error(msg))

    def _show_preview(self, rows: list[list[str]]):
        header, data = rows[0], rows[1:]
        self._set_status(f"プレビュー: {len(data):,} 行", busy=False)
        self._tree.delete(*self._tree.get_children())
        column_ids = [f"col_{i}" for i in range(len(header))]
        self._tree.configure(columns=column_ids)
        for i, c in enumerate(header):
            self._tree.heading(column_ids[i], text=c or f"(列{i + 1})")
            self._tree.column(column_ids[i], width=130, minwidth=60)
        for row in data:
            self._tree.insert("", "end", values=row)

    # ---------------------------------------------------------------- 書き出し --

    def _export(self):
        if not self._path:
            messagebox.showwarning("警告", "ファイルを開いてください。")
            return
        if self._working:
            return
        try:
            col_idx = self._selected_indices()
            row_ranges = parse_row_ranges(self._row_var.get())
        except ValueError as e:
            messagebox.showwarning("入力を確認", str(e))
            return
        out = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("すべて", "*.*")])
        if not out:
            return
        if os.path.normcase(os.path.abspath(out)) == os.path.normcase(os.path.abspath(self._path)):
            messagebox.showwarning("入力を確認", "入力元ファイルに上書き保存はできません。")
            return
        self._cancel.clear()
        job = (self._path, self._source_encoding, self._dialect,
               self._skip_lines, self._columns[:])
        self._set_status("書き出し中…", busy=True)
        threading.Thread(target=self._export_thread,
                         args=(out, col_idx, row_ranges, job), daemon=True).start()

    def _export_thread(self, out_path: str, col_idx, row_ranges, job):
        temp_path = None
        try:
            count = 0
            with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="",
                                             dir=os.path.dirname(out_path) or ".",
                                             prefix=".csv-extractor-", suffix=".tmp", delete=False) as f:
                temp_path = f.name
                writer = csv.writer(f)
                for i, row in enumerate(self._iter_rows(col_idx, row_ranges, None, *job)):
                    writer.writerow(row)
                    if i > 0:
                        count += 1
                        if count % 100_000 == 0:
                            self.after(0, lambda c=count: self._status.config(
                                text=f"書き出し中… {c:,} 行"))
            if self._cancel.is_set():
                self.after(0, lambda: self._set_status("中止しました", busy=False))
                return
            os.replace(temp_path, out_path)
            temp_path = None
            self.after(0, lambda: self._on_export_done(out_path, count))
        except Exception as e:
            msg = str(e)
            self.after(0, lambda: self._on_error(msg))
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    # ---------------------------------------------------------------- 列の値で分割 --

    def _split_export(self):
        if not self._path:
            messagebox.showwarning("警告", "ファイルを開いてください。")
            return
        if self._working:
            return
        sel = self._split_col.get()
        if not sel:
            messagebox.showwarning("警告", "分割位置の列を選択してください。")
            return
        key_idx = int(sel.split(":", 1)[0]) - 1  # "5: 年齢" -> 4（後半の先頭列）
        if key_idx < 1:
            messagebox.showwarning("警告", "前半が空になります。2列目以降を選んでください。")
            return
        try:
            row_ranges = parse_row_ranges(self._row_var.get())
        except ValueError as e:
            messagebox.showwarning("入力を確認", str(e))
            return
        out_dir = filedialog.askdirectory(title="分割ファイルの出力先フォルダを選択")
        if not out_dir:
            return
        stem = os.path.splitext(os.path.basename(self._path))[0]
        left_path = os.path.join(out_dir, self._safe_name(f"{stem}_left"))
        right_path = os.path.join(out_dir, self._safe_name(f"{stem}_right"))
        if any(os.path.exists(path) for path in (left_path, right_path)):
            if not messagebox.askyesno("上書き確認", "分割先に同名ファイルがあります。上書きしますか？"):
                return
        self._cancel.clear()
        job = (self._path, self._source_encoding, self._dialect,
               self._skip_lines, self._columns[:])
        self._set_status("分割書き出し中…", busy=True)
        threading.Thread(target=self._split_thread,
                         args=(left_path, right_path, key_idx, row_ranges, job), daemon=True).start()

    def _split_thread(self, left_path: str, right_path: str, key_idx: int, row_ranges, job):
        """指定列の手前で列を 2 分割し、それぞれ別ファイルに全行を書き出す。"""
        path, enc, dialect, skip_lines, columns = job
        ncol = len(columns)
        left_idx = list(range(0, key_idx))      # 前半: 0 〜 key-1
        right_idx = list(range(key_idx, ncol))   # 後半: key 〜 末尾
        total = 0
        temp_left = temp_right = None
        try:
            fl = tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="",
                                             dir=os.path.dirname(left_path), prefix=".csv-left-", delete=False)
            temp_left = fl.name
            fr = tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="",
                                             dir=os.path.dirname(right_path), prefix=".csv-right-", delete=False)
            temp_right = fr.name
            wl, wr = csv.writer(fl), csv.writer(fr)
            wl.writerow([columns[i] for i in left_idx])
            wr.writerow([columns[i] for i in right_idx])

            with open(path, "r", encoding=enc, newline="") as f:
                reader = csv.reader(f, dialect)
                for _ in range(skip_lines):
                    next(reader, None)
                for data_idx, row in enumerate(reader):
                    if self._cancel.is_set():
                        break
                    if not row_selected(data_idx, row_ranges):
                        continue
                    wl.writerow([row[i] if i < len(row) else "" for i in left_idx])
                    wr.writerow([row[i] if i < len(row) else "" for i in right_idx])
                    total += 1
                    if total % 100_000 == 0:
                        self.after(0, lambda t=total: self._status.config(
                            text=f"分割中… {t:,} 行"))
            fl.close()
            fr.close()
            if self._cancel.is_set():
                self.after(0, lambda: self._set_status("中止しました", busy=False))
                return
            os.replace(temp_left, left_path)
            temp_left = None
            os.replace(temp_right, right_path)
            temp_right = None
            self.after(0, lambda: self._on_split_done(
                os.path.basename(left_path), os.path.basename(right_path), total))
        except Exception as e:
            msg = str(e)
            self.after(0, lambda: self._on_error(msg))
        finally:
            for handle in (locals().get("fl"), locals().get("fr")):
                if handle and not handle.closed:
                    handle.close()
            for temp_path in (temp_left, temp_right):
                if temp_path and os.path.exists(temp_path):
                    os.unlink(temp_path)

    @staticmethod
    def _safe_name(name: str) -> str:
        """ファイル名に使えない文字を除去し .csv を付ける。"""
        for ch in '\\/:*?"<>|':
            name = name.replace(ch, "_")
        return name[:120] + ".csv"

    def _on_split_done(self, left: str, right: str, total: int):
        self._set_status("分割完了 ✓", busy=False)
        messagebox.showinfo(
            "完了",
            f"各 {total:,} 行を 2 ファイルに分割しました:\n"
            f"・前半: {left}\n・後半: {right}")

    def _on_export_done(self, path: str, count: int):
        self._set_status("書き出し完了 ✓", busy=False)
        messagebox.showinfo("完了", f"{count:,} 行を保存しました:\n{path}")

    # ---------------------------------------------------------------- ヘルパー --

    def _set_status(self, msg: str, *, busy: bool):
        self._working = busy
        self._status.config(text=msg)
        for button in (self._preview_btn, self._export_btn, self._split_btn):
            button.configure(state="disabled" if busy else "normal")
        self._cancel_btn.configure(state="normal" if busy else "disabled")
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
