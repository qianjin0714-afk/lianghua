#!/usr/bin/env python3
"""邮件发送模块 - 支持环境变量配置"""
import os, smtplib, json
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from typing import List, Dict, Any

from time_utils import now_bj

SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 465
TO_EMAIL = "573878544@qq.com"

def load_config():
    # GitHub Actions: 从环境变量读取
    sender = os.environ.get('MAIL_SENDER')
    code = os.environ.get('MAIL_AUTH_CODE')
    to_addr = os.environ.get('MAIL_TO', TO_EMAIL)
    if sender and code:
        return sender, code, to_addr
    # 本地: 从配置文件读取
    config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mail_config.json")
    if os.path.exists(config_file):
        with open(config_file) as f:
            cfg = json.load(f)
        return cfg.get('sender_email',''), cfg.get('auth_code',''), cfg.get('to_email', TO_EMAIL)
    return '', '', TO_EMAIL

def send_stock_report(stocks, session_label):
    sender_email, auth_code, to_email = load_config()
    if not sender_email or not auth_code:
        print("邮件配置未设置")
        return False

    date_str = now_bj().strftime('%Y-%m-%d')
    time_str = now_bj().strftime('%H:%M')
    subject = f"股票策略 {date_str} {session_label} 推荐{len(stocks)}只"

    # 构建邮件内容
    text = []
    text.append(f"选股报告 - {date_str} {session_label}")
    text.append(f"生成时间: {date_str} {time_str}")
    text.append(f"推荐数量: {len(stocks)} 只\n")
    for i, s in enumerate(stocks, 1):
        name = s.get('股票名称','N/A')
        code = s.get('股票代码','N/A')
        price = s.get('最新价',0)
        chg = s.get('涨跌幅',0)
        vol = s.get('量比',0)
        score = s.get('综合评分',0)
        reasons = s.get('评分理由','')
        support = s.get('支撑位',0)
        resistance = s.get('压力位',0)
        text.append(f"{i}. {name}({code}) 评分:{score}/10")
        text.append(f"   涨跌幅:{chg}% 量比:{vol}")
        if support:
            text.append(f"   支撑:{support} 压力:{resistance}")
        board = s.get('所属板块','')
        if board and board != 'nan':
            text.append(f"   板块:{board}")
        text.append(f"   理由:{reasons}\n")
    text.append("⚠️ 仅供参考，不构成投资建议")
    body = "\n".join(text)

    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = Header(subject, 'utf-8')
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(sender_email, auth_code)
            server.send_message(msg)
        print(f"邮件已发送至 {to_email}")
        return True
    except Exception as e:
        print(f"邮件发送失败: {e}")
        return False
