#!/usr/bin/env python3
"""
工具模块：股票数据接口
使用 curl + 东方财富/腾讯API
"""
import subprocess
import json
import time
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import pandas as pd
import numpy as np

from time_utils import now_bj

# ============================================================
# 全局请求控制（避免东方财富限流）
# ============================================================
_last_request_time = 0.0
_MIN_INTERVAL = 0.6  # 请求最小间隔(秒)


def _rate_limit():
    """请求频率控制"""
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_request_time = time.time()


CURL = "/usr/bin/curl"
CURL_OPTS = ["-s", "--connect-timeout", "10", "--max-time", "20",
             "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
             "-H", "Referer: https://quote.eastmoney.com/"]


def _curl(url: str) -> Optional[str]:
    """curl 获取数据（带频率控制）"""
    _rate_limit()
    for attempt in range(3):
        try:
            r = subprocess.run([CURL] + CURL_OPTS + [url],
                               capture_output=True, text=True, timeout=25)
            if r.returncode == 0 and r.stdout and len(r.stdout) > 10:
                return r.stdout.strip()
            if attempt < 2:
                time.sleep(2)
        except Exception:
            if attempt < 2:
                time.sleep(2)
                continue
    return None


# ============================================================
# 实时行情（东方财富）
# ============================================================

def get_all_stocks_realtime(max_retries: int = 3) -> Optional[pd.DataFrame]:
    """获取A股全市场实时行情"""
    for attempt in range(max_retries):
        try:
            url = (f"https://push2.eastmoney.com/api/qt/clist/get?"
                   f"pn=1&pz=2000&po=1&np=1&"
                   f"fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&"
                   f"fields=f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18")

            data_str = _curl(url)
            if not data_str:
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                return None

            data = json.loads(data_str)
            if data.get("rc") != 0:
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                return None

            items = data.get("data", {}).get("diff", [])
            if not items:
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                return None

            rows = []
            for item in items:
                f2 = item.get('f2')
                if f2 is None or str(f2) == '-':
                    continue
                rows.append({
                    '股票代码': str(item.get('f12', '')).zfill(6),
                    '股票名称': str(item.get('f14', '')),
                    '最新价': float(f2) if f2 else 0,
                    '涨跌幅': float(item.get('f3', 0) or 0),
                    '涨跌额': float(item.get('f4', 0) or 0),
                    '成交量': float(item.get('f5', 0) or 0),
                    '成交额': float(item.get('f6', 0) or 0),
                    '换手率': float(item.get('f8', item.get('f9', 0) or 0)),
                    '量比': float(item.get('f10', 0) or 0),
                    '最高': float(item.get('f15', 0) or 0),
                    '最低': float(item.get('f16', 0) or 0),
                    '今开': float(item.get('f17', 0) or 0),
                    '昨收': float(item.get('f18', 0) or 0),
                })

            if not rows:
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                return None

            return pd.DataFrame(rows)

        except Exception:
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            return None
    return None


# ============================================================
# 个股K线（腾讯接口）
# ============================================================

def _tx_code(code: str) -> str:
    if code.startswith('6') or code.startswith('9'):
        return f"sh{code}"
    return f"sz{code}"


def get_stock_kline(symbol: str, days: int = 60) -> Optional[pd.DataFrame]:
    """获取个股K线数据（腾讯接口）"""
    for attempt in range(3):
        try:
            tx_code = _tx_code(symbol)
            lmt = min(days + 20, 120)
            url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={tx_code},day,,,{lmt},qfq"

            raw = _curl(url)
            if not raw:
                if attempt < 2:
                    time.sleep(2)
                    continue
                return None

            data = json.loads(raw)
            if data.get("code") != 0:
                if attempt < 2:
                    time.sleep(2)
                    continue
                return None

            kline_data = (data.get("data", {}).get(tx_code, {}).get("qfqday")
                          or data.get("data", {}).get(tx_code, {}).get("day"))
            if not kline_data or len(kline_data) < 20:
                if attempt < 2:
                    time.sleep(2)
                    continue
                return None

            rows = []
            for k in kline_data:
                if len(k) >= 6:
                    rows.append({
                        '日期': k[0],
                        '开盘': float(k[1]),
                        '收盘': float(k[2]),
                        '最高': float(k[3]),
                        '最低': float(k[4]),
                        '成交量': float(k[5]),
                    })

            df = pd.DataFrame(rows)
            if len(df) < 20:
                return None

            # 计算涨跌幅
            closes = df['收盘'].values.astype(float)
            pct = np.zeros(len(closes))
            for i in range(1, len(closes)):
                if closes[i-1] > 0:
                    pct[i] = (closes[i] - closes[i-1]) / closes[i-1] * 100
            df['涨跌幅'] = pct

            # 计算成交额（估算）
            df['成交额'] = df['成交量'] * df['收盘']

            return df

        except Exception:
            if attempt < 2:
                time.sleep(3)
                continue
            return None
    return None


