"""システムプロンプトを組み立てる。

役割・ルール + 国交省 legal corpus を1つの文字列として返す。
Claude API のキャッシュ対象（system blocks）に渡す前提。
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent
ROLE_RULES_PATH = Path(__file__).parent / "01_role_and_rules.md"
EXTRACTED_DIR = ROOT / "extracted"

# 文書のメタ情報（ファイル名 → 表示名 / 出典）
DOCS = [
    ("guideline_v12_R8-1.txt", "建設業法令遵守ガイドライン 第12版（令和8年1月）",
     "https://www.mlit.go.jp/totikensangyo/const/content/001979927.pdf"),
    ("sekoutaisei_manual.txt", "施工体制台帳等活用マニュアル",
     "https://www.mlit.go.jp/common/001067896.pdf"),
    ("sekoutaisei_checkpoint.txt", "施工体制台帳の写しのチェックポイント",
     "https://www.mlit.go.jp/common/001067897.pdf"),
    ("ktr_kensetsugyohou_R8-2.txt", "関東地方整備局『建設工事の適正な施工を確保するための建設業法』(令和8.2版)",
     "https://www.ktr.mlit.go.jp/ktr_content/content/000699485.pdf"),
    ("kkr_all-data_R7-4.txt", "近畿地方整備局 建設業法解説資料 (令和7年4月最終改訂)",
     "https://www.mlit.go.jp/tochi_fudousan_kensetsugyo/const/content/all-data_R0704.pdf"),
    ("kkr_sekoutaisei_270401.txt", "近畿地整 施工体制台帳記入例",
     "https://www.kkr.mlit.go.jp/kensei/kensetsu/qgl8vl0000003mue-att/sekoutaiseidaityou270401.pdf"),
    ("kensetsu_keizai_001855436.txt", "国交省 不動産・建設経済局 建設業課 関連資料",
     "https://www.mlit.go.jp/totikensangyo/const/content/001855436.pdf"),
]


def build_corpus_xml() -> str:
    parts = ["<legal_corpus>"]
    for filename, title, source_url in DOCS:
        path = EXTRACTED_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"missing extracted text: {path}")
        text = path.read_text(encoding="utf-8")
        parts.append(f'<document title="{title}" source="{source_url}">')
        parts.append(text)
        parts.append("</document>")
    parts.append("</legal_corpus>")
    return "\n".join(parts)


def build_system_prompt() -> str:
    role_rules = ROLE_RULES_PATH.read_text(encoding="utf-8")
    corpus = build_corpus_xml()
    return role_rules + "\n\n" + corpus


def build_system_blocks() -> list[dict]:
    """Anthropic API用のsystem blocks（キャッシュ制御付き）を返す。

    2ブロック構成：
      1. 役割・ルール（先頭、~3.9K tokens — Opus 4.7 の最小キャッシュ閾値 4096
         未満なので単独では cache 不可。breakpoint slot を消費しないよう
         cache_control は付けない）
      2. 法令コーパス（~423K tokens、ephemeral cache_control 付き）
         block 1 の breakpoint は prefix 全体（block 0 + block 1 = ~427K）を
         キャッシュするため、block 0 も実質的にキャッシュされる。
    """
    return [
        {
            "type": "text",
            "text": ROLE_RULES_PATH.read_text(encoding="utf-8"),
        },
        {
            "type": "text",
            "text": build_corpus_xml(),
            "cache_control": {"type": "ephemeral"},
        },
    ]


if __name__ == "__main__":
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    blocks = build_system_blocks()
    print(f"system blocks: {len(blocks)}")
    total = 0
    for i, b in enumerate(blocks):
        n = len(enc.encode(b["text"]))
        total += n
        print(f"  block {i}: {n:,} tokens (cache_control={b.get('cache_control', None)})")
    print(f"total: {total:,} tokens (~{total/1_000_000*100:.1f}% of 1M context)")
