#!/usr/bin/env python3
"""
上午9点选股策略（热点题材+趋势股 快速版）
策略：
1. 识别当前热点板块（概念+行业涨跌前10）
2. 从热点板块中筛选涨幅>2%的个股
3. 并行获取K线，计算MACD和均线
4. 综合评分：热点题材(0-3) + 技术形态(0-3) + 趋势潜力(0-3) + 涨停预期(0-1)
"""
import sys
import os
from typing import List, Dict, Any

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from time_utils import now_bj, get_date_str, get_time_str, get_datetime_str, is_trading_day
from stock_monitor.utils import (
    get_stock_kline,
    get_all_stocks_realtime,
    get_board_concept_list,
    get_board_industry_list,
    get_board_stocks,
    filter_by_macd_batch,
    batch_calc_price_levels,
)


def filter_morning_stocks() -> List[Dict[str, Any]]:
    """上午9点选股主逻辑"""
    print("=" * 60)
    print(f"【上午9点选股】开始分析 - {get_datetime_str()}")
    print("=" * 60)

    # 1. 获取热点板块+实时行情(并行)
    print("\n[Step 1] 获取热点板块和实时行情...")
    hot_boards, all_stocks = _get_hot_boards_and_stocks()
    print(f"  热点板块: {len(hot_boards)} 个 | 实时行情: {len(all_stocks) if all_stocks is not None else 0} 只")

    # 2. 筛选候选股
    print("\n[Step 2] 筛选候选股...")
    candidates = _select_candidates(hot_boards, all_stocks)
    if not candidates:
        print("  ❌ 无候选股")
        return []
    print(f"  候选股: {len(candidates)} 只")

    # 3. 批量K线分析（含价格区间）
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
    print(f"  K线分析完成: {len(tech_data)}/{len(codes)} 只成功")
    print(f"  K线分析完成: {len(tech_data)}/{len(codes)} 只成功")

    # 4. 综合评分排序
    print("\n[Step 4] 综合评分...")
    scored = _score(candidates[:60], tech_data, hot_boards)
    scored = sorted(scored, key=lambda x: x['综合评分'], reverse=True)

    top10 = scored[:10]
    print(f"\n【最终推荐 {len(top10)} 只股票】")
    print("-" * 40)
    for i, s in enumerate(top10, 1):
        print(f"  {i}. {s['股票名称']}({s['股票代码']}) 评分:{s['综合评分']:.1f}/10 | {s['评分理由'][:60]}")

    # 在评分理由中加入买卖价位
    for s in top10:
        td = tech_data.get(s['股票代码'], {})
        support = td.get('支撑位', 0)
        resistance = td.get('压力位', 0)
        buy_low = td.get('买入区间下限', 0)
        buy_high = td.get('买入区间上限', 0)
        target = td.get('目标价', 0)
        stop = td.get('止损价', 0)
        if support and resistance:
            s['支撑位'] = support
            s['压力位'] = resistance
            s['买入区间下限'] = buy_low
            s['买入区间上限'] = buy_high
            s['目标价'] = target
            s['止损价'] = stop
            s['评分理由'] += f"|支撑{support} 压力{resistance} 买入{buy_low}-{buy_high}"

    return top10


def _get_hot_boards_and_stocks():
    """同时获取热点板块和实时行情"""
    hot_boards = []

    try:
        concepts = get_board_concept_list()
        if concepts is not None and not concepts.empty:
            top = concepts.nlargest(10, '涨跌幅') if '涨跌幅' in concepts.columns else concepts.head(10)
            for _, r in top.iterrows():
                hot_boards.append({
                    '板块名称': r.get('板块名称', ''),
                    '板块代码': r.get('板块代码', ''),
                    '涨跌幅': float(r.get('涨跌幅', 0)),
                    '类型': '概念',
                })
    except Exception:
        pass

    try:
        industries = get_board_industry_list()
        if industries is not None and not industries.empty:
            top = industries.nlargest(5, '涨跌幅') if '涨跌幅' in industries.columns else industries.head(5)
            for _, r in top.iterrows():
                name = r.get('板块名称', '')
                if name and name not in [b['板块名称'] for b in hot_boards]:
                    hot_boards.append({
                        '板块名称': name,
                        '板块代码': r.get('板块代码', ''),
                        '涨跌幅': float(r.get('涨跌幅', 0)),
                        '类型': '行业',
                    })
    except Exception:
        pass

    # 获取全市场行情
    stocks = get_all_stocks_realtime()
    return hot_boards, stocks