# ============================================================
# MACD
# ============================================================

def get_macd(close_prices: np.ndarray,
             fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, np.ndarray]:
    close_prices = np.array(close_prices, dtype=float)

    def ema(data, period):
        result = np.zeros_like(data)
        m = 2.0 / (period + 1)
        result[0] = data[0]
        for i in range(1, len(data)):
            result[i] = (data[i] - result[i-1]) * m + result[i-1]
        return result

    ema_f = ema(close_prices, fast)
    ema_s = ema(close_prices, slow)
    dif = ema_f - ema_s
    dea = ema(dif, signal)
    macd = 2 * (dif - dea)
    return {'DIF': dif, 'DEA': dea, 'MACD': macd}


# ============================================================
# 资金流向（东方财富）
# ============================================================

def get_fund_flow_rank(indicator: str = "今日") -> Optional[pd.DataFrame]:
    for attempt in range(3):
        try:
            url = (f"https://push2.eastmoney.com/api/qt/clist/get?"
                   f"pn=1&pz=1000&po=1&np=1&fltt=2&invt=2&fid=f62&"
                   f"fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&"
                   f"fields=f12,f14,f2,f3,f62")

            data_str = _curl(url)
            if not data_str:
                if attempt < 2:
                    time.sleep(5)
                    continue
                return None

            data = json.loads(data_str)
            if data.get("rc") != 0:
                if attempt < 2:
                    time.sleep(5)
                    continue
                return None

            items = data.get("data", {}).get("diff", [])
            if not items:
                if attempt < 2:
                    time.sleep(5)
                    continue
                return None

            rows = []
            for item in items:
                f2 = item.get('f2')
                if f2 is None or str(f2) == '-':
                    continue
                rows.append({
                    '股票代码': str(item.get('f12', '')).zfill(6),
                    '股票名称': str(item.get('f14', '')),
                    '最新价': float(f2) if f2 else 0,
                    '涨跌幅': float(item.get('f3', 0) or 0),
                    '主力净流入': float(item.get('f62', 0) or 0),
                })

            return pd.DataFrame(rows)

        except Exception:
            if attempt < 2:
                time.sleep(5)
                continue
            return None
    return None


# ============================================================
# 板块数据（东方财富）
# ============================================================

def get_board_concept_list() -> Optional[pd.DataFrame]:
    for attempt in range(3):
        try:
            url = (f"https://push2.eastmoney.com/api/qt/clist/get?"
                   f"pn=1&pz=500&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:90+t:3&"
                   f"fields=f2,f3,f12,f14")
            data_str = _curl(url)
            if not data_str:
                if attempt < 2:
                    time.sleep(5)
                    continue
                return None
            data = json.loads(data_str)
            if data.get("rc") != 0:
                if attempt < 2:
                    time.sleep(5)
                    continue
                return None
            items = data.get("data", {}).get("diff", [])
            if not items:
                if attempt < 2:
                    time.sleep(5)
                    continue
                return None
            rows = []
            for item in items:
                f2 = item.get('f2')
                if f2 is None or str(f2) == '-':
                    continue
                rows.append({
                    '板块名称': str(item.get('f14', '')),
                    '板块代码': str(item.get('f12', '')),
                    '涨跌幅': float(f2) if f2 else 0,
                })
            return pd.DataFrame(rows)
        except Exception:
            if attempt < 2:
                time.sleep(5)
                continue
            return None
    return None


def get_board_industry_list() -> Optional[pd.DataFrame]:
    for attempt in range(3):
        try:
            url = (f"https://push2.eastmoney.com/api/qt/clist/get?"
                   f"pn=1&pz=500&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:90+t:2&"
                   f"fields=f2,f3,f12,f14")
            data_str = _curl(url)
            if not data_str:
                if attempt < 2:
                    time.sleep(5)
                    continue
                return None
            data = json.loads(data_str)
            if data.get("rc") != 0:
                if attempt < 2:
                    time.sleep(5)
                    continue
                return None
            items = data.get("data", {}).get("diff", [])
            if not items:
                if attempt < 2:
                    time.sleep(5)
                    continue
                return None
            rows = []
            for item in items:
                f2 = item.get('f2')
                if f2 is None or str(f2) == '-':
                    continue
                rows.append({
                    '板块名称': str(item.get('f14', '')),
                    '板块代码': str(item.get('f12', '')),
                    '涨跌幅': float(f2) if f2 else 0,
                })
            return pd.DataFrame(rows)
        except Exception:
            if attempt < 2:
                time.sleep(5)
                continue
            return None
    return None


