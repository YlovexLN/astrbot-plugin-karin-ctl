# 验证流程

按顺序做。任一步不符合预期就停下，先查 [`skills/troubleshooting.md`](../skills/troubleshooting.md)。命令速查见 [`commands/common.md`](../commands/common.md)。

## 1. 语法与配置
```bash
python -m py_compile main.py && rm -rf __pycache__
python -c "import json;print(sorted(json.load(open('_conf_schema.json',encoding='utf-8'))))"
python -c "import yaml;print(yaml.safe_load(open('metadata.yaml',encoding='utf-8'))['version'])"
```
**预期**：编译无输出；七个键（`_note` + 六个配置项）；版本 `0.0.1`（不带 `v`）。**Windows 上必须带 `encoding="utf-8"`**，否则 GBK 解码报 `UnicodeDecodeError`。

## 2. 工具、action 与钩子
```bash
grep -c 'llm_tool' main.py           # 7
grep -n '_post(' main.py              # 只有 plugins/commands/search/status/call/share/logs
grep -n '@filter.on_\|create_task\|while True' main.py
grep -c '_enabled' main.py          # >= 8（1 处定义 + 每个工具 1 处）
```
**预期**：七个 llm_tool；action 与 bridge 的 `dispatch` 分支一致（`_probe` 另用 `ping`）；三个 `@filter.on_`，`create_task` 只在 `_auto_share` 里一处且紧跟 `self._bg_tasks.add`，`while True` 无输出；任何钩子里出现 `await self._post` 都算违反 I7。

## 3. 截断覆盖
```bash
grep -n '_clip(' main.py; grep -nE '^[A-Z_]+LIMIT' main.py
```
**预期**：`karin_call` / `karin_logs` / `karin_search` 的返回都过 `_clip`；常量有 `REPLY_LIMIT` / `PLUGIN_LIMIT` / `COMMAND_LIMIT` / `LOG_LIMIT`。

## 4. 真实环境冒烟（需用户执行）
面板确认 `karin_url` 指向 Karin 主机的 7777（**不是 WebUI 端口**；跨容器时 127.0.0.1 一定不通），`karin_token` 与 `HTTP_AUTH_KEY` 一致，然后问「看看 Karin 装了哪些插件」。**预期**：模型调 `karin_plugins` 并列出插件名。再做一次端到端：「用 Karin 查一下转发状态」——模型应走 `karin_search`/`karin_commands` 拿到 `sample` 后 `karin_call`，最后总结给用户。

## 5. 卡片链路（真机）
发一条 B站链接给 AstrBot，**不要**要求它调工具。**预期**：正文里是可点链接，10~14 秒后同会话出现卡片，Karin 日志有 `[astrbot-bridge] action=share`。正文出现 `[[` 说明标记没被剥掉；卡片没出先看 `karin_logs`。

## 6. 收尾
```bash
find . -maxdepth 2 \( -name '_*' -o -name '*.pyc' -o -name '*.tmp' \) -print
```
**预期**：无输出。
