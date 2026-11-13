# 不变量

改动前逐条确认。每条写明「破坏后会发生什么」和「怎么验证」。

---

## I1. 只依赖 `aiohttp` 与标准库

`requirements.txt` 只有 `aiohttp>=3.9`（AstrBot 自带，这里只是把下限写清楚）。AstrBot 加载插件时会按
`requirements.txt` 安装依赖（`star_manager.py` 的 `_install_requirements_with_precheck`），多一个依赖就多一次
安装失败或版本冲突的机会；错误发生在加载阶段，表现为「插件在面板里是灰色的」。

**验证**：`cat requirements.txt`；`grep -n '^import \|^from ' main.py` 只出现
`asyncio` / `json` / `re` / `pathlib` / `urllib.parse` / `aiohttp` / `astrbot.api`。

---

## I2. 工具 docstring 是给模型的 prompt

`@filter.llm_tool` 的函数 docstring 会被解析成 JSON Schema 与 `description` 注入每一轮请求。
模型完全靠这段文字决定「什么时候调、参数填什么」。改一句描述，调用率就可能从常用变成从不；
它**不是**注释，压成一句话也是行为变更（尤其 `text` 该填 `sample` 这类约定）。

**验证**：改完问它「看看 Karin 装了哪些插件」，看它调 `karin_plugins` 还是去瞎猜。

---

## I3. 每个工具先判 `self._enabled`

七个工具的第一句都是判 `_enabled`，为假时直接返回
「karin_ctl 已关闭（配置项 enabled=false），请先在 AstrBot 面板打开。」。
关插件的目的常常是省 token / 排障；如果工具仍然发请求，用户以为已隔离，实际 Karin 还在被打。

**验证**：面板里 `enabled=false`，随便问一句，应无任何到 Karin 的请求。

---

## I4. 所有返回文本都要 `_clip`

`_clip(text, limit)` 用于 `karin_call` 的回复体、`karin_logs` 的日志、`karin_search` 的结果。
上限由模块常量给出（`REPLY_LIMIT`=2000、`LOG_LIMIT`=3000、`COMMAND_LIMIT*60`）。

工具返回会进入上下文，并在**后续每一轮**重新计费。一次 `karin_call` 吐 20000 字，
可能让这段对话此后每轮多花几千 token，而用户看不出是哪句造成的。

**验证**：`karin_call` 一个输出长文本的指令（如帮助菜单），返回长度应接近 `REPLY_LIMIT`。

---

## I5. `deliver=True` 不打回正文

`deliver` 且 `ok` 时只返回「已执行，回复已直接发到 QQ（N 字，未回传上下文）」。
已经发到 QQ 的内容用户能看见，再塞进上下文是为同一段文字付两次钱，模型还会「复述」它。

**验证**：`karin_call(..., deliver=True)` 的返回只有一句状态，不含插件正文。

---

## I6. `_post` 必须区分四类失败

| 情形 | 提示方向 |
| --- | --- |
| HTTP 401 | token 不一致——检查 `karin_token` 与 Karin 的 `HTTP_AUTH_KEY` |
| HTTP 5xx | Karin 侧内部错误——去看 `karin_logs` |
| `ClientConnectorError` | 连不上——**容器之间不能用 127.0.0.1**（`_reach_hint` 按 `karin_url` 形状给不同方向） |
| `asyncio.TimeoutError` | 超时——调大 `timeout` |

这四种在模型看来都叫「请求失败」。不区分的话，模型会反复重试同一个错误调用，用户也拿不到下一步。

**验证**：把 `karin_url` 指向不存在的端口，返回应明确说「连不上」并提示容器网络。

---

## I7. 不轮询、不注册定时器；事件钩子只允许「零 LLM 调用的本地判断」

`main.py` 里不出现 `while True`、`initialize()` 里的后台进程、以及**任何按周期重复的** `create_task`。
一次性、由某条具体消息触发的任务（目前只有补卡片）允许存在。

三个钩子，都必须是「不跑模型、不凭空发请求」的本地动作：

