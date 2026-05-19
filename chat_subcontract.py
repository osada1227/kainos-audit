"""法令コーパスを背景にした対話 / 単発Q&A CLI（セッションJSON永続化）.

使い方:
    # 単発質問
    python3 chat_subcontract.py -s sess.json -q "主任技術者の専任要件は？"

    # PDF/画像を添付して単発質問
    python3 chat_subcontract.py -s sess.json -q "この通知書の問題点は？" -a doc.pdf

    # 対話モード
    python3 chat_subcontract.py -s sess.json -i
        >>> :attach 通知書.pdf
        >>> この書類で社会保険欄に問題はある？
        >>> 修正案を箇条書きで
        >>> :exit
"""
import argparse
import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "system_prompt"))
from build_system_prompt import build_system_blocks  # noqa: E402

import anthropic  # noqa: E402

IMAGE_MEDIA = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def build_attachment(path: Path) -> dict:
    suffix = path.suffix.lower()
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    if suffix == ".pdf":
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data},
        }
    if suffix in IMAGE_MEDIA:
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": IMAGE_MEDIA[suffix], "data": data},
        }
    raise ValueError(
        f"unsupported file type: {suffix}. PDF / PNG / JPG / GIF / WebP のみ対応。"
    )


def build_user_message(text: str, attachments: list[Path]) -> dict:
    content: list[dict] = [build_attachment(p) for p in attachments]
    if text:
        content.append({"type": "text", "text": text})
    if not content:
        raise ValueError("user message must contain at least text or an attachment")
    return {"role": "user", "content": content}


def load_session(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "model": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None,
        "messages": [],
    }


def save_session(path: Path, session: dict) -> None:
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def summarize_message(msg: dict) -> str:
    """Human-readable summary of a stored message for the transcript log."""
    if isinstance(msg["content"], str):
        return msg["content"][:80].replace("\n", " ")
    parts = []
    for block in msg["content"]:
        t = block.get("type")
        if t == "text":
            parts.append(block["text"][:80].replace("\n", " "))
        elif t == "document":
            parts.append(f"<PDF {len(block['source']['data'])//1024}KB>")
        elif t == "image":
            parts.append(f"<image {block['source']['media_type']}>")
    return " | ".join(parts)


def stream_turn(
    client: anthropic.Anthropic,
    *,
    model: str,
    effort: str,
    thinking_display: str,
    max_tokens: int,
    messages: list[dict],
    system_blocks: list[dict],
) -> tuple[str, object]:
    """Stream one turn. Returns (assistant_text, usage)."""
    out: list[str] = []
    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        thinking={"type": "adaptive", "display": thinking_display},
        output_config={"effort": effort},
        system=system_blocks,
        messages=messages,
        cache_control={"type": "ephemeral"},  # auto-cache last cacheable block
    ) as stream:
        for event in stream:
            if event.type == "content_block_start":
                if event.content_block.type == "thinking":
                    sys.stderr.write("\n[thinking] ")
                    sys.stderr.flush()
                elif event.content_block.type == "text":
                    sys.stderr.write("\n[assistant]\n")
                    sys.stderr.flush()
            elif event.type == "content_block_delta":
                if event.delta.type == "thinking_delta":
                    sys.stderr.write(event.delta.thinking)
                    sys.stderr.flush()
                elif event.delta.type == "text_delta":
                    out.append(event.delta.text)
                    sys.stdout.write(event.delta.text)
                    sys.stdout.flush()
        sys.stdout.write("\n")
        final = stream.get_final_message()
    return "".join(out), final


def print_usage(final) -> None:
    u = final.usage
    print(
        f"[usage] in={u.input_tokens:,} cache_w={u.cache_creation_input_tokens:,} "
        f"cache_r={u.cache_read_input_tokens:,} out={u.output_tokens:,} "
        f"stop={final.stop_reason}",
        file=sys.stderr,
    )


def run_turn(
    client: anthropic.Anthropic,
    session: dict,
    session_path: Path,
    text: str,
    attachments: list[Path],
    *,
    model: str,
    effort: str,
    thinking_display: str,
    max_tokens: int,
    system_blocks: list[dict],
) -> None:
    user_msg = build_user_message(text, attachments)
    candidate = session["messages"] + [user_msg]
    reply, final = stream_turn(
        client,
        model=model,
        effort=effort,
        thinking_display=thinking_display,
        max_tokens=max_tokens,
        messages=candidate,
        system_blocks=system_blocks,
    )
    print_usage(final)
    session["messages"].append(user_msg)
    session["messages"].append({"role": "assistant", "content": reply})
    save_session(session_path, session)


