#!/usr/bin/env python3
"""Create, update, inspect, and export Mochi Reviewer state."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_EXPORT_DIRECTORY = Path(r"G:\My Drive\MochiCards")


class StateError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StateError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise StateError(f"Invalid JSON in {path}: {exc}") from exc


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StateError(f"{label} must be a non-empty string")
    return value.strip()


def require_content(value: Any, label: str) -> str:
    """Validate card Markdown without normalizing or trimming its source text."""
    if not isinstance(value, str) or not value.strip():
        raise StateError(f"{label} must be a non-empty string")
    return value


def validate_state(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise StateError("State must be a JSON object")
    if state.get("schemaVersion") != SCHEMA_VERSION:
        raise StateError(f"Unsupported schemaVersion: {state.get('schemaVersion')!r}")
    require_text(state.get("id"), "id")
    require_text(state.get("topic"), "topic")
    if not isinstance(state.get("revision"), int) or state["revision"] < 1:
        raise StateError("revision must be a positive integer")
    if not isinstance(state.get("currentIndex"), int) or state["currentIndex"] < 0:
        raise StateError("currentIndex must be a non-negative integer")
    require_text(state.get("exportDirectory"), "exportDirectory")
    cards = state.get("cards")
    comments = state.get("comments")
    if not isinstance(cards, list) or not isinstance(comments, list):
        raise StateError("cards and comments must be arrays")
    card_ids: set[str] = set()
    for position, card in enumerate(cards, start=1):
        if not isinstance(card, dict):
            raise StateError(f"cards[{position}] must be an object")
        card_id = require_text(card.get("id"), f"cards[{position}].id")
        if card_id in card_ids:
            raise StateError(f"Duplicate card id: {card_id}")
        card_ids.add(card_id)
        require_content(card.get("front"), f"cards[{position}].front")
        require_content(card.get("back"), f"cards[{position}].back")
    comment_ids: set[str] = set()
    for position, comment in enumerate(comments, start=1):
        if not isinstance(comment, dict):
            raise StateError(f"comments[{position}] must be an object")
        comment_id = require_text(comment.get("id"), f"comments[{position}].id")
        if comment_id in comment_ids:
            raise StateError(f"Duplicate comment id: {comment_id}")
        comment_ids.add(comment_id)
        if require_text(comment.get("cardId"), f"comments[{position}].cardId") not in card_ids:
            raise StateError(f"comments[{position}] targets a missing card")
        if comment.get("side") not in {"front", "back"}:
            raise StateError(f"comments[{position}].side must be front or back")
        if comment.get("scope") not in {"side", "line"}:
            raise StateError(f"comments[{position}].scope must be side or line")
        if comment.get("scope") == "line":
            if not isinstance(comment.get("lineNumber"), int) or comment["lineNumber"] < 0:
                raise StateError(f"comments[{position}].lineNumber must be non-negative")
        require_text(comment.get("text"), f"comments[{position}].text")
    if cards:
        state["currentIndex"] = min(state["currentIndex"], len(cards) - 1)
    else:
        state["currentIndex"] = 0
    return state


def load_state(path: Path) -> dict[str, Any]:
    return validate_state(read_json(path))


def slugify_topic(topic: str) -> str:
    slug = re.sub(r"[^0-9A-Za-zА-Яа-яЁё_-]+", "_", topic.strip())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:80] or "cards"


def export_state(state: dict[str, Any], output: Path | None = None) -> Path:
    cards = state["cards"]
    if not cards:
        raise StateError("Cannot export an empty deck")
    export_directory = Path(state["exportDirectory"])
    export_directory.mkdir(parents=True, exist_ok=True)
    if output is None:
        filename = f"mochi_{slugify_topic(state['topic'])}_{dt.date.today().isoformat()}.md"
        output = export_directory / filename
    blocks = [f"{card['front']}\n---\n{card['back']}" for card in cards]
    atomic_write_text(output, "\n\n***\n\n".join(blocks) + "\n")
    return output.resolve()


def command_init(args: argparse.Namespace) -> None:
    draft = read_json(args.draft)
    if not isinstance(draft, dict):
        raise StateError("Draft must be a JSON object")
    topic = require_text(draft.get("topic"), "topic")
    raw_cards = draft.get("cards")
    if not isinstance(raw_cards, list) or not raw_cards:
        raise StateError("cards must be a non-empty array")
    cards = []
    for position, raw_card in enumerate(raw_cards, start=1):
        if not isinstance(raw_card, dict):
            raise StateError(f"cards[{position}] must be an object")
        cards.append(
            {
                "id": require_text(raw_card.get("id"), f"cards[{position}].id")
                if raw_card.get("id")
                else f"card-{position:03d}-{uuid.uuid4().hex[:8]}",
                "front": require_content(raw_card.get("front"), f"cards[{position}].front"),
                "back": require_content(raw_card.get("back"), f"cards[{position}].back"),
            }
        )
    state = {
        "schemaVersion": SCHEMA_VERSION,
        "id": require_text(draft.get("id"), "id") if draft.get("id") else f"deck-{uuid.uuid4().hex}",
        "topic": topic,
        "revision": 1,
        "currentIndex": 0,
        "exportDirectory": str(args.export_directory.resolve()),
        "cards": cards,
        "comments": [],
        "updatedAt": utc_now(),
    }
    validate_state(state)
    args.state.parent.mkdir(parents=True, exist_ok=True)
    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    if not args.template.is_file():
        raise StateError(f"Template not found: {args.template}")
    shutil.copyfile(args.template, args.artifact)
    atomic_write_json(args.state, state)
    if args.active_pointer:
        atomic_write_json(
            args.active_pointer,
            {
                "statePath": str(args.state.resolve()),
                "artifactPath": str(args.artifact.resolve()),
                "deckId": state["id"],
                "updatedAt": state["updatedAt"],
            },
        )
    print(json.dumps({"state": str(args.state.resolve()), "artifact": str(args.artifact.resolve())}, ensure_ascii=False))


def command_apply(args: argparse.Namespace) -> None:
    state = load_state(args.state)
    payload = read_json(args.updates)
    if not isinstance(payload, dict):
        raise StateError("Updates file must contain an object")
    expected = payload.get("expectedRevision")
    if expected != state["revision"]:
        raise StateError(f"Revision conflict: expected {expected}, current {state['revision']}")
    updates = payload.get("updates", [])
    resolved = payload.get("resolvedCommentIds", [])
    if not isinstance(updates, list) or not isinstance(resolved, list):
        raise StateError("updates and resolvedCommentIds must be arrays")
    by_id = {card["id"]: card for card in state["cards"]}
    changed_cards = 0
    for position, update in enumerate(updates, start=1):
        if not isinstance(update, dict):
            raise StateError(f"updates[{position}] must be an object")
        card_id = require_text(update.get("id"), f"updates[{position}].id")
        if card_id not in by_id:
            raise StateError(f"Unknown card id: {card_id}")
        card = by_id[card_id]
        next_front = require_content(update.get("front", card["front"]), f"updates[{position}].front")
        next_back = require_content(update.get("back", card["back"]), f"updates[{position}].back")
        if next_front != card["front"] or next_back != card["back"]:
            card["front"] = next_front
            card["back"] = next_back
            changed_cards += 1
    resolved_ids = {str(value) for value in resolved}
    before = len(state["comments"])
    state["comments"] = [comment for comment in state["comments"] if comment["id"] not in resolved_ids]
    resolved_count = before - len(state["comments"])
    if changed_cards or resolved_count:
        state["revision"] += 1
        state["updatedAt"] = utc_now()
        atomic_write_json(args.state, validate_state(state))
    print(json.dumps({"updatedCards": changed_cards, "resolvedComments": resolved_count, "revision": state["revision"]}, ensure_ascii=False))


def command_comments(args: argparse.Namespace) -> None:
    state = load_state(args.state)
    cards = {card["id"]: card for card in state["cards"]}
    result = []
    for comment in state["comments"]:
        result.append({"card": cards[comment["cardId"]], "comment": comment})
    print(json.dumps({"revision": state["revision"], "items": result}, ensure_ascii=False, indent=2))


def command_export(args: argparse.Namespace) -> None:
    state = load_state(args.state)
    output = export_state(state, args.output)
    print(str(output))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create reviewer state and copy the fixed HTML artifact")
    init_parser.add_argument("--draft", type=Path, required=True)
    init_parser.add_argument("--state", type=Path, required=True)
    init_parser.add_argument("--artifact", type=Path, required=True)
    init_parser.add_argument("--template", type=Path, required=True)
    init_parser.add_argument("--active-pointer", type=Path)
    init_parser.add_argument("--export-directory", type=Path, default=DEFAULT_EXPORT_DIRECTORY)
    init_parser.set_defaults(handler=command_init)

    apply_parser = subparsers.add_parser("apply", help="Apply model-generated card updates without touching HTML")
    apply_parser.add_argument("--state", type=Path, required=True)
    apply_parser.add_argument("--updates", type=Path, required=True)
    apply_parser.set_defaults(handler=command_apply)

    comments_parser = subparsers.add_parser("comments", help="Print pending comments with their current cards")
    comments_parser.add_argument("--state", type=Path, required=True)
    comments_parser.set_defaults(handler=command_comments)

    export_parser = subparsers.add_parser("export", help="Export current cards as Mochi Markdown")
    export_parser.add_argument("--state", type=Path, required=True)
    export_parser.add_argument("--output", type=Path)
    export_parser.set_defaults(handler=command_export)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.handler(args)
        return 0
    except StateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
