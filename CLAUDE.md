# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个 Claude Code **技能（skill）**，用于汇总国内外热点新闻。从 bilibili（时政搜索+热搜）、微博热搜、传统媒体（新华网、澎湃新闻、参考消息、环球网、凤凰网、新浪新闻）并行获取数据，经过去重→分类→评分→排序后，以中文 Markdown 输出，附带配图下载。

技能入口文件为 `SKILL.md`，触发词包括"新闻"、"热点"、"今日新闻"、"news"等。

## 工作流程（8 步）

```
0. 环境自检 → 检测 bilibili MCP 是否可用，不可用则运行 setup_bilibili_mcp.sh
1. 解析意图 → 提取 source_scope/count/output_format → 合并 config.yaml → 北京时间感知（凌晨减半、晚间加国内）
2. 并行获取 4 路数据（阶段 A/B/C/D 必须在同一批次发起）
3. 去重(dedup.py) → 分类(classify.py) → 计算 HeatScore → 排序
4. 并行获取内容详情（curl bilibili API / 抓取传统媒体 HTML / bilibili MCP 增强）
5. 下载配图（download_image.sh）
6. 格式化输出（Markdown 或 JSON）
7. 保存历史(history.py) + 输出总结
```

### 评分公式

由 LLM 按 `references/scoring.md` 中的规则执行，无独立评分脚本：

```
HeatScore = BilibiliSignal(0-45) + CrossPlatformSignal(0-40) + NewsMatchSignal(0-15)
```

- BilibiliSignal：候选 ≥ 5 时用自适应百分位制，< 5 时用固定阈值
- CrossPlatformSignal：微博+ bilibili 热搜交叉验证，微博不可用时上限降为 20
- NewsMatchSignal + diversity_bonus：由 `dedup.py` 去重时自动计算

## Python 工具链

所有工具位于 `tools/`，通过 **stdin → stdout JSON** 串联：

```bash
echo '<candidates.json>' | python tools/dedup.py [threshold] | python tools/classify.py
```

| 工具 | 用途 | 关键细节 |
|------|------|----------|
| `tools/cache.py` | TTL 文件缓存 | get/set/clear/list，缓存目录 `cache/` |
| `tools/dedup.py` | 跨来源去重合并 | 中文 2-gram + Jaccard 相似度 ≥0.4；Union-Find 分组；自动加 diversity_bonus（最多+9） |
| `tools/classify.py` | 话题分类标注 | 关键词匹配 `references/topics.md`；读取 `config.yaml` 的 `favorite_topics` 加 +5 分；零依赖 YAML 解析 |
| `tools/history.py` | 历史管理 | save/diff/trending/today，文件存 `history/YYYY-MM-DD.json` |

## Shell 脚本

| 脚本 | 用途 | 注意事项 |
|------|------|----------|
| `scripts/setup_bilibili_mcp.sh` | bilibili MCP 自动配置 | 零网络依赖，用 Python 合并 JSON，自动转换 Git Bash 路径→Windows 路径，幂等 |
| `scripts/fetch_weibo.sh` | 微博热搜（三级降级链） | 使用 `mktemp` 避免并发冲突 |
| `scripts/download_image.sh` | 图片下载 | 重试 3 次，MIME 验证，20MB 限制，纯 `$(( ))` 运算（无 bc 依赖） |
| `scripts/fetch_rss.sh` | RSS 补充源 | 从临时文件读取避免 pipe subshell 导致 JSON 缺逗号的 bug |

## 核心原则

1. **并行优先**：Step 2 四路数据源必须并行，Step 4 内容详情必须并行
2. **容错降级**：所有 curl 后加 `|| true`；微博有三级降级链；MCP 不可用时静默跳过
3. **缓存复用**：所有 API 结果先查缓存（`tools/cache.py get <key>`），命中直接复用
4. **去重合并**：同一事件跨平台报道合并为一条，附带全部来源链接
5. **比例目标**：bilibili ~40%，传统+热搜 ~60%；配图率 ≥ 60%；总量 10-15 条

## 环境注意事项

- **平台**：Windows 10 + Git Bash。bash 中路径为 `/c/Users/...`，传给原生 Windows Python 时需转为 `C:\Users\...`（用 `cygpath -w` 或 `sed 's|^/\([a-zA-Z]\)/|\1:/|' | tr '/' '\'`）
- **Python**：`C:\Users\asus\AppData\Local\Programs\Python\Python314\python.exe`（3.14.3）。PATH 上的 `python3` 是 Windows Store 重定向存根（不可用），脚本中需探测真实路径
- **`bc` 不可用**：所有 shell 算术必须用 `$(( ))`
- **npx 被安全分类器拦截**：脚本中禁止调用 npx/npm。MCP 加载由 Claude Code 启动时自行处理
- **Bilibili MCP**：`@xzxzzx/bilibili-mcp` v1.6.3，配置在 `~/.mcp.json`。提供 7 个工具：`bilibili-search`、`get_video_info`、`get_video_metadata`、`get_video_transcript`、`get_video_comments`、`download_subtitle`、`check_bilibili_credentials`。字幕和评论功能需要 Bilibili Cookie（`npx -y @xzxzzx/bilibili-mcp@latest config`）
