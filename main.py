# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 YlovexLN

import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star


REPLY_LIMIT = 2000
PLUGIN_LIMIT = 40
COMMAND_LIMIT = 40
LOG_LIMIT = 3000

INSTALL_RECORD = "_install_record.json"

# B站 / 抖音 的链接特征与 kkk 自己认的一模一样，认不出来就不要发
MEDIA_LINK = re.compile(
    r"https?://(?:[^\s]*(?:bilibili\.com|b23\.tv|bili2233\.cn|douyin\.com|iesdouyin\.com)[^\s]*)",
    re.I,
)
# 纯视频号也算一条：BV 号 / av 号，kkk 的 handleBilibili 直接认
MEDIA_ID = re.compile(r"(?<![0-9A-Za-z])(BV[1-9A-Za-z]{10}|av\d{1,12})(?![0-9A-Za-z])")
# 模型用它点明"这一条要出卡片"：[[share:https://...]] 或 [[share:BV1xx...]]
# 标记只给插件看，发出去之前会被剥掉；没有标记时正文里每条链接都补一张卡（不挑、不猜）
SHARE_TAG = re.compile(r"\[\[\s*share\s*:\s*([^\]]+?)\s*\]\]", re.I)
# 一轮回复里最多补几张卡：AstrBot 正常给 1~3 条，再多就是它把整页列表贴上来了；
# 每条都要渲染一张 2~3 MB 的图，不封顶会把 puppeteer 和聊天窗一起拖死
MAX_AUTO_LINKS = 5
# 不补卡片的平台：面板里的 webchat / console 是调试窗口，不是聊天场景。
# 那里回复里常有调试输出、贴进去的测试链接，自动补卡片会把卡片发到 QQ 上（2026-11-10 真机踩到过）
NO_CARD_PLATFORMS = {"webchat", "console"}

# 没装 skill 时的兜底：模型自己不会主动写标记，得有人告诉它这个格式
# 只在「这一轮像是要视频」时注入，普通闲聊不多花 token
HINT_TRIGGER = re.compile(
    r"视频|短片|剪辑|下一个|再来|来一支|来一个|看看|发个|"
    r"BV[1-9A-Za-z]{10}|b23\.tv|bilibili\.com|douyin\.com",
    re.I,
)
SHARE_HINT = (
    "\n[视频投递格式] 发 B站/抖音视频时：正文只写两三句观后感受，链接不要夹在句子里，"
    "另起一行单独写 [[share:<完整链接>]]。插件会把这一行换成可点链接，并在当前会话补一张卡片；"
    "一次只发一条。"
)


def _clip(text: str, limit: int) -> str:
    """截断长文本，保留尾部提示，防止把整段输出灌进模型上下文"""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[已截断 {len(text) - limit} 字，可用 deliver=true 直接发到 QQ]"


