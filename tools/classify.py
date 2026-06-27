#!/usr/bin/env python3
"""
News Search 话题分类标注工具
用法: 从 stdin 读取去重后的 JSON 候选列表，输出标注了 topic_tags 的 JSON 到 stdout

读取 references/topics.md 中的关键词库，对每条新闻标题+摘要做关键词匹配，
标注 1-3 个话题标签（科技/财经/军事/社会/国际/政治/娱乐）。
零外部依赖，纯 Python 标准库。

同时检查 config.yaml 中的 favorite_topics，匹配的条目在 heat_score 中 +5。
"""

import sys
import json
import re
from pathlib import Path
from typing import Any

# ── 话题分类关键词库（与 references/topics.md 同步） ────────────────

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "科技": [
        "AI", "人工智能", "芯片", "半导体", "5G", "6G", "航天", "卫星", "火箭",
        "特斯拉", "苹果", "Apple", "华为", "小米", "GPT", "ChatGPT", "机器人",
        "自动驾驶", "新能源", "电池", "量子", "区块链", "元宇宙", "大模型",
        "深度学习", "SpaceX", "NASA", "北斗", "探月", "火星", "空间站",
    ],
    "财经": [
        "股市", "A股", "港股", "美股", "央行", "利率", "加息", "降息", "GDP",
        "房价", "楼市", "人民币", "美元", "通胀", "比特币", "加密货币", "基金",
        "保险", "银行", "贸易", "关税", "制裁", "债务", "破产", "收购", "IPO",
        "上市",
    ],
    "军事": [
        "军事", "演习", "导弹", "航母", "国防", "战争", "冲突", "北约", "南海",
        "台海", "军演", "核武器", "核弹", "战机", "驱逐舰", "潜艇", "征兵",
        "军费", "武器", "弹药",
    ],
    "社会": [
        "地震", "洪水", "台风", "暴雨", "事故", "疫情", "高考", "中考", "医保",
        "养老", "教育", "环保", "污染", "食品安全", "房价", "就业", "失业",
        "扶贫", "乡村振兴", "交通", "春运",
    ],
    "国际": [
        "美国", "日本", "韩国", "欧盟", "俄罗斯", "乌克兰", "中东", "联合国",
        "外交", "访华", "出访", "峰会", "G7", "G20", "北约", "制裁", "协议",
        "条约", "大使", "使馆", "签证", "移民", "难民",
    ],
    "政治": [
        "两会", "人大", "政协", "政策", "法规", "改革", "反腐", "人事", "选举",
        "换届", "国务院", "外交部", "国防部", "商务部", "住建部", "政治局",
        "常委", "总书记", "主席", "总理",
    ],
    "娱乐": [
        "明星", "电影", "综艺", "音乐", "游戏", "演唱会", "票房", "上映",
        "开播", "杀青", "代言", "八卦",
    ],
}

# 娱乐类降级权重（在排序时置后，这里只做标记）
DOWNGRADE_TOPICS = {"娱乐"}


def classify_item(item: dict) -> dict:
    """为单条新闻标注话题标签"""
    title = item.get("title", "") or ""
    summary = item.get("summary", "") or item.get("desc", "") or ""
    text = f"{title} {summary}".lower()

    scores: dict[str, int] = {}

    for topic, keywords in TOPIC_KEYWORDS.items():
        count = 0
        for kw in keywords:
            if kw.lower() in text:
                count += 1
        if count > 0:
            scores[topic] = count

    # 按匹配关键词数量降序，取 Top 1-3
    sorted_topics = sorted(scores.items(), key=lambda x: -x[1])
    tags = [t for t, _ in sorted_topics[:3]]

    if not tags:
        tags = ["综合"]

    item["topic_tags"] = tags
    return item


def apply_favorite_boost(item: dict, favorites: list[str]) -> dict:
    """如果条目标签匹配用户偏好话题，+5 分"""
    tags = set(item.get("topic_tags", []))
    fav_set = set(fav for f in favorites for fav in f.split(","))
    fav_set = {f.strip() for f in fav_set if f.strip()}

    if tags & fav_set:
        current = float(item.get("heat_score", 0) or 0)
        item["heat_score"] = current + 5
        item["topic_bonus"] = 5

    return item


def load_favorites() -> list[str]:
    """从 config.yaml 读取 favorite_topics"""
    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    if not config_path.exists():
        return []

    try:
        content = config_path.read_text(encoding="utf-8")
        # 简单 YAML 解析：找 favorite_topics 下的列表项
        in_fav = False
        favorites: list[str] = []
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("favorite_topics:"):
                in_fav = True
                continue
            if in_fav:
                if stripped.startswith("#"):
                    continue
                if stripped.startswith("- "):
                    favorites.append(stripped[2:].strip().strip('"').strip("'"))
                elif stripped and not stripped.startswith(" ") and not stripped.startswith("-"):
                    break
        return favorites
    except OSError:
        return []


def classify(items: list[dict]) -> list[dict]:
    """对候选列表进行话题分类"""
    favorites = load_favorites()

    for item in items:
        classify_item(item)
        if favorites:
            apply_favorite_boost(item, favorites)

    return items


def main() -> None:
    try:
        raw = sys.stdin.read()
        items = json.loads(raw)
        if not isinstance(items, list):
            print(json.dumps({"error": "输入必须是 JSON 数组"}, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"JSON 解析失败: {e}"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    result = classify(items)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
