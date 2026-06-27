# 🧰 Tools Hub

便利ツール集をまとめる静的サイト。GitHub Pages で無料公開できます。
ビルド不要・依存ゼロ。`tools.json` を編集するだけでツールを追加できます。

## ファイル構成

| ファイル | 役割 |
|---|---|
| `index.html` | ページ本体 |
| `style.css` | スタイル（ライト/ダーク対応） |
| `app.js` | カード描画・検索・タグ絞り込み・テーマ切替 |
| `tools.json` | **ツール一覧データ（ここを編集）** |

## ツールの追加方法

`tools.json` に項目を足すだけです。

```json
{
  "icon": "📊",
  "title": "ツール名",
  "desc": "説明文",
  "tags": ["CSV", "Python"],
  "url": "https://github.com/your-name/repo",
  "cta": "詳しく見る →"
}
```

## ローカルで確認

`fetch` を使うため、ファイルを直接開くのではなく簡易サーバーが必要です。

```bash
python -m http.server 8000
# → http://localhost:8000 を開く
```

## GitHub Pages で公開する手順

1. GitHub で新しいリポジトリを作成（例: `tools-hub`）
2. このフォルダの中身をプッシュ:

   ```bash
   git init
   git add .
   git commit -m "Initial commit: Tools Hub"
   git branch -M main
   git remote add origin https://github.com/<ユーザー名>/tools-hub.git
   git push -u origin main
   ```

3. リポジトリの **Settings → Pages** を開く
4. **Build and deployment → Source** を `Deploy from a branch` に設定
5. Branch を `main` / `(root)` にして **Save**
6. 数十秒後、`https://<ユーザー名>.github.io/tools-hub/` で公開されます

## カスタマイズ

- サイト名: `index.html` の `<h1>` とタイトル
- 配色: `style.css` 冒頭の `:root` 変数
