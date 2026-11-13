# 验证流程

按顺序做。任一步不符合预期就停下，先查 [`skills/troubleshooting.md`](../skills/troubleshooting.md)。

## 1. 语法与导入

```bash
python -m py_compile main.py && echo OK
```

**预期**：打印 OK，随后删掉 `__pycache__`。

## 2. 配置文件可解析

```bash
python -c "import json;print(sorted(json.load(open('_conf_schema.json',encoding='utf-8'))))"
python -c "import yaml;print(yaml.safe_load(open('metadata.yaml',encoding='utf-8'))['version'])"
```

**预期**：七个键（`_note` 加六个配置项），版本 `0.0.1`（不带 `v` 前缀）。
**Windows 上必须带 `encoding='utf-8'`**，否则 GBK 解码报 `UnicodeDecodeError`。

## 3. 工具与 action 的一致性

```bash
grep -n 'llm_tool' main.py
grep -n '_post(' main.py
```

**预期**：七个 llm_tool；`_post` 的 action 只出现
plugins / commands / search / status / call / share / logs，与 bridge 的 `dispatch` 分支一致；
`_probe` 另外用了 `ping`。

## 4. 钩子与后台任务

```bash
grep -n '@filter.on_\|create_task\|while True' main.py
```

**预期**：三个 `@filter.on_`（`on_astrbot_loaded` / `on_llm_request` / `on_decorating_result`）；
`create_task` 只出现一处且在 `_auto_share` 里，紧跟 `self._bg_tasks.add`；
`while True` 无输出。任何钩子里出现 `await self._post` 都算违反 I7。

## 5. 截断覆盖

```bash
grep -n '_clip(' main.py
grep -nE '^[A-Z_]+LIMIT' main.py
```

**预期**：`karin_call` / `karin_logs` / `karin_search` 的返回都经过 `_clip`；
常量有 `REPLY_LIMIT` / `PLUGIN_LIMIT` / `COMMAND_LIMIT` / `LOG_LIMIT`。

## 6. enabled 闸门数量

```bash
grep -c '_enabled' main.py
```

**预期**：>= 8（1 处定义 + 每个工具 1 处）。

## 7. 真实环境冒烟（需用户执行）

1. AstrBot 面板确认 `karin_url` 指向 Karin 主机的 7777（**不是 WebUI 端口**；两者在不同容器时 127.0.0.1 一定不通）。
2. `karin_token` 与 Karin 的 `HTTP_AUTH_KEY`（或 `ASTRBOT_BRIDGE_TOKEN`）一致。
3. 在对话里说「看看 Karin 装了哪些插件」。

**预期**：模型调用 `karin_plugins` 并列出插件名。

## 8. 端到端

「用 Karin 查一下转发状态」或「帮我用 karin 发个抽卡」——

**预期**：模型先走 `karin_search` 或 `karin_commands`，拿到 `sample` 后 `karin_call`，最后把插件回复总结给用户。

## 9. 卡片链路（真机）

发一条 B站链接给 AstrBot，**不要**要求它调工具。

**预期**：正文里是可点链接，10~14 秒后同会话出现卡片；Karin 日志有 `[astrbot-bridge] action=share`。
正文里出现 `[[` 说明标记没被剥掉；卡片没出先看 `karin_logs`。

## 10. 收尾

```bash
rm -rf __pycache__
find . -maxdepth 2 \( -name '_*' -o -name '*.pyc' -o -name '*.tmp' \) -print
```

**预期**：无输出。
