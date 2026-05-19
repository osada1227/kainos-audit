"""再下請負通知書（全建統一様式第1号-甲）を Claude API で審査する CLI."""
import argparse
import base64
import sys
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

USER_INSTRUCTION = (
    "添付の再下請負通知書（全建統一様式第1号-甲）を、システムプロンプトの"
    "Step 1〜4 と <legal_corpus> に照らして厳格に審査し、指定の出力"
    "フォーマット（全体判定 / 法令違反 / 記載漏れ / 正常項目 / 読み取り"
    "不能 / 実務アドバイス）で Markdown 形式の審査結果を返してください。"
)


def build_user_content(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    if suffix == ".pdf":
        attachment = {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data},
        }
    elif suffix in IMAGE_MEDIA:
        attachment = {
            "type": "image",
            "source": {"type": "base64", "media_type": IMAGE_MEDIA[suffix], "data": data},
        }
    else:
        raise ValueError(
            f"unsupported file type: {suffix}. PDF / PNG / JPG / GIF / WebP のみ対応。"
        )
    return [attachment, {"type": "text", "text": USER_INSTRUCTION}]


def main() -> int:
    parser = argparse.ArgumentParser(description="再下請負通知書を Claude で審査する")
    parser.add_argument("input", type=Path, help="審査対象の PDF または画像ファイル")
    parser.add_argument("--model", default="claude-sonnet-4-6", help="モデルID")
    parser.add_argument("--max-tokens", type=int, default=16000)
    parser.add_argument(
        "--effort",
        default="high",
        choices=["low", "medium", "high", "xhigh", "max"],
        help="thinking depth / agentic token spend",
    )
    parser.add_argument(
        "--thinking-display",
        default="summarized",
        choices=["summarized", "omitted"],
        help="思考過程を表示するか（summarized=stderr に流す / omitted=非表示）",
    )
    parser.add_argument("--output", "-o", type=Path, help="結果を書き出すファイル")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="API送信せず、system blocks のトークン数と入力ファイル情報を表示して終了",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: file not found: {args.input}", file=sys.stderr)
        return 2

    system_blocks = build_system_blocks()
    try:
        user_content = build_user_content(args.input)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    file_bytes = args.input.stat().st_size
    print(
        f"[info] input        : {args.input} ({file_bytes:,} bytes, type={args.input.suffix})",
        file=sys.stderr,
    )
    print(
        f"[info] system blocks: {len(system_blocks)} (ephemeral cache_control 付き)",
        file=sys.stderr,
    )
    print(f"[info] model        : {args.model}", file=sys.stderr)
    print(f"[info] effort       : {args.effort}", file=sys.stderr)

    if args.dry_run:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        total = 0
        for i, b in enumerate(system_blocks):
            n = len(enc.encode(b["text"]))
            total += n
            print(f"[dry-run] system block {i}: {n:,} tokens", file=sys.stderr)
        print(f"[dry-run] system total  : {total:,} tokens", file=sys.stderr)
        print("[dry-run] API送信はスキップしました。", file=sys.stderr)
        return 0

    client = anthropic.Anthropic()
    out_chunks: list[str] = []
    with client.messages.stream(
        model=args.model,
        max_tokens=args.max_tokens,
        thinking={"type": "adaptive", "display": args.thinking_display},
        output_config={"effort": args.effort},
        system=system_blocks,
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        for event in stream:
            if event.type == "content_block_start":
                if event.content_block.type == "thinking":
                    sys.stderr.write("\n[thinking] ")
                    sys.stderr.flush()
                elif event.content_block.type == "text":
                    sys.stderr.write("\n[response]\n")
                    sys.stderr.flush()
            elif event.type == "content_block_delta":
                if event.delta.type == "thinking_delta":
                    sys.stderr.write(event.delta.thinking)
                    sys.stderr.flush()
                elif event.delta.type == "text_delta":
                    text = event.delta.text
                    out_chunks.append(text)
                    sys.stdout.write(text)
                    sys.stdout.flush()
        sys.stdout.write("\n")
        final = stream.get_final_message()

    u = final.usage
    print("", file=sys.stderr)
    print(f"[usage] input        : {u.input_tokens:,}", file=sys.stderr)
    print(f"[usage] cache_create : {u.cache_creation_input_tokens:,}", file=sys.stderr)
    print(f"[usage] cache_read   : {u.cache_read_input_tokens:,}", file=sys.stderr)
    print(f"[usage] output       : {u.output_tokens:,}", file=sys.stderr)
    print(f"[usage] stop_reason  : {final.stop_reason}", file=sys.stderr)

    if args.output:
        args.output.write_text("".join(out_chunks), encoding="utf-8")
        print(f"[info] saved to {args.output}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
