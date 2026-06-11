#!/usr/bin/env python3
"""
下午2点选股策略（强势股筛选 快速版）
策略：
1. 量比>1.3, 涨幅2.5%-9.5%, 成交额>5000万
2. 并行获取K线，计算MACD金叉、突破前高
3. 主力净流入为正值
4. 综合评分
"""
import sys
import os
from typing import List, Dict, Any

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from time_utils import now_bj, get_date_str, get_time_str, get_datetime_str
from stock_monitor.utils import (
    get_all_stocks_realtime,
    get_stock_kline,
    get_fund_flow_rank,
    filter_by_macd_batch,
    batch_calc_price_levels,
)


def filter_afternoon_stocks() -> List[Dict[str, Any]]:
    """下午2点选股主逻辑"""
    print("=" * 60)
    print(f"【下午2点选股】开始分析 - {get_datetime_str()}")
    print("=" * 60)

    # 1. 获取实时行情
    print("\n[Step 1] 获取实时行情...")
    stocks = get_all_stocks_realtime()
    if stocks is None or stocks.empty:
        print("  ❌ 无数据")
        return []
    print(f"  {len(stocks)} 只股票")

    # 2. 初步筛选
    print("\n[Step 2] 初步筛选...")
    candidates = _prefilter(stocks)
    if not candidates:
        return []
    print(f"  {len(candidates)} 只候选")

    # 3. 并行K线分析（含价格区间）
    print("\n[Step 3] 并行K线分析（含价格区间）...")
    codes = [c["股票代码"] for c in candidates[:60]]
    tech_data = filter_by_macd_batch(candidates[:60], codes, days=60, max_workers=10)
    # 计算买卖价位
    kline_dict = {}
    for code in codes:
        if code in tech_data:
            k = get_stock_kline(code, days=60)
            if k is not None:
                kline_dict[code] = k
    if kline_dict:
        price_levels = batch_calc_price_levels(kline_dict)
        for code, lv in price_levels.items():
            if code in tech_data:
                tech_data[code].update(lv)

    # 4. 资金流筛选
    print("\n[Step 4] 资金流分析...")
    fund_map = _get_fund_flow_map()

    # 5. 评分
    print("\n[Step 5] 综合评分...")
    scored = _score(candidates[:60], tech_data, fund_map)
    scored = sorted(scored, key=lambda x: x['综合评分'], reverse=True)

    top10 = scored[:10]
    print(f"\n【最终推荐 {len(top10)} 只股票】")
    print("-" * 40)
    for i, s in enumerate(top10, 1):
        print(f"  {i}. {s['股票名称']}({s['股票代码']}) 评分:{s['综合评分']:.1f}/10 | {s['评分理由'][:60]}")

    return top10


def _prefilter(df: pd.DataFrame) -> List[Dict]:
    """初步筛选"""
    if df is None or df.empty:
        return []

    df = df.copy()
    df = df[~df['股票名称'].str.contains('ST|退|N', na=False)]
    df = df[~df['股票代码'].str.startswith('8')]
    df = df[df['最新价'] > 0]

    if '涨跌幅' in df.columns:
        df = df[(df['涨跌幅'] >= 2.5) & (df['涨跌幅'] <= 9.5)]
    if '量比' in df.columns:
        df = df[df['量比'] > 1.3]
    if '成交额' in df.columns:
        df = df[df['成交额'] > 5e7]
    if '最新价' in df.columns:
        df = df[(df['最新价'] >= 3) & (df['最新价'] <= 200)]

    # 按涨幅排序取前60只
    if '涨跌幅' in df.columns and len(df) > 60:
        df = df.nlargest(60, '涨跌幅')

    return df.to_dict('records')


def _get_fund_flow_map() -> Dict[str, float]:
    """获取主力净流入映射"""
    try:
        flow = get_fund_flow_rank('今日')
        if flow is not None and not flow.empty:
            return dict(zip(flow['股票代码'], flow['主力净流入']))
    except Exception:
        pass
    return {}


def _score(candidates: List[Dict], tech_data: Dict, fund_map: Dict[str, float]) -> List[Dict]:
    """综合评分(0-10)"""
    results = []

    for row in candidates:
        code = row['股票代码']
        score = 0.0
        reasons = []

        chg = float(row.get('涨跌幅', 0))
        vol = float(row.get('量比', 1))
        price = float(row.get('最新价', 0))
        td = tech_data.get(code)
        fund = fund_map.get(code, 0)

        # === 技术面 (0-3) ===
        tech_score = 0.0
        if td:
            if td['macd_gc']:
                tech_score += 1.0
                reasons.append("MACD金叉")
            if td['ma_bullish']:
                tech_score += 0.8
                reasons.append("均线多头")
            br = td['break_ratio']
            if br >= 1.0:
                tech_score += 0.5
                reasons.append("突破前高")
            elif br >= 0.97:
                tech_score += 0.3
                reasons.append("逼近前高")
        else:
            tech_score += 0.5
        tech_score = min(tech_score, 3.0)
        score += tech_score

        # === 资金面 (0-3) ===
        fund_score = 0.0
        if fund > 1e7:
            fund_score += 3.0
            reasons.append("主力大幅流入")
        elif fund > 5e6:
            fund_score += 2.0
            reasons.append("主力明显流入")
        elif fund > 1e6:
            fund_score += 1.0
            reasons.append("主力温和流入")
        elif fund > 0:
            fund_score += 0.5
            reasons.append("主力微幅流入")
        if vol > 3:
            fund_score += 0.5
            reasons.append("量比>3")
        elif vol > 2:
            fund_score += 0.3
        fund_score = min(fund_score, 3.0)
        score += fund_score

        # === 形态面 (0-3) ===
        form_score = 0.0
        if td and td['current_vol'] > td['vol_ma5'] * 1.5:
            form_score += 1.0
            reasons.append("放量突破")
        if 4 <= chg <= 6:
            form_score += 1.0
            reasons.append("中阳稳健")
        elif 6 < chg <= 8:
            form_score += 0.8
            reasons.append("大阳强势")
        elif 8 < chg <= 9.5:
            form_score += 0.3
        form_score = min(form_score, 3.0)
        score += form_score

        # === 预期面 (0-1) ===
        expect_score = 0.0
        if vol > 2:
            expect_score += 0.3
        if td and td['break_ratio'] >= 1.0:
            expect_score += 0.3
        if 3 <= chg <= 7:
            expect_score += 0.2
        if td and td['up_days'] >= 3:
            expect_score += 0.2
        expect_score = min(expect_score, 1.0)
        score += expect_score

        td = tech_data.get(code, {})
        support = td.get('支撑位', 0)
        resistance = td.get('压力位', 0)
        buy_low = td.get('买入区间下限', 0)
        buy_high = td.get('买入区间上限', 0)
        target = td.get('目标价', 0)
        stop = td.get('止损价', 0)
        if support and resistance:
            reasons.append(f"支撑{support}压力{resistance}买入{buy_low}-{buy_high}")
        results.append({
            '股票代码': code,
            '股票名称': row.get('股票名称', ''),
            '最新价': price,
            '涨跌幅': chg,
            '量比': vol,
            '成交额': float(row.get('成交额', 0)),
            '主力净流入': fund,
            '综合评分': round(score, 1),
            '评分理由': '; '.join(reasons),
            '选股时段': '14:00',
            '支撑位': support,
            '压力位': resistance,
            '买入区间下限': buy_low,
            '买入区间上限': buy_high,
            '目标价': target,
            '止损价': stop,
        })

    return results
