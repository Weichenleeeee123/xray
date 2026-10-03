"""Create or promote a shared demo account from the server terminal.

Run from backend: python tools/admin_account.py admin@example.com
Existing passwords are preserved. New passwords are entered using getpass.
Uses XRAY_PRIVATE_DIR; production must load the service environment first.
"""
import argparse
from getpass import getpass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import accounts


def main():
    parser = argparse.ArgumentParser(description="创建或提升不限研究次数的管理员账号")
    parser.add_argument("email", help="管理员邮箱")
    args = parser.parse_args()
    try:
        email = accounts.normalize_email(args.email)
        if accounts._by_email(email) is None:
            password = getpass("新账号密码（至少 8 位）：")
            if getpass("再次输入密码：") != password:
                parser.error("两次密码不一致")
            accounts.register(email, password)
        accounts.grant_admin(email)
    except accounts.AccountError as error:
        parser.exit(1, error.detail + "\n")
    print(f"管理员账号已启用：{email}；研究次数不限额，可多设备同时登录。")


if __name__ == "__main__":
    main()
