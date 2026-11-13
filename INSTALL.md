# astrbot-plugin-karin-ctl 安装说明

打好的包在本地 `dist/` 下（zip 与解压副本各一份），**不需要编译**——单个 `main.py`，第三方依赖只有 `aiohttp`（AstrBot 自带；`requirements.txt` 也只有它）。

## 安装

1. AstrBot → 插件管理 → 安装插件 → 填仓库地址 `https://github.com/YlovexLN/astrbot-plugin-karin-ctl`
   （仓库根目录就是插件根目录，`metadata.yaml` 在根上），或上传本地打好的 `dist/astrbot-plugin-karin-ctl-v0.0.1.zip`
2. 插件配置里填两项：
   - `karin_url`：Karin 的 **HTTP_PORT**（默认 7777，不是 WebUI 端口）。容器之间不能用 `127.0.0.1`
   - `karin_token`：与 Karin 的 `HTTP_AUTH_KEY`（或 `ASTRBOT_BRIDGE_TOKEN`）一致
3. 重启 AstrBot。日志里应出现 `[karin_ctl] 已加载：自动补卡片=开，Karin=http://...`，
   这一行同时证明插件已加载、Karin 地址已填
4. 对 AstrBot 说「用 karin_status 看看 Karin」——第一行就是连通自检：

   | 输出 | 含义 |
   | --- | --- |
   | `✓ 已连通 Karin：http://...` | 通了 |
   | `⚠ 已连上 Karin 但 token 不对（401）` | 两边 token 不一致 |
   | `⚠ Karin 里的 bridge 插件还没配 token（500）` | Karin 侧没填 |
   | `⚠ 连不上 ...（ClientConnectorError）` | 地址/端口不对，或跨容器用了 127.0.0.1 |

手动装也行（不解压）：把本仓库的文件拷到
`data/plugins/astrbot_plugin_karin_ctl/`（目录名必须与 `metadata.yaml` 的 `name` 一致），重启即可。

## 配套的 Karin 侧

另一个仓库 `karin-plugin-astrbot-bridge`（`dist/karin-plugin-astrbot-bridge-v0.0.1.zip`）负责提供
`/api/v1/astrbot/*` 接口。两个包必须一起装，token 两边填一致。

## 重新打包

```bash
node scripts/pack.mjs
```

只用 Node 标准库，不装依赖、不需要 Python。每次都重新生成 zip 与 `dist/astrbot-plugin-karin-ctl/` 解压副本，两者内容保证一致。
