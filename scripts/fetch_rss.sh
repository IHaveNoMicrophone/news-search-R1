#!/bin/bash
# News Search RSS 源解析脚本
# 用法: bash fetch_rss.sh <RSS_URL> [max_items]
#
# 从 RSS/Atom feed 获取最新条目，解析为 JSON 输出到 stdout。
# 零外部依赖（仅 curl + sed + grep），兼容 RSS 2.0 和 Atom 格式。

set -euo pipefail

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
trap 'rm -f "$TMPFILE"' EXIT

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
# 不依赖 xmllint/xmlstarlet/jq，用纯 shell 解析
#
# 策略：提取所有 <item> 块（RSS）或 <entry> 块（Atom），
# 从每个块中提取 title, link, description, pubDate/published

FEED_CONTENT=$(cat "$TMPFILE")

# 判断格式
IS_ATOM=false
if echo "$FEED_CONTENT" | grep -q "<entry>"; then
    IS_ATOM=true
fi

# ── 提取条目 ──────────────────────────────────────────────────────
output_json() {
    local count=0
    echo "["

    if $IS_ATOM; then
        # Atom 格式解析
        # 将 feed 按 <entry> 分割
        echo "$FEED_CONTENT" | tr '\n' ' ' | grep -oP '<entry>.*?</entry>' | head -n "$MAX_ITEMS" | while IFS= read -r entry; do
            if [ $count -gt 0 ]; then
                echo ","
            fi

            # 提取各字段
            title=$(echo "$entry" | grep -oP '<title[^>]*>\K[^<]+' | head -1 | sed 's/"/\\"/g')
            link=$(echo "$entry" | grep -oP '<link[^>]*href="\K[^"]+' | head -1 | sed 's/"/\\"/g')
            [ -z "$link" ] && link=$(echo "$entry" | grep -oP '<link[^>]*>\K[^<]+' | head -1 | sed 's/"/\\"/g')
            summary=$(echo "$entry" | grep -oP '<summary[^>]*>\K[^<]+' | head -1 | sed 's/"/\\"/g; s/&lt;/</g; s/&gt;/>/g; s/&amp;/\\&/g')
            [ -z "$summary" ] && summary=$(echo "$entry" | grep -oP '<content[^>]*>\K[^<]+' | head -1 | sed 's/"/\\"/g')
            pubdate=$(echo "$entry" | grep -oP '<published[^>]*>\K[^<]+' | head -1 | sed 's/"/\\"/g')
            [ -z "$pubdate" ] && pubdate=$(echo "$entry" | grep -oP '<updated[^>]*>\K[^<]+' | head -1 | sed 's/"/\\"/g')

            # 截断过长摘要
            if [ ${#summary} -gt 200 ]; then
                summary="${summary:0:200}..."
            fi

            printf '  {"title": "%s", "url": "%s", "source_type": "traditional", "source_name": "rss", "summary": "%s", "pubdate": "%s", "image_url": null}' \
                "$title" "$link" "$summary" "$pubdate"

            count=$((count + 1))
        done
    else
        # RSS 2.0 格式解析
        echo "$FEED_CONTENT" | tr '\n' ' ' | grep -oP '<item>.*?</item>' | head -n "$MAX_ITEMS" | while IFS= read -r item; do
            if [ $count -gt 0 ]; then
                echo ","
            fi

            title=$(echo "$item" | grep -oP '<title>\K[^<]+' | head -1 | sed 's/"/\\"/g; s/<!\[CDATA\[//g; s/\]\]>//g')
            link=$(echo "$item" | grep -oP '<link>\K[^<]+' | head -1 | sed 's/"/\\"/g')
            desc=$(echo "$item" | grep -oP '<description>\K[^<]+' | head -1 | sed 's/"/\\"/g; s/<!\[CDATA\[//g; s/\]\]>//g; s/&lt;/</g; s/&gt;/>/g; s/&amp;/\\&/g')
            pubdate=$(echo "$item" | grep -oP '<pubDate>\K[^<]+' | head -1 | sed 's/"/\\"/g')

            # 从 description 中提取 og:image（如果有）
            img=$(echo "$desc" | grep -oP '<img[^>]+src="\K[^"]+' | head -1 | sed 's/"/\\"/g' || echo "")
            img_field="null"
            [ -n "$img" ] && img_field="\"$img\""

            # 去 HTML 标签，截断
            clean_desc=$(echo "$desc" | sed 's/<[^>]*>//g')
            if [ ${#clean_desc} -gt 200 ]; then
                clean_desc="${clean_desc:0:200}..."
            fi

            printf '  {"title": "%s", "url": "%s", "source_type": "traditional", "source_name": "rss", "summary": "%s", "pubdate": "%s", "image_url": %s}' \
                "$title" "$link" "$clean_desc" "$pubdate" "$img_field"

            count=$((count + 1))
        done
    fi

    echo ""
    echo "]"
}

output_json

log "完成: 已获取最多 $MAX_ITEMS 条"
exit 0
