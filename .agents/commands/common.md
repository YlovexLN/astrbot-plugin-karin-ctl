# 可复用命令

## 语法检查 + 清理

```bash
python -m py_compile main.py && echo OK; rm -rf __pycache__
```

## 配置 schema 键位

```bash
python -c "import json;print(sorted(json.load(open('_conf_schema.json',encoding='utf-8'))))"
```

**预期**：`_note` / `auto_share` / `enabled` / `karin_token` / `karin_url` / `prompt_hint` / `timeout`。

## 工具列表

```bash
grep -n 'name="karin_' main.py
```

**预期**：七条，名字与 README 的工具表一致。

## action 清单

```bash
grep -oE '"[a-z]+", *\{|_post\("[a-z]+"' main.py | sort -u
```

**预期**：plugins / commands / search / status / call / share / logs（工具用），加 ping（`_probe` 用）。

## 钩子与后台任务

```bash
grep -n '@filter.on_\|create_task' main.py
```

**预期**：三个 `@filter.on_`（`on_astrbot_loaded` / `on_llm_request` / `on_decorating_result`），
`create_task` 只在 `_auto_share` 里一处，紧跟 `self._bg_tasks.add`。

## 常量一览

```bash
grep -nE '^[A-Z_]+ = ' main.py
```

## 事后自检

```bash
ls -d __pycache__ 2>/dev/null; find . -maxdepth 2 \( -name '_*' -o -name '*.pyc' \) -print
```

## 打包

```bash
node scripts/pack.mjs
# 产物：dist/astrbot-plugin-karin-ctl-v0.0.1.zip + dist/astrbot-plugin-karin-ctl/（解压副本）
```
