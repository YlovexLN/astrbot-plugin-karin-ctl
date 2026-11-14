# ADR（karin_ctl）

每条记一件事：当时有哪些选项、为什么选了这个、付出什么代价。想推翻某个设计之前先读对应条目。

## ADR-1 不让 AstrBot 学文档，而是给它工具去问 Karin
最初诉求是「让 AstrBot 知道 Karin 框架的内容以及插件的使用方法」。塞文档进 system prompt 会过期、第三方插件根本没文档、每轮都付费；写说明文件进 Karin 要求同机且仍要人维护。**给模型一组工具现场查**：数据永远最新，只在用时付费。代价是工具描述每轮的固定开销（见 ADR-3）。

## ADR-2 直接调 Karin 进程内的插件函数，不走 QQ 消息
让 AstrBot 经 QQ 发给 Karin 的 bot 要依赖中继插件；伪造 OneBot 事件会参与统计与风控，还得维护完整结构。用户明确否决这两条（不依赖中继、不借助 OneBot），改为在 Karin 进程内直接调插件函数。代价：依赖框架内部模块，且不是真实事件，部分插件跑不通。

## ADR-3 六个细粒度工具，而不是一个 `karin(action, payload)` 万能工具
万能工具省 token，但模型得自己拼 JSON、参数名全靠记，错误率高。**专用工具**每个参数都有类型与描述。代价：约 700–900 token/轮（后来加到七个工具，约 800–1000）——这是为「模型真的会用」付的钱。

## ADR-4 `karin_call` 的 `text` 用 `sample` 作为约定
指令以正则注册，模型不知道该填什么。bridge 从正则反推 `sample`，工具输出里直接写「调用时 text 填：<sample>」。代价：反推不完美时会填错，好在 `call` 失败会返回候选指令名，模型能自我修正一次。

## ADR-5 `enabled` 开关 + 全链路截断
用户问「会不会每次都调 API 太耗 token」。事实：不轮询不监听，只有主动调用才请求；但 schema 每轮注入是固定开销，工具返回值还会永久留在上下文里反复计费。**决定**：`enabled` 总开关 + 所有返回文本过 `_clip` + `deliver` 时正文不回传。宁可让模型要两次，也不要一次塞爆上下文。

## ADR-6 `karin_search` 作为第六个工具
用户记不住插件指令、又要保留指令能力，模型也背不下整张表。**加一个模糊检索工具**：按需查，只带回 10 条。`karin_commands` 管「已知插件名」，`karin_search` 管「不知道」。代价：再 +1 个 schema 的开销。

## ADR-7 `karin_share` 只交出链接，不取回解析结果
用 `karin_call` 调 kkk 解析只能拿回消息元素，转文本会丢内容还占上下文。**新增 `karin_share`，强制 `deliver`，只回一句确认**。代价：AstrBot 不知道解析成败，失败要靠 `karin_logs`；平台白名单只有 bridge 侧的 `LINK_USE_CASES`（bilibili / douyin），扩平台必须改 bridge。

## ADR-8 `usecase` 由 bridge 判断，AstrBot 只透传空串
`main.py` 里再写一份域名正则必然漂移。`usecase` 留空，bridge 按链接 `inferUseCase`——判据只有一处。代价：docstring 得说清「一般留空」，填错时 bridge 报错里带上可用用例，模型能自我纠正。

## ADR-9 投递对象 = 消息所在的会话，不是提问的人
初版缺省是 `('group', group_id)`。中途改成「谁问发给谁」被用户否决（m01050）——AstrBot 的文字回复本来就回到提问处，卡片也该回到同一个会话。**决定**：`_resolve_scene` 顺序 = 显式 `target`（+`scene`）→ 显式 `scene` → `group_id`（group）→ `sender_id`（friend）→ 空（报错）；只给 `target` 时按当前消息判断它是群号还是 QQ 号。代价：发到别处必须显式传 `scene`+`target`；接非 QQ 平台时拿到的 ID 在 Karin 侧不存在。

## ADR-10 卡片由 `on_decorating_result` 自动补发，不再依赖模型主动调 `karin_share`
真机实测（2026-11-09）：只有明确说「触发一下 kkk 解析」时模型才调 `karin_share`，正常聊到视频它只把链接写进回复。只加强 docstring 是**建议**而非保证，还多跑一轮。**决定**：模型在回复末尾写 `[[share:<链接>]]`，插件读走并替换成完整链接——选哪条由模型决定，零额外工具调用。初版「取正文第一条链接」被否决（m04505）：正文常列 5 条候选，按位置取必然取错且错得很安静。
**真机修正史（都是踩出来的，别再改回去）**
1. **`auto_share` 必须写进 `_conf_schema.json`**：只写 `getattr(self.config, "auto_share", True)` 时属性存在但值为 `None`，默认值不生效，日志显示「关」且标记原样漏给用户。修法：补进 schema + `_auto_share_on()` 统一判定。
2. **标记是替换不是删除**：纯删除会让用户只剩一段没链接的正文（原话「卡片是有了 但是没给我链接啊」）。
3. **解析必须后台跑**：`await self._post("share", …)` 堵在 `on_decorating_result` 里，kkk 出卡片 10~14 秒，正文发不出去，卡片还会抢在前面到。现在 `create_task` + `self._bg_tasks`。
4. **`timeout` 20 → 60**（`_conf_schema.json`、`_post`、`_probe` 三处对齐）。
5. **成功路径不打日志**，只有失败才 `logger.warning`。
**代价**：用户不再能从正文得知「卡片失败了」（用户明确说只想要卡片）。

