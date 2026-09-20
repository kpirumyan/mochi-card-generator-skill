#!/usr/bin/env python3
"""Serve one Mochi Reviewer artifact and persist its local interactions."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from reviewer_state import StateError, atomic_write_json, export_state, load_state, require_content, require_text, utc_now


MAX_BODY_BYTES = 1_000_000


def content_lines(text: str) -> list[str]:
    return [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]


class ReviewerServer(ThreadingHTTPServer):
    state_path: Path
    artifact_path: Path


class Handler(BaseHTTPRequestHandler):
    server: ReviewerServer

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}", file=sys.stderr)

    def send_bytes(self, status: int, content_type: str, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, status: int, value: Any) -> None:
        self.send_bytes(status, "application/json; charset=utf-8", json.dumps(value, ensure_ascii=False).encode("utf-8"))

    def read_json_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise StateError("Invalid Content-Length") from exc
        if length <= 0 or length > MAX_BODY_BYTES:
            raise StateError("Request body is empty or too large")
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StateError("Request body must be valid UTF-8 JSON") from exc
        if not isinstance(value, dict):
            raise StateError("Request body must be a JSON object")
        return value

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path in {"/", "/mochi-reviewer.html"}:
                self.send_bytes(HTTPStatus.OK, "text/html; charset=utf-8", self.server.artifact_path.read_bytes())
                return
            if path == "/api/state":
                self.send_json(HTTPStatus.OK, load_state(self.server.state_path))
                return
            if path == "/favicon.ico":
                self.send_bytes(HTTPStatus.NO_CONTENT, "image/x-icon", b"")
                return
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
        except (OSError, StateError) as exc:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/api/action":
                self.handle_action(self.read_json_body())
                return
            if path == "/api/export":
                state = load_state(self.server.state_path)
                output = export_state(state)
                self.send_json(HTTPStatus.OK, {"path": str(output), "revision": state["revision"]})
                return
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
        except StateError as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except OSError as exc:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def handle_action(self, payload: dict[str, Any]) -> None:
        state = load_state(self.server.state_path)
        expected = payload.get("expectedRevision")
        if expected != state["revision"]:
            self.send_json(
                HTTPStatus.CONFLICT,
                {"error": "Состояние изменилось. Панель обновлена.", "state": state},
            )
            return
        action = payload.get("type")
        cards = state["cards"]
        comments = state["comments"]
        by_id = {card["id"]: card for card in cards}

        if action == "set_index":
            index = payload.get("index")
            if not isinstance(index, int):
                raise StateError("index must be an integer")
            state["currentIndex"] = max(0, min(index, max(0, len(cards) - 1)))
        elif action == "update_card":
            card_id = require_text(payload.get("cardId"), "cardId")
            side = payload.get("side")
            if card_id not in by_id or side not in {"front", "back"}:
                raise StateError("Unknown card or side")
            by_id[card_id][side] = require_content(payload.get("value"), "value")
        elif action == "add_comment":
            card_id = require_text(payload.get("cardId"), "cardId")
            side = payload.get("side")
            scope = payload.get("scope")
            if card_id not in by_id or side not in {"front", "back"} or scope not in {"side", "line"}:
                raise StateError("Invalid comment target")
            line_number = payload.get("lineNumber") if scope == "line" else None
            snapshot = None
            if scope == "line":
                if not isinstance(line_number, int) or line_number < 0:
                    raise StateError("lineNumber must be non-negative")
                lines = content_lines(by_id[card_id][side])
                if line_number >= len(lines):
                    raise StateError("The target line no longer exists")
                snapshot = lines[line_number]
            comments.append(
                {
                    "id": f"comment-{uuid.uuid4().hex}",
                    "cardId": card_id,
                    "side": side,
                    "scope": scope,
                    "lineNumber": line_number,
                    "lineSnapshot": snapshot,
                    "text": require_text(payload.get("text"), "text"),
                    "createdAt": utc_now(),
                }
            )
        elif action == "delete_comment":
            comment_id = require_text(payload.get("commentId"), "commentId")
            next_comments = [comment for comment in comments if comment["id"] != comment_id]
            if len(next_comments) == len(comments):
                raise StateError("Comment not found")
            state["comments"] = next_comments
        elif action == "update_comment":
            comment_id = require_text(payload.get("commentId"), "commentId")
            comment = next((item for item in comments if item["id"] == comment_id), None)
            if comment is None:
                raise StateError("Comment not found")
            comment["text"] = require_text(payload.get("text"), "text")
            comment["updatedAt"] = utc_now()
        elif action == "delete_card":
            card_id = require_text(payload.get("cardId"), "cardId")
            next_cards = [card for card in cards if card["id"] != card_id]
            if len(next_cards) == len(cards):
                raise StateError("Card not found")
            state["cards"] = next_cards
            state["comments"] = [comment for comment in comments if comment["cardId"] != card_id]
            state["currentIndex"] = min(state["currentIndex"], max(0, len(next_cards) - 1))
        else:
            raise StateError(f"Unknown action: {action!r}")

        state["revision"] += 1
        state["updatedAt"] = utc_now()
        atomic_write_json(self.server.state_path, state)
        self.send_json(HTTPStatus.OK, state)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        load_state(args.state)
        if not args.artifact.is_file():
            raise StateError(f"Artifact not found: {args.artifact}")
    except StateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    server = ReviewerServer((args.host, args.port), Handler)
    server.state_path = args.state.resolve()
    server.artifact_path = args.artifact.resolve()
    url = f"http://{args.host}:{server.server_address[1]}/mochi-reviewer.html"
    print(f"MOCHI_REVIEWER_URL={url}", flush=True)
    print(f"MOCHI_REVIEWER_STATE={server.state_path}", flush=True)
    try:
        server.serve_forever(poll_interval=0.35)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
