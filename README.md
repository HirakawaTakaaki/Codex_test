# マイAIワーカー (フロント + バックエンド)

ChatGPT / Gemini / Claude のいずれかを選択し、文章・ファイルを処理するサンプル実装です。

## 対応ファイル形式（1ファイル）

- jpeg / jpg / png / webp
- PDF
- Docs (`.doc`, `.docx`)
- Excel (`.xls`, `.xlsx`)
- Txt (`.txt`)
- CSV (`.csv`)

## 起動方法

1. `.env.example` をコピーして `.env` を作成し、必要なAPIキーを設定します。

```bash
cp .env.example .env
```

2. サーバーを起動します。

```bash
python3 server.py
```

- デフォルトは `http://127.0.0.1:8000`
- `PORT` 環境変数で変更できます。

## APIキー設定（.env）

`.env` に以下を記述してください。

- ChatGPT: `OPENAI_API_KEY`
- Gemini: `GEMINI_API_KEY`
- Claude: `ANTHROPIC_API_KEY`

`server.py` 起動時に `.env` を読み込みます。シェルで既に同名の環境変数がある場合は、その値を優先します。

未設定の場合はモック応答を返します。

## 使い方

1. `http://127.0.0.1:8000` を開く。
2. ワーカー名、命令文、リサーチ対象を入力。
3. ファイルを1つ選択。
4. API種別（ChatGPT / Gemini / Claude）とモデルを選択。
5. 実行ボタンでバックエンド `/api/process` を呼び出し、結果を表示。

## 補足

- `txt` / `csv` は先頭テキストをバックエンドで抽出し、**画面上にプレビュー表示**した上でプロンプトへ利用します。
- それ以外の形式は「非テキスト形式のためプレビューなし」と表示します。
