# 架构与数据流

一个 `Star` 子类，向模型暴露七个 `llm_tool`；每个工具把参数转成一次 HTTP POST，打到 Karin 进程里由 `karin-plugin-astrbot-bridge` 执行：

```
用户说话 → LLM 决定调 karin_xxx → KarinCtl.karin_xxx(event, ...) → _post(action, payload)
  → POST {karin_url}/api/v1/astrbot/{action} → bridge 在 Karin 进程内执行 → JSON → 中文文本 → 上下文
```

## 加载与自检

`__init__` 存好 `config`、`_self_check = ""`、`_bg_tasks = set()`（后台补卡片的 create_task 引用）。名称/作者/版本只写在 `metadata.yaml`；继承 `Star` 即自动注册，不用已废弃的 `@register`。

`initialize()` 做两件事：`_forget_install_record()` 只删自己目录里的 `_install_record.json`；`_self_check = await self._probe()` 打一次 `POST /api/v1/astrbot/ping`（超时 `min(timeout, 10)`），结果存成一句话（`✓ 已连通` / `⚠ token 不对（401）` / `⚠ bridge 没配 token（500）` / `⚠ 连不上…` / `⚠ 超时`），`karin_status` 的第一行就是它。

## `_post`

`async def _post(self, action: str, payload: dict) -> dict`：URL = `karin_url.rstrip("/")` + `/api/v1/astrbot/` + action；头 `Authorization: Bearer <karin_token>`；每次新建 `aiohttp.ClientSession(timeout=ClientTimeout(total=timeout))`；失败一律 `RuntimeError`（中文说明，按 I6 分四类）；成功返回整个 JSON。

Karin 的 HTTP 端口同时承载 OneBot WebSocket，`karin_url` 指向它没错，但别指望 `GET /` 能探活——只有 `/api/v1/*` 有意义。

## 工具与场景

七个工具的参数与返回形状见 [README](../../README.md) 与 [AGENTS](../../AGENTS.md)。这里只记三处：`karin_commands` 有分页（`hasMore` 时提示下一个 `offset`）；`karin_call` 有五种结局（正常 / `ambiguous` 候选 / `error`+堆栈 / `blocked=hook` / `permission=denied`）；`karin_logs` 把 `only_error` 转发成 bridge 的 `onlyError`。

`_event_ids(event)` 取 `(群号, 发送者QQ)`：`get_group_id()` → 含 `GroupMessage` 时用 `get_session_id()` → 解析 UMO `platform:GroupMessage:789` / `platform:FriendMessage:123456`。`_resolve_scene` 的顺序见 AGENTS 与 ADR-9。

`usecase` 缺省传空串，由 bridge 的 `inferUseCase` 判断 B站 / 抖音——平台白名单只有 bridge 一处，避免两边正则各写一份慢慢漂移。
