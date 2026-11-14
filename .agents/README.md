# .agents

维护者视角的文档。入口是仓库根目录的 [`AGENTS.md`](../AGENTS.md)。

| 目录 | 放什么 | 文件 |
| --- | --- | --- |
| `rules/` | 不变量、作用域与清理 | [invariants.md](./rules/invariants.md) · [workspace.md](./rules/workspace.md) |
| `memory/` | 架构与数据流、决策记录 | [architecture.md](./memory/architecture.md) · [decisions.md](./memory/decisions.md) |
| `workflows/` | 多步骤流程 | [verify.md](./workflows/verify.md) |
| `commands/` | 可复用命令 | [common.md](./commands/common.md) |
| `skills/` | 可复用的操作说明 | [troubleshooting.md](./skills/troubleshooting.md) · [lieflat-less-ai-tone/](./skills/lieflat-less-ai-tone/SKILL.md)（本地，未入库） |

`skills/lieflat-less-ai-tone/` 是 [larashero3-dotcom/lieflat-less-ai-tone](https://github.com/larashero3-dotcom/lieflat-less-ai-tone) 的本地副本（2026-11-14 拉取，commit `fe77df0`），用于成稿去 AI 味检测与改写。已被 `.gitignore` 忽略、不分发；许可 **CC BY-NC 4.0（作者 shiujan，禁止商用）**，与本仓库 AGPL-3.0-only 不同，`LICENSE` 与署名不动，商用前向作者取得授权。`assets/` 大图未拷贝；Windows 下跑脚本需 `PYTHONIOENCODING=utf-8`，否则 GBK 控制台会因 `−` 等字符报 `UnicodeEncodeError`。

暂未使用：`prompts/`（本地自用，不入库）、`tools/`（无 MCP 集成）。

配对的仓库：[karin-plugin-astrbot-bridge](../../karin-plugin-astrbot-bridge/AGENTS.md)——两边的 action 与工具必须成对增删。
