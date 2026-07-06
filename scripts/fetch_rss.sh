#!/bin/bash
# News Search RSS 源解析脚本
# 用法: bash fetch_rss.sh <RSS_URL> [max_items]
#
# 从 RSS/Atom feed 获取最新条目，解析为 JSON 输出到 stdout。
# 零外部依赖（仅 curl + sed + grep），兼容 RSS 2.0 和 Atom 格式。
#
# v2 修复:
#   - 移除 set -e（pipefail + grep -oP 在空 feed 时不触发退出）
#   - 修复 subshell count 变量 bug（pipe while read 导致 JSON 缺逗号）
#   - 改用临时文件 + while read < file 避免 subshell

set -uo pipefail

# ── 参数 ──────────────────────────────────────────────────────────
if [ $# -lt 1 ]; then
    echo "用法: bash fetch_rss.sh <RSS_URL> [max_items]" >&2
    echo "示例: bash fetch_rss.sh https://rss.huanqiu.com/world/china.xml 5" >&2
    exit 1
fi

RSS_URL="$1"
MAX_ITEMS="${2:-5}"
TIMEOUT=10
TMPFILE=$(mktemp /tmp/news_search_rss_XXXXXX)
ENTRIES_FILE=$(mktemp /tmp/news_search_rss_entries_XXXXXX)
trap 'rm -f "$TMPFILE" "$ENTRIES_FILE"' EXIT

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

# ── 下载 feed ─────────────────────────────────────────────────────
log() { echo "[fetch_rss] $*" >&2; }

log "获取: $RSS_URL"

HTTP_CODE=$(curl -sL --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" \
    -H "User-Agent: $UA" \
    -w "%{http_code}" -o "$TMPFILE" \
    "$RSS_URL" 2>/dev/null || echo "000")

if [ "$HTTP_CODE" != "200" ]; then
    log "失败: HTTP $HTTP_CODE"
    echo "[]"
    exit 0
fi

# ── 解析 XML → JSON ──────────────────────────────────────────────
FEED_CONTENT=$(cat "$TMPFILE")

# 判断格式
IS_ATOM=false
if echo "$FEED_CONTENT" | grep -q "<entry>"; then
    IS_ATOM=true
fi

# ── 安全 grep 包装（避免 pipefail 导致空结果触发 exit） ──────────
safe_grep() {
    grep -oP "$@" 2>/dev/null || true
}

# ── 提取条目到临时文件（避免 pipe while read 的 subshell bug） ───
if $IS_ATOM; then
    echo "$FEED_CONTENT" | tr '\n' ' ' | safe_grep '<entry>.*?</entry>' | head -n "$MAX_ITEMS" > "$ENTRIES_FILE"
else
    echo "$FEED_CONTENT" | tr '\n' ' ' | safe_grep '<item>.*?</item>' | head -n "$MAX_ITEMS" > "$ENTRIES_FILE"
fi

# ── 输出 JSON 数组 ───────────────────────────────────────────────
echo "["
count=0
first=true

while IFS= read -r entry; do
    [ -z "$entry" ] && continue

    if $first; then
        first=false
    else
        echo ","
    fi

    if $IS_ATOM; then
        # Atom 格式解析
        title=$(echo "$entry" | grep -oP '<title[^>]*>\K[^<]+' | head -1 | sed 's/"/\\"/g')
        link=$(echo "$entry" | grep -oP '<link[^>]*href="\K[^"]+' | head -1 | sed 's/"/\\"/g')
        [ -z "$link" ] && link=$(echo "$entry" | grep -oP '<link[^>]*>\K[^<]+' | head -1 | sed 's/"/\\"/g')
        summary=$(echo "$entry" | grep -oP '<summary[^>]*>\K[^<]+' | head -1 | sed 's/"/\\"/g; s/&lt;/</g; s/&gt;/>/g; s/&amp;/\\&/g')
        [ -z "$summary" ] && summary=$(echo "$entry" | grep -oP '<content[^>]*>\K[^<]+' | head -1 | sed 's/"/\\"/g')
        pubdate=$(echo "$entry" | grep -oP '<published[^>]*>\K[^<]+' | head -1 | sed 's/"/\\"/g')
        [ -z "$pubdate" ] && pubdate=$(echo "$entry" | grep -oP '<updated[^>]*>\K[^<]+' | head -1 | sed 's/"/\\"/g')

        # 截断过长摘要
        if [ "${#summary}" -gt 200 ]; then
            summary="${summary:0:200}..."
        fi

        printf '  {"title": "%s", "url": "%s", "source_type": "traditional", "source_name": "rss", "summary": "%s", "pubdate": "%s", "image_url": null}' \
            "$title" "$link" "$summary" "$pubdate"
    else
        # RSS 2.0 格式解析
        title=$(echo "$entry" | grep -oP '<title>\K[^<]+' | head -1 | sed 's/"/\\"/g; s/<!\[CDATA\[//g; s/\]\]>//g')
        link=$(echo "$entry" | grep -oP '<link>\K[^<]+' | head -1 | sed 's/"/\\"/g')
        desc=$(echo "$entry" | grep -oP '<description>\K[^<]+' | head -1 | sed 's/"/\\"/g; s/<!\[CDATA\[//g; s/\]\]>//g; s/&lt;/</g; s/&gt;/>/g; s/&amp;/\\&/g')
        pubdate=$(echo "$entry" | grep -oP '<pubDate>\K[^<]+' | head -1 | sed 's/"/\\"/g')

        # 从 description 中提取 og:image（如果有）
        img=$(echo "$desc" | grep -oP '<img[^>]+src="\K[^"]+' | head -1 | sed 's/"/\\"/g' || echo "")
        img_field="null"
        [ -n "$img" ] && img_field="\"$img\""

        # 去 HTML 标签，截断
        clean_desc=$(echo "$desc" | sed 's/<[^>]*>//g')
        if [ "${#clean_desc}" -gt 200 ]; then
            clean_desc="${clean_desc:0:200}..."
        fi

        printf '  {"title": "%s", "url": "%s", "source_type": "traditional", "source_name": "rss", "summary": "%s", "pubdate": "%s", "image_url": %s}' \
            "$title" "$link" "$clean_desc" "$pubdate" "$img_field"
    fi

    count=$((count + 1))
done < "$ENTRIES_FILE"

echo ""
echo "]"

log "完成: 已获取 $count 条"
exit 0
