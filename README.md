# 快手大肥鱼 · DeepSeek 评论区自动回复机器人

> 参考抖音侧成熟方案（`douyin-comment-reply`、`auto-douyin-bot`、`Tik-Tok-Web-fully-automatic-reply` 等）的原理，为快手实现的评论区 AI 互动机器人：定时抓取作品评论，用 DeepSeek 生成带人设的回复，自动发送楼中楼回复（文字 + emoji，可选图片表情包）。

## 背景与调研结论

调研结论（详见下方"设计原理"）：

1. **快手官方开放平台没有评论相关 API**（`open.kuaishou.com` 服务端 SDK 仅覆盖 OAuth、用户信息、视频发布、直播；评论只以 `commentCount` 统计字段出现）。**结论：无法通过官方 API 发送评论/回复/私信**，唯一可行路径是浏览器自动化。
2. 快手**创作者中心**的评论管理页可以集中查看、回复所有作品评论（管理更高效），但**后台不支持图片表情包回复**；作品前台评论区同时支持文字与图片评论。本项目以**作品前台评论区**为主源，并把创作者中心做成可选扩展点。

## 设计原理

```
┌─────────────────────────────────────────────────────────┐
│                    主循环 (Watcher)                       │
│  ┌─────────┐   ┌──────────┐   ┌─────────┐   ┌─────────┐ │
│  │ 评论抓取 │──▶│ 去重入库   │──▶│ AI 生成  │──▶│ 楼中楼发送 │ │
│  │ Playwright│   │ SQLite   │   │ DeepSeek│   │ Playwright│ │
│  └─────────┘   └──────────┘   └─────────┘   └─────────┘ │
│       ▲                                   │              │
│       └─────────── 反检测（随机延迟/人化输入）───────────┘  │
└─────────────────────────────────────────────────────────┘
```

| 模块 | 技术 | 职责 |
|------|------|------|
| `app/browser/` | Playwright（持久化 user_data_dir） | 登录态复用、评论抓取、楼中楼回复、表情包 |
| `app/ai/` | DeepSeek API（OpenAI 兼容协议） | 生成回复；人设系统；剥离 R1 思考标记 |
| `app/db/` | 标准库 sqlite3 | 评论去重、回复状态、频率统计 |
| `app/scheduler/` | 自研主循环 | 轮询、频率限制（每小时/每日）、作品驱动 |
| `app/utils/` | — | 日志、人类行为模拟（逐字输入、随机延迟） |

### 关键技术点（吸取抖音方案的教训）

- **回复输入框定位**：快手/抖音的回复输入框可能出现在评论容器**之外**，不能只在评论项内查找，需全页定位 `contenteditable`；多个输入框时取页面最底部那个。
- **发送按钮区分**：页面常有多个"发送"按钮（顶部发新评论 vs 评论内回复），按"从后往前找第一个可见按钮"的策略选择，避免发错位置。
- **登录态持久化**：`launch_persistent_context` 复用 `data/chrome-profile`，登录一次长期有效；启动时通过快手域 Cookie 标记（`userId`/`passToken` 等）判断登录态。
- **去重**：`photo_id + comment_id` 唯一键；拿不到 DOM ID 时用 `用户名|文本` 的 md5 兜底。
- **频率控制**：相邻回复随机间隔 + 每小时/每日上限，均在 `config.yaml` 可调。

## 快速开始

### 1. 安装

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### 2. 配置

编辑 `config.yaml`：

```yaml
deepseek:
  api_key: "sk-你的DeepSeekKey"      # https://platform.deepseek.com 获取

creator:
  photo_urls:
    - "https://www.kuaishou.com/short-video/你的作品ID"   # 填写你的快手作品页地址
```

> `creator_center_url`（创作者中心评论管理页）为可选扩展：填了后需按下方"DOM 校准指南"适配该页选择器。

### 3. 登录快手（一次性）

```bash
python -m app.main --login
```

会弹出浏览器，手动扫码/账号登录快手；登录态自动保存，之后无需重复登录。

### 4. 运行

```bash
python -m app.main --check      # 体检：配置、登录态、入库统计
python -m app.main --once       # 试运行一轮（抓取+回复）
python -m app.main              # 持续运行（Ctrl+C 停止）
```

