#!/bin/bash
# 选股自动化入口脚本
# 被 Codex 自动化定时调用
#
# 用法:
#   bash stock_monitor.sh morning    # 上午9点选股（北京时间）
#   bash stock_monitor.sh afternoon  # 下午2点选股（北京时间）
#

BASEDIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="/Users/xx/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
SCRIPT_DIR="$BASEDIR/stock_monitor"
OUTPUT_DIR="$BASEDIR/../outputs/stock_monitor"
mkdir -p "$OUTPUT_DIR"

# 打印北京时间
BJ_TIME=$(TZ='Asia/Shanghai' date '+%Y-%m-%d %H:%M:%S')
LOG="$OUTPUT_DIR/$(TZ='Asia/Shanghai' date '+%Y%m%d')_$1.log"

echo "=========================================="
echo "选股自动化 - $1"
echo "北京时间: $BJ_TIME"
echo "=========================================="

echo "===== 选股自动化 $1 $(TZ='Asia/Shanghai' date) =====" >> "$LOG"

# 运行选股
$PYTHON "$SCRIPT_DIR/run_daily.py" "$1" >> "$LOG" 2>&1

echo "===== 完成 $(TZ='Asia/Shanghai' date) =====" >> "$LOG"
echo "日志: $LOG"
