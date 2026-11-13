# 架构与数据流

## 一句话

AstrBot 的一个 `Star` 子类，向模型暴露七个 `llm_tool`；每个工具把参数转成一次 HTTP POST，
打到 Karin 进程里由 `karin-plugin-astrbot-bridge` 提供接口。

```
用户说话
  → AstrBot 的 LLM 决定调用 karin_xxx
  → KarinCtl.karin_xxx(event, ...)
  → _post(action, payload)
  → POST {karin_url}/api/v1/astrbot/{action}
  → bridge 在 Karin 进程内执行
  → JSON 回来 → 拼成中文文本 → 回到模型上下文
```

## 加载与自检

```python
class KarinCtl(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context, config)
        self.config = config
        self._self_check = ""
        self._bg_tasks = set()      # 后台补卡片的 create_task 引用
```

名称、作者、版本等元数据只写在 `metadata.yaml`；类继承 `Star` 后 AstrBot 会自动注册，
不再使用已废弃的 `@register` 装饰器。

`initialize()` 做两件事：

1. `_forget_install_record()`：只删掉自己目录里的 `_install_record.json`，不删插件目录、不碰其它路径。
2. `self._self_check = await self._probe()`：打一次 `POST /api/v1/astrbot/ping`（超时取 `min(timeout, 10)`），
   把结果存成一句话——`✓ 已连通` / `⚠ token 不对（401）` / `⚠ bridge 没配 token（500）` /
   `⚠ 连不上…` / `⚠ 超时`。`karin_status` 的第一行就是它，用户不用翻日志。

## 配置

来自 `_conf_schema.json`：

| 键 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `karin_url` | string | `http://127.0.0.1:7777` | Karin 的 HTTP_PORT，**不是 WebUI 端口** |
| `karin_token` | string | 空 | bridge 侧按 `HTTP_AUTH_KEY` → `ASTRBOT_BRIDGE_TOKEN` → 配置项 的顺序取 |
| `timeout` | int | `60` | 单次请求超时（秒）。`_probe` 另用 `min(timeout, 10)` |
| `enabled` | bool | `true` | 总开关 |
| `auto_share` | bool | `true` | 自动补卡片（`_auto_share_on()` 读它） |
| `prompt_hint` | bool | `true` | 按需注入格式提示 |

**每个开关都必须同时出现在 schema 里**，读取一律用 `self.config.get("x", True)`：
`AstrBotConfig` 的 `__getattr__` 对缺失键返回 `None`，`getattr(config, "x", True)`
的默认值不会生效——`auto_share` 真机踩过这个坑，现在代码已改成 `dict.get`。

## `_post`

```
async def _post(self, action: str, payload: dict) -> dict
```

- URL：`self._base`（= `karin_url.rstrip("/")`）+ `/api/v1/astrbot/` + action
- 头：`Authorization: Bearer <karin_token>`、`Content-Type: application/json`
- 每次新建 `aiohttp.ClientSession(timeout=ClientTimeout(total=timeout))`
- 失败一律 `raise RuntimeError`（中文说明）：401 / 5xx 且 body 是 JSON / 其它非 200 / `success` 为假 /
  `ClientConnectorError`（附 `_reach_hint()`）/ `TimeoutError`
- 成功返回整个 JSON（调用方读 `ok` / `reply` / `plugins` / `commands` 等字段）

**注意**：Karin 的 HTTP 端口同时承载 OneBot WebSocket。`karin_url` 指向它没错，
但别指望 `GET /` 能探活——只有 `/api/v1/*` 有意义。

## 三个钩子

| 钩子 | 做什么 | 请求 |
| --- | --- | --- |
| `_auto_share_loaded`（`on_astrbot_loaded`） | 打一行启动日志 | 无 |
| `_hint_share_format`（`on_llm_request`） | `HINT_TRIGGER` 命中时给 `req.system_prompt` 追加 `SHARE_HINT` | 无 |
| `_auto_share`（`on_decorating_result`） | 取链接 → `create_task(_deliver_share)` | 后台发 `share` |

`_auto_share` 的分支：有 `[[share:]]` 标记 → 只发那一条，并把标记替换成完整链接；
没标记 → `_all_links()` 取全部链接（去重、上限 5）；`webchat`/`console` 直接返回；
非 `is_llm_result()` 直接返回。

## 工具清单

七个工具、各自参数与返回形状见 [README 的工具表](../../README.md) 与 [AGENTS 的工具一览](../../AGENTS.md)。
只有三处值得在这里记：`karin_commands` 有分页（`hasMore` 时提示下一个 `offset`）、
`karin_call` 有五种结局（正常 / `ambiguous` 候选 / `error`+堆栈 / `blocked=hook` / `permission=denied`）、
`karin_logs` 把 `only_error` 转发成 bridge 的 `onlyError`。

## 场景判定

`_event_ids(event)` 取 `(群号, 发送者QQ)`：`get_group_id()` → 含 `GroupMessage` 时用 `get_session_id()` →
最后解析 UMO `platform:GroupMessage:789` / `platform:FriendMessage:123456`。

`_resolve_scene(event, scene, target)` 的顺序：显式 `scene`+`target` → 只给 `target` 时按当前消息判断它是群号还是 QQ 号
→ `scene=group` 用群号 → `scene=friend` 用发送者 → 缺省「群号优先，没有就发送者」。
即**卡片回到这条消息所在的会话**：群里问发群，私聊问发私聊。发到别处才显式传 `scene`+`target`。

`usecase` 缺省传空串，由 bridge 的 `inferUseCase` 按链接判断 B站 / 抖音——本插件不维护域名表，
平台白名单只有 bridge 一处（避免两边正则各写一份、慢慢漂移）。

## token 账

| 项 | 成本 | 何时产生 |
| --- | --- | --- |
| 七个工具的 schema | 约 800–1000 token | **每一轮**，无论用不用 |
| `karin_plugins` 结果 | 约 40 行 | 调用时 |
| `karin_commands` 一页 | 约 40 条 × 2 行 | 调用时 |
| `karin_call` 返回正文 | 至多 `REPLY_LIMIT`=2000 字 | 调用时，之后每轮重新计费 |
| `karin_logs` | 至多 `LOG_LIMIT`=3000 字 | 同上 |
| `SHARE_HINT` | 约 60 token | 只在 `HINT_TRIGGER` 命中的那轮 |

固定开销只能靠 `enabled=false` 或卸载插件消除——改代码绕不过去。