### 5. 表情包

把本地表情包图片放到 `data/stickers/`（默认 `data/stickers/logo.png`），
发送时会先尝试附加图片再发送；页面无上传框或失败时自动降级为纯文字。
不想用图片就把 `bot.sticker` 设为 `false`。

## 配置说明（config.yaml）

| 段 | 键 | 说明 |
|----|----|------|
| `deepseek` | `api_key` / `model` / `temperature` | DeepSeek 参数；`model` 可换 `deepseek-reasoner`（R1） |
| `browser` | `headless` / `user_data_dir` / `slow_mo` | 首次登录须 `headless: false`；`slow_mo` 越大越像真人 |
| `creator` | `photo_urls` / `creator_center_url` / `max_scrolls` | 评论源与滚动深度 |
| `bot` | `persona` | `ks_bro`（老铁）/`warm`/`professional`/`funny` |
| `bot` | `auto_reply` / `poll_interval_seconds` | 发送开关与轮询频率 |
| `bot` | `reply_interval_min/max` / `max_replies_per_hour/day` | 频率限制 |
| `bot` | `filter_keywords` / `trigger_keywords` | 过滤不回复 / 只回复命中关键词 |
| `bot` | `emoji` / `sticker` / `sticker_path` | 表情能力开关 |
| `selectors` | 评论项/用户名/文本/回复按钮/输入框/发送/加载更多/上传框 | DOM 选择器，快手改版后在此校准 |
| `db` | `path` | SQLite 位置（默认 `data/bot.db`） |

## DOM 校准指南（重要）

快手前端会不定期改版，默认选择器可能失效。此时**无需改代码**，只调 `config.yaml` 的 `selectors`：

1. 打开你的快手作品页，F12 打开开发者工具，选中一条评论节点。
2. 从上往下确认：
   - 评论容器统一的选择器 → `selectors.comment_item`
   - 昵称节点 → `selectors.comment_user`
   - 评论文本节点 → `selectors.comment_text`
3. 注意两个高频坑（抖音项目踩过、快手同理）：
   - **回复输入框在评论容器外**：`input_box` 保持全页级选择器（`div[contenteditable=true], textarea`），不要限定在评论项内部。
   - **多个发送按钮**：本实现已按"从后往前找可见按钮"处理，无需配置。
4. 改完用 `--once` 验证；失败时框架会在 `data/screenshots/` 留下截图（`notfound.png` / `no_input_box.png` / `send_failed.png`），按截图调整选择器。

> 若使用创作者中心（`creator_center_url`）作为数据源，`/fetch` 前建议先开该页确认其列表 DOM，并把 `comment_item` 等选择器按该页调整。

## 项目结构

```
app/
├── main.py                  # CLI：--login / --check / --once / 持续运行
├── config.py                # YAML 配置加载与路径解析
├── browser/
│   ├── browser.py           # Playwright 持久化上下文 + 登录态检测
│   ├── fetcher.py           # 作品页评论抓取（滚动/加载更多 + 数项提取）
│   └── sender.py            # 楼中楼回复 + 表情包 + 发送验证
├── ai/
│   ├── engine.py            # DeepSeek API 封装（剥离思考标记）
│   ├── persona.py           # 人设定义
│   └── prompts.py           # system/user prompt 构建
├── db/
│   ├── models.py            # 表结构
│   └── store.py             # 去重入库/查询/状态标记/统计
├── scheduler/watcher.py     # 主循环 + 频率限制
└── utils/
    ├── humanize.py          # 随机延迟/逐字人化输入
    └── logger.py            # 滚动日志
```

## 合规与风险提示

- 本项目用于**管理你自己作品下的评论区**，请遵守快手社区规范与相关法律法规，控制发送频率，勿用于刷量、营销骚扰或任何违规行为。
- 自动化操作存在账号风控风险，请谨慎使用，并自行承担后果。

## 后续迭代方向

- [ ] 创作者中心评论管理页适配（集中式数据源）
- [ ] 楼中楼"回复楼内指定评论"的多轮上下文记忆
- [ ] 评论评论区关键词驱动（自动追评自己的回复）
- [ ] 简单 Web 管理面板（评论列表 + 手动审核后由机器人代发）
- [ ] 多账号轮换
