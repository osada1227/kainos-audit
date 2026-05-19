"""初期セットアップ: 管理者+カイノス様ユーザーを作成し、認証 cookie_key を生成.

最初に1回だけ実行する想定。出力された情報を:
    - cookie_key  → Streamlit Cloud の Secrets 欄に貼り付け
    - パスワード  → カイノス様に安全な手段で連絡 (パスワード共有ツール等)

このスクリプトを再実行すると既存ユーザーは上書きされる (パスワード再発行)。
"""
from __future__ import annotations

import secrets
import string
import sys
from pathlib import Path

import streamlit_authenticator as stauth
import yaml

CONFIG_PATH = Path(__file__).parent / "auth_config.yaml"


def gen_password(length: int = 14) -> str:
    """記号入りのランダムパスワード (URLセーフ範囲)."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        # 種類混在を保証
        if (
            any(c.islower() for c in pw)
            and any(c.isupper() for c in pw)
            and any(c.isdigit() for c in pw)
        ):
            return pw


INITIAL_USERS = [
    {"username": "kainos", "name": "カイノス様", "email": "kainos@example.com"},
    {"username": "admin", "name": "管理者 (race-tech)", "email": "admin@example.com"},
]


def main() -> int:
    if not CONFIG_PATH.exists():
        print(f"ERROR: {CONFIG_PATH} が見つかりません。", file=sys.stderr)
        return 2

    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    cfg.setdefault("cookie", {})
    cfg.setdefault("credentials", {})
    cfg["credentials"].setdefault("usernames", {})

    cookie_key = secrets.token_urlsafe(32)
    cfg["cookie"]["key"] = "dev-only-replace-via-secrets"  # secrets.tomlで上書き想定
    cfg["cookie"].setdefault("name", "kainos_audit_auth")
    cfg["cookie"].setdefault("expiry_days", 7)

    print("=" * 72)
    print("初期セットアップ完了")
    print("=" * 72)
    print()
    print("【1】Streamlit Cloud の Secrets 欄に貼り付ける値:")
    print()
    print("```toml")
    print("[auth]")
    print(f'cookie_key = "{cookie_key}"')
    print()
    print("[anthropic]")
    print('api_key = "sk-ant-..."  # ← race-tech 側で発行した実キーに置換')
    print("```")
    print()
    print("【2】ログイン用パスワード (カイノス様に安全に連絡):")
    print()

    generated_passwords: dict[str, str] = {}
    for user in INITIAL_USERS:
        pw = gen_password()
        generated_passwords[user["username"]] = pw
        cfg["credentials"]["usernames"][user["username"]] = {
            "email": user["email"],
            "name": user["name"],
            "password": stauth.Hasher.hash(pw),
            "failed_login_attempts": 0,
            "logged_in": False,
        }
        print(f"  ユーザー名 : {user['username']}")
        print(f"  表示名     : {user['name']}")
        print(f"  パスワード : {pw}")
        print()

    CONFIG_PATH.write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"  → auth_config.yaml を更新 ({len(generated_passwords)}ユーザー)")
    print()
    print("=" * 72)
    print("次のステップ:")
    print("  1. 上記 Secrets 値を Streamlit Cloud に登録")
    print("  2. git add auth_config.yaml && git commit -m 'initial users'")
    print("  3. git push → Cloud が自動デプロイ")
    print("  4. パスワードはこの画面以外には保存されない。今すぐ控えてください。")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