1. **`_auto_share_loaded`**（`@filter.on_astrbot_loaded`）：只打一行启动日志
   （`[karin_ctl] 已加载：自动补卡片=开/关，Karin=…`），它是唯一的配置自检。
2. **`_hint_share_format`**（`@filter.on_llm_request`）：只往 `req.system_prompt` 末尾追加 `SHARE_HINT`。
   必须同时满足：先判 `_enabled` / `_auto_share_on()` / `prompt_hint`；只在 `HINT_TRIGGER` 命中当前消息时追加
   （普通闲聊不注入，否则每轮多付一份 token）；系统提示里已含 `[[share:` 就不重复追加；**不发请求、不改用户消息**。
3. **`_auto_share`**（`@filter.on_decorating_result`）：把链接交给 kkk。必须同时满足：
   - 判定靠本地正则，不发起 LLM 调用：有 `[[share:<链接>]]` 标记就只发标记那一条（**显式优先**）；
     没有标记时取 `_all_links` 的全部结果，**正文里有几条媒体链接就发几条**（去重、上限 `MAX_AUTO_LINKS`=5）。
     不挑也不猜；
   - 标记必须先被 `_strip_share_tag` 换成普通完整链接（不是删除——用户既要链接也要卡片），绝不外泄；
   - 只处理 `result.is_llm_result()` 为真的那一条回复，不回扫历史；
     `_platform_of(event)` 命中 `NO_CARD_PLATFORMS`（`webchat` / `console`）时直接返回；
   - 失败不抛异常、只写日志，不改用户已看到的正文；
   - **钩子里不许 await 网络请求**：每条链接 `asyncio.create_task(self._deliver_share(...))`，
     引用存进 `self._bg_tasks` 并 `add_done_callback(discard)`。kkk 出卡片要 10~14 秒，
     堵在 `on_decorating_result` 里会让正文发不出去，还会让卡片抢在正文前面到达。

**为什么**：这是用户最明确的约束——只在**用户主动让它查**时消耗 token 和网络请求。
一个 30 秒定时器就能让一天多出 2880 次请求，且用户完全不知情。
而 `_auto_share` 的动机相反：它省掉的是「模型多跑一轮工具调用」的上下文开销，本地一次正则约等于零成本。
区别在于**有没有额外跑模型、有没有凭空发请求**。

**验证**：`grep -n '@filter.on_\|create_task\|while True' main.py` 只应命中三个钩子与
`_auto_share` 里那一处 `create_task`（紧跟 `self._bg_tasks.add`，且不在循环里）；
`_auto_share` 内不出现 `await self._post`；`_hint_share_format` 内不出现 `_post` / `create_task`。

---

## I8. 工具数量本身是成本

新增工具前先问「能不能并进已有工具的参数里」。`@filter.llm_tool` 的 schema 是**每一轮**都注入的固定开销，
七个工具约 800–1000 token/轮，加到十个接近 1500。这对「偶尔用一下」的功能不划算。

**验证**：关掉插件前后各问一句闲聊，比较 token 用量。

---

## I9. 与 bridge 的 action 成对

`_post(action, payload)` 的 `action` 只能是
`plugins / commands / search / status / call / share / logs` 七个之一（`_probe` 另外用 `ping`）。
两边是分开发布的仓库，单边加了 action，另一边会拿到 404 或「未知 action」，而双方代码看起来都「改对了」。

**验证**：`grep -n '_post(' main.py` 的 action 参数与 bridge `route.js` 的 `dispatch` 分支一一对应。

---

## 改动检查清单

- [ ] `python -m py_compile main.py`，收工删掉 `__pycache__`
- [ ] `_conf_schema.json` 能被 `json.load(..., encoding='utf-8')` 解析
- [ ] 新增/修改工具 → 同步 README 工具表、AGENTS 工具表、bridge 的 action
- [ ] 新的返回文本一律过 `_clip`
- [ ] 模型侧行为有变 → 同步 `.agents/memory/decisions.md`
