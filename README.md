# astrbot-plugin-karin-ctl

让 AstrBot 的 Agent 看见并调用 Karin 的插件。

配套 Karin 侧插件：**karin-plugin-astrbot-bridge**（提供 `/api/v1/astrbot/*`）。两个插件必须一起装。

## 安装

1. **从插件市场 / 仓库安装**（推荐）：AstrBot 面板 → 插件管理 → 安装插件，填仓库地址
   `https://github.com/YlovexLN/astrbot-plugin-karin-ctl`。仓库根目录就是插件根目录
   （`metadata.yaml`、`main.py` 都在根上），装完插件目录名为 `astrbot_plugin_karin_ctl`。
2. 插件配置里填两项：`karin_url`（Karin 的 HTTP 地址，含端口）、`karin_token`（与 Karin 侧一致）。
3. 重启 AstrBot，日志里应出现 `[karin_ctl] 已加载：自动补卡片=开，Karin=http://...`。
4. 对 AstrBot 说「用 karin_status 看看 Karin」——第一行就是连通自检结果。

手动安装：把本仓库的文件拷进 `data/plugins/astrbot_plugin_karin_ctl/`（目录名必须与
`metadata.yaml` 的 `name` 一致），重启即可。

维护者本地打包：`node scripts/pack.mjs` 生成 `dist/astrbot-plugin-karin-ctl-v0.0.1.zip` 与解压副本；
`dist/` 已被 `.gitignore` 忽略，仓库里不包含打包产物。

## 配置项

| 配置项 | 必填 | 说明 |
| --- | --- | --- |
| `karin_url` | 是 | 例 `http://192.0.2.10:7777`。这是 Karin 的 `HTTP_PORT`（OneBot 与 HTTP 共用），**不是 WebUI 端口**；容器之间不能用 `127.0.0.1` |
| `karin_token` | 是 | 与 Karin 的 `HTTP_AUTH_KEY`（或 `ASTRBOT_BRIDGE_TOKEN`）一致，bridge 按这个顺序取 |
| `timeout` | 否 | 请求超时秒数，默认 60。kkk 出卡片要 10~14 秒；自动补卡片已走后台，不受它限制 |
| `enabled` | 否 | 总开关，默认 true。关掉后七个工具立即返回提示，不再打 Karin |
| `auto_share` | 否 | 自动补卡片，默认 true。回复里的 `[[share:<链接>]]` 交给 kkk；没标记时正文里每条链接都补一张。关掉后链接原样留在正文、不出卡片 |
| `prompt_hint` | 否 | 格式兜底，默认 true。消息像是在要视频时往系统提示补一句「链接单独一行写 `[[share:<链接>]]`」。普通闲聊不注入 |

填错时的典型报错：

- `连不上 ...（ClientConnectorError）` → URL 不通，或跨容器用了 `127.0.0.1`
- `已连上 Karin 但 token 不对（401）` → 两边 token 不一致
- `Karin 里的 bridge 插件还没配 token（500）` → Karin 侧没填，去 Karin WebUI 的插件配置里填

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

三条典型链路：

- **记不住指令**：`karin_search("转发")` → 拿 `sample` → `karin_call(text=sample)`
- **知道插件名**：`karin_plugins` → `karin_commands(plugin)` → `karin_call(plugin, method, text)`
- **要卡片**：见下一节，正常不需要调工具

`karin_call` 只给 `text` 也能调：它按正则匹配指令，没带前缀时自动补 Karin 的 alias 重试。
所以模型不必记方法名，把 `karin_search` 返回的 `sample` 原样传进去即可。

## 卡片是怎么出来的

想要 QQ 里出现视频卡片，**不用调工具**，在回复正文最后另起一行写一条标记：

```
...正文...
[[share:https://www.bilibili.com/video/BV1P24y1b7Gx]]
```

插件会读走这一行、交给 kkk，并**把标记换成普通完整链接**再发出去——用户看到的是可点链接 + 随后到达的卡片，
`[[...]]` 本身不外泄。标记里可以写完整链接（`bilibili.com`、`b23.tv`、`bili2233.cn`、`douyin.com`、`iesdouyin.com`），
也可以只写 BV 号 / av 号。

