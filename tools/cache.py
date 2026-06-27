#!/usr/bin/env python3
"""
News Search TTL 文件缓存工具
用法:
  python tools/cache.py get <key>          # 命中则输出到 stdout (exit 0), 未命中/过期 exit 1
  python tools/cache.py set <key> <ttl>    # 从 stdin 读取值并写入缓存
  python tools/cache.py clear              # 清空所有缓存文件
  python tools/cache.py list               # 列出所有缓存条目及剩余 TTL

默认缓存目录: 脚本所在目录的 ../cache/ (即 skills/news-search/cache/)
可通过环境变量 NEWS_SEARCH_CACHE_DIR 覆盖。

TTL 参考值:
  - bilibili trending:    300s (5分钟)
  - weibo hot:            120s (2分钟)
  - bilibili video detail: 600s (10分钟)
  - traditional search:   600s (10分钟)
  - websearch result:     600s (10分钟)
"""

import sys
import os
import json
import time
import hashlib
from pathlib import Path

# 缓存目录：优先环境变量，其次脚本相对路径
def _get_cache_dir() -> Path:
    env_dir = os.environ.get("NEWS_SEARCH_CACHE_DIR", "")
    if env_dir:
        return Path(env_dir)
    return Path(__file__).resolve().parent.parent / "cache"


CACHE_DIR = _get_cache_dir()


def _safe_key(key: str) -> str:
    """将任意 key 转为安全的文件名"""
    h = hashlib.sha256(key.encode()).hexdigest()[:16]
    # 保留部分可读前缀
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)[:32]
    return f"{safe}_{h}"


def _meta_path(key: str) -> Path:
    return CACHE_DIR / f"{_safe_key(key)}.meta"


def _data_path(key: str) -> Path:
    return CACHE_DIR / f"{_safe_key(key)}.json"


def cmd_get(key: str) -> None:
    """获取缓存：新鲜则输出到 stdout 并 exit 0，否则 exit 1"""
    mp = _meta_path(key)
    dp = _data_path(key)

    if not mp.exists() or not dp.exists():
        sys.exit(1)

    try:
        meta = json.loads(mp.read_text(encoding="utf-8"))
        created_at = meta.get("created_at", 0)
        ttl = meta.get("ttl", 300)
        age = time.time() - created_at

        if age < ttl:
            # 新鲜，输出数据
            data = dp.read_text(encoding="utf-8")
            sys.stdout.write(data)
            remaining = int(ttl - age)
            # 剩余 TTL 输出到 stderr 供调试
            print(f"[cache] 命中 key={key}, 剩余 {remaining}s / {ttl}s", file=sys.stderr)
            sys.exit(0)
        else:
            print(f"[cache] 过期 key={key}, 已过 {int(age)}s > {ttl}s", file=sys.stderr)
            sys.exit(1)
    except (json.JSONDecodeError, KeyError) as e:
        print(f"[cache] 元数据损坏 key={key}: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_set(key: str, ttl: int) -> None:
    """设置缓存：从 stdin 读取值，写入缓存文件"""
    data = sys.stdin.read()
    if not data.strip():
        print(f"[cache] 拒绝缓存空数据 key={key}", file=sys.stderr)
        sys.exit(1)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    meta = {
        "created_at": time.time(),
        "ttl": ttl,
        "key": key,
    }

    mp = _meta_path(key)
    dp = _data_path(key)

    mp.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    dp.write_text(data, encoding="utf-8")

    size_bytes = len(data.encode("utf-8"))
    print(f"[cache] 已缓存 key={key}, TTL={ttl}s, 大小={size_bytes}B", file=sys.stderr)


def cmd_clear() -> None:
    """清空所有缓存"""
    if not CACHE_DIR.exists():
        print("[cache] 缓存目录不存在，无需清理", file=sys.stderr)
        return

    count = 0
    for f in CACHE_DIR.iterdir():
        if f.suffix in (".json", ".meta"):
            f.unlink()
            count += 1
    print(f"[cache] 已清理 {count} 个缓存文件", file=sys.stderr)


def cmd_list() -> None:
    """列出所有缓存条目"""
    if not CACHE_DIR.exists():
        print("(缓存目录为空)")
        return

    entries = []
    for f in CACHE_DIR.glob("*.meta"):
        try:
            meta = json.loads(f.read_text(encoding="utf-8"))
            age = time.time() - meta.get("created_at", 0)
            ttl = meta.get("ttl", 0)
            remaining = max(0, int(ttl - age))
            entries.append({
                "key": meta.get("key", f.stem),
                "ttl": ttl,
                "age": int(age),
                "remaining": remaining,
                "fresh": remaining > 0,
            })
        except (json.JSONDecodeError, KeyError):
            pass

    if not entries:
        print("(无有效缓存条目)")
        return

    entries.sort(key=lambda e: e["remaining"], reverse=True)
    print(f"{'状态':<6} {'剩余TTL':<10} {'已过':<8} {'Key'}")
    print("-" * 60)
    for e in entries:
        status = "✅ 新鲜" if e["fresh"] else "❌ 过期"
        print(f"{status:<6} {e['remaining']}s{'':<5} {e['age']}s{'':<4} {e['key'][:50]}")


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python cache.py <get|set|clear|list> [key] [ttl]", file=sys.stderr)
        print("  get <key>          获取缓存（新鲜→stdout, 过期→exit 1）", file=sys.stderr)
        print("  set <key> <ttl>    从stdin读取值并缓存（ttl单位秒）", file=sys.stderr)
        print("  clear              清空所有缓存", file=sys.stderr)
        print("  list               列出所有缓存条目", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "get":
        if len(sys.argv) < 3:
            print("用法: python cache.py get <key>", file=sys.stderr)
            sys.exit(1)
        cmd_get(sys.argv[2])

    elif cmd == "set":
        if len(sys.argv) < 4:
            print("用法: python cache.py set <key> <ttl_seconds>", file=sys.stderr)
            sys.exit(1)
        cmd_set(sys.argv[2], int(sys.argv[3]))

    elif cmd == "clear":
        cmd_clear()

    elif cmd == "list":
        cmd_list()

    else:
        print(f"未知命令: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
