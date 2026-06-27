#!/usr/bin/env python3
"""
News Search 输出历史管理工具
用法:
  python tools/history.py save              # 从 stdin 读取 JSON 摘要，保存到 history/YYYY-MM-DD.json
  python tools/history.py diff <d1> <d2>    # 对比两个日期的新闻变化
  python tools/history.py trending [N]      # 列出连续 N 天上榜的话题（默认 3 天）
  python tools/history.py last              # 显示最近一次历史的日期
  python tools/history.py get <date>        # 输出指定日期的历史 JSON

历史文件存储格式: history/YYYY-MM-DD.json
JSON 结构与 references/output-templates.md 中 JSON 格式一致。
"""

import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any

HISTORY_DIR = Path(__file__).resolve().parent.parent / "history"

# ── 辅助函数 ──────────────────────────────────────────────────────

def _ensure_dir() -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def _date_to_path(date_str: str) -> Path:
    """将 YYYY-MM-DD 转为文件路径"""
    return HISTORY_DIR / f"{date_str}.json"


def _load_history(date_str: str) -> dict | None:
    """加载指定日期的历史数据，不存在则返回 None"""
    path = _date_to_path(date_str)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _item_key(item: dict) -> str:
    """生成条目的唯一标识（用于跨天对比）"""
    # 优先用标题，附带来源类型
    title = item.get("title", "")
    source = item.get("source_type", "")
    return f"{source}:{title}"


# ── 命令实现 ──────────────────────────────────────────────────────

def cmd_save() -> None:
    """保存当前新闻摘要到历史文件"""
    _ensure_dir()
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(f"[history] JSON 解析失败: {e}", file=sys.stderr)
        sys.exit(1)

    date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    path = _date_to_path(date)

    # 如果今天已有，做合并（保留旧条目中仍有热度的）
    if path.exists():
        existing = _load_history(date)
        if existing:
            existing_titles = {item.get("title", "") for item in existing.get("items", [])}
            new_titles = {item.get("title", "") for item in data.get("items", [])}
            # 合并：新数据优先，补充旧数据中不重复的条目
            merged_items = list(data.get("items", []))
            for old_item in existing.get("items", []):
                if old_item.get("title", "") not in new_titles:
                    old_item["rank"] = len(merged_items) + 1
                    merged_items.append(old_item)
            data["items"] = merged_items
            data["total_items"] = len(merged_items)

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[history] 已保存 {date} ({len(data.get('items', []))} 条)", file=sys.stderr)


def cmd_get(date_str: str) -> None:
    """输出指定日期的历史 JSON"""
    data = _load_history(date_str)
    if data is None:
        print(f"[history] 未找到 {date_str} 的历史数据", file=sys.stderr)
        sys.exit(1)
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def cmd_last() -> None:
    """显示最近的历史日期"""
    files = sorted(HISTORY_DIR.glob("*.json"), reverse=True) if HISTORY_DIR.exists() else []
    if not files:
        print("(无历史数据)")
        return
    latest = files[0].stem  # YYYY-MM-DD
    data = _load_history(latest)
    if data:
        print(f"{latest} ({len(data.get('items', []))} 条)")


