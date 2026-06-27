#!/bin/bash
# News Search 微博热搜获取脚本（带降级链）
# 用法: bash fetch_weibo.sh [--json]
#   输出微博热搜数据到 stdout（JSON 格式）
#   按优先级尝试多个数据源，任一成功即停止
#
# 降级链:
#   1. 主: 60s.viki.moe/v2/weibo (当前主力)
#   2. 备A: tenapi.cn/v2/weibohot
#   3. 备B: 返回特殊标记 "FALLBACK_WEIBO_WEBSEARCH" (调用方应改用 WebSearch)
#   4. 备C: 返回特殊标记 "FALLBACK_BILIBILI_ONLY" (降级为仅 bilibili 热搜)

set -euo pipefail

TIMEOUT=10
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
OUTPUT_FORMAT="${1:---json}"

# ── 辅助函数 ──────────────────────────────────────────────────────

log() {
    echo "[fetch_weibo] $*" >&2
}

try_api() {
    local name="$1"
    local url="$2"
    log "尝试 $name: $url"

    local http_code
    http_code=$(curl -s --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" \
        -H "User-Agent: $UA" \
        -w "%{http_code}" -o /tmp/news_search_weibo_resp.json \
        "$url" 2>/dev/null || echo "000")

    if [ "$http_code" = "200" ]; then
        local size
        size=$(wc -c < /tmp/news_search_weibo_resp.json 2>/dev/null || echo 0)
        if [ "$size" -gt 100 ]; then
            log "✓ $name 成功 ($size bytes)"
            cat /tmp/news_search_weibo_resp.json
            rm -f /tmp/news_search_weibo_resp.json
            return 0
        fi
    fi

    log "✗ $name 失败 (HTTP $http_code)"
    rm -f /tmp/news_search_weibo_resp.json
    return 1
}

# ── 主流程 ────────────────────────────────────────────────────────

# 步骤 1: 尝试主数据源
if try_api "60s.viki.moe" "https://60s.viki.moe/v2/weibo"; then
    exit 0
fi

# 步骤 2: 尝试备用 API
if try_api "tenapi.cn" "https://tenapi.cn/v2/weibohot"; then
    exit 0
fi

# 步骤 3: 降级到 WebSearch 模式
# 无法在此脚本内执行 WebSearch，返回特殊 JSON 标记
# 调用方检测到此标记后应使用 WebSearch 工具搜索 "site:weibo.com 热搜榜"
log "所有 API 均失败，返回 FALLBACK_WEIBO_WEBSEARCH 标记"
cat <<'FALLBACK_JSON'
{"fallback": "websearch", "message": "微博 API 不可用，请使用 WebSearch 工具搜索 'site:weibo.com 热搜榜' 获取热搜数据", "cross_platform_max": 30}
FALLBACK_JSON
exit 0