class KarinCtl(Star):
    """对接 karin-plugin-astrbot-bridge 暴露的 /api/v1/astrbot/* 接口。

    插件名称、作者、版本等元数据全部来自 metadata.yaml；AstrBot 会自动把继承
    Star 的类注册为插件，不需要（也不应）再用已废弃的 @register 装饰器。
    """

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context, config)
        self.config = config
        self._self_check = ""
        # 后台补卡片的任务引用：create_task 的返回值必须有人持有，否则可能被 GC 收掉
        self._bg_tasks = set()

    async def initialize(self):
        """首次加载时清掉旧记录并自检一次；结果挂在实例上，由 karin_status 带出"""
        self._forget_install_record()
        self._self_check = await self._probe()

    def _forget_install_record(self):
        """装完之后就不需要了：只删自己目录里的 _install_record.json

        不删除插件目录本身，也不碰 data/plugins 下的其它路径——插件只清理
        自己写下的这一个文件；删不掉就留着，不影响加载。
        """
        try:
            (Path(__file__).resolve().parent / INSTALL_RECORD).unlink(missing_ok=True)
        except OSError:
            pass

    async def _probe(self) -> str:
        """启动自检：token 缺失或连不上时直接写进返回文本，不用靠用户去翻日志"""
        token = str(self.config.get("karin_token", "") or "")
        if not token:
            return "⚠ karin_token 还没填：到 AstrBot 面板 → 插件 → astrbot_plugin_karin_ctl 里填写（与 Karin 侧 ASTRBOT_BRIDGE_TOKEN 一致）"
        url = f"{self._base}/api/v1/astrbot/ping"
        timeout = aiohttp.ClientTimeout(total=min(float(self.config.get("timeout", 60)), 10))
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    url,
                    json={},
                    headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
                ) as resp:
                    if resp.status == 401:
                        return f"⚠ 已连上 Karin 但 token 不对（401）：{url}"
                    if resp.status == 500:
                        return f"⚠ Karin 里的 bridge 插件还没配 token（500）：{url}"
                    if resp.status != 200:
                        return f"⚠ Karin 返回 {resp.status}：{url}"
            return f"✓ 已连通 Karin：{self._base}"
        except aiohttp.ClientConnectorError as exc:
            return f"⚠ 连不上 {url}：{exc}. {self._reach_hint()}"
        except asyncio.TimeoutError:
            return f"⚠ 连接 Karin 超时：{url}"

    @property
    def _enabled(self) -> bool:
        """关掉开关后所有工具都不产生实际调用，token 消耗归零（工具本身仍会在 tools 列表里）"""
        return bool(self.config.get("enabled", True))

    @property
    def _base(self) -> str:
        return str(self.config.get("karin_url", "")).rstrip("/")

    def _reach_hint(self) -> str:
        """按 karin_url 的形状给不同的排查方向：指本机多半是容器隔阂，指别处则是网络/端口"""
        host = (urlparse(self._base).hostname or "").lower()
        if host in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
            return "这个地址指向本机，AstrBot 跑在容器里时要用 Karin 容器的内网地址或它所在主机的局域网 IP"
        return "检查 karin_url 的 IP、端口（是 Karin 的 HTTP_PORT）以及两者是否在同一网络"

    async def _post(self, action: str, payload: dict) -> dict:
        url = f"{self._base}/api/v1/astrbot/{action}"
        headers = {
            "Authorization": "Bearer " + str(self.config.get("karin_token", "")),
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(total=float(self.config.get("timeout", 60)))
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    text = await resp.text()
                    if resp.status == 401:
                        raise RuntimeError(
                            "Karin 拒绝访问（401）：astrbot_plugin_karin_ctl 的 karin_token 与 "
                            "karin-plugin-astrbot-bridge 里配置的 token 不一致"
                        )
                    if resp.status >= 500 and text.startswith("{"):
                        raise RuntimeError(f"Karin 内部错误 {resp.status}: {text[:500]}")
                    if resp.status != 200:
                        raise RuntimeError(f"Karin 返回 {resp.status}: {text[:400]}")
                    data = json.loads(text)
                    if not data.get("success"):
                        raise RuntimeError(str(data.get("message") or data))
                    return data
        except aiohttp.ClientConnectorError as exc:
            raise RuntimeError(
                f"连不上 Karin（{url}）：{exc}. {self._reach_hint()}"
            ) from exc
        except asyncio.TimeoutError as exc:
            raise RuntimeError(
                f"请求 Karin 超时（{self.config.get('timeout', 60)}s）：{url}"
            ) from exc

    @filter.llm_tool(name="karin_search")
    async def karin_search(self, event: AstrMessageEvent, keyword: str, limit: int = 10):
        """不知道插件叫什么、也记不住指令时用这个：把用户原话里的关键词直接丢进来做模糊检索。
        它会匹配插件名、方法名、指令文本，以及插件 README 和配置项里的词。

        keyword 填用户原话的关键词即可（如「转发」「点歌」「抽卡」「状态」），不需要是准确的指令名；
        填「全部」或「列表」可列出所有指令。
        查到后用 karin_call，把返回的 sample 原样当 text 传进去。

        Args:
            keyword(string): 用户原话里的关键词
            limit(number): 最多返回几条，默认 10
        """
        if not self._enabled:
            return "karin_ctl 已关闭（配置项 enabled=false），请先在 AstrBot 面板打开。"
        data = await self._post("search", {"keyword": keyword, "limit": min(max(int(limit), 1), 50)})
        rows = data.get("commands") or []
        if not rows:
            return (
                f"没找到与「{keyword}」相关的 Karin 指令。"
                "可以换个说法重试，或先 karin_plugins 看装了哪些插件。"
            )
        lines = [f"共找到 {data.get('total', 0)} 条，显示前 {len(rows)} 条（跨插件命中时按相关度排序）："]
        for c in rows:
            lines.append(f"- {c['command']}（{c['plugin']}｜{c['method']}｜权限 {c.get('permission')}）")
            if c.get("sample"):
                lines.append(f"  调用时 text 填：{c['sample']}")
        for p in data.get("plugins") or []:
            if p.get("accepts"):
                lines.append(f"注意：{p['plugin']} 还有 {p['accepts']} 个监听式入口（accept），只能被动响应通知/请求，无法直接调用。")
        return _clip("\n".join(lines), COMMAND_LIMIT * 60)

    @filter.llm_tool(name="karin_plugins")
    async def karin_plugins(self, event: AstrMessageEvent, force: bool = False):
        """列出 Karin 已安装的插件（名称、类型、版本、是否启用）以及当前在线的 Bot。
        仅在用户主动询问 Karin 插件相关问题时调用，不要凭空调用。

        Args:
            force(boolean): 是否强制刷新 Karin 的插件缓存，默认 false
        """
        if not self._enabled:
            return "karin_ctl 已关闭（配置项 enabled=false），请先在 AstrBot 面板打开。"
        data = await self._post("plugins", {"force": bool(force)})
        plugins = data.get("plugins", [])
        lines = [f"共 {len(plugins)} 个插件："]
        for p in plugins[:PLUGIN_LIMIT]:
            flag = "启用" if p.get("enabled") else "未启用"
            desc = f" - {p['description']}" if p.get("description") else ""
            lines.append(f"- {p['name']} [{p['type']}] v{p.get('version')} {flag}{desc}")
        if len(plugins) > PLUGIN_LIMIT:
            lines.append(f"...另有 {len(plugins) - PLUGIN_LIMIT} 个未列出")
        bots = (data.get("runtime") or {}).get("bots") or []
        if bots:
            lines.append("在线 Bot：" + "、".join(f"{b['selfId']}({b['standard']})" for b in bots))
        return "\n".join(lines)

    @filter.llm_tool(name="karin_commands")
    async def karin_commands(
        self,
        event: AstrMessageEvent,
        plugin: str = "",
        keyword: str = "",
        offset: int = 0,
        limit: int = 40,
    ):
        """列出 Karin 插件注册的指令。已知插件名、想看清它的全部指令时用这个；
        不知道插件名或记不住指令名时，改用 karin_search 做关键词模糊检索。
        结果里的 sample 字段可以直接作为 karin_call 的 text 使用。

        Args:
            plugin(string): 插件名，例如 karin-plugin-selfmsg；留空返回全部插件
            keyword(string): 按指令正则里的关键字过滤
            offset(number): 跳过多少条，用于翻页，默认 0
            limit(number): 本次返回条数，默认 40，上限 200
        """
        if not self._enabled:
            return "karin_ctl 已关闭（配置项 enabled=false），请先在 AstrBot 面板打开。"
        data = await self._post(
            "commands",
            {
                "plugin": plugin,
                "keyword": keyword,
                "includeTrigger": False,
                "offset": int(offset),
                "limit": min(max(int(limit), 1), 200),
            },
        )
        commands = data.get("commands", [])
        if not commands:
            return (
                f"没有找到指令（plugin={plugin or '全部'}）。"
                "该插件可能只监听消息内容（accept），可以改用 karin_call 按插件名直接调用。"
            )
        rows = [
            f"- {c['command']}（{c['plugin']}｜{c['method']}｜权限 {c.get('permission')}）"
            + (f" 示例text: {c['sample']}" if c.get("sample") and c["sample"] != c["command"] else "")
            for c in commands
        ]
        head = f"共 {data.get('total', len(commands))} 条指令，本次返回 {len(commands)} 条："
        if data.get("hasMore"):
            head += f"（还有更多，用 offset={int(offset) + len(commands)} 继续）"
        accepts = data.get("accepts", [])
        tail = f"\n另有 {len(accepts)} 个 notify/request 监听，这类只能被动响应用户消息，无法直接调用。" if accepts else ""
        return "\n".join([head, *rows]) + tail

    @filter.llm_tool(name="karin_call")
    async def karin_call(
        self,
        event: AstrMessageEvent,
        plugin: str,
        method: str = "",
        text: str = "",
        deliver: bool = False,
    ):
        """直接调用 Karin 插件的某个指令函数，返回插件的回复文本。
        不经过 QQ，也不构造 OneBot 事件。

        plugin 填插件包名（如 karin-plugin-selfmsg）；method 填插件文件里的方法名（见 karin_commands）；
        text 填该方法期望的消息文本，用于匹配参数。

        Args:
            plugin(string): 插件包名
            method(string): 插件方法名，留空则该插件只能匹配到一条指令时自动选中
            text(string): 传给插件的消息文本
            deliver(boolean): 是否让插件的回复真的发到 QQ（默认 false，只把文本返回给 AstrBot）
        """
        if not self._enabled:
            return "karin_ctl 已关闭（配置项 enabled=false），请先在 AstrBot 面板打开。"

        payload = {"plugin": plugin, "method": method, "text": text, "deliver": bool(deliver)}
        data = await self._post("call", payload)

        if data.get("ambiguous"):
            cands = data.get("candidates") or []
            rows = [f"- {c['plugin']} / {c['method']}（{c['command']}）" for c in cands]
            return "该插件有多条指令，请补 method 或 text：\n" + "\n".join(rows)

        reply = data.get("reply") or []
        full = "\n---\n".join(map(str, reply)) if reply else ""
        body = _clip(full, REPLY_LIMIT)

        # deliver 时正文已经发到 QQ，只回一句确认，避免长文本重复进上下文
        if deliver and data.get("ok"):
            return (
                f"{data.get('plugin')}/{data.get('method')} 已执行，回复已直接发到 QQ"
                f"（{len(full)} 字，未回传上下文）。"
            )
        if data.get("error"):
            parts = [f"调用 {plugin}/{method} 出错：{data['error']}"]
            if data.get("stack"):
                parts.append("堆栈：\n" + str(data["stack"]))
            parts.append("回复：" + body)
            return "\n".join(parts)
        if data.get("blocked") == "hook":
            return f"{plugin}/{method} 被 Karin 的事件钩子拦截，未执行（可能被禁用或白名单挡了）。"
        if data.get("permission") == "denied":
            hint = f"（{data['authFailMsg']}）" if data.get("authFailMsg") else ""
            return (
                f"{plugin}/{method} 权限不足：该指令要求 {data.get('need')}{hint}。"
                f"当前身份是普通用户；可以换 userId 或忽略权限重试。"
            )
        return f"{data.get('plugin')}/{data.get('method')} 执行完毕：\n{body}"

    @filter.llm_tool(name="karin_share")
    async def karin_share(
        self,
        event: AstrMessageEvent,
        url: str,
        usecase: str = "",
        scene: str = "",
        target: str = "",
    ):
        """让 Karin 的解析插件（karin-plugin-kkk）在**当前会话**里发一张视频卡片。

        正常情况下**不需要调用本工具**：想要卡片时，在你的回复正文最后另起一行写
            [[share:https://www.bilibili.com/video/BVxxxx]]
        （BV 号 / av 号 / b23.tv 短链 / 抖音链接也都可以写进 [[share: ...]]）
        插件会读出这一行、发给 kkk，并且**把这一行换成普通的完整链接**再发出去——
        用户看到的是可点的链接 + 随后到达的卡片，`[[...]]` 本身不会外泄。
        一次回复只写**一行**，写多行只认第一行。

        这是省 token 的关键：写一行文字不算工具调用，你还是只输出一轮回复；
        而调用本工具要额外跑一轮「等结果 → 再回话」。

        正文里出现链接本身**不会**触发卡片——只有 [[share:...]] 里那一条会。
        所以列表里同时贴了 5 条链接时，用 [[share:...]] 点明你真正推荐的那一条。

        只有下面两种情况才手动调用本工具：
        1. 用户要求把卡片发到**别的地方**（另一个群、私发给某人）——需要 scene + target；
        2. 用户明确要求「再解析一次」「重新出卡片」，而上一次已经失败。

        手动调用只传一条链接：不要把 5 条都传进来，也不要为每条调一次，那会刷出一堆卡片。

        url 填完整链接即可（B站：bilibili.com/...、b23.tv 短链或 BV 号；
        抖音：v.douyin.com 短链或 douyin.com 链接），不要自己改写。
        usecase 一般留空，让 Karin 按链接自动判断。
        scene/target 一般也留空：卡片会发回当前会话——群里问就发到这个群，私聊问就发回这个私聊。
        只有用户要求发到「别的地方」（另一个群、或者私发给某人）时才传 scene + target。

        Args:
            url(string): 要解析的那一条链接（只传一条）
            usecase(string): bilibili 或 douyin，留空自动判断
            scene(string): group 或 friend，留空按当前会话自动判断
            target(string): 群号或 QQ 号，留空按当前会话自动判断
        """
        if not self._enabled:
            return "karin_ctl 已关闭（配置项 enabled=false），请先在 AstrBot 面板打开。"
        scene, target = self._resolve_scene(event, scene, target)
        if not target:
            return "不知道要发到哪个会话：这个事件里没有群号也没有发送者 ID，请显式传 scene 与 target。"

        data = await self._post(
            "share",
            {
                "useCase": (usecase or "").strip().lower(),
                "text": url,
                "scene": scene,
                "target": target,
            },
        )
        if not data.get("ok"):
            parts = [f"交给解析插件失败：{data.get('error') or '未知原因'}"]
            if data.get("candidates"):
                parts.append(
                    "该插件的指令："
                    + "、".join(f"{c['plugin']}/{c['method']}" for c in data["candidates"][:5])
                )
            return "\n".join(parts)

        where = f"群 {target}" if data.get("scene") == "group" else f"QQ {target}"
        kind = {"bilibili": "B站", "douyin": "抖音"}.get(str(data.get("useCase") or ""), "")
        # bridge 的 share 回的是 exportName（handleBilibili），method 是 call 的字段，别取错成 None
        who = data.get("method") or data.get("exportName") or "?"
        head = f"已交给 {data.get('plugin')}/{who}"
        if kind:
            head += f"（{kind}解析）"
        lines = [f"{head}，解析结果会直接以卡片形式发到{where}。"]
        if data.get("notices"):
            lines.append("插件返回的提示：" + "；".join(data["notices"]))
        lines.append("卡片内容不会回到这里；如果迟迟没有出现，用 karin_logs 看 Karin 的报错。")
        return "\n".join(lines)

    def _auto_share_on(self) -> bool:
        """自动补卡片是否开启

        默认**开**：配置项缺失（老版本装的、面板没渲染出来的）一律当开启，
        否则用户看得到链接、永远等不到卡片，还查不出原因。

        注意用 dict.get 而不是 getattr：AstrBotConfig.__getattr__ 对缺失键返回
        None，会让 getattr 的默认值失效（None 被 bool() 成 False）。
        """
        return bool(self.config.get("auto_share", True))

    @filter.on_astrbot_loaded()
    async def _auto_share_loaded(self):
        """启动时打一行，方便在 AstrBot 日志里确认本插件真的装上了、自动补卡片是开的"""
        logger.info(
            f"[karin_ctl] 已加载：自动补卡片={'开' if self._auto_share_on() else '关'}，"
            f"Karin={self.config.get('karin_url', '') or ''}"
        )

    @filter.on_llm_request()
    async def _hint_share_format(self, event: AstrMessageEvent, req):
        """没装 skill 时的兜底：把「视频怎么发」这几句塞进系统提示

        为什么需要：`fixed-reply-format` 那类 skill 里写了「链接单独一条纯 URL + 再让 kkk 出卡片」，
        但 skill 是用户自己装的，换台机器就没了。没有它的时候模型只会把链接夹在正文里，
        结果既没有独立链接、也没有卡片。这里补一句最小格式提示，输出大致对得上。

        只在消息像是要视频时才加（HINT_TRIGGER），普通闲聊不花 token。
        已经带 `[[share:` 的提示不重复加，避免同一轮叠两句。
        """
        if not self._enabled or not self._auto_share_on():
            return
        if not bool(self.config.get("prompt_hint", True)):
            return
        if not HINT_TRIGGER.search(str(getattr(event, "message_str", "") or "")):
            return
        prompt = getattr(req, "system_prompt", None)
        if not isinstance(prompt, str) or "[[share:" in prompt:
            return
        req.system_prompt = prompt + SHARE_HINT

    @filter.on_decorating_result()
    async def _auto_share(self, event: AstrMessageEvent):
        """把这一条回复里的 B站/抖音链接交给 kkk，由它在同一会话补卡片

        **发哪几条由 AstrBot 定，插件不挑也不猜**：
        模型写了 [[share:<链接>]] 就只发标记那一条（这一行只给插件看，发出去前会被剥掉）；
        没写标记时，正文里有几条媒体链接就发几条——AstrBot 有时给一条、有时给三四条，
        给几条补几张卡，用户要的就是"链接进了群就变成卡片"。去重后最多 MAX_AUTO_LINKS 条。

        为什么不干脆让模型调 karin_share：那要多跑一整轮「决定调用 → 等结果 → 再组织回复」，
        而这里只多写一行文本，零额外工具调用。命令失败了也不影响用户读到正文。

        解析本身丢到后台（_deliver_share）：kkk 出卡片要 10~14 秒，堵在这个钩子里会让
        正文一直发不出去，卡片还会抢在正文前面到达。现在正文立刻发出，卡片随后补上。

        只处理「已经生成好、还没发出去」的这一条回复；否则会把历史消息里的老链接也解析一遍。
        """
        if not self._auto_share_on():
            return
        if not self._enabled:
            return
        if self._platform_of(event) in NO_CARD_PLATFORMS:
            # 调试窗口里的链接不该变成 QQ 上的卡片
            return
        result = event.get_result()
        if not result or not getattr(result, "is_llm_result", lambda: False)():
            return

        raw = result.get_plain_text() or ""
        match = SHARE_TAG.search(raw)
        if match:
            link = self._normalize_link(match.group(1))
            # 标记行本来就不该给用户看，不管后面解析成不成功都先剥掉；
            # 剥掉的同时把**链接正文**留在原处——用户既要点得到的链接，也要卡片，标记只是给插件看的信使
            self._strip_share_tag(result, link)
            links = [link] if link else []
        else:
            links = self._all_links(raw)
            if len(links) > MAX_AUTO_LINKS:
                logger.warning(
                    f"[karin_ctl] 这轮回复有 {len(links)} 条链接，只解析前 {MAX_AUTO_LINKS} 条（防止一次渲染一堆图）"
                )
                links = links[:MAX_AUTO_LINKS]
        if not links:
            return

        scene, target = self._resolve_scene(event, "", "")
        if not target:
            return
        # 丢到后台跑：kkk 出卡片要 10~14 秒，堵在 on_decorating_result 里会让正文一直发不出去，
        # 而且卡片会抢在正文前面到达。这里只负责把链接交出去，成败只写日志、不改正文。
        # 每条链接一个任务：AstrBot 有时给一条、有时给好几条，给几条就补几张卡。
        for link in links:
            task = asyncio.create_task(self._deliver_share(link, scene, target))
            self._bg_tasks.add(task)
            task.add_done_callback(self._bg_tasks.discard)

    async def _deliver_share(self, link: str, scene: str, target: str) -> None:
        """后台把一条链接交给 kkk 解析；失败只记日志，不打扰用户，也不改已经发出去的正文"""
        try:
            data = await self._post(
                "share",
                {"useCase": "", "text": link, "scene": scene, "target": target},
            )
        except Exception as exc:  # noqa: BLE001 - 自动补卡片失败不能影响正常回复
            logger.warning(f"[karin_ctl] 自动解析 {link} 失败：{exc}")
            return
        # 成功路径不刷日志：一轮会话只关心「有没有出卡片」，失败才值得留痕
        if not data.get("ok"):
            logger.warning(f"[karin_ctl] 自动解析 {link} 失败：{data.get('error')}")

    @staticmethod
    def _strip_share_tag(result, link: str = "") -> None:
        """把 [[share:...]] 换成普通链接（可能被模型夹在句子中间）

        标记只给插件看，但用户要的是可点的链接：所以默认用 `link` 原地替换，
        文案里已经有这条链接时（模型自己写了）就只删标记，不重复贴。
        """
        for comp in result.chain:
            text = getattr(comp, "text", None)
            if not isinstance(text, str) or "[[" not in text:
                continue
            replacement = ""
            # 正文别处已经贴过就不重复
            if link and link not in SHARE_TAG.sub("", text):
                replacement = link
            cleaned = SHARE_TAG.sub(lambda _m: replacement, text)
            # 标记独占一行时摘掉后留下的空行一并收掉
            cleaned = re.sub(r"[ \t]*\n[ \t]*(?=\n)", "", cleaned).strip("\n")
            comp.text = cleaned

    @staticmethod
    def _all_links(text: str) -> list:
        """正文里所有 B站/抖音 链接，按出现顺序去重后返回

        为什么「没写标记也发」：没装 fixed-reply-format 这类 skill 时，模型只会把链接写进正文，
        它给一条就给一条、给三条就给三条——给几条补几张卡，不挑也不猜（挑才需要猜）。

        链接里本来就含 BV 号（https://www.bilibili.com/video/BV1xx），所以先用链接的区间
        把 BV/av 号的命中盖掉，否则一条链接会被数成两条、补两张一模一样的卡。
        """
        links = []
        spans = []
        for m in MEDIA_LINK.finditer(text or ""):
            spans.append((m.start(), m.end()))
            link = KarinCtl._normalize_link(m.group(0))
            if link and link not in links:
                links.append(link)
        for m in MEDIA_ID.finditer(text or ""):
            if any(start <= m.start() < end for start, end in spans):
                continue
            link = KarinCtl._normalize_link(m.group(1))
            if link and link not in links:
                links.append(link)
        return links

    @staticmethod
    def _normalize_link(raw: str) -> str:
        """标记里的内容可能是完整链接，也可能只是 BV/av 号

        剥掉首尾标点（kkk 的正则认不得「。」和引号）；不是链接/号的一律当没写，宁可不出卡片也不乱发。

        用正则一次性剥，不能先剥引号再剥逗号：模型把链接贴成 Python 列表时是「…BV1xx',」，
        先剥引号时尾巴是逗号剥不动，逗号剥掉后引号就留在链接里了（真机日志出现过「…BV1xx'」）。
        """
        text = re.sub(r"^[<>\"'`\s]+", "", (raw or "").strip())
        text = re.sub(r"[<>\"'`.,;:!?)\]}>，。；：！？）」』》\s]+$", "", text)
        if not text:
            return ""
        if MEDIA_LINK.match(text):
            return text
        found = MEDIA_ID.findall(text)
        return found[0] if found else ""

    @staticmethod
    def _platform_of(event: AstrMessageEvent) -> str:
        """当前消息来自哪个平台（webchat / aiocqhttp / …），取不到就返回空串

        两种取法都留着：`get_platform_name()` 是 AstrBot 的正规接口，
        UMO 前缀是兜底（形如 `webchat:FriendMessage:xxx`），老版本没这个方法时还能判断。
        """
        getter = getattr(event, "get_platform_name", None)
        if callable(getter):
            try:
                name = str(getter() or "").strip().lower()
                if name:
                    return name
            except Exception:  # noqa: BLE001 - 取平台名失败不该影响回复
                pass
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        return umo.split(":", 1)[0].strip().lower()

    @staticmethod
    def _event_ids(event: AstrMessageEvent) -> tuple:
        """当前这条消息的 (群号, 发送者QQ)；私聊的群号为空，群聊的发送者是发言人

        只读 event 的公开接口。AstrBot 各适配器的 get_group_id() / get_sender_id() 都是
        getattr(self.message_obj, ...) 的包装，取值不依赖 OneBot 的原始字段
        （唯一例外是部分适配器把 sender 塞在 raw_message 里，这时拿不到就返回空串）。
        """
        def pick(*getters) -> str:
            for getter in getters:
                try:
                    value = getter()
                except Exception:
                    continue
                if value:
                    return str(value)
            return ""

        umo = str(getattr(event, "unified_msg_origin", "") or "")
        group_id = pick(lambda: event.get_group_id())
        if not group_id and "GroupMessage" in umo:
            # 少数适配器（如 telegram 在话题群外）不带 group_id，此时 session_id 就是群号
            group_id = pick(lambda: event.get_session_id())
        sender_id = pick(lambda: event.get_sender_id())
        if not group_id and not sender_id:
            # 兜底：platform:GroupMessage:789 或 platform:FriendMessage:123456
            parts = umo.split(":")
            if len(parts) >= 3:
                if parts[1] == "GroupMessage":
                    group_id = parts[2]
                elif parts[1] == "FriendMessage":
                    sender_id = parts[2]
        return group_id, sender_id

    def _resolve_scene(self, event: AstrMessageEvent, scene: str, target: str) -> tuple:
        """没显式给 scene/target 时，跟着当前这条消息所在的会话走：
        群里问就发到那个群，私聊问就发回那个私聊。

        显式给的 scene + target 优先级最高；只给 target 时按这条消息判断它是群号还是 QQ 号。
        """
        scene = (scene or "").strip().lower()
        target = (target or "").strip()
        group_id, sender_id = self._event_ids(event)

        if target:
            if scene in ("group", "friend"):
                return scene, target
            # 只给了号码没给场景：跟这条消息对一下，对不上就按 QQ 号处理
            return ("group", target) if target == group_id else ("friend", target)
        if scene == "group":
            return scene, group_id
        if scene == "friend":
            return scene, sender_id
        return ("group", group_id) if group_id else ("friend", sender_id)

    @filter.llm_tool(name="karin_logs")
    async def karin_logs(self, event: AstrMessageEvent, lines: int = 80, only_error: bool = True):
        """查看 Karin 的运时报错：最近的结构化错误（带堆栈）以及日志里的报错行。
        回答「Karin 那边怎么了 / 为什么没反应 / 报什么错了」时用这个。

        Args:
            lines(number): 从日志里取多少行，默认 80
            only_error(boolean): 只挑含 error/失败/异常 的行，默认 true；查一般活动时设为 false
        """
        if not self._enabled:
            return "karin_ctl 已关闭（配置项 enabled=false），请先在 AstrBot 面板打开。"
        data = await self._post("logs", {"lines": lines, "onlyError": bool(only_error)})
        blocks = []
        errors = data.get("errors") or []
        if errors:
            blocks.append(f"Karin 进程内有 {data.get('errorCount', 0)} 条错误记录，最近 {len(errors)} 条：")
            for e in errors:
                head = " ".join(x for x in [e.get("time"), e.get("type")] if x)
                blocks.append(f"- {head} {e.get('message')}".strip())
                if e.get("stack"):
                    blocks.append("  " + str(e["stack"]).replace("\n", "\n  "))
        else:
            blocks.append("Karin 进程内没有捕获到未处理错误。")
        log = _clip(str(data.get("log") or "").strip(), LOG_LIMIT)
        if log:
            blocks.append(f"日志（来源 {data.get('source') or 'unknown'}）：\n{log}")
        else:
            blocks.append("日志为空或读取失败，请检查 Karin 的 HTTP_PORT 与日志目录。")
        return "\n".join(blocks)

    @filter.llm_tool(name="karin_status")
    async def karin_status(self, event: AstrMessageEvent):
        """查看 Karin 的运行状态：在线 Bot、主人列表、消息前缀。"""
        if not self._enabled:
            return "karin_ctl 已关闭（配置项 enabled=false），请先在 AstrBot 面板打开。"
        self._self_check = await self._probe()
        data = await self._post("status", {})
        bots = data.get("bots") or []
        lines = []
        if self._self_check:
            lines.append(self._self_check)
        lines.append(
            "Bot：" + ("、".join(f"{b['selfId']} {b.get('name', '')}".strip() for b in bots) or "无")
        )
        lines.append("主人：" + ("、".join(data.get("master") or []) or "未配置"))
        lines.append("前缀：" + "、".join(data.get("prefix") or []))
        return "\n".join(lines)