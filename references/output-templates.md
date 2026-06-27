# 输出模板

支持两种输出格式：**Markdown**（默认）和 **JSON**。

---

## Markdown 格式（默认）

### 颜色规范

| 颜色码 | 用途 |
|--------|------|
| `\033[1;33m` 粗体黄色 | 分类标题 |
| `\033[1;36m` 粗体青色 | 热度分数、播放量等数据指标 |
| `\033[1;32m` 粗体绿色 | 链接/URL |
| `\033[1;31m` 粗体红色 | 警告/跳过/异常说明 |
| `\033[0m` | 颜色重置 |

### 输出模板

```markdown
## 热点新闻汇总 (YYYY年MM月DD日)

> 共搜集 X 条内容 | 热度驱动排序 | 配图已保存至 pics/ 目录
> 时段：[早上/中午/下午/晚间/凌晨] | [如有降级：⚠️ 已降级来源: xxx]

---

\033[1;33m### Bilibili 时政新闻\033[0m

**1. [科技] [国际] [视频标题]**  热度: \033[1;36m85\033[0m
- UP主：xxx
- 播放：\033[1;36m417万\033[0m | 弹幕：4137 | 点赞：4.8万 | 投币：2.4万
- 简介：[2-3句中文概述视频内容]
- 观看：\033[1;32mhttps://www.bilibili.com/video/BV1xxx\033[0m
- 封面：pics/bilibili-20260624-01.jpg
- 同时报道：参考消息 / 环球网 / 微博热搜 #3

**2. [财经] [视频标题]**  热度: \033[1;36m72\033[0m
- ...

---

\033[1;33m### 全网热搜\033[0m

**1. [社会] [热点话题]** 微博热度: \033[1;36m1,188,539\033[0m
- 摘要：[2-3句中文概括事件]
- 同时登上：bilibili热搜 #3 / 微博热搜 #1
- 来源：\033[1;32m[报道链接]\033[0m
- 配图：pics/weibo-hot-20260624-01.jpg

---

\033[1;33m### 国际新闻\033[0m

**1. [国际] [军事] [新闻标题]** 热度: \033[1;36m62\033[0m
- 来源：参考消息 | 时间：2026年6月24日
- 摘要：[2-4句中文事件介绍]
- 原文：\033[1;32mhttps://...\033[0m
- 配图：pics/cankaoxi-20260624-01.jpg

---

\033[1;33m### 国内新闻\033[0m

**1. [科技] [新闻标题]** 热度: \033[1;36m45\033[0m
- 来源：新华网 | 时间：2026年6月24日
- 摘要：[2-4句中文事件介绍]
- 原文：\033[1;32mhttps://...\033[0m
- 配图：pics/xinhua-20260624-01.jpg
```

### 底部摘要

```markdown
---
完成：共搜集 X 条内容（Bilibili Y 条，热搜 Z 条，国际 W 条，国内 V 条）
去重合并：M 组（去重前 N 条，合并为 M 条）
配图覆盖率：\033[1;36mN%\033[0m | 图片已保存至 pics/ 目录
今日最热：\033[1;33mxxx\033[0m（综合热度 \033[1;36mXX\033[0m 分）
\033[1;31m失败来源：[如有]\033[0m
```

---

## JSON 格式

通过 `config.yaml` 中设置 `output_format: json` 或在请求中指定 JSON 输出启用。

### JSON Schema

```json
{
  "date": "2026-06-27",
  "generated_at": "2026-06-27T14:30:00+08:00",
  "time_of_day": "afternoon",
  "source_scope": "all",
  "total_items": 12,
  "dedup_info": {
    "before_dedup": 20,
    "after_dedup": 12,
    "groups_merged": 5,
    "single_items": 7
  },
  "items": [
    {
      "rank": 1,
      "title": "视频/新闻标题",
      "topic_tags": ["科技", "国际"],
      "heat_score": 85,
      "score_breakdown": {
        "bilibili_signal": 35,
        "cross_platform": 28,
        "news_match": 12,
        "diversity_bonus": 6,
        "topic_bonus": 5
      },
      "source_type": "bilibili",
      "source_name": "bilibili",
      "url": "https://...",
      "image_url": "https://...",
      "image_local_path": "pics/bilibili-20260627-01.jpg",
      "summary_cn": "2-4句中文摘要",
      "related_links": [
        {"source_name": "weibo", "url": "...", "title": "相关微博话题"},
        {"source_name": "xinhua", "url": "...", "title": "相关报道"}
      ],
      "cross_source_count": 3,
      "cross_sources": ["bilibili", "weibo", "xinhua"],
      "metadata": {
        "plays": 4170000,
        "danmaku": 4137,
        "likes": 48000,
        "pubdate": "2026-06-27T10:00:00+08:00"
      }
    }
  ],
  "stats": {
    "bilibili_count": 5,
    "hot_search_count": 3,
    "international_count": 2,
    "domestic_count": 2,
    "image_coverage_pct": 75,
    "failed_sources": []
  }
}
```

此 JSON 格式与 `tools/history.py` 的存储格式一致，可直接用于历史对比。

---

## 配图命名规则

`{来源}-{日期}-{序号}.{扩展名}`

示例：
- `bilibili-20260627-01.jpg`
- `weibo-hot-20260627-01.jpg`
- `xinhua-20260627-01.jpg`
- `cankaoxi-20260627-01.jpg`
- `huanqiu-20260627-01.jpg`

## 配图下载

使用增强版下载脚本：
```bash
bash scripts/download_image.sh "<图片URL>" "pics/<文件名>"
```

特性：
- 自动重试 3 次，间隔 2 秒
- 下载后验证 MIME 类型为图片
- 拒绝超过 20MB 的文件
- bilibili 封面图（i0/i1/i2.hdslb.com）始终可直接访问
