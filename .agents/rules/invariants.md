# 不变量

改动前逐条确认。每条写明「破坏后会发生什么」和「怎么验证」。

## I1. 只依赖 `aiohttp` 与标准库
`requirements.txt` 只有 `aiohttp`。AstrBot 加载插件会按它装依赖（`star_manager.py` 的 `_install_requirements_with_precheck`），多一个依赖就多一次安装失败；错误发生在加载阶段，表现为「插件在面板里是灰色的」。
**验证**：`grep -n "^import \|^from " main.py` 只有 `asyncio`/`json`/`re`/`pathlib`/`urllib.parse`/`aiohttp`/`astrbot.api`。

## I2. 工具 docstring 是给模型的 prompt
`@filter.llm_tool` 的 docstring 被解析成 JSON Schema 与 description 注入每一轮请求，模型完全靠它决定「什么时候调、参数填什么」。改一句就可能从常用变成从不，**压成一句话也是行为变更**。
**验证**：改完问它「看看 Karin 装了哪些插件」，看它调 `karin_plugins` 还是瞎猜。

## I3. 每个工具先判 `self._enabled`
七个工具第一句都是判 `_enabled`，为假直接返回提示。关插件的目的常是省 token / 排障；工具仍发请求会让用户以为已隔离。

## I4. 所有返回文本都要 `_clip`
`_clip(text, limit)` 用于 `karin_call` 的回复体、`karin_logs` 的日志、`karin_search` 的结果。上限由模块常量给出（`REPLY_LIMIT`=2000、`LOG_LIMIT`=3000、`COMMAND_LIMIT*60`）。工具返回会进上下文并在**后续每一轮**重新计费。
**验证**：`karin_call` 一个长输出指令（如帮助菜单），返回长度应接近 `REPLY_LIMIT`。

## I5. `deliver=True` 不打回正文
已发到 QQ 的内容再塞进上下文是为同一段文字付两次钱，模型还会复述它。**验证**：`karin_call(..., deliver=True)` 只回一句状态。

## I6. `_post` 必须区分四类失败
| 情形 | 提示方向 |
| --- | --- |
| HTTP 401 | token 不一致——检查 `karin_token` 与 Karin 的 `HTTP_AUTH_KEY` |
| HTTP 5xx | Karin 侧内部错误——看 `karin_logs` |
| `ClientConnectorError` | 连不上——**容器之间不能用 127.0.0.1**（`_reach_hint` 按 `karin_url` 形状给方向） |
| `asyncio.TimeoutError` | 超时——调大 `timeout` |

这四种在模型看来都叫「请求失败」，不区分它就会反复重试同一个错误调用。

## I7. 不轮询、不注册定时器；钩子只做「零 LLM 调用的本地判断」
`main.py` 里不出现 `while True`、`initialize()` 里的后台进程、以及任何按周期重复的 `create_task`。三个钩子：
1. **`_auto_share_loaded`**（`on_astrbot_loaded`）：只打一行 `[karin_ctl] 已加载：自动补卡片=开/关，Karin=…`，是唯一的配置自检。
2. **`_hint_share_format`**（`on_llm_request`）：只往 `req.system_prompt` 追加 `SHARE_HINT`。先判 `_enabled` / `_auto_share_on()` / `prompt_hint`；只在该消息命中 `HINT_TRIGGER` 时追加；已含 `[[share:` 不重复；**不发请求、不改用户消息**。
3. **`_auto_share`**（`on_decorating_result`）：判定靠本地正则——有标记只发标记那一条（**显式优先**），没标记发 `_all_links` 的全部（去重、上限 `MAX_AUTO_LINKS`=5）；标记先经 `_strip_share_tag` 换成完整链接、绝不外泄；只处理 `result.is_llm_result()`；`_platform_of(event)` 命中 `NO_CARD_PLATFORMS`（`webchat`/`console`）直接返回；失败只写日志。**钩子里不许 await 网络请求**：每条链接 `create_task(self._deliver_share(...))`，引用存进 `self._bg_tasks` 并 `add_done_callback(discard)`。
**为什么**：用户最明确的约束是只在主动让它查时消耗 token 和网络请求——一个 30 秒定时器一天就多 2880 次请求。而 `_auto_share` 省掉的是「模型多跑一轮工具调用」，本地一次正则约等于零成本；区别在于**有没有额外跑模型、有没有凭空发请求**。
**验证**：`grep -n "@filter.on_\|create_task\|while True" main.py` 只命中三个钩子与 `_auto_share` 里紧跟 `_bg_tasks.add` 的那一处；`_auto_share` 内不出现 `await self._post`。

## I8. 工具数量本身是成本
新增工具前先问「能不能并进已有参数」。schema 每轮都注入，七个工具约 800–1000 token/轮，加到十个接近 1500。

## I9. 与 bridge 的 action 成对
`_post(action, payload)` 的 action 只能是 `plugins / commands / search / status / call / share / logs`（`_probe` 另用 `ping`）。单边加了 action，另一边只会拿到 404 或「未知 action」，而双方代码看起来都「改对了」。
**验证**：`grep -n "_post(" main.py` 的 action 与 bridge `route.js` 的 `dispatch` 分支一一对应。

## 改动检查清单
- [ ] `python -m py_compile main.py`，收工删掉 `__pycache__`
- [ ] `_conf_schema.json` 能被 `json.load(..., encoding="utf-8")` 解析
- [ ] 新增/修改工具 → 同步 README 与 AGENTS 的工具表、bridge 的 action
- [ ] 新的返回文本一律过 `_clip`
- [ ] 模型侧行为有变 → 同步 `.agents/memory/decisions.md`
