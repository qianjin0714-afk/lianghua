#!/usr/bin/env python3
"""
主调度脚本
被Codex自动化定时调用
"""
import sys
import os
import json
from datetime import datetime
from time_utils import now_bj, get_date_str, get_datetime_str

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stock_selector_morning import filter_morning_stocks
from stock_selector_afternoon import filter_afternoon_stocks
from email_sender import send_stock_report


def run_morning():
    """运行上午9点选股"""
    print(f"\n{'=' * 60}")
    print(f"【上午9点选股流程】{now_bj().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}\n")

    stocks = filter_morning_stocks()
    if stocks:
        # 保存结果到文件
        _save_results(stocks, "morning")
        # 发送邮件
        print(f"\n{'=' * 60}")
        print("【发送邮件】")
        send_stock_report(stocks, "上午9点-热点题材选股")
    else:
        print("\n⚠️ 未选出符合条件的股票")

    return stocks


def run_afternoon():
    """运行下午2点选股"""
    print(f"\n{'=' * 60}")
    print(f"【下午2点选股流程】{now_bj().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}\n")

    stocks = filter_afternoon_stocks()
    if stocks:
        _save_results(stocks, "afternoon")
        print(f"\n{'=' * 60}")
        print("【发送邮件】")
        send_stock_report(stocks, "下午2点-强势股选股")
    else:
        print("\n⚠️ 未选出符合条件的股票")

    return stocks


def _save_results(stocks: list, session: str):
    """保存选股结果到文件"""
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "..", "outputs", "stock_monitor"
    )
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    date_str = now_bj().strftime('%Y%m%d')
    filename = f"{date_str}_{session}.json"
    filepath = os.path.join(output_dir, filename)

    # 序列化
    serializable = []
    for s in stocks:
        entry = {}
        for k, v in s.items():
            if isinstance(v, (str, int, float, bool)):
                entry[k] = v
            elif isinstance(v, (list, dict)):
                entry[k] = str(v)
            else:
                try:
                    entry[k] = float(v) if v is not None else 0
                except (ValueError, TypeError):
                    entry[k] = str(v)
        serializable.append(entry)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    print(f"  结果已保存至: {filepath}")

    # 同时保存文本格式方便查看
    txt_file = os.path.join(output_dir, f"{date_str}_{session}.txt")
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write(f"选股报告 - {date_str} {session}\n")
        f.write("=" * 50 + "\n\n")
        for i, s in enumerate(stocks, 1):
            f.write(f"{i}. {s.get('股票名称','')}({s.get('股票代码','')})  "
                    f"评分:{s.get('综合评分','')}/10\n")
            f.write(f"   涨幅:{s.get('涨跌幅','')}%  量比:{s.get('量比','')}\n")
            f.write(f"   理由:{s.get('评分理由','')}\n\n")
    print(f"  文本结果已保存至: {txt_file}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='选股调度器')
    parser.add_argument('session', choices=['morning', 'afternoon', 'both'],
                        help='选股时段: morning(上午9点), afternoon(下午2点), both(都运行)')
    args = parser.parse_args()

    if args.session in ('morning', 'both'):
        run_morning()
    if args.session in ('afternoon', 'both'):
        run_afternoon()

    print(f"\n{'=' * 60}")
    print(f"【流程完成】{now_bj().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")
