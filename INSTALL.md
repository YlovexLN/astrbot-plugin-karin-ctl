# 安装

打好的包在 `dist/` 下（zip 与解压副本各一份），**不需要编译**——单个 `main.py`，第三方依赖只有 `aiohttp`（AstrBot 自带）。

1. AstrBot → 插件管理 → 安装插件 → 填仓库地址 `https://github.com/YlovexLN/astrbot-plugin-karin-ctl`（仓库根目录就是插件根），或上传 `dist/astrbot-plugin-karin-ctl-v0.0.1.zip`。
2. 配置里填两项：`karin_url` = Karin 的 **HTTP_PORT**（默认 7777，不是 WebUI 端口；容器之间不能用 `127.0.0.1`）；`karin_token` = Karin 的 `HTTP_AUTH_KEY`（或 `ASTRBOT_BRIDGE_TOKEN`）。
3. 重启 AstrBot，日志里应出现 `[karin_ctl] 已加载：自动补卡片=开，Karin=http://...`——这一行同时证明插件已加载、Karin 地址已填。
4. 对 AstrBot 说「用 karin_status 看看 Karin」，第一行就是自检：`✓ 已连通` / `⚠ 401 token 不对` / `⚠ 500 bridge 没配 token` / `⚠ 连不上（ClientConnectorError）`，后三种的排查见排障文档。

手动装也行：把仓库文件拷到 `data/plugins/astrbot_plugin_karin_ctl/`（目录名必须与 `metadata.yaml` 的 `name` 一致）后重启。

## 配套的 Karin 侧

另一个仓库 `karin-plugin-astrbot-bridge` 提供 `/api/v1/astrbot/*`。两个包必须一起装，`karin_token` 两边填一致。

## 重新打包

```bash
node scripts/pack.mjs    # 只用 Node 标准库；每次重新生成 zip 与 dist/astrbot-plugin-karin-ctl/ 解压副本
```
