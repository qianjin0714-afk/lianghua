#!/usr/bin/env python3
"""
邮件配置设置脚本
运行此脚本配置QQ邮箱授权码
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from email_sender import save_config


def main():
    print("=" * 50)
    print("📧 QQ邮箱配置向导")
    print("=" * 50)
    print()
    print("请按以下步骤操作：")
    print("1. 登录QQ邮箱: https://mail.qq.com")
    print("2. 设置 -> 账户 -> POP3/IMAP/SMTP服务")
    print("3. 开启SMTP服务并生成授权码")
    print()

    sender = input("请输入发件人QQ邮箱地址: ").strip()
    if not sender or '@' not in sender:
        print("❌ 邮箱格式不正确")
        return

    auth_code = input("请输入SMTP授权码（不是QQ密码）: ").strip()
    if not auth_code:
        print("❌ 授权码不能为空")
        return

    save_config(sender, auth_code)
    print()
    print("✅ 配置完成！")
    print("选股报告将自动发送至: 573878544@qq.com")


if __name__ == '__main__':
    main()
