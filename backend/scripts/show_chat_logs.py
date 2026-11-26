"""Read the chat log in a readable form.

    .venv\\Scripts\\python scripts\\show_chat_logs.py                  # last 10 questions today
    .venv\\Scripts\\python scripts\\show_chat_logs.py --problems       # failures and failed evals
    .venv\\Scripts\\python scripts\\show_chat_logs.py --conversation ID --full
    .venv\\Scripts\\python scripts\\show_chat_logs.py --date 2026-11-26 --source app --last 50
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.chat.chatlog import read_entries  # noqa: E402
from app.core.config import get_settings  # noqa: E402


def short(value, full: bool, size: int = 200) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if full or len(text) <= size else text[:size] + "..."


def is_problem(entry: dict) -> bool:
    if entry.get("status") != "ok" or entry.get("evalProblems"):
        return True
    return any("error" in e or "error" in (e.get("result") or {}) for e in entry.get("events", []))


def render(entry: dict, full: bool) -> str:
    head = f"{entry['ts']}  [{entry['source']}] {entry['status']}  {entry.get('durationMs', '?')} ms"
    lines = ["=" * 90, head, f"conversation: {entry.get('conversationId')}", f"USER   : {entry['message']}"]
    if full:
        lines += [f"  history {turn['role']}: {turn['content']}" for turn in entry.get("history", [])]
    for event in entry.get("events", []):
        if event["type"] == "model":
            tokens = event.get("tokens", {}).get("total")
            lines.append(f"MODEL  : {event['model']}  {event['ms']} ms" + (f"  {tokens} tokens" if tokens else ""))
            if "error" in event:
                lines.append(f"  ERROR  {short(event['error'], full)}")
        elif event["type"] == "tool":
            lines.append(f"TOOL   : {event['name']}({event['arguments']})  {event.get('ms')} ms")
            lines.append(f"  result {short(event.get('result', event.get('error')), full)}")
            for query in event.get("sql", []):
                lines.append(f"  sql    {short(query['sql'], full)}  params={short(query['params'], full)}")
        else:
            lines.append(f"SKIPPED: {event['model']} ({event['why']})")
    if entry.get("modelReply") is not None and entry.get("modelReply") != entry.get("reply"):
        lines.append(f"RAW    : {short(entry['modelReply'], full, 600)}")
    lines.append(f"REPLY  : {short(entry.get('reply', '(none)'), full, 600)}")
    lines += [f"CARD   : {p['summary']}" for p in entry.get("proposals", [])]
    lines += [f"BUTTON : {a['label']} -> {a['href']}" for a in entry.get("actions", [])]
    lines += [f"FAILED : {problem}" for problem in entry.get("evalProblems", [])]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--conversation", help="conversation id (or part of it)")
    parser.add_argument("--source", choices=["app", "eval"])
    parser.add_argument("--problems", action="store_true", help="only failures, tool errors and failed evals")
    parser.add_argument("--last", type=int, default=10)
    parser.add_argument("--full", action="store_true", help="do not shorten anything")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    path = get_settings().chat_log_path / f"{args.date}.jsonl"
    if not path.exists():
        print(f"No chat log for {args.date} ({path})")
        return 1
    entries, unreadable = read_entries(path)
    if unreadable:
        print(f"Skipped {unreadable} unreadable line(s).")
    if args.conversation:
        entries = [e for e in entries if args.conversation in (e.get("conversationId") or "")]
    if args.source:
        entries = [e for e in entries if e["source"] == args.source]
    if args.problems:
        entries = [e for e in entries if is_problem(e)]
    for entry in entries[-args.last :]:
        print(render(entry, args.full))
    print(f"\n{len(entries)} matching entries in {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
