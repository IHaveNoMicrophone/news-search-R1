# 工作流程详细步骤

本文档描述 news-search 技能的完整执行步骤。
SKILL.md 中仅保留高层协调流程，具体细节参考本文档。

---

## 第一步：解析用户意图 + 时间感知

### 参数提取

从用户输入中提取：

| 参数 | 可选值 | 默认值 |
|------|--------|--------|
| 来源范围 | `domestic` / `international` / `all` | `all`（可经 config.yaml 覆盖） |
| 每类条数 | 正整数 | `3` |
| 输出格式 | `markdown` / `json` | `markdown` |

识别规则：
- "国际新闻"、"国外"、"海外" → `international`
- "国内新闻"、"中国" → `domestic`
- "全部"、"国内外"或未指定 → `all`
- "N条"、"前N条" → 对应 count
- "JSON格式"、"输出JSON" → json 格式
- "刷新"、"最新"、"重新搜索" → 清除缓存

### 合并配置文件

读取 `config.yaml`（如存在），用用户参数覆盖配置默认值：
- 参数合并优先级：用户显式指定 > config.yaml > 硬编码默认值
- 如果 config.yaml 不存在，使用硬编码默认值

### 时间感知

获取当前北京时间（UTC+8），根据时段调整策略：

| 时段 | 时间范围 | 策略 |
|------|----------|------|
| 早上 | 6:00-11:00 | 国际新闻 +2 配额，优先展示隔夜要闻 |
| 中午 | 11:00-14:00 | 均衡展示，不做调整 |
| 下午 | 14:00-18:00 | 优先展示当日突发事件 |
| 晚间 | 18:00-24:00 | 国内/社会 +2 配额，优先全天总结 |
| 凌晨 | 0:00-6:00 | 总量减半（6 条），仅高热度项（>50 分） |

### 缓存清理

如果用户要求刷新或 config.yaml 中设置了 `cache_refresh: true`：
```bash
python tools/cache.py clear
```

---

## 第二步：获取实时热搜和热度数据（并行）

参考 `references/sources.md` 了解每个数据源的详细获取方式。

**关键执行规则：**

1. **所有阶段必须在同一批次中并行发起**
2. 每条 curl 命令后加 `|| true` 防止非零退出码中断批次
3. 每个数据源先从缓存读取：
   ```bash
   if python tools/cache.py get "bilibili_trending" > /tmp/cache_hit.json 2>/dev/null; then
     # 使用缓存数据
   else
     # 发起请求并缓存结果
     curl ... | python tools/cache.py set "bilibili_trending" 300
   fi
   ```
4. 记录哪些数据源失败（用于 Step 7 摘要）

### 并行数据源清单

| 阶段 | 数据源 | 缓存 Key | TTL | 降级方案 |
|------|--------|----------|-----|----------|
| A | Bilibili 时政 WebSearch | `bilibili_news_<scope>` | 600s | 无（核心源） |
| B | Bilibili 热搜 curl | `bilibili_trending` | 300s | 无（公共 API） |
| C | 微博热搜 fetch_weibo.sh | `weibo_hot` | 120s | 三级降级链 |
| D | 传统媒体 WebSearch | `traditional_<scope>` | 600s | RSS 补充（阶段 E） |

---

## 第三步：计算热度评分并排序

### 步骤 3a：构建候选列表

将所有数据源的结果统一为候选条目格式：

```json
{
  "title": "...",
  "source_type": "bilibili|weibo|traditional",
  "source_name": "bilibili|weibo|xinhua|thepaper|sina|cankaoxi|huanqiu|ifeng|rss",
  "url": "...",
  "image_url": "...",
  "summary": "...",
  "desc": "...",
  "heat_score": 0,
  "metadata": {}
}
```

### 步骤 3b：去重

```bash
echo '<candidates_json>' | python tools/dedup.py [threshold]
```

默认 threshold = 0.4。去重后条目自动获得 `diversity_bonus` 加分。

### 步骤 3c：话题分类

