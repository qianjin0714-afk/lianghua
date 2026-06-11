#!/usr/bin/env python3
"""
时区工具模块
所有时间统一使用北京时间 (Asia/Shanghai)
"""
from datetime import datetime, time
import pytz

# 北京时间时区
BJ_TZ = pytz.timezone('Asia/Shanghai')


def now_bj() -> datetime:
    """获取当前北京时间"""
    return datetime.now(BJ_TZ)


def is_trading_day(dt: datetime = None) -> bool:
    """
    判断是否为交易日（周一到周五，排除周末）
    注：不处理法定节假日，那些需要交易日历API
    """
    if dt is None:
        dt = now_bj()
    return 0 <= dt.weekday() <= 4  # 周一=0, 周日=6


def is_market_open(dt: datetime = None) -> bool:
    """
    判断当前是否在交易时段
    上午: 09:30 - 11:30
    下午: 13:00 - 15:00
    """
    if dt is None:
        dt = now_bj()

    if not is_trading_day(dt):
        return False

    t = dt.time()
    morning_start = time(9, 30)
    morning_end = time(11, 30)
    afternoon_start = time(13, 0)
    afternoon_end = time(15, 0)

    return (morning_start <= t <= morning_end) or (afternoon_start <= t <= afternoon_end)


def get_date_str(dt: datetime = None) -> str:
    """获取北京时间日期字符串 YYYYMMDD"""
    if dt is None:
        dt = now_bj()
    return dt.strftime('%Y%m%d')


def get_time_str(dt: datetime = None) -> str:
    """获取北京时间时间字符串 HH:MM"""
    if dt is None:
        dt = now_bj()
    return dt.strftime('%H:%M')


def get_datetime_str(dt: datetime = None) -> str:
    """获取北京时间完整字符串"""
    if dt is None:
        dt = now_bj()
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def get_last_trade_date() -> str:
    """
    获取最近一个交易日（简单的往前推到上一个工作日）
    返回 YYYYMMDD 格式
    """
    dt = now_bj()
    # 如果是周末，往前推到周五
    while dt.weekday() >= 5:
        from datetime import timedelta
        dt -= timedelta(days=1)
    return dt.strftime('%Y%m%d')


def get_morning_cron() -> str:
    """上午9点 cron 表达式（每天工作日 9:00 北京时间）"""
    # 机器在美西，北京时间9点 = 美西时间前一天18点(PDT) 或 17点(PST)
    # 使用 TZ 环境变量来确保 cron 正确触发
    # 这里返回标准 cron，执行脚本时会切换到北京时间判断
    return "0 9 * * 1-5"


def get_afternoon_cron() -> str:
    """下午2点 cron 表达式"""
    return "0 14 * * 1-5"