def get_board_stocks(board_name: str, board_code: str = "") -> Optional[pd.DataFrame]:
    for attempt in range(2):
        try:
            if not board_code:
                for src_func in [get_board_concept_list, get_board_industry_list]:
                    src = src_func()
                    if src is not None and not src.empty:
                        m = src[src['板块名称'] == board_name]
                        if not m.empty:
                            board_code = m.iloc[0]['板块代码']
                            break
            if board_code:
                url = (f"https://push2.eastmoney.com/api/qt/clist/get?"
                       f"pn=1&pz=500&po=1&np=1&fltt=2&invt=2&fid=f3&fs=b:{board_code}+f:!50&"
                       f"fields=f12,f14")
                data_str = _curl(url)
                if data_str:
                    data = json.loads(data_str)
                    if data.get("rc") == 0:
                        items = data.get("data", {}).get("diff", [])
                        if items:
                            return pd.DataFrame([{
                                '股票代码': str(i.get('f12', '')).zfill(6),
                                '股票名称': str(i.get('f14', '')),
                            } for i in items])
            if attempt < 1:
                time.sleep(3)
        except Exception:
            if attempt < 1:
                time.sleep(3)
    return None


# ============================================================
# 涨停板
# ============================================================

def get_limit_up_pool(trade_date: str = None) -> Optional[pd.DataFrame]:
    if trade_date is None:
        trade_date = now_bj().strftime('%Y%m%d')
    for attempt in range(2):
        try:
            url = (f"https://push2ex.eastmoney.com/getTopicZTPool?"
                   f"ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt&"
                   f"Pageindex=0&pagesize=5000&sort=fbt%3Aasc&date={trade_date}")
            data_str = _curl(url)
            if data_str:
                data = json.loads(data_str)
                pool = data.get("data", {}).get("pool", []) if isinstance(data, dict) else []
                if pool:
                    return pd.DataFrame([{
                        '股票代码': str(i.get('sc', '')).zfill(6),
                        '股票名称': i.get('n', ''),
                    } for i in pool])
            if attempt < 1:
                time.sleep(3)
        except Exception:
            if attempt < 1:
                time.sleep(3)
    return None


# ============================================================
# 批量K线获取（并行）
# ============================================================

def get_stock_klines_batch(codes: List[str], days: int = 30,
                           max_workers: int = 10) -> Dict[str, Optional[pd.DataFrame]]:
    """
    批量获取多只股票的K线数据（并行请求）
    返回 {code: DataFrame} 字典
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        fut_map = {executor.submit(get_stock_kline, code, days): code for code in codes}
        for fut in as_completed(fut_map):
            code = fut_map[fut]
            try:
                df = fut.result(timeout=25)
                if df is not None:
                    results[code] = df
            except Exception:
                pass
    return results


def filter_by_macd_batch(
    stock_rows: List[Dict],
    codes: List[str],
    days: int = 30,
    max_workers: int = 10
) -> Dict[str, Dict]:
    """
    批量计算MACD和均线指标
    返回 {code: {macd_golden_cross, ma_bullish, ...}} 字典
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import numpy as np

    def _calc_single(code: str) -> tuple:
        """计算单只股票的指标"""
        try:
            kline = get_stock_kline(code, days=days)
            if kline is None or len(kline) < 20:
                return (code, None)

            close = kline['收盘'].values.astype(float)
            macd = get_macd(close)

            # MACD金叉
            gc = (macd['DIF'][-1] > macd['DEA'][-1] and
                  macd['DIF'][-1] > macd['DIF'][-3])

            # 均线多头
            ma5 = np.mean(close[-5:])
            ma10 = np.mean(close[-10:])
            ma20 = np.mean(close[-20:])
            bullish = ma5 > ma10 > ma20

            # 特征数据
            highs = kline['最高'].values.astype(float)
            high_5d = max(highs[-5:])
            high_20d = max(highs[-20:])
            break_ratio = high_5d / high_20d if high_20d > 0 else 1.0

            # 涨幅
            pct = kline['涨跌幅'].values.astype(float)
            up_days = 0
            for i in range(-1, -6, -1):
                if len(pct) >= abs(i) and pct[i] > 0:
                    up_days += 1
                else:
                    break

            # 趋势斜率
            x = np.arange(len(close[-10:]))
            y = close[-10:]
            slope = 0
            if np.std(x) > 0:
                slope = np.polyfit(x, y, 1)[0]
                avg = np.mean(y)
                slope = (slope / avg * 100) if avg > 0 else 0

            return (code, {
                'macd_gc': gc,
                'dif': macd['DIF'][-1],
                'dea': macd['DEA'][-1],
                'macd_hist': macd['MACD'][-1],
                'ma_bullish': bullish,
                'ma5': ma5,
                'ma10': ma10,
                'ma20': ma20,
                'break_ratio': break_ratio,
                'up_days': up_days,
                'slope_pct': slope,
                'vol_ma5': np.mean(kline['成交量'].values.astype(float)[-6:-1]),
                'current_vol': kline['成交量'].values.astype(float)[-1],
            })

        except Exception:
            return (code, None)

    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        fut_map = {executor.submit(_calc_single, code): code for code in codes}
        for fut in as_completed(fut_map):
            code = fut_map[fut]
            try:
                code, data = fut.result(timeout=25)
                if data:
                    results[code] = data
            except Exception:
                pass

    return results