## ADR-11 格式提示按需注入：不装 skill 也要能出卡片
真机私聊「发个视频」全链通了，但那条链路**完全是 skill（`fixed-reply-format`）撑起来的**，`[[share:]]` 根本没参与——skill 是用户自己装的，换机器就没了。**决定**：`_hint_share_format`（`on_llm_request`）在 `HINT_TRIGGER` 命中时把 `SHARE_HINT` 追加到 `req.system_prompt`，由 `prompt_hint` 控制；不发请求、不调模型、已有标记就不重复加。`HINT_TRIGGER` 覆盖：视频 / 短片 / 剪辑 / 下一个 / 再来 / 来一支 / 来一个 / 看看 / 发个 / BV 号 / b23.tv / bilibili.com / douyin.com。
**追加：提示词不够，必须再有本地兜底**。让它「随便给我一条 B站视频看看」，它调了别的工具、最后只输出「正文两句 + 单独一条链接」，12 秒内 Karin 没有 `action=share`。于是 `_auto_share` 改成两层：有标记认标记；没标记取 `_all_links`。
**同日再改：从「唯一链接」到「每条都发」（用户 m06356）**。先是只认「全篇恰好一条链接」，用户否决：「要 因为有时候 astrbot 莫名其妙会多给链接 有时候只给一条」——要的是**给几条就补几张卡**。`_sole_link` 换成 `_all_links`（按出现顺序收集去重），每条各 `create_task` 一个 `_deliver_share`；新增 `MAX_AUTO_LINKS = 5`，超了只发前 5 条并写 warning（每条渲染 2~3 MB 图，不封顶会拖死 puppeteer 和聊天窗）。
**两个必须记住的实现细节**
- **去重靠区间覆盖**：链接本身含 BV 号，不先用 `MEDIA_LINK` 的区间盖掉 `MEDIA_ID` 的命中，就会数成两条、补两张一样的图。
- **`_normalize_link` 用一条正则剥首尾标点**：分两步剥（先引号后逗号）时，模型把链接贴成 Python 列表（`…BV1xx' ,`）会留下尾巴。
**代价**：正文里顺口提一条 B站/抖音链接也会触发一次渲染（数秒 + 数 MB）。要关就设 `auto_share=false`。

## ADR-12 视频解析崩溃不归本插件管（2026-11-14）

用户 m09920 问「kkk 报 `reading 'video'` 是不是调用视频解析才出现、是不是 AstrBot 没规定好」，m09932 定调：**README 不写明，但要让 AI 知道有这个 bug**。

结论：崩溃只在 kkk 解析 B站视频时出现（`videoQuality > 64` + 有登录态 → 读 `dash.video`，B站 playurl 只回 `durl`），**与调用方无关**——本插件只递一条链接，`SHARE_HINT`（`main.py:48`）与 `_deliver_share`（`main.py:507`）都不取视频流、不选清晰度。出卡片本身就依赖 kkk 拉流渲染，所以「不解析视频、只传链接」绕不开它。

记录方式：不进 README（用户视角不需要知道），写进 `.agents/skills/troubleshooting.md` 与 bridge 侧的同一份文档 + ADR-10 补记，让维护者和 AI 看得到。**不自动降 `videoQuality`、不碰 Karin 的 node_modules**，失败如实回报。

## 已知偏差（记着，暂不改）
`main.py` 里 `karin_share` 的 docstring（约 :357）还写着「正文里出现链接本身**不会**触发卡片——只有 `[[share:...]]` 里那一条会」。前半句与 ADR-11 冲突：没标记时 `_auto_share` 会为正文里**每条**链接各补一张卡（上限 `MAX_AUTO_LINKS = 5`）。
2026-11-11 决定**先不改**（用户确认）：日常路径（写标记 → 只发那一条）说明书与实现一致，错的那半句只在「不想出卡」时才有意义；改成「不写标记也出卡」可能让模型偷懒不点名，反而一次弹多张。**下次动这个插件时顺手一起改**，改完必须重新上传插件才生效（改的是 prompt，不是逻辑）。