def _select_candidates(boards: List[Dict], all_stocks) -> List[Dict]:
    """筛选候选股"""
    if all_stocks is None or all_stocks.empty:
        return []

    df = all_stocks.copy()
    # 排除ST、北交所、停牌
    df = df[~df['股票名称'].str.contains('ST|退|N', na=False)]
    df = df[~df['股票代码'].str.startswith('8')]
    df = df[df['最新价'] > 0]
    df = df[df['涨跌幅'] >= 2.0]

    candidates = []

    # 方法1: 来自板块
    board_codes = set()
    for board in boards:
        try:
            stocks = get_board_stocks(board['板块名称'], board.get('板块代码', ''))
            if stocks is not None and not stocks.empty:
                for _, r in stocks.iterrows():
                    code = str(r.get('股票代码', ''))
                    if code and code not in board_codes:
                        board_codes.add(code)
                        match = df[df['股票代码'] == code]
                        if not match.empty:
                            row = match.iloc[0].to_dict()
                            row['所属板块'] = board['板块名称']
                            row['板块涨跌幅'] = board['涨跌幅']
                            row['来源'] = '板块'
                            candidates.append(row)
        except Exception:
            pass

    # 方法2: 全市场涨幅前20（作为补充）
    top_strong = df.nlargest(20, '涨跌幅')
    for _, row in top_strong.iterrows():
        code = row['股票代码']
        if code not in board_codes:
            candidates.append({
                **row.to_dict(),
                '所属板块': '',
                '板块涨跌幅': 0,
                '来源': '全市场强势',
            })

    return candidates


def _score(candidates: List[Dict], tech_data: Dict, hot_boards: List[Dict]) -> List[Dict]:
    """综合评分"""
    results = []
    board_names = {b['板块名称'] for b in hot_boards}

    for row in candidates:
        code = row['股票代码']
        score = 0.0
        reasons = []

        # === 热点题材 (0-3) ===
        theme_score = 0.0
        board = str(row.get('所属板块', ''))
        if board and board != 'nan' and board in board_names:
            # 昨日涨停等特殊板块权重降低
            is_special = any(k in board for k in ['昨日涨停', '昨日打板', '昨日连板'])
            base = 0.5 if is_special else 1.0
            theme_score += base
            reasons.append(f"热点:{board}")
            board_pct = float(row.get('板块涨跌幅', 0))
            # 板块真实涨幅按正常涨跌幅算（昨涨停板块涨幅虚高）
            if not is_special and board_pct > 3:
                theme_score += 1.5
                reasons.append("板块领涨")
            elif board_pct > 2:
                theme_score += 1.0
        elif row.get('来源') == '全市场强势':
            theme_score += 1.0
            reasons.append("独立强势")
        theme_score = min(theme_score, 3.0)
        score += theme_score

        # === 技术形态 (0-3) + 趋势 (0-3) + 预期 (0-1) ===
        td = tech_data.get(code)

        tech_score = 0.0
        trend_score = 0.0
        expect_score = 0.0

        chg = float(row.get('涨跌幅', 0))
        vol = float(row.get('量比', 1))

        if td:
            # MACD金叉
            if td['macd_gc']:
                tech_score += 1.5
                reasons.append("MACD金叉")
                trend_score += 1.0
                reasons.append("金叉上攻")

            # 均线多头
            if td['ma_bullish']:
                tech_score += 1.0
                reasons.append("均线多头")
                trend_score += 1.0

            # 突破前高
            br = td['break_ratio']
            if br >= 1.0:
                tech_score += 0.5
                reasons.append("突破前高")
                expect_score += 0.4
            elif br >= 0.97:
                reasons.append("逼近前高")
                expect_score += 0.2

            # 连续上涨
            if td['up_days'] >= 3:
                trend_score += 1.0
                reasons.append(f"连涨{td['up_days']}日")
                expect_score += 0.3

            # 趋势斜率
            if td['slope_pct'] > 1:
                trend_score += 0.5
                reasons.append("趋势陡峭")

            # 放量
            vol_ma_ratio = td['current_vol'] / td['vol_ma5'] if td['vol_ma5'] > 0 else 1
            if vol_ma_ratio > 1.5:
                tech_score += 0.5
                reasons.append("放量突破")
        else:
            # 没有K线数据，仅用实时行情
            if vol > 2:
                tech_score += 0.5
                reasons.append("量比>2")
            if chg > 5:
                tech_score += 0.5
                reasons.append("强势上攻")

        # 涨幅位置评分
        if 3 <= chg <= 7:
            expect_score += 0.3
            reasons.append(f"涨幅{chg:.1f}%有空间")
        if vol > 2:
            expect_score += 0.3
            reasons.append("量能充足")

        tech_score = min(tech_score, 3.0)
        trend_score = min(trend_score, 3.0)
        expect_score = min(expect_score, 1.0)

        score += tech_score + trend_score + expect_score

        td = tech_data.get(code, {})
        results.append({
            '股票代码': code,
            '股票名称': row.get('股票名称', ''),
            '最新价': float(row.get('最新价', 0)),
            '涨跌幅': chg,
            '量比': vol,
            '成交额': float(row.get('成交额', 0)),
            '所属板块': board,
            '综合评分': round(score, 1),
            '评分理由': '; '.join(reasons),
            '选股时段': '09:00',
            '支撑位': td.get('支撑位', 0),
            '压力位': td.get('压力位', 0),
            '买入区间下限': td.get('买入区间下限', 0),
            '买入区间上限': td.get('买入区间上限', 0),
            '目标价': td.get('目标价', 0),
            '止损价': td.get('止损价', 0),
        })

    return results