```bash
echo '<deduped_json>' | python tools/classify.py
```

标注 topic_tags，匹配 favorite_topics 的条目获得 +5 加分。

### 步骤 3d：计算 HeatScore

按照 `references/scoring.md` 中的公式计算每条的综合热度分。

### 步骤 3e：排序

- 按 HeatScore 降序
- Bilibili 时政视频优先排列（即使分数稍低）
- [娱乐] 标签条目降级到最后
- 控制最终输出总量在 10-15 条

---

## 第四步：获取内容详情（并行）

对排名后的每条候选内容，并行获取详情。

### Bilibili 视频

```bash
curl -s --connect-timeout 10 "https://api.bilibili.com/x/web-interface/view?bvid={bvid}" \
  -H "User-Agent: Mozilla/5.0" -H "Referer: https://www.bilibili.com/"
```

提取 `desc`（描述）、`duration`（时长）、`pic`（高清封面）。

### MCP bilibili 增强（可选）

对排名前 3 的 bilibili 视频，尝试使用 MCP bilibili-mcp 工具：
- `get_video_transcript(bvid)` → 提取 2-3 句关键内容作为"视频要点"
- `get_video_comments(bvid, detail_level="brief")` → 提取时间戳评论定位关键片段

MCP 工具不可用时静默跳过，不影响主流程。

### 传统新闻

```bash
curl -sL --connect-timeout 10 "<新闻URL>" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
  --limit-rate 500K
```

从 HTML 提取：标题（`<title>`）、og:image、发布时间、摘要。

### 配图优先策略

1. 优先 bilibili 视频的 `pic` 封面图（始终可访问）
2. 其次提取 `<meta property="og:image">`
3. 再次 `<meta name="twitter:image">`
4. 无图即跳过，从候选中取下一篇（目标配图率 ≥ 60%）

---

## 第五步：下载配图

```bash
# 确保 pics/ 目录存在
mkdir -p pics/

# 下载每张配图
bash scripts/download_image.sh "<图片URL>" "pics/<文件名>"
```

命名规则见 `references/output-templates.md` 配图命名规则。

`download_image.sh` 特性：
- 自动重试 3 次
- MIME 类型验证
- 20MB 大小限制

---

## 第六步：格式化输出

根据 `output_format` 参数选择模板。详细模板见 `references/output-templates.md`。

---

## 第七步：保存历史 + 输出总结

### 保存历史

```bash
echo '<results_json>' | python tools/history.py save
```

写入 `history/YYYY-MM-DD.json`。

### 输出总结

```markdown
---
完成：共搜集 X 条内容（Bilibili Y 条，热搜 Z 条，国际 W 条，国内 V 条）
去重合并：M 组（去重前 N 条）
配图覆盖率：N% | 图片已保存至 pics/ 目录
今日最热：xxx（综合热度 XX 分）
失败来源：[如有，标红]
---
```

### 趋势对比（如果用户请求）

```bash
python tools/history.py diff <yesterday> <today>
```

如果用户说 "对比昨天"、"有什么变化"、"趋势" 等，在输出末尾附加趋势对比部分。

---

## 重要注意事项

1. **并行优先**：Step 2 A/B/C/D 必须并行，Step 4 详情获取必须并行
2. **容错**：某个 API 超时/异常 → 跳过该源，不阻塞整体（curl + `|| true`）
3. **缓存**：Step 2 前先检查缓存，避免重复请求
4. **去重**：Step 3 必须运行 `tools/dedup.py` 进行跨来源合并
5. **分类**：去重后运行 `tools/classify.py` 标注话题标签
6. **配图**：bilibili 封面图始终可用，传统新闻无图则跳过
7. **中文输出**：所有摘要统一使用中文
8. **礼貌爬取**：同源请求间隔由 `config.yaml` `request_delay_ms` 控制
9. **降级**：微博 API 不可用时走 fetch_weibo.sh 降级链
10. **历史**：每次执行后自动保存到 history/
