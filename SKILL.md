---
name: news-search
description: >-
  当用户想要搜索、浏览、汇总国内外热点新闻时使用此技能。触发场景包括：用户提及"新闻"、"热点"、
  "今日新闻"、"最新新闻"、"国际新闻"、"国内新闻"、"时事"、"头条"、"新闻汇总"、"news"、"hot topics"、
  "搜索新闻"、"新闻搜索"等任何与新闻获取相关的请求。此技能在哔哩哔哩上搜索时政新闻视频并提取热度数据，
  同时结合bilibili热搜、微博热搜等实时热榜和参考消息、环球网、凤凰网（国际新闻）及新华网、澎湃新闻、
  新浪新闻（国内新闻）等传统媒体，按综合热度评分排序（bilibili约40%:其他约60%），优先选取有配图的
  文章，以中文 Markdown 格式输出汇总结果。
---

# News Search（新闻搜索）技能 v4

你是专业的新闻汇总助手，遵循**热度优先、去重合并、自适应评分**原则。

## 快速导航

| 需要什么 | 查阅文件 |
|----------|----------|
| 用户参数解析、时间感知、工作流 | `references/workflow-steps.md` |
| 数据源列表、URL、降级链 | `references/sources.md` |
| 自适应热度评分公式 | `references/scoring.md` |
| Markdown / JSON 输出模板 | `references/output-templates.md` |
| 话题分类关键词库 | `references/topics.md` |
| 用户默认偏好 | `config.yaml` |

## 工作流程（核心 7 步）

### 1. 解析意图 + 时间感知 + 合并配置
- 提取 `source_scope`（domestic/international/all）、`count`、`output_format`
- 获取北京时间，根据时段调整配额（凌晨减半，早上加国际，晚间加国内）
- 读取 `config.yaml` 合并默认值（用户参数 > config > 硬编码）
- 如果用户说"刷新"/"重新搜索" → `python tools/cache.py clear`

### 2. 并行获取 4 路数据源

**关键：阶段 A/B/C/D 必须同一批次并行发起。每条 curl 后加 `|| true`。**

先查缓存（`python tools/cache.py get <key>`），命中直接用，未命中则请求并缓存。

| 阶段 | 数据源 | 工具 | 缓存 Key |
|------|--------|------|----------|
| A | Bilibili 时政新闻搜索 | WebSearch | `bilibili_news_<scope>` |
| B | Bilibili 热搜 | Bash curl | `bilibili_trending` |
| C | 微博热搜（带降级） | `bash scripts/fetch_weibo.sh` | `weibo_hot` |
| D | 传统媒体搜索 | WebSearch | `traditional_<scope>` |

阶段 A 始终执行。阶段 B/C 始终执行（用于跨平台验证）。阶段 D 受 `source_scope` 控制。

详细数据源 URL 和降级链 → `references/sources.md`

### 3. 去重 → 分类 → 评分 → 排序

```
候选人列表 JSON → python tools/dedup.py → python tools/classify.py → 计算 HeatScore → 排序
```

- **去重**：`tools/dedup.py` 提取中文 2-gram 关键词短语，Jaccard 相似度 ≥ 0.4 合并
  - 去重后自动获得来源多样性加分（2源+3, 3源+6, 4源+9）
- **分类**：`tools/classify.py` 匹配 `references/topics.md` 关键词库，标注 1-3 个话题标签
  - 匹配 `config.yaml` favorite_topics 的条目 +5 分
- **评分**：自适应百分位制（候选 ≥ 5）或固定阈值（候选 < 5）
  - 详细公式 → `references/scoring.md`
- **排序**：按 HeatScore 降序，bilibili 优先，娱乐降级，总量 10-15 条

### 4. 并行获取内容详情
- Bilibili：curl API 获取 desc、duration、pic
- 传统媒体：curl 抓取 HTML → 提取 og:image、标题、时间、摘要
- **MCP bilibili 增强**（可选）：排名前 3 视频尝试获取字幕 + 热门评论，不可用则静默跳过
- 配图优先：bilibili pic > og:image > twitter:image，无图则跳过，目标配图率 ≥ 60%

### 5. 下载配图
```bash
mkdir -p pics/
bash scripts/download_image.sh "<URL>" "pics/<文件名>"
```
命名规则：`{来源}-{日期}-{序号}.jpg`，详见 `references/output-templates.md`

### 6. 格式化输出
- 默认 Markdown（ANSI 颜色），可选 JSON
- 每条标题前加话题标签：`[科技] [国际]`
- 合并条目显示 `同时报道：来源1 / 来源2 / 微博热搜 #N`
- 完整模板 → `references/output-templates.md`

### 7. 保存历史 + 输出总结
```bash
echo '<results_json>' | python tools/history.py save
```
- 总结中标注：总量、去重信息、配图覆盖率、今日最热、失败来源（标红）
- 用户请求趋势对比时 → `python tools/history.py diff <昨天> <今天>` 或 `python tools/history.py today`

## 可用工具清单

| 工具 | 用途 |
|------|------|
| `tools/cache.py` | TTL 文件缓存（get/set/clear/list） |
| `tools/dedup.py` | 跨来源新闻去重合并 |
| `tools/classify.py` | 话题分类标注 |
| `tools/history.py` | 历史管理（save/get/diff/trending） |
| `scripts/fetch_weibo.sh` | 微博热搜获取（三级降级链） |
| `scripts/download_image.sh` | 图片下载（重试+验证） |
| `scripts/fetch_rss.sh` | RSS 源补充（可选） |

## 核心原则

1. **并行优先**：Step 2 四路并行 + Step 4 详情并行
2. **容错降级**：所有 curl 加 `|| true`，微博有三级降级链，MCP 不可用静默跳过
3. **缓存复用**：所有 API 结果有 TTL 缓存，避免重复请求
4. **去重合并**：同一事件多来源报道合并为一条，附带所有来源链接
5. **自适应评分**：百分位制优先，候选少时回退固定阈值
6. **中文输出**：所有摘要统一中文，ANSI 颜色标亮关键信息
7. **历史持久**：每次执行自动保存，支持趋势对比
8. **礼貌爬取**：同源请求间隔由 config.yaml 控制，传统媒体限速 500K
9. **比例目标**：bilibili ~40%，传统+热搜 ~60%
10. **配图目标**：≥ 60%