def cmd_interactive(args, client, session, system_blocks) -> int:
    turns = len(session["messages"]) // 2
    print(
        f"[info] interactive mode. session={args.session} (turns so far: {turns})",
        file=sys.stderr,
    )
    print(
        "[info] commands: :attach <path>  /  :history  /  :reset  /  :exit",
        file=sys.stderr,
    )
    pending: list[Path] = list(args.attach)
    if pending:
        print(f"[info] pending attachments: {[str(p) for p in pending]}", file=sys.stderr)
    while True:
        try:
            line = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[info] bye", file=sys.stderr)
            return 0
        if not line:
            continue
        if line == ":exit":
            return 0
        if line == ":reset":
            session["messages"] = []
            save_session(args.session, session)
            print("[info] history cleared", file=sys.stderr)
            continue
        if line == ":history":
            for i, m in enumerate(session["messages"]):
                print(f"  [{i}] {m['role']}: {summarize_message(m)}", file=sys.stderr)
            continue
        if line.startswith(":attach "):
            p = Path(line[len(":attach "):].strip())
            if not p.exists():
                print(f"[error] not found: {p}", file=sys.stderr)
                continue
            try:
                build_attachment(p)  # validate
            except ValueError as e:
                print(f"[error] {e}", file=sys.stderr)
                continue
            pending.append(p)
            print(f"[info] queued: {p} (sent with next message)", file=sys.stderr)
            continue
        if line.startswith(":"):
            print(f"[error] unknown command: {line}", file=sys.stderr)
            continue
        try:
            run_turn(
                client,
                session,
                args.session,
                line,
                pending,
                model=args.model,
                effort=args.effort,
                thinking_display=args.thinking_display,
                max_tokens=args.max_tokens,
                system_blocks=system_blocks,
            )
        except anthropic.APIError as e:
            print(f"[error] API: {e}", file=sys.stderr)
            continue
        pending = []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="法令コーパスを背景にした対話 / Q&A CLI"
    )
    parser.add_argument("--session", "-s", type=Path, required=True, help="会話履歴JSONのパス")
    parser.add_argument("--question", "-q", help="単発質問。指定時は1ターン実行して終了")
    parser.add_argument(
        "--attach", "-a", type=Path, action="append", default=[], help="添付ファイル（複数指定可）"
    )
    parser.add_argument("--interactive", "-i", action="store_true", help="対話モード")
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--max-tokens", type=int, default=16000)
    parser.add_argument(
        "--effort",
        default="high",
        choices=["low", "medium", "high", "xhigh", "max"],
    )
    parser.add_argument(
        "--thinking-display",
        default="summarized",
        choices=["summarized", "omitted"],
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="API送信せず、構築結果（system tokens / 添付 / 履歴件数）を表示",
    )
    args = parser.parse_args()

    if not args.interactive and not args.question:
        parser.error("--interactive か --question のどちらかが必要です")

    for a in args.attach:
        if not a.exists():
            print(f"ERROR: attachment not found: {a}", file=sys.stderr)
            return 2

    session = load_session(args.session)
    if session["model"] and session["model"] != args.model:
        print(
            f"[warn] session was created with {session['model']}, now using {args.model}",
            file=sys.stderr,
        )
    session["model"] = args.model

    system_blocks = build_system_blocks()

    turns_so_far = len(session["messages"]) // 2
    print(
        f"[info] session    : {args.session} (turns so far: {turns_so_far})",
        file=sys.stderr,
    )
    print(f"[info] model      : {args.model}", file=sys.stderr)
    print(f"[info] effort     : {args.effort}", file=sys.stderr)
    print(f"[info] attachments: {[str(p) for p in args.attach]}", file=sys.stderr)

    if args.dry_run:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        total = sum(len(enc.encode(b["text"])) for b in system_blocks)
        print(f"[dry-run] system tokens (cl100k): {total:,}", file=sys.stderr)
        if args.question:
            try:
                msg = build_user_message(args.question, args.attach)
            except ValueError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                return 2
            print(
                f"[dry-run] would send user msg with {len(msg['content'])} content block(s):",
                file=sys.stderr,
            )
            for b in msg["content"]:
                t = b["type"]
                if t == "text":
                    print(f"  - text ({len(b['text'])} chars)", file=sys.stderr)
                elif t == "document":
                    kb = len(b["source"]["data"]) // 1024
                    print(f"  - document/pdf ({kb}KB base64)", file=sys.stderr)
                elif t == "image":
                    kb = len(b["source"]["data"]) // 1024
                    print(f"  - image/{b['source']['media_type']} ({kb}KB base64)", file=sys.stderr)
        else:
            print("[dry-run] interactive mode — no request built", file=sys.stderr)
        print("[dry-run] API送信はスキップしました。", file=sys.stderr)
        return 0

    client = anthropic.Anthropic()

    if args.question:
        try:
            run_turn(
                client,
                session,
                args.session,
                args.question,
                args.attach,
                model=args.model,
                effort=args.effort,
                thinking_display=args.thinking_display,
                max_tokens=args.max_tokens,
                system_blocks=system_blocks,
            )
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        return 0

    return cmd_interactive(args, client, session, system_blocks)


if __name__ == "__main__":
    raise SystemExit(main())
