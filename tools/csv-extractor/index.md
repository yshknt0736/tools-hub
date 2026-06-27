# 📊 CSV 高速抽出ツール（軽量版）

GB 超の CSV から、選択した列・行範囲を抜き出す軽量デスクトップアプリ。
**Python 標準ライブラリのみ**で動作。完全ストリーミング処理でメモリ使用量は一定。

## ダウンロード

- **[CSV抽出ツール.exe](CSV抽出ツール.exe)** … Windows 用実行ファイル（Python 不要）

> Windows Defender が警告を出す場合は「詳細情報」→「実行」で起動できます（自前ビルドのため安全です）。

## 特徴

- 列をチェックボックスで選択／行を範囲指定（例: `1-1000, 2001, 3000-5000`）
- 区切り文字を自動判定（カンマ / タブ / セミコロン）
- 文字コード切替（UTF-8 / Shift-JIS / CP932 など）
- 先頭の空行を自動スキップ、空・重複ヘッダーにも対応
- プレビュー（先頭100行）とストリーミング書き出し

## ソースから実行・ビルド

ソースコードは [`src/`](src/) にあります。

```bash
# そのまま実行（依存ゼロ）
python src/csv_extractor.py

# exe をビルド
pip install pyinstaller
python -m PyInstaller --onefile --windowed --name "CSV抽出ツール" src/csv_extractor.py
# → dist/CSV抽出ツール.exe をこのフォルダ直下にコピー
```

## テストデータの生成

```bash
python src/make_test_csv.py 100000 test_data.csv   # 10万行
```
