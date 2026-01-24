#!/usr/bin/env python3
"""Local YAML/JSON-driven interview questionnaire with a minimal web UI."""

from __future__ import annotations

import argparse
import http.server
import json
import socketserver
import threading
import webbrowser
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

TEMPLATE_PATH = Path(__file__).with_name("template.html")


@lru_cache(maxsize=1)
def load_template() -> str:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Missing template file: {TEMPLATE_PATH}")
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def _json_for_html(data: Dict[str, Any]) -> str:
    raw = json.dumps(data, ensure_ascii=True)
    return raw.replace("</", "<\\/")


def build_html(data: Dict[str, Any]) -> str:
    return load_template().replace("__QUESTIONS__", _json_for_html(data))


def parse_input(path: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:
            raise ValueError("YAML support requires PyYAML. Install with: pip install pyyaml") from exc
        data = yaml.safe_load(raw)
    else:
        data = json.loads(raw)

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("Questions file must be a JSON/YAML object")
    return data


def load_questions(path: Path) -> Dict[str, Any]:
    data = parse_input(path)
    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError("questions must be a non-empty list")
    for idx, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            raise ValueError("each question must be an object")
        if "id" not in question:
            question["id"] = f"q{idx}"
        if "type" not in question:
            raise ValueError(f"question {question['id']} is missing type")
    return data


def build_output(payload: Dict[str, Any], source_path: Path) -> Dict[str, Any]:
    questions = payload.get("questions", [])
    answers = payload.get("answers", {})
    collected = []
    for question in questions:
        qid = question.get("id")
        collected.append({
            "id": qid,
            "type": question.get("type"),
            "label": question.get("label"),
            "response": answers.get(qid, {}),
        })

    final_note = answers.get("__final_note__", {}).get("text") if isinstance(answers, dict) else None
    return {
        "title": payload.get("title"),
        "description": payload.get("description"),
        "source": str(source_path),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "answers": collected,
        "final_note": final_note,
    }


def run_server(data: Dict[str, Any], host: str, port: int, open_browser: bool, out_path: Path, source_path: Path) -> int:
    done = threading.Event()
    state: Dict[str, Any] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                html = build_html(data)
                encoded = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self) -> None:
            if self.path != "/submit":
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", "0"))
            payload = self.rfile.read(length)
            try:
                state["payload"] = json.loads(payload)
                self.send_response(200)
                self.end_headers()
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                return
            done.set()

        def log_message(self, format: str, *args: Any) -> None:
            return

    with socketserver.TCPServer((host, port), Handler) as httpd:
        actual_port = httpd.server_address[1]
        url = f"http://{host}:{actual_port}/"
        print(f"Interview sheet running at {url}")
        if open_browser:
            try:
                webbrowser.open(url)
            except Exception:
                pass

        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            while not done.wait(0.2):
                pass
        except KeyboardInterrupt:
            print("Interrupted; exiting.")
            return 1
        finally:
            httpd.shutdown()

    payload = state.get("payload")
    if not payload:
        print("No submission received.")
        return 1

    output = build_output({**data, **payload}, source_path)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved answers to {out_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local interview sheet from YAML/JSON")
    parser.add_argument("--in", dest="in_path", required=True, help="Path to questions YAML/JSON")
    parser.add_argument("--out", dest="out_path", help="Path to write answers JSON")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="Port to bind (0 = random free port)")
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser window")
    args = parser.parse_args()

    source_path = Path(args.in_path).expanduser().resolve()
    if not source_path.exists():
        print(f"Questions file not found: {source_path}")
        return 1

    try:
        load_template()
    except FileNotFoundError as exc:
        print(str(exc))
        return 1

    try:
        data = load_questions(source_path)
    except ValueError as exc:
        print(f"Invalid questions file: {exc}")
        return 1

    out_path = Path(args.out_path).expanduser().resolve() if args.out_path else source_path.with_suffix(".answers.json")
    return run_server(data, args.host, args.port, not args.no_open, out_path, source_path)


if __name__ == "__main__":
    raise SystemExit(main())
