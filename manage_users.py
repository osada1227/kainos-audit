"""auth_config.yaml のユーザーを追加・削除・一覧する CLI.

使い方:
    python3 manage_users.py list
    python3 manage_users.py add <username> <display_name> <email>
    python3 manage_users.py remove <username>
    python3 manage_users.py rotate <username>   # パスワード再発行
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

import streamlit_authenticator as stauth
import yaml

CONFIG_PATH = Path(__file__).parent / "auth_config.yaml"


def load() -> dict:
    if not CONFIG_PATH.exists():
        print(f"ERROR: {CONFIG_PATH} が見つかりません。", file=sys.stderr)
        sys.exit(2)
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def save(cfg: dict) -> None:
    CONFIG_PATH.write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"saved -> {CONFIG_PATH}")


def cmd_list(_args) -> int:
    cfg = load()
    users = (cfg.get("credentials") or {}).get("usernames") or {}
    if not users:
        print("(ユーザーなし)")
        return 0
    print(f"{'username':<20} {'name':<25} {'email':<40}")
    print("-" * 86)
    for u, info in users.items():
        print(f"{u:<20} {info.get('name', '-'):<25} {info.get('email', '-'):<40}")
    return 0


def _prompt_password() -> str:
    while True:
        p1 = getpass.getpass("パスワード: ")
        if len(p1) < 8:
            print("8文字以上にしてください。")
            continue
        p2 = getpass.getpass("パスワード（確認）: ")
        if p1 != p2:
            print("一致しません。再度入力してください。")
            continue
        return p1


def cmd_add(args) -> int:
    cfg = load()
    users = cfg.setdefault("credentials", {}).setdefault("usernames", {})
    if args.username in users:
        print(f"ERROR: '{args.username}' は既に存在します。", file=sys.stderr)
        return 2
    password = _prompt_password()
    users[args.username] = {
        "email": args.email,
        "name": args.display_name,
        "password": stauth.Hasher.hash(password),
        "failed_login_attempts": 0,
        "logged_in": False,
    }
    save(cfg)
    print(f"added: {args.username} ({args.display_name} / {args.email})")
    return 0


def cmd_remove(args) -> int:
    cfg = load()
    users = (cfg.get("credentials") or {}).get("usernames") or {}
    if args.username not in users:
        print(f"ERROR: '{args.username}' が見つかりません。", file=sys.stderr)
        return 2
    del users[args.username]
    save(cfg)
    print(f"removed: {args.username}")
    return 0


def cmd_rotate(args) -> int:
    cfg = load()
    users = (cfg.get("credentials") or {}).get("usernames") or {}
    if args.username not in users:
        print(f"ERROR: '{args.username}' が見つかりません。", file=sys.stderr)
        return 2
    password = _prompt_password()
    users[args.username]["password"] = stauth.Hasher.hash(password)
    users[args.username]["failed_login_attempts"] = 0
    save(cfg)
    print(f"password rotated: {args.username}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="auth_config.yaml の管理")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list").set_defaults(func=cmd_list)

    add_p = sub.add_parser("add", help="新規ユーザー追加")
    add_p.add_argument("username")
    add_p.add_argument("display_name")
    add_p.add_argument("email")
    add_p.set_defaults(func=cmd_add)

    rm_p = sub.add_parser("remove", help="ユーザー削除")
    rm_p.add_argument("username")
    rm_p.set_defaults(func=cmd_remove)

    ro_p = sub.add_parser("rotate", help="パスワード再発行")
    ro_p.add_argument("username")
    ro_p.set_defaults(func=cmd_rotate)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
