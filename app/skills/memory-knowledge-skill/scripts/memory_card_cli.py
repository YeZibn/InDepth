import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict


def _add_project_root_to_path() -> None:
    current = os.path.abspath(__file__)
    root = os.path.dirname(current)
    for _ in range(6):
        root = os.path.dirname(root)
        if os.path.isdir(os.path.join(root, "app")) and os.path.isdir(os.path.join(root, "db")):
            if root not in sys.path:
                sys.path.insert(0, root)
            return


_add_project_root_to_path()

from app.core.memory.system_memory_store import SystemMemoryStore


def _load_json(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"file not found: {path}")
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("memory card json must be an object")
    return data


def cmd_upsert_json(args: argparse.Namespace) -> int:
    store = SystemMemoryStore(db_file=args.db)
    card = _load_json(args.path)
    result = store.upsert_card(card)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    store = SystemMemoryStore(db_file=args.db)
    rows = store.search_cards(
        stage=args.stage,
        query=args.query,
        limit=args.limit,
        only_active=not args.include_inactive,
    )
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def cmd_due(args: argparse.Namespace) -> int:
    store = SystemMemoryStore(db_file=args.db)
    rows = store.list_due_review_cards(within_days=args.days, limit=args.limit)
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="System memory card CLI")
    parser.add_argument("--db", default="db/system_memory.db", help="sqlite db path")

    sub = parser.add_subparsers(dest="command", required=True)

    upsert = sub.add_parser("upsert-json", help="upsert memory card from a json file")
    upsert.add_argument("path", help="path to memory card json file")
    upsert.set_defaults(func=cmd_upsert_json)

    search = sub.add_parser("search", help="search memory cards")
    search.add_argument("query", nargs="?", default="", help="keyword query")
    search.add_argument("--stage", default="", help="scenario stage filter")
    search.add_argument("--limit", type=int, default=5)
    search.add_argument("--include-inactive", action="store_true")
    search.set_defaults(func=cmd_search)

    due = sub.add_parser("due", help="list cards due for review")
    due.add_argument("--days", type=int, default=7)
    due.add_argument("--limit", type=int, default=50)
    due.set_defaults(func=cmd_due)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
