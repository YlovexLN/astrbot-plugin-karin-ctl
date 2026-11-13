# AGENTS.md

面向 AI 编码助手与新维护者。**改代码前先读 [`.agents/rules/invariants.md`](./.agents/rules/invariants.md)。**

## 是什么

AstrBot 侧的一个插件：给 LLM 注册七个调用工具，让它能**看见并驱动** Karin。

AstrBot 自己不认识 Karin 的插件。这个插件只做一件事：把 `karin_*` 工具调用翻译成
Karin 侧 `/api/v1/astrbot/<action>` 的 HTTP 请求。真正的逻辑在姊妹仓库
[`karin-plugin-astrbot-bridge`](../karin-plugin-astrbot-bridge/) 里。

**两边是一对**：这里新增一个工具，那边必须新增一个 action，反之亦然。

## 目录

| 路径 | 作用 |
| --- | --- |
| `main.py` | 全部代码（约 700 行）：`KarinCtl(Star)`、`_probe`/`_post`、七个 `@filter.llm_tool`、三个事件钩子、链接工具函数（`_all_links` / `_normalize_link` / `_strip_share_tag` / `_platform_of` / `_event_ids` / `_resolve_scene`）、`_clip` |
| `_conf_schema.json` | 面板配置项：`enabled` / `karin_url` / `karin_token` / `timeout` / `auto_share` / `prompt_hint` |
| `metadata.yaml` | 插件元数据（版本 `0.0.1`）：市场与更新只认它；改版本时同步 `pack.mjs` 的 `ZIP_NAME` 和 README/INSTALL 里的包名 |
| `requirements.txt` | 只有 `aiohttp` |
| `README.md` / `INSTALL.md` | 面向使用者的用法与安装说明 |
| `scripts/pack.mjs` | 本地打包（Node 标准库，不进插件包），产出 `dist/*.zip` 与解压副本 |
| `dist/` | 打包产物，已被 `.gitignore` 忽略 |
| `.agents/` | `rules/` 约束 · `memory/` 背景与决策 · `workflows/` 流程 · `skills/` 排障与说话方式 · `commands/` 命令 |

## 硬约束

1. **不新增第三方依赖**——只用 `aiohttp`（AstrBot 自带）与标准库。AstrBot 加载插件会按 `requirements.txt` 装依赖（`star_manager.py` 的 `_install_requirements_with_precheck`），多一个依赖就多一次安装失败/版本冲突的机会，而失败会表现为「插件在面板里是灰色的」。
2. **工具 docstring 是给模型看的 prompt**，不是注释。改描述等于改行为。
3. **每个工具先判 `self._enabled`**，关掉时返回一句话就退出，不能悄悄不打请求。
4. **返回给模型的文本都要 `_clip`**——进上下文的东西按 token 反复计费。
5. **`deliver=True` 时正文不回传**，只回「已发送」。
6. **`_post` 必须区分 401 / 5xx / 连接失败 / 超时**，错误信息要指向具体排查动作。
7. **不轮询、不注册定时器**。事件钩子只有三个，都是零 LLM 调用的本地动作：
   `on_astrbot_loaded` 打一行启动日志、`on_llm_request` 按需补一句格式提示、
   `on_decorating_result` 扫链接并交给后台任务。
   **钩子里不许 await 网络请求**，必须 `create_task` 到 `_deliver_share` 并持有引用（`self._bg_tasks`）。
8. **不改宿主环境**：不 `pip install`、不动 AstrBot 源码、不写 `data/` 以外的路径。
9. **不自行提交、不改版本号、不部署。**

细节：1–6 与 7 的完整条款见 [`rules/invariants.md`](./.agents/rules/invariants.md)，
8–9 与清理规则见 [`rules/workspace.md`](./.agents/rules/workspace.md)。

## 工具一览

| 工具 | Karin action | 参数 | 用途 |
| --- | --- | --- | --- |
| `karin_plugins` | `plugins` | `force` | 已装插件清单 + 在线 Bot |
| `karin_commands` | `commands` | `plugin` `keyword` `offset` `limit` | 按插件名取指令，带 `sample` 与分页 |
| `karin_search` | `search` | `keyword` `limit` | 不知道插件名时模糊检索 |
| `karin_status` | `status` | — | 连通自检、在线 Bot、主人、前缀 |
| `karin_call` | `call` | `plugin` `method` `text` `deliver` | 执行一条指令，可 `deliver` 直发 QQ |
| `karin_share` | `share` | `url` `usecase` `scene` `target` | 手动交给 kkk，卡片发到当前会话 |
| `karin_logs` | `logs` | `lines` `only_error` | 运行时错误与日志尾部 |

另外 `_probe` 用的是第八个 action `ping`（不是工具，启动自检和 `karin_status` 第一行用它）。

`karin_share` 的 docstring 里写着「一般不用它，写 `[[share:]]` 就行」——这是刻意的：
模型主动调它要多跑一整轮，而标记只多写一行文字。

## 影响面

| 改动 | 风险 |
| --- | --- |
| README、注释 | 无 |
| `_clip` 上限 | 低：只影响上下文长度 |
| 工具 docstring | **中**：模型按新描述调用，可能不再用它 |
| `SHARE_HINT` / `HINT_TRIGGER` | **中**：改这句等于改模型发视频的习惯，命中即付 token |
| `NO_CARD_PLATFORMS` / `_all_links` / `MAX_AUTO_LINKS` | **中**：放宽会误发卡片，收紧等于回到「没装 skill 就没卡片」 |
| 工具数量 | **中**：固定开销随工具数线性增长 |
| `_post` 的鉴权头、URL 拼接 | **高**：全线 401 或 404 |

## 改完必跑

```bash
python -m py_compile main.py && rm -rf __pycache__
python -c "import json;json.load(open('_conf_schema.json',encoding='utf-8'))"
python -c "import yaml;yaml.safe_load(open('metadata.yaml',encoding='utf-8'))"
```

Windows 上读文件必须显式 `encoding='utf-8'`，否则 GBK 解码会炸。完整流程见
[`.agents/workflows/verify.md`](./.agents/workflows/verify.md)。

## 别踩的坑

- **不要用 `@register`**：该装饰器自 AstrBot v3.5.19 起已废弃（进程首次调用会发 `DeprecationWarning`）。插件类只要继承 `Star` 就会被自动识别，名称/作者/版本以 `metadata.yaml` 为准。
- **配置项开关必须同时写进 `_conf_schema.json`**，读取用 `self.config.get("x", True)`：`AstrBotConfig` 的 `__getattr__` 对缺失键返回 `None`，`getattr(config, "x", True)` 的默认值不会生效——`auto_share` 真机静默变成 `None`。
- **标记是「替换」不是「删除」**：剥掉 `[[share:...]]` 时要把完整链接留在原处，否则用户只剩一段没有链接的正文。
- **解析必须后台跑**：kkk 出卡片 10~14 秒，堵在 `on_decorating_result` 里正文发不出去，卡片还会抢在前面到。
- **去重靠区间覆盖**：`_all_links` 要先用链接区间盖掉 BV/av 命中，否则一条链接数成两条、补两张一样的图。
- **调试窗口别补卡片**：`webchat`/`console` 必须跳过，否则面板里贴的测试链接会把卡片发到真实 QQ。
- 更多踩坑记录与取舍见 [`.agents/memory/decisions.md`](./.agents/memory/decisions.md)。
