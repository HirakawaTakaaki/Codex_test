#!/usr/bin/env python3
import cgi
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request, error

BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "index.html"

ALLOWED_EXT = {"jpeg", "jpg", "png", "webp", "pdf", "doc", "docx", "xls", "xlsx", "txt", "csv"}
MAX_FILE_BYTES = 20 * 1024 * 1024

MODEL_MAP = {
    "chatgpt": {"gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"},
    "gemini": {"gemini-2.0-flash", "gemini-1.5-pro"},
    "claude": {"claude-3-5-sonnet", "claude-3-haiku"},
}


def json_response(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def extract_text_snippet(filename, file_bytes):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in {"txt", "csv"}:
        return "(非テキスト形式のためプレビューなし)"
    return file_bytes.decode("utf-8", errors="ignore")[:1200]


def build_prompt(worker_name, instruction_text, target, filename, file_snippet):
    return (
        f"ワーカー名: {worker_name}\n"
        f"命令文: {instruction_text}\n"
        f"対象: {target}\n"
        f"ファイル名: {filename}\n"
        f"ファイルプレビュー:\n{file_snippet}\n\n"
        "上記内容を踏まえ、処理結果を日本語で簡潔に出力してください。"
    )


def process_chatgpt(model, prompt):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "[Mock] OPENAI_API_KEY が未設定のため、ChatGPT連携を模擬実行しました。"

    payload = {
        "model": model,
        "input": prompt,
    }
    req = request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("output_text", "(output_text が空です)")


def process_gemini(model, prompt):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "[Mock] GEMINI_API_KEY が未設定のため、Gemini連携を模擬実行しました。"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    candidates = data.get("candidates", [])
    if not candidates:
        return "(Geminiの応答が空です)"
    parts = candidates[0].get("content", {}).get("parts", [])
    texts = [p.get("text", "") for p in parts if p.get("text")]
    return "\n".join(texts) if texts else "(Geminiのテキスト応答が空です)"


def process_claude(model, prompt):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return "[Mock] ANTHROPIC_API_KEY が未設定のため、Claude連携を模擬実行しました。"

    payload = {
        "model": model,
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    content = data.get("content", [])
    texts = [chunk.get("text", "") for chunk in content if chunk.get("type") == "text"]
    return "\n".join(texts) if texts else "(Claudeのテキスト応答が空です)"


def process_with_provider(provider, model, prompt):
    if provider == "chatgpt":
        return process_chatgpt(model, prompt)
    if provider == "gemini":
        return process_gemini(model, prompt)
    if provider == "claude":
        return process_claude(model, prompt)
    raise ValueError("未対応の provider です")


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in {"/", "/index.html"}:
            body = INDEX_FILE.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self):
        if self.path != "/api/process":
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        ctype, pdict = cgi.parse_header(self.headers.get("content-type", ""))
        if ctype != "multipart/form-data":
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "multipart/form-data で送信してください"})
            return

        pdict["boundary"] = pdict["boundary"].encode("utf-8")
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"}, keep_blank_values=True)

        worker_name = (form.getvalue("workerName") or "").strip()
        instruction_text = (form.getvalue("instruction") or "").strip()
        target = (form.getvalue("target") or "").strip()
        provider = (form.getvalue("provider") or "").strip()
        model = (form.getvalue("model") or "").strip()

        if not worker_name or not instruction_text:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "ワーカー名と命令文は必須です"})
            return

        if provider not in MODEL_MAP:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "provider が不正です"})
            return

        if model not in MODEL_MAP[provider]:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "model が provider と一致しません"})
            return

        upload = form["file"] if "file" in form else None
        if upload is None or not upload.filename:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "ファイルを1つ選択してください"})
            return

        filename = os.path.basename(upload.filename)
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_EXT:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"未対応の拡張子です: {filename}"})
            return

        file_bytes = upload.file.read()
        if len(file_bytes) > MAX_FILE_BYTES:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "ファイルサイズ上限(20MB)を超えています"})
            return

        file_snippet = extract_text_snippet(filename, file_bytes)
        prompt = build_prompt(worker_name, instruction_text, target, filename, file_snippet)

        try:
            result = process_with_provider(provider, model, prompt)
        except error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            json_response(self, HTTPStatus.BAD_GATEWAY, {"error": f"外部API呼び出しエラー: {e.code}", "detail": body[:1000]})
            return
        except Exception as e:
            json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"サーバー内部エラー: {str(e)}"})
            return

        json_response(
            self,
            HTTPStatus.OK,
            {
                "provider": provider,
                "model": model,
                "workerName": worker_name,
                "file": {"name": filename, "size": len(file_bytes)},
                "filePreview": file_snippet,
                "result": result,
            },
        )


def run():
    host = "0.0.0.0"
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"Server running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
