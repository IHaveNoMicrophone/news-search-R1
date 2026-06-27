# 数据源与获取方式

## 概述

通过 4 路并行数据源获取全网热点信号，然后按综合热度评分排序。

## 阶段 A：Bilibili 时政新闻搜索 🔴 核心来源 (40%)

### 搜索方式
使用 **WebSearch** 工具在 bilibili 上搜索时政新闻类视频：

| 搜索词 | 说明 |
|--------|------|
| `site:bilibili.com 时政新闻` | 时政类视频 |
| `site:bilibili.com 国际新闻` | 国际新闻视频 |
| `site:bilibili.com 社会热点` | 社会热点视频 |
| `site:bilibili.com 今日新闻` | 当日新闻视频 |

### 获取详情
从 WebSearch 结果中提取 bvid（URL 中 `/video/BVxxx`），然后对每个 bvid 并行 curl：

```bash
curl -s --connect-timeout 10 "https://api.bilibili.com/x/web-interface/view?bvid={bvid}" \
  -H "User-Agent: Mozilla/5.0" -H "Referer: https://www.bilibili.com/"
```

### 提取字段
- `stat.view` — 播放量（🔥 核心指标）
- `stat.danmaku` — 弹幕数
- `stat.like` — 点赞数
- `stat.coin` — 投币数
- `stat.share` — 分享数
- `stat.reply` — 评论数
- `pic` — 封面图 URL（始终可访问）
- `title`, `desc`, `owner.name`, `pubdate`, `tname`（分区名）

### 筛选规则
- 优先保留时政、社会、国际、科技、财经类内容
- 排除纯娱乐、游戏、鬼畜、舞蹈等非新闻分区
- 按播放量降序，取前 6-8 条进入排名

### 缓存 TTL
- WebSearch 结果：600s
- 视频详情 API：600s

---

## 阶段 B：Bilibili 热搜关键词

### 获取方式
```bash
curl -s --connect-timeout 10 "https://app.bilibili.com/x/v2/search/trending/ranking?limit=20" \
  -H "User-Agent: Mozilla/5.0"
```

### 提取字段
- `list[].keyword` — 热搜词
- `list[].show_name` — 显示名称
- `list[].position` — 排名

### 用途
用于交叉验证传统新闻热度。热搜词与新闻标题做模糊匹配（包含关系即算匹配）。

### 缓存 TTL
- 300s（5 分钟）

---

## 阶段 C：全网热搜聚合（微博热搜）

### 获取方式（带降级链）
使用 `bash scripts/fetch_weibo.sh` 脚本：

降级链：
1. **主**：`https://60s.viki.moe/v2/weibo` — 第三方微博热搜 API
2. **备 A**：`https://tenapi.cn/v2/weibohot` — 备用第三方 API
3. **备 B**：WebSearch `site:weibo.com 热搜榜` — 搜索引擎抓取
4. **备 C**：仅用 bilibili 热搜数据，CrossPlatformSignal 上限降为 20 分

### 检测降级
脚本返回 JSON，如果包含 `"fallback"` 字段，说明降级触发：
- `"fallback": "websearch"` → 执行备 B（WebSearch）
- 若 WebSearch 也失败 → 执行备 C

### 提取字段
- `data[].title` — 热搜标题
- `data[].hot_value` — 热度值
- `data[].link` — 微博搜索链接

### 缓存 TTL
- 120s（2 分钟）

---

## 阶段 D：传统来源搜索

### 搜索方式
使用 **WebSearch** 工具。受 `source` 参数控制（`international` / `domestic` / `all`）。

### 国际新闻来源（中文报道国际事件）

| 来源 | 搜索词 |
|------|--------|
| 参考消息 | `site:cankaoxiaoxi.com 国际新闻 热点` |
| 环球网 | `site:huanqiu.com 国际新闻 头条` |
| 凤凰网 | `site:ifeng.com 国际新闻 热点` |

### 国内新闻来源

| 来源 | 搜索词 |
|------|--------|
| 新华网 | `site:xinhuanet.com 今日热点` |
| 澎湃新闻 | `site:thepaper.cn 热点新闻` |
| 新浪新闻 | `site:news.sina.com.cn 今日热点` |

### 获取内容详情
```bash
curl -sL --connect-timeout 10 "<新闻URL>" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
  --limit-rate 500K
```

### 提取字段
- **标题**：`<title>` 标签（去除站点后缀）
- **og:image**：`grep -oP '<meta[^>]+property="og:image"[^>]+content="\K[^"]+'`
- **时间**：`<meta name="pubdate">` 或 `<meta name="publishdate">` 或 `<time>` 标签
- **摘要**：优先 `<meta name="description">`，其次正文前 200 字

### 缓存 TTL
- WebSearch 结果：600s

---

## 阶段 E：RSS 源补充（可选，P3）

当传统媒体 WebSearch 结果稀疏（< 5 条）时，自动补充 RSS 源。

详见 `sources/rss_feeds.md`，使用 `bash scripts/fetch_rss.sh <rss_url>` 获取。

---

## 并行执行要求

- 阶段 A（WebSearch bilibili 时政）、B（curl 热搜）、C（fetch_weibo.sh）、D（WebSearch 传统来源）**必须在同一批次中并行发起**
- 阶段 A 的 bilibili 搜索始终执行，不受 `source` 参数影响
- 阶段 B/C 数据始终执行，用于跨平台热度交叉验证
- 阶段 D 受 `source` 参数控制
- 每条 curl 命令后加 `|| true` 防止单点失败中断批次
- 同源请求之间间隔由 `config.yaml` `request_delay_ms` 控制

## 最终输出比例目标
- bilibili 时政视频：约 40%
- 传统新闻 + 热搜：约 60%
- 最终总量：10-15 条