# ============================================================
# 压力位 / 支撑位 / 买卖建议
# ============================================================

def calc_price_levels(close_prices: np.ndarray,
                      highs: np.ndarray,
                      lows: np.ndarray,
                      volumes: np.ndarray) -> Dict[str, float]:
    """
    计算压力位、支撑位和买卖建议价位
    返回: {支撑位, 压力位, 买入区间下限, 买入区间上限, 目标价}
    """
    if len(close_prices) < 20:
        return {}

    close = np.array(close_prices, dtype=float)
    high = np.array(highs, dtype=float)
    low = np.array(lows, dtype=float)
    vol = np.array(volumes, dtype=float)

    # 当前价
    current = close[-1]

    # === 支撑位 ===
    # 方法1: 近10日最低点
    support_1 = np.min(low[-10:])

    # 方法2: 20日均线
    ma20 = np.mean(close[-20:])

    # 方法3: 近5日放量阳线的低点（筹码密集区）
    volume_avg = np.mean(vol[-20:])
    dense_lows = []
    for i in range(-10, 0):
        if vol[i] > volume_avg * 1.2 and close[i] > close[i - 1]:
            dense_lows.append(low[i])
    support_3 = np.median(dense_lows) if dense_lows else support_1

    # 综合支撑位（取三个中最高的，最接近当前价）
    supports = [support_1, ma20, support_3]
    support = max(s for s in supports if s < current and s > 0) if any(s < current and s > 0 for s in supports) else support_1

    # === 压力位 ===
    # 方法1: 近20日最高点
    resist_1 = np.max(high[-20:])

    # 方法2: 前高（近60日最高）
    resist_2 = np.max(high) if len(close) >= 60 else resist_1

    # 压力位
    resistance = max(resist_1, resist_2) if resist_2 > current else resist_1

    # === 买卖建议 ===
    buy_lower = round(support * 1.005, 2)  # 支撑位上浮0.5%
    buy_upper = round(current * 1.005, 2)  # 当前价附近
    target = round(resistance * 0.995, 2)  # 压力位下方

    # 止损位：跌破支撑位3%
    stop_loss = round(support * 0.97, 2)

    return {
        '当前价': current,
        '支撑位': round(support, 2),
        '压力位': round(resistance, 2),
        '买入区间下限': buy_lower,
        '买入区间上限': buy_upper,
        '目标价': target,
        '止损价': stop_loss,
    }


def batch_calc_price_levels(
    kline_data: Dict[str, pd.DataFrame]
) -> Dict[str, Dict[str, float]]:
    """批量计算多只股票的压力位/支撑位"""
    results = {}
    for code, df in kline_data.items():
        if df is None or len(df) < 20:
            continue
        try:
            levels = calc_price_levels(
                df['收盘'].values.astype(float),
                df['最高'].values.astype(float),
                df['最低'].values.astype(float),
                df['成交量'].values.astype(float),
            )
            if levels:
                results[code] = levels
        except Exception:
            pass
    return results