def cmd_diff(date1: str, date2: str) -> None:
    """对比两个日期的新闻变化"""
    d1 = _load_history(date1)
    d2 = _load_history(date2)

    if not d1:
        print(f"[history] 缺少 {date1} 的数据", file=sys.stderr)
        sys.exit(1)
    if not d2:
        print(f"[history] 缺少 {date2} 的数据", file=sys.stderr)
        sys.exit(1)

    items1 = {_item_key(item): item for item in d1.get("items", [])}
    items2 = {_item_key(item): item for item in d2.get("items", [])}

    keys1 = set(items1.keys())
    keys2 = set(items2.keys())

    new_keys = keys2 - keys1
    dropped_keys = keys1 - keys2
    common_keys = keys1 & keys2

    # 上升/下降（热度变化 > 10 分）
    rising = []
    falling = []
    for key in common_keys:
        score1 = items1[key].get("heat_score", 0) or 0
        score2 = items2[key].get("heat_score", 0) or 0
        delta = score2 - score1
        if delta > 10:
            rising.append((key, delta, items2[key]))
        elif delta < -10:
            falling.append((key, delta, items2[key]))

    rising.sort(key=lambda x: -x[1])
    falling.sort(key=lambda x: x[1])

    # 输出对比结果
    print(f"## 新闻趋势对比：{date1} → {date2}\n")

    if new_keys:
        print(f"### 🆕 新增话题 ({len(new_keys)} 条)")
        for key in sorted(new_keys)[:10]:
            item = items2[key]
            tags = " ".join(f"[{t}]" for t in item.get("topic_tags", []))
            print(f"- {tags} **{item.get('title', key)}** 热度: {item.get('heat_score', '?')}")
        if len(new_keys) > 10:
            print(f"  ... 等共 {len(new_keys)} 条")
        print()

    if dropped_keys:
        print(f"### ⬇️ 消失话题 ({len(dropped_keys)} 条)")
        for key in sorted(dropped_keys)[:5]:
            item = items1[key]
            print(f"- ~~{item.get('title', key)}~~")
        if len(dropped_keys) > 5:
            print(f"  ... 等共 {len(dropped_keys)} 条")
        print()

    if rising:
        print(f"### 📈 热度上升 ({len(rising)} 条)")
        for key, delta, item in rising[:5]:
            print(f"- {item.get('title', key)}  +{delta}分 → {item.get('heat_score', '?')}")
        if len(rising) > 5:
            print(f"  ... 等共 {len(rising)} 条")
        print()

    if falling:
        print(f"### 📉 热度下降 ({len(falling)} 条)")
        for key, delta, item in falling[:5]:
            print(f"- {item.get('title', key)}  {delta}分 → {item.get('heat_score', '?')}")
        if len(falling) > 5:
            print(f"  ... 等共 {len(falling)} 条")
        print()

    if not (new_keys or dropped_keys or rising or falling):
        print("无明显变化。")


def cmd_trending(n: int = 3) -> None:
    """列出连续 N 天上榜的话题"""
    files = sorted(HISTORY_DIR.glob("*.json")) if HISTORY_DIR.exists() else []
    if len(files) < n:
        print(f"[history] 历史数据不足（需要至少 {n} 天，当前 {len(files)} 天）", file=sys.stderr)
        sys.exit(1)

    # 取最近 N 天的数据
    recent_files = files[-n:]
    title_sets: list[set[str]] = []

    for f in recent_files:
        data = _load_history(f.stem)
        if data:
            titles = {item.get("title", "") for item in data.get("items", [])}
            title_sets.append(titles)

    if len(title_sets) < n:
        print("[history] 部分历史数据损坏", file=sys.stderr)
        sys.exit(1)

    # 求交集
    common = title_sets[0]
    for ts in title_sets[1:]:
        common = common & ts

    if common:
        print(f"## 连续 {n} 天上榜话题 ({len(common)} 条)\n")
        for title in sorted(common):
            print(f"- {title}")
    else:
        print(f"无连续 {n} 天上榜的话题。")


def cmd_today_trend() -> None:
    """比较今天和昨天的趋势（快捷方式）"""
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    if not _date_to_path(today).exists():
        print(f"[history] 今天 ({today}) 暂无历史数据，请先执行一次新闻搜索", file=sys.stderr)
        sys.exit(1)
    if not _date_to_path(yesterday).exists():
        print(f"[history] 昨天 ({yesterday}) 暂无历史数据，无法对比", file=sys.stderr)
        sys.exit(1)

    cmd_diff(yesterday, today)


# ── CLI ────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python history.py <save|get|last|diff|trending|today> [参数...]", file=sys.stderr)
        print("  save              从 stdin 读取 JSON 摘要并保存", file=sys.stderr)
        print("  get <YYYY-MM-DD>  输出指定日期的历史 JSON", file=sys.stderr)
        print("  last              显示最近历史日期", file=sys.stderr)
        print("  diff <d1> <d2>    对比两个日期", file=sys.stderr)
        print("  trending [N]      列出连续 N 天上榜话题（默认 3）", file=sys.stderr)
        print("  today             快捷对比今天 vs 昨天", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "save":
        cmd_save()
    elif cmd == "get":
        if len(sys.argv) < 3:
            print("用法: python history.py get <YYYY-MM-DD>", file=sys.stderr)
            sys.exit(1)
        cmd_get(sys.argv[2])
    elif cmd == "last":
        cmd_last()
    elif cmd == "diff":
        if len(sys.argv) < 4:
            print("用法: python history.py diff <YYYY-MM-DD> <YYYY-MM-DD>", file=sys.stderr)
            sys.exit(1)
        cmd_diff(sys.argv[2], sys.argv[3])
    elif cmd == "trending":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
        cmd_trending(n)
    elif cmd == "today":
        cmd_today_trend()
    else:
        print(f"未知命令: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
