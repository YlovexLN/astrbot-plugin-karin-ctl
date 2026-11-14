![astrbot-plugin-karin-ctl](https://socialify.git.ci/YlovexLN/astrbot-plugin-karin-ctl/image?language=1&owner=1&name=1&theme=Light)

让 AstrBot 的 Agent 看见并调用 Karin 的插件。

[![version](https://img.shields.io/badge/version-0.0.1-blue.svg?style=flat-square)](./metadata.yaml) [![license](https://img.shields.io/badge/license-AGPL--3.0-blue.svg?style=flat-square)](./LICENSE) [![python](https://img.shields.io/badge/python-3.10%2B-3776AB.svg?style=flat-square)](https://www.python.org)

配套 Karin 侧插件 **karin-plugin-astrbot-bridge**（提供 `/api/v1/astrbot/*`），**两个必须一起装**。

## 安装

1. AstrBot 面板 → 插件管理 → 安装插件，填仓库地址 `https://github.com/YlovexLN/astrbot-plugin-karin-ctl`（仓库根目录就是插件根目录），装完目录名是 `astrbot_plugin_karin_ctl`；也可上传本地打好的 `dist/astrbot-plugin-karin-ctl-v0.0.1.zip`。
2. 插件配置里填两项：`karin_url`（Karin 的 `HTTP_PORT`，含端口）与 `karin_token`（与 Karin 侧一致）。
3. 重启 AstrBot，日志里应出现 `[karin_ctl] 已加载：自动补卡片=开，Karin=http://...`。
4. 对 AstrBot 说「用 karin_status 看看 Karin」——第一行就是连通自检。

手动安装：把仓库文件拷进 `data/plugins/astrbot_plugin_karin_ctl/`（目录名必须与 `metadata.yaml` 的 `name` 一致）后重启。更多细节见 [INSTALL.md](./INSTALL.md)。

## 配置项

| 配置项 | 默认 | 说明 |
| --- | --- | --- |
| `karin_url` | `http://127.0.0.1:7777` | Karin 的 `HTTP_PORT`（OneBot 与 HTTP 共用），**不是 WebUI 端口**；容器之间不能用 `127.0.0.1` |
| `karin_token` | 空 | 与 Karin 的 `HTTP_AUTH_KEY`（或 `ASTRBOT_BRIDGE_TOKEN`）一致，bridge 按这个顺序取 |
| `timeout` | 60 | 请求超时秒数。kkk 出卡片要 10~14 秒；自动补卡片走后台，不受它限制 |
| `enabled` | true | 总开关。关掉后七个工具立即返回提示，不再打 Karin |
| `auto_share` | true | 自动补卡片。有 `[[share:<链接>]]` 标记就发那一条，没标记时正文里每条链接都补一张；关掉后链接原样留在正文 |
| `prompt_hint` | true | 格式兜底。消息像是在要视频时往系统提示补一句写标记的说明，普通闲聊不注入 |

## 工具

| 工具 | 作用 |
| --- | --- |
| `karin_search` | **记不住插件名时用这个**：关键词模糊检索指令，返回里带可直接用的 `sample` |
| `karin_plugins` | 已装插件 + 在线 Bot |
| `karin_commands` | 已知插件名时列它的全部指令（方法名、权限、示例文本），支持分页 |
| `karin_call` | 直接调用插件函数，返回插件回复文本；`deliver=true` 时真发到 QQ |
| `karin_share` | 手动把 B站/抖音链接交给 kkk。**一般不用它**——回复里写 `[[share:<链接>]]` 就会自动出卡片 |
| `karin_logs` | Karin 的运行时错误与日志尾部 |
| `karin_status` | 连通自检 + 在线 Bot / 主人 / 前缀 |

三条典型链路：`karin_search("转发")` → 拿 `sample` → `karin_call(text=sample)`；或 `karin_plugins` → `karin_commands(plugin)` → `karin_call(plugin, method, text)`。`karin_call` 只给 `text` 也能调——它按正则匹配，没带前缀时自动补 alias 重试，所以模型不必记方法名。

## 卡片是怎么出来的

想要 QQ 里出现视频卡片，**不用调工具**，在回复正文最后另起一行写：

```
[[share:https://www.bilibili.com/video/BV1P24y1b7Gx]]
```

插件会读走这一行交给 kkk，并**把标记换成普通完整链接**再发出去——用户看到可点链接 + 随后到达的卡片，`[[...]]` 不外泄。标记里可以写完整链接（`bilibili.com`、`b23.tv`、`bili2233.cn`、`douyin.com`、`iesdouyin.com`），也可以只写 BV 号 / av 号。卡片发到**当前这个会话**：群里问发那个群，私聊问发回这个私聊。

**模型不写标记也照样出卡片**，发出去之前有一道本地判断：有标记 → 只发标记那一条（显式优先）；没标记 → 正文里 N 条媒体链接都发，各补一张卡（去重，最多 5 条）。去重是必须的：链接本身含 BV 号，不处理会数成两条、补两张一样的图。解析在**后台**跑，正文立刻发出，卡片 10~14 秒后自己到；失败只写日志，不往正文塞错误信息。`webchat` / `console`（面板调试窗口）一律跳过，否则调试时贴的测试链接会把卡片发到真实 QQ。

### 没装 skill 也能出卡片

`fixed-reply-format` 那类 skill 规定了「观后两三句 + 链接单独一条纯 URL + 再 `karin_share`」，但 skill 是用户自己装的，换台机器就可能没有。插件用两层兜底：`prompt_hint` 在消息像是要视频时（`HINT_TRIGGER`）往系统提示补一句格式说明；`auto_share` 保证模型不听话时也照样出卡片。skill 存在时两处说法一致，有标记时只发标记那一条，不会出两张卡。

## token 账

- **不会被自动触发**：没有轮询、没有定时任务。到 Karin 的请求只来自这一轮的工具调用，或那一条标记/链接。
- **固定开销**：七个工具的名称与描述注入每轮请求的 tools 数组，约 800–1000 token/轮，与是否调用无关。想归零就把 `enabled` 设为 false 或禁用插件。
- **变量开销已封顶**：插件回复 2000 字、插件列表 40 条、指令列表 40 条×60 字、检索 10 条（上限 50）、日志 3000 字，超出附截断提示。
- **长输出不进上下文**：`karin_call(deliver=true)` 的回复直接发到 QQ，模型只收到一句「已执行」。

## 限制

- 只能调 `karin.command` / `karin.regex` 注册的指令；`karin.accept`（通知/请求监听）无法被主动调用。
- 插件若读 `e.rawEvent` / `e.message_id`，或直接调 `e.bot.sendMsg`，拿不到真实 OneBot 数据（我们给的是最小事件对象）。默认以 Karin 主人身份调用，权限检查照常生效。
- 投递对象只认 QQ 好友/群：AstrBot 接的是别的平台（Telegram 等）时 `target` 拿到的是那边的 ID，Karin 发不出去，要显式指定 `scene` 与 QQ 号。
- `karin_share` 支持 **B站 与抖音**，其它平台在 bridge 侧被白名单挡下；依赖 `karin-plugin-kkk` 已装且启用。它拿不到卡片内容，也不校验链接存在性，失败只能从 `karin_logs` 看出来。

## 仓库结构

| 路径 | 说明 |
| --- | --- |
| `main.py` | 插件全部代码：继承 `Star` 的 `KarinCtl` |
| `metadata.yaml` | 插件元数据（市场与更新依赖它，必须在仓库根） |
| `_conf_schema.json` / `requirements.txt` | 面板配置 schema / 依赖（只有 `aiohttp`） |
| `README.md` / `INSTALL.md` | 使用与安装说明 |
| `scripts/pack.mjs` | 本地打包（不进插件包），产出 `dist/` 下 zip 与解压副本 |
| `AGENTS.md` / `.agents/` | 维护者文档（不进插件包） |

排障见 [`.agents/skills/troubleshooting.md`](./.agents/skills/troubleshooting.md)。

## 致谢

- 代码与文档由 **DeepSeekRuntime** 配合 **DeepSeek-V4.1-Flash** 模型编写；需求、部署与实测由作者完成。
- 指令表、日志与卡片能力由姊妹仓库 [karin-plugin-astrbot-bridge](https://github.com/YlovexLN/karin-plugin-astrbot-bridge) 提供，本插件只做翻译。
- 视频卡片依赖 [karin-plugin-kkk](https://github.com/ikenxuan/karin-plugin-kkk)；工具与配置的边界参照 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 的插件接口。

## 许可证

[AGPL-3.0-only](./LICENSE)。插件能通过 Karin 驱动聊天账号，修改后分发请同样以 AGPL 开源。
