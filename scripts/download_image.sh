#!/bin/bash
# News Search 图片下载辅助脚本 (Enhanced v2)
# 用法: bash download_image.sh <图片URL> <保存路径> [超时秒数(默认15)]
#
# 使用 curl 从指定 URL 下载图片并保存到本地路径。
# - 自动重试 3 次，间隔 2 秒
# - 下载后验证 MIME 类型是否为图片
# - 拒绝超过 20MB 的文件
# - 模拟浏览器请求头
# - 自动创建目标目录

set -euo pipefail

# ── 参数检查 ──────────────────────────────────────────────────────
if [ $# -lt 2 ]; then
    echo "用法: bash download_image.sh <图片URL> <保存路径> [超时秒数]" >&2
    echo "示例: bash download_image.sh https://example.com/photo.jpg pics/news-01.jpg" >&2
    exit 1
fi

IMAGE_URL="$1"
SAVE_PATH="$2"
TIMEOUT="${3:-15}"
MAX_RETRIES=3
RETRY_DELAY=2
MAX_SIZE_MB=20
MAX_SIZE_BYTES=$((MAX_SIZE_MB * 1024 * 1024))

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

# ── 确保目标目录存在 ──────────────────────────────────────────────
TARGET_DIR=$(dirname "$SAVE_PATH")
if [ ! -d "$TARGET_DIR" ]; then
    mkdir -p "$TARGET_DIR"
fi

echo "[下载] $IMAGE_URL"
echo "[目标] $SAVE_PATH"

START_TIME=$(date +%s)

# ── 带重试的下载 ──────────────────────────────────────────────────
download_with_retry() {
    local attempt=1

    while [ $attempt -le $MAX_RETRIES ]; do
        if [ $attempt -gt 1 ]; then
            echo "[重试] 第 $attempt/$MAX_RETRIES 次尝试..." >&2
            sleep "$RETRY_DELAY"
        fi

        # 使用 curl 下载
        HTTP_CODE=$(curl \
            --location \
            --connect-timeout "$TIMEOUT" \
            --max-time "$TIMEOUT" \
            --retry 0 \
            --silent \
            --show-error \
            --output "$SAVE_PATH" \
            --write-out "%{http_code}" \
            --user-agent "$UA" \
            "$IMAGE_URL" 2>/dev/null || echo "000")

        if [ "$HTTP_CODE" = "200" ] && [ -s "$SAVE_PATH" ]; then
            return 0
        fi

        echo "[警告] 第 $attempt 次尝试失败 (HTTP $HTTP_CODE)" >&2
        rm -f "$SAVE_PATH"
        attempt=$((attempt + 1))
    done

    return 1
}

# ── 执行下载 ──────────────────────────────────────────────────────
if ! download_with_retry; then
    echo "[失败] 重试 $MAX_RETRIES 次后仍失败" >&2
    rm -f "$SAVE_PATH"
    exit 1
fi

# ── 检查文件大小 ──────────────────────────────────────────────────
FILE_SIZE=$(wc -c < "$SAVE_PATH" 2>/dev/null || echo 0)

if [ "$FILE_SIZE" -eq 0 ]; then
    echo "[失败] 下载的文件为空" >&2
    rm -f "$SAVE_PATH"
    exit 1
fi

if [ "$FILE_SIZE" -gt "$MAX_SIZE_BYTES" ]; then
    FILE_SIZE_MB=$(echo "scale=1; $FILE_SIZE / 1048576" | bc 2>/dev/null || echo "?")
    echo "[失败] 文件过大 (${FILE_SIZE_MB}MB > ${MAX_SIZE_MB}MB 上限)" >&2
    rm -f "$SAVE_PATH"
    exit 1
fi

# ── 验证 MIME 类型 ────────────────────────────────────────────────
# 优先用 file 命令，不可用时跳过验证
if command -v file &>/dev/null; then
    MIME_TYPE=$(file --mime-type -b "$SAVE_PATH" 2>/dev/null || echo "")
    if [ -n "$MIME_TYPE" ] && ! echo "$MIME_TYPE" | grep -qE "^image/"; then
        echo "[失败] 非图片文件 (MIME: $MIME_TYPE)" >&2
        rm -f "$SAVE_PATH"
        exit 1
    fi
    echo "[验证] MIME: $MIME_TYPE"
else
    # 回退：检查文件扩展名
    EXT="${SAVE_PATH##*.}"
    case "$EXT" in
        jpg|jpeg|png|gif|webp|bmp|svg|ico|avif)
            ;;
        *)
            echo "[警告] 无法验证文件类型（file 命令不可用），根据扩展名 '$EXT' 继续" >&2
            ;;
    esac
fi

# ── 成功 ──────────────────────────────────────────────────────────
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
FILE_SIZE_KB=$(echo "scale=1; $FILE_SIZE / 1024" | bc 2>/dev/null || echo "?")

echo "[成功] 已保存 (${FILE_SIZE_KB} KB): $SAVE_PATH"
echo "[完成] 耗时 ${ELAPSED}s"
exit 0
