# 可复用命令

**语法检查 + 清理**：`python -m py_compile main.py && echo OK; rm -rf __pycache__`

**配置 schema 键位**：`python -c "import json;print(sorted(json.load(open('_conf_schema.json',encoding='utf-8'))))"` —— 预期 `_note` / `auto_share` / `enabled` / `karin_token` / `karin_url` / `prompt_hint` / `timeout`。

**工具列表**：`grep -n 'name="karin_' main.py` —— 预期七条，与 README 工具表一致。

**action 清单**：`grep -oE '"[a-z]+", *\{|_post\("[a-z]+"' main.py | sort -u` —— 预期 plugins / commands / search / status / call / share / logs，加 ping。

**钩子与后台任务**：`grep -n '@filter.on_\|create_task' main.py` —— 三个 `@filter.on_`，`create_task` 只在 `_auto_share` 一处。

**常量**：`grep -nE '^[A-Z_]+ = ' main.py`

**事后自检**：`find . -maxdepth 2 \( -name '_*' -o -name '*.pyc' \) -print`（应无输出）

**打包**：`node scripts/pack.mjs` —— 产出 `dist/astrbot-plugin-karin-ctl-v0.0.1.zip` 与 `dist/astrbot-plugin-karin-ctl/` 解压副本。
