# RSS 源列表（可选补充数据源）

当传统媒体 WebSearch 结果稀疏（< 5 条）时，自动使用 RSS 源补充。
RSS 提供结构化、可靠的内容，是 WebSearch 抓取的有效补充。

## 可用 RSS 源

### 国际新闻

| 来源 | RSS URL | 类型 |
|------|---------|------|
| 环球网（国际） | `https://rss.huanqiu.com/world/china.xml` | 国际 |
| 参考消息 | `http://www.cankaoxiaoxi.com/feed` | 国际 |

### 国内新闻

| 来源 | RSS URL | 类型 |
|------|---------|------|
| 新华网（时政） | `http://www.xinhuanet.com/politics/xhll.xml` | 国内 |
| 澎湃新闻 | `https://www.thepaper.cn/rss.xml` | 国内 |

## 使用方式

```bash
# 获取 RSS 并解析为 JSON
bash scripts/fetch_rss.sh "<RSS_URL>" [max_items]

# 示例
bash scripts/fetch_rss.sh "https://rss.huanqiu.com/world/china.xml" 5
```

输出为标准 JSON 格式，可直接合并到候选列表中：
```json
[
  {
    "title": "新闻标题",
    "url": "https://...",
    "source_type": "traditional",
    "source_name": "huanqiu-rss",
    "summary": "新闻描述摘录",
    "pubdate": "2026-06-27T10:00:00+08:00",
    "image_url": null
  }
]
```

## 触发条件

在 Step 2 阶段 D 之后添加检查：
- 如果 `source = international` 或 `all` 且国际来源 < 3 条 → 补充环球网/参考消息 RSS
- 如果 `source = domestic` 或 `all` 且国内来源 < 3 条 → 补充新华网/澎湃 RSS

RSS 条目自动参与后续的去重、分类、评分流程。

## 注意事项

- RSS 条目通常无配图（`image_url: null`），在配图优先级中排最后
- RSS 条目默认 NewsMatchSignal 为基础分 4（等于 1 家传统媒体报道）
- RSS fetch 超时 10 秒，失败静默跳过
- RSS 条目标注 `source_name` 末尾带 `-rss` 后缀以便区分
