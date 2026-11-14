# 排障

## 现象速查
| 现象 | 先查哪里 |
| --- | --- |
| 面板里插件是灰的 / 加载失败 | ImportError——有没有用 aiohttp 之外的库 |
| 模型从来不调这几个工具 | 工具描述被改坏了；或 `enabled` 是 false |
| 返回「连不上 Karin」 | `karin_url` 的主机与端口；容器之间不能用 127.0.0.1 |
| 返回 401 | `karin_token` 与 Karin 的 `HTTP_AUTH_KEY`（或 `ASTRBOT_BRIDGE_TOKEN`）不一致 |
| 返回 500「还没配置 token」 | Karin 侧根本没配，去 WebUI 插件配置里填 |
| `karin_plugins` 返回空 | Karin 里确实没装插件，或 getPlugins 失败，先看 `karin_status` |
| `karin_search` 老是 0 条 | 关键词太具体；换功能词，或改用 `karin_commands` |
| `karin_call` 说「没有匹配指令」 | `text` 用了 command 而不是 `sample` |
| `karin_call` 超时 | 插件里做了慢网络请求；调大 `timeout` |
| 回复里露出 `[[share:...]]` | 标记没被剥掉——`auto_share` 关了，或这条不是 `is_llm_result()` |
| 卡片没出、正文有链接 | 平台是 `webchat`/`console`（故意跳过），或链接不是 B站/抖音，或 `karin_logs` 里 kkk 报错 |
| 卡片比正文先到 | 旧版本才会；现在解析在后台，正文先发 |
| 对话越聊越贵 | `karin_call` 拉了大段文本；改用 `deliver=True` |

## 连不上：九成是网络
AstrBot 与 Karin 常在同一台主机的**不同容器**里：容器内的 127.0.0.1 是自己不是宿主，要用宿主 IP 或 compose 服务名；`karin_url` 的端口是 Karin 的 HTTP_PORT（默认 7777），不是 WebUI 端口。验证：在 AstrBot 容器里 `curl http://<karin 主机>:7777/api/v1/ping`，这个都不通就不用往下看。

## 401：token 到底填哪个
bridge 取令牌的顺序是 `HTTP_AUTH_KEY` → `ASTRBOT_BRIDGE_TOKEN` → 插件配置项 `astrbotBridge.token`，`karin_token` 填**与 Karin 实际生效的那个一致**即可（本机部署通常就是 `HTTP_AUTH_KEY`）。401 只说明两边不一致：到 Karin WebUI 的插件配置页看 bridge 拿到的是哪个，或容器里 `echo $HTTP_AUTH_KEY` 比对。

## 工具返回对但插件没反应
插件读 `e.rawEvent` / `e.bot.sendMsg` 的拿不到数据（已知限制）；插件内部异步、return 后还在跑，回复会晚到；插件依赖的配置没配（如 kkk 的 apiKey）。

## 卡片链路排障（顺序查，每步现象确定）
1. **AstrBot 日志**有没有 `[karin_ctl] 已加载：自动补卡片=开`。没有 → 没加载；显示「关」→ `auto_share` 被关或 schema 缺键。
2. **正文里有没有 `[[`**。有 → 标记没被处理：这条不是 LLM 回复，或平台在 `NO_CARD_PLATFORMS` 里。
3. **Karin 日志**有没有 `[astrbot-bridge] action=share`。没有 → 链接没被识别（不是 B站/抖音，或 `_normalize_link` 判成无效）。
4. 有 `action=share` 但没卡片 → kkk 的问题（apiKey / puppeteer），看 `karin_logs`。
5. 卡片出现在别的会话 → 看 `_resolve_scene`：非 QQ 平台的 ID 在 Karin 侧不存在，要显式传 `scene`+`target`。

**别在 webchat 里验证卡片**：面板调试窗口被 `NO_CARD_PLATFORMS` 跳过，否则调试时贴的测试链接会把卡片发到真实 QQ。

## 截断让你看不到完整结果
`_clip` 会在末尾追加截断提示。需要完整内容时：用 `offset` 分页取 `karin_commands`；或 `karin_call(..., deliver=True)` 发到 QQ 在手机上看全文。