卡片发到**当前这个会话**：群里问就发那个群，私聊问就发回这个私聊。

**模型不写标记也照样出卡片。** 发出去之前有一道本地判断：

| 这一条回复里的情况 | 结果 |
| --- | --- |
| 有 `[[share:<链接>]]` 标记 | 只发标记那一条（显式优先） |
| 没有标记，正文里有 N 条媒体链接 | N 条都发，各补一张卡（去重，最多 5 条） |

去重是必须的：一条链接本身就含 BV 号，不处理会数成两条、补两张一模一样的图。
上限 5 条是防止模型把整页列表贴上来时一次渲染十几张图。

解析在**后台**跑：正文立刻发出，卡片 10~14 秒后自己到，不会出现「卡片比正文先到」。
解析失败只写日志，不往正文里塞错误信息。

**只在真实聊天平台补卡片**：`webchat` / `console`（AstrBot 面板里的调试窗口）一律跳过——
调试窗口的回复里常有命令输出和贴进去的测试链接，不拦就会把卡片发到你的 QQ 上。

### 没装 skill 也能出卡片

`fixed-reply-format` 那类 skill 规定了「观后两三句 + 链接单独一条纯 URL + 再 `karin_share`」，
但 skill 是用户自己装的，换台机器就可能没有。插件用两层兜底：`prompt_hint` 在消息像是要视频时
（`HINT_TRIGGER`：视频 / 短片 / 下一个 / 看看 / 发个 / BV 号 / `b23.tv` / `bilibili.com` / `douyin.com` 等）
往系统提示补一句格式说明；`auto_share` 则保证模型不听话时也照样出卡片（判定见上一张表）。
skill 存在时两处说法一致，不冲突；有标记时只发标记那一条，不会出两张卡。

## token 账

- **不会被自动触发**：没有轮询、没有定时任务。到 Karin 的请求只可能来自这一轮的工具调用或那一条标记/链接。
- **固定开销**：七个工具的名称与描述注入每轮请求的 tools 数组，约 800–1000 token/轮，与是否调用无关。
  想彻底归零就把 `enabled` 设为 false，或在插件管理里直接禁用本插件。
- **变量开销已封顶**：插件回复 2000 字、插件列表 40 条、指令列表 40 条×60 字、检索结果 10 条（上限 50）、日志 3000 字，超出附截断提示。
- **长输出不进上下文**：`karin_call(deliver=true)` 时插件回复直接发到 QQ，模型只收到一句「已执行」。

## 限制

- 只能调 `karin.command` / `karin.regex` 注册的指令；`karin.accept`（通知/请求监听）无法被主动调用。
- 插件若读 `e.rawEvent` / `e.message_id`，或直接调 `e.bot.sendMsg`，拿不到真实 OneBot 数据（我们给的是最小事件对象）。
- 默认以 Karin 主人身份调用，权限检查照常生效。
- `karin_share` 的投递对象只认 QQ 好友/群：AstrBot 接的是别的平台（Telegram 等）时，`target` 拿到的是那边的 ID，
  Karin 发不出去——这种情况要显式指定 `scene` 与 QQ 号。
- `karin_share` 支持 **B站 与抖音**，其它平台在 bridge 侧被白名单挡下；依赖 `karin-plugin-kkk` 已装且启用。
  它拿不到卡片内容，也不做链接存在性校验（不额外抓标题），失败只能从 `karin_logs` 里看出来。

## 仓库结构

| 路径 | 说明 |
| --- | --- |
| `main.py` | 插件全部代码：继承 `Star` 的 `KarinCtl` |
| `metadata.yaml` | 插件元数据（AstrBot 插件市场与更新依赖它，必须在仓库根目录） |
| `_conf_schema.json` | 面板配置 schema |
| `requirements.txt` | 第三方依赖，只有 `aiohttp` |
| `README.md` / `INSTALL.md` | 使用与安装说明 |
| `scripts/pack.mjs` | 本地打包脚本（不进插件包） |
| `AGENTS.md` / `.agents/` | 维护者文档（不进插件包） |

## 许可证

[AGPL-3.0-only](./LICENSE)。插件能通过 Karin 驱动聊天账号，修改后分发请同样以 AGPL 开源。
