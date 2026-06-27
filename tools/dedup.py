#!/usr/bin/env python3
"""
News Search 跨来源新闻去重工具
用法: 从 stdin 读取 JSON 候选列表，输出去重合并后的 JSON 到 stdout

零外部依赖，纯 Python 标准库实现。
使用中文 2-gram 关键词短语提取 + Jaccard 相似度进行模糊匹配。
相似度 >= 0.4 视为同一事件，合并为一组。
"""

import sys
import json
import re
from typing import Any

# ── 中文常用停用词表 ──────────────────────────────────────────────
STOPWORDS: set[str] = {
    # 结构词
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
    "所", "为", "所以", "因为", "但是", "然而", "而且", "虽然", "如果",
    "可以", "这个", "那个", "什么", "怎么", "哪", "吗", "啊", "呢", "吧",
    "被", "把", "从", "对", "与", "或", "及", "并", "而", "且", "但",
    # 新闻常用中性词
    "视频", "新闻", "报道", "最新", "今日", "热点", "关注", "网友", "表示",
    "进行", "相关", "目前", "已经", "正在", "可能", "预计", "据悉",
    "据了解", "记者", "发布", "消息", "事件", "发生", "情况", "问题",
    "方面", "工作", "发展", "建设", "国家", "社会", "中国", "美国",
    "国内", "国际", "世界", "全球", "地区", "部门", "单位", "组织",
}

# ── 标点/空白清理 ─────────────────────────────────────────────────
_RE_PUNCT = re.compile(r"[^一-鿿\w]+")  # 保留中文、字母、数字
_RE_SPACES = re.compile(r"\s+")


def tokenize(text: str) -> list[str]:
    """简单中文分词：去标点 → 按空白切分 → 再对纯中文片段做 2-gram 切分"""
    text = _RE_PUNCT.sub(" ", text).strip().lower()
    tokens: list[str] = []
    for segment in text.split():
        # 如果是纯中文（无空格字母），做 2-gram
        if re.fullmatch(r"[一-鿿]+", segment):
            if len(segment) == 1:
                tokens.append(segment)
            else:
                for i in range(len(segment) - 1):
                    tokens.append(segment[i : i + 2])
        else:
            # 英文/混合词直接保留
            if len(segment) >= 2:
                tokens.append(segment)
    # 去停用词
    return [t for t in tokens if t not in STOPWORDS and len(t) >= 2]


def extract_key_phrases(text: str) -> set[str]:
    """提取关键词短语集合（用于相似度比较）"""
    return set(tokenize(text))


def jaccard_similarity(a: set[str], b: set[str]) -> float:
    """Jaccard 相似度"""
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union > 0 else 0.0


def are_same_story(item1: dict, item2: dict, threshold: float = 0.4) -> bool:
    """判断两条新闻是否为同一事件"""
    title1 = item1.get("title", "")
    title2 = item2.get("title", "")
    desc1 = item1.get("summary", "") or item1.get("desc", "") or ""
    desc2 = item2.get("summary", "") or item2.get("desc", "") or ""

    # 两个相似度：仅标题 vs 标题+摘要
    title_sim = jaccard_similarity(extract_key_phrases(title1), extract_key_phrases(title2))
    full_sim = jaccard_similarity(
        extract_key_phrases(title1 + " " + desc1),
        extract_key_phrases(title2 + " " + desc2),
    )

    # 综合相似度：标题权重更高
    combined = title_sim * 0.6 + full_sim * 0.4
    return combined >= threshold


def pick_primary(group: list[dict]) -> dict:
    """从一个去重组中选出主条目
    优先级：bilibili 视频 > 有配图 > 高热度分 > 第一项
    """
    # 排序键：bilibili 来源优先，有图片优先，热度高优先
    def rank(item: dict) -> tuple[int, int, float]:
        is_bilibili = 1 if item.get("source_type") == "bilibili" else 0
        has_image = 1 if item.get("image_url") else 0
        heat = float(item.get("heat_score", 0) or 0)
        # 返回负值使高的排前面（sort 默认升序）
        return (-is_bilibili, -has_image, -heat)

    group.sort(key=rank)
    return group[0]


def deduplicate(items: list[dict], threshold: float = 0.4) -> list[dict]:
    """
    对候选新闻列表进行去重合并。

    输入每一项格式:
      {
        "title": str,
        "source_type": str,      # "bilibili" | "weibo" | "traditional"
        "source_name": str,      # "bilibili" | "weibo" | "xinhua" | ...
        "url": str,
        "image_url": str | None,
        "summary": str | None,
        "desc": str | None,
        "heat_score": float | None,
        "extra": dict | None     # 其他元数据（播放量等）
      }

    输出去重后的列表，每个合并项增加字段:
      - related_links: [{"source_name": str, "url": str, "title": str}]
      - cross_source_count: int
      - cross_sources: [str]
    """
    if not items:
        return []

    n = len(items)
    # Union-Find
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # 两两比较（O(n²)，对于 10-30 条候选完全可接受）
    for i in range(n):
        for j in range(i + 1, n):
            if are_same_story(items[i], items[j], threshold):
                union(i, j)

    # 按根节点分组
    groups: dict[int, list[int]] = {}
    for i in range(n):
        root = find(i)
        groups.setdefault(root, []).append(i)

    # 合并每组
    result: list[dict] = []
    for indices in groups.values():
        group_items = [items[i] for i in indices]
        primary = pick_primary(group_items)

        # 收集所有来源链接
        related_links: list[dict] = []
        seen_urls: set[str] = set()
        source_names: set[str] = set()

        for item in group_items:
            source_names.add(item.get("source_name", item.get("source_type", "")))
            url = item.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                related_links.append({
                    "source_name": item.get("source_name", item.get("source_type", "")),
                    "url": url,
                    "title": item.get("title", ""),
                })

        # 构建合并条目
        merged = dict(primary)
        merged["related_links"] = related_links
        merged["cross_source_count"] = len(source_names)
        merged["cross_sources"] = sorted(source_names)

        # 如果有多个不同来源，给热度加分
        if merged.get("heat_score") is not None:
            diversity_bonus = min((len(source_names) - 1) * 3, 9)  # 最多 +9
            merged["heat_score"] += diversity_bonus
            merged["diversity_bonus"] = diversity_bonus

        # 合并后的标题：如果有多个来源，优先使用主条目标题
        if len(group_items) > 1:
            merged["original_count"] = len(group_items)
            merged["merged_titles"] = [item.get("title", "") for item in group_items]

        result.append(merged)

    # 按热度降序排列
    result.sort(key=lambda x: float(x.get("heat_score", 0) or 0), reverse=True)
    return result


def main() -> None:
    """CLI 入口：从 stdin 读取 JSON 数组，输出去重后的 JSON 数组"""
    try:
        raw = sys.stdin.read()
        items = json.loads(raw)
        if not isinstance(items, list):
            print(json.dumps({"error": "输入必须是 JSON 数组"}, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"JSON 解析失败: {e}"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    threshold = float(sys.argv[1]) if len(sys.argv) > 1 else 0.4
    result = deduplicate(items, threshold)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
