# MultipleCheckin 🐱

基于青龙面板的多平台自动签到脚本集合，覆盖顺丰速运、WPS Office、什么值得买、WorkBuddy、Trae CN、Agent Router 等平台。

> **⚠️ 免责声明**
> 本项目中的大量代码由 AI 辅助编写生成，代码规范和格式可能存在不足之处，敬请见谅。
> 本项目仅供学习交流使用，请勿用于商业用途。使用本项目所造成的一切后果由使用者自行承担。

---

##  拉库命令

### 青龙面板（QingLong）

**推荐方式：使用 `ql git` 整库克隆（避免文件缺失）**

`ql repo` 默认只识别 `.py` / `.js` / `.ts` / `.sh` 等脚本文件，会自动跳过 `config/`、`tests/` 等非脚本目录。由于本项目脚本依赖 `_shared` 共享包、`notification` 推送模块，且必须在 `config/token.json` 中配置账号，请使用 `ql git` 整库克隆：

```bash
ql git https://github.com/angussleeping/MultipleCheckin.git main
```

克隆完成后所有文件位于 `/ql/data/scripts/MultipleCheckin/`，包含完整目录结构：

```
/ql/data/scripts/MultipleCheckin/
├── config/                  # 账号与推送配置
├── notification/            # 统一推送模块
├── script/
│   ├── _shared/             # 共享基础设施
│   ├── sf/                  # 顺丰
│   ├── wps/                 # WPS
│   ├── smzdm/               # 什么值得买
│   ├── workbuddy/           # WorkBuddy
│   ├── trae/                # Trae CN
│   └── agentrouter/         # Agent Router
└── ...
```

#### 配置步骤

1. **安装依赖**（在青龙容器内执行一次）：

```bash
pip3 install -r /ql/data/scripts/MultipleCheckin/requirements.txt
```

2. **填写配置文件**（`config/token.json` 已随仓库提供占位模板，直接编辑即可）：

```bash
cd /ql/data/scripts/MultipleCheckin/config
vi token.json              # 填写各平台账号,字段说明见下文
vi notification.json       # 可选,不需要推送可跳过
```

也可在青龙面板「配置文件」页面，于 `MultipleCheckin/config/` 下直接编辑 `token.json`。

3. **添加定时任务**：在青龙面板「定时任务」中新建任务，例如：

| 名称 | 命令 | 定时规则 |
|---|---|---|
| 顺丰签到 | `task MultipleCheckin/script/sf/main.py` | `0 8 * * *` |
| WPS 签到 | `task MultipleCheckin/script/wps/main.py` | `30 8 * * *` |
| SMZDM 签到 | `task MultipleCheckin/script/smzdm/sign_daily_task/main.py` | `0 9 * * *` |
| WorkBuddy 签到 | `task MultipleCheckin/script/workbuddy/main.py` | `30 8 * * *` |
| Trae CN 签到 | `task MultipleCheckin/script/trae/main.py` | `0 9 * * *` |
| Agent Router 签到 | `task MultipleCheckin/script/agentrouter/main.py` | `30 9 * * *` |

> **⚠️ 不要使用 `ql repo` 拉取本仓库**：它会跳过 `config/`、`notification/` 等目录，导致脚本运行时找不到配置文件或导入失败。

### 呆呆面板（DaiDai）

呆呆面板基于 Docker，挂载方式与青龙类似，但推荐使用**整库 clone**：

```bash
# 进入容器
docker exec -it daidai bash

# 克隆到脚本目录
cd /root/scripts
git clone https://github.com/angussleeping/MultipleCheckin.git
```

然后在呆呆面板的「脚本管理」中新建定时任务，例如：

| 名称 | 命令 |
|---|---|
| WPS 签到 | `python3 /root/scripts/MultipleCheckin/script/wps/main.py` |
| SMZDM 签到 | `python3 /root/scripts/MultipleCheckin/script/smzdm/sign_daily_task/main.py` |

依赖安装（一次性）：

```bash
pip3 install -r /root/scripts/MultipleCheckin/requirements.txt
```

---

## ✅ 脚本可用性状态

| 平台 | 脚本路径 | 状态 | 说明 |
|---|---|---|---|
| 🚚 顺丰速运 | `script/sf/main.py` | ✅ 可用 | 支持签到和积分任务 |
| 📝 WPS Office | `script/wps/main.py` | ✅ 可用 | 支持任务中心和天天领福利双页面任务 |
| 💰 什么值得买 | `script/smzdm/sign_daily_task/main.py` | ✅ 可用 | 支持每日签到、众测/互动/爆料任务 |
| 🤖 WorkBuddy | `script/workbuddy/main.py` | ✅ 可用 | 支持每日签到、令牌自动续期 |
| 🐅 Trae CN | `script/trae/main.py` | ✅ 可用 | 支持积分模式每日签到 |
| 🚀 Agent Router | `script/agentrouter/main.py` | ✅ 可用 | OAuth 登录即签到、余额查询 |

### 状态说明

- ✅ **可用**：脚本完整且功能正常，可以直接使用
- ⚠️ **部分可用**：脚本基本可用，但可能存在某些功能限制
- 🚧 **开发中**：脚本正在开发或测试阶段
- ❌ **不可用**：脚本存在问题或已废弃

---

## ⚙️ 配置说明

### 配置文件位置

所有账号与推送配置统一放在 `config/` 目录，青龙面板可直接在「配置文件」中编辑：

- `config/token.json`：各平台账号 Cookie / Token（必填）
- `config/notification.json`：推送渠道配置（可选，不配置则不推送）

仓库中的这两个文件是**占位模板**，直接在其中填写真实账号信息即可：

> ⚠️ 填写后的 `config/token.json` 含真实凭证。如果 fork 或推送到公开仓库，请先用
> `git rm --cached config/token.json config/notification.json` 取消跟踪，避免凭证泄露。

### 各平台 Cookie / Token 配置

下面列出每个平台在 `config/token.json` 中需要填写的关键字段及获取方式。

#### 🚚 顺丰速运（`sf`）

```json
"sf": {
  "accounts": [
    {
      "account_name": "大号",
      "sign": "顺丰 APP 分享链接中的 sign 参数",
      "channel": "weixin",
      "device_id": "设备ID",
      "user_agent": ""
    }
  ]
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `sign` | ✅ | 顺丰 APP「分享」生成的签名，脚本用它换登录态；**有效期很短**，失效后需重新获取 |
| `channel` | ✅ | 渠道标识，PC 浏览器抓包可得，常见值 `weixin` |
| `device_id` | ✅ | APP 侧设备标识，需从 APP 抓包获取 |
| `user_agent` | ❌ | 留空则使用脚本内置 UA |

获取方式：

1. **`sign`**：手机打开顺丰速运 APP → 进入积分/福利页面 → 点「分享」→ 复制分享链接，链接里 `sign=xxxx` 的值即为所需（脚本会自动 URL 解码，原样粘贴即可）。分享链接需在 APP 内生成，**PC 浏览器无法直接获取**。
2. **`channel`**：PC 浏览器登录 [顺丰福利页](https://mcs-mimp-web.sf-express.com/superWelfare)，DevTools → Network → 任一 `/mcs-mimp/` 请求 → 请求头 `channel` 的值。
3. **`device_id`**：从顺丰 APP 抓包（请求体中的 `deviceId` / 请求头设备标识）获取；浏览器侧没有这个值。

> `cookies` / `user_id` 已不再需要填写：脚本会通过 `sign` 调用分享登录接口自动换取。

#### 📝 WPS Office（`wps`）

```json
"wps": {
  "accounts": [
    {
      "account_name": "大号",
      "user_id": 123456789,
      "cookies": "从 wps.cn 登录后的完整 Cookie（含 wps_sid / csrf）",
      "user_agent": "浏览器 UA，例如 Mozilla/5.0 (Windows NT 10.0; ...)"
    }
  ]
}
```

获取方式：浏览器登录 [https://account.wps.cn](https://account.wps.cn)，打开 DevTools → Network，从任意请求复制 `Cookie` 与 `User-Agent`。

#### 💰 什么值得买（`smzdm`）

```json
"smzdm": {
  "accounts": [
    {
      "name": "111",
      "cookie": "从 smzdm APP 抓包获取的 Cookie（含 sess= 字段）",
      "user_agent": "APP 抓包 UA，例如 smzdm 11.1.35 rv:167 ...",
      "setting": "APP 抓包请求中的 setting 字段"
    }
  ]
}
```

获取方式：抓包什么值得买 APP，请求头里的 `Cookie`、`User-Agent` 以及 body 里的 `setting` 字段。

> **注意**：`cookie` 中必须包含 `sess=xxx`，脚本会从该字段提取 token 计算签名。

#### 🤖 WorkBuddy（`workbuddy`）

```json
"workbuddy": {
  "accounts": [
    {
      "account_name": "主号",
      "email": "you@example.com",
      "access_token": "从官方客户端导入或手动填入",
      "refresh_token": "refresh_token",
      "uid": "用户ID",
      "enterprise_id": "企业ID（个人版留空）",
      "domain": "域名（个人版留空）"
    }
  ]
}
```

获取方式（推荐）：使用脚本一键从官方客户端导入——

```bash
python3 script/workbuddy/import_accounts.py
```

或参考 [script/workbuddy/README.md](script/workbuddy/README.md) 手动从 [cockpit-tools](https://github.com/jlcodes99/cockpit-tools) 批量导入。

> **注意**：`access_token` 有效期 60 天，`refresh_token` 90 天，脚本支持过期自动续期并回写配置。

#### 🐅 Trae CN（`trae`）

```json
"trae": {
  "accounts": [
    {
      "account_name": "主号",
      "sessionid": "浏览器 Cookie 中的 sessionid 值"
    }
  ]
}
```

获取方式：浏览器登录 [https://www.trae.cn](https://www.trae.cn)，DevTools → Application → Cookies → `sessionid` 字段。

> 脚本会自动调用登录刷新接口换取访问令牌，无需手动维护 access_token。

####  Agent Router（`agentrouter`）

```json
"agentrouter": {
  "accounts": [
    {
      "account_name": "主号",
      "github_session": "GitHub 登录后 Cookie 中的 user_session 值"
    }
  ]
}
```

获取方式：浏览器登录 GitHub 后，DevTools → Cookies → `user_session` 字段。

---

## 📢 通知推送配置（可选）

所有平台共用一套推送配置 `config/notification.json`，按需启用至少一个渠道即可。支持以下渠道：

| 渠道 | 关键字段 | 获取方式 |
|---|---|---|
| Bark | `bark.push` / `bark.sckey` | iOS Bark APP 推送 Key |
| Server酱 | `server.sckey` / `server.sendkey` | [sct.ftqq.com](https://sct.ftqq.com) |
| CoolPush | `coolpush.skey` | [cp.xuthus.cc](https://cp.xuthus.cc) |
| Qmsg酱 | `qmsg.key` | [qmsg.zendee.cn](https://qmsg.zendee.cn) |
| Telegram | `telegram.bot_token` + `telegram.user_id` | @BotFather + @userinfobot |
| 飞书 | `feishu.key` | 飞书自定义机器人 Webhook 地址末尾 key |
| 钉钉 | `dingtalk.access_token` + `dingtalk.secret` | 钉钉自定义机器人 Webhook 与加签 |
| 企业微信 | `qywx.key` / `qywx.corpid` + `agentid` + `corpsecret` | 企业微信机器人 / 应用消息 |
| PushPlus | `pushplus.token` | [pushplus.plus](https://pushplus.plus) |
| PushDeer | `pushdeer.pushkey` | [pushdeer.com](https://pushdeer.com) |
| Gotify | `gotify.url` + `gotify.token` | 自建 Gotify 服务 |
| Ntfy | `ntfy.url` + `ntfy.topic` | [ntfy.sh](https://ntfy.sh) |

> 优先级：`config/notification.json` > 环境变量 > 默认值。环境变量名约定为 `QIYE_WEIXIN_KEY`、`BARK_PUSH` 等，与原 ZaiZaiCat-Checkin 项目保持一致。

---

## 🏗️ 项目结构

```
MultipleCheckin/
├── config/
│   ├── token.json                  # 账号配置（占位模板，按需填写）
│   └── notification.json           # 推送配置（占位模板，可选）
├── notification/                   # 统一推送模块
│   ├── manager.py                  # 渠道编排入口
│   ├── config_loader.py            # 配置加载
│   └── channels/                   # 各推送渠道实现
├── script/
│   ├── _shared/                    # 共享基础设施（日志/HTTP/配置/调度/报告）
│   │   ├── logging.py
│   │   ├── http_client.py          # 带重试 Session + post_and_parse 统一响应解析
│   │   ├── config.py
│   │   ├── runner.py               # 启动抖动 + 账号间隔
│   │   └── report.py               # 结果汇总 + 推送
│   ├── sf/                         # 顺丰速运
│   ├── wps/                        # WPS Office
│   │   ├── main.py
│   │   ├── task_center.py          # 任务中心
│   │   ├── daily_benefits.py       # 天天领福利
│   │   └── benefit_entry.py        # 福利入口发现
│   ├── smzdm/                      # 什么值得买
│   │   ├── api/
│   │   │   ├── api.py              # SmzdmAPI 门面（经 Mixin 组合）
│   │   │   ├── activity.py         # 众测任务
│   │   │   ├── tasks.py            # 任务执行
│   │   │   ├── checkin.py          # 每日签到
│   │   │   ├── follow.py           # 关注用户
│   │   │   ├── baoliao.py          # 爆料
│   │   │   └── sign_calculator.py
│   │   └── sign_daily_task/
│   │       └── main.py
│   ├── workbuddy/                  # WorkBuddy
│   ├── trae/                       # Trae CN
│   └── agentrouter/                # Agent Router
├── tests/                          # 单元测试（pytest）
├── requirements.txt
└── README.md
```

---

##  各平台详细文档

- 顺丰速运（配置字段见上方「各平台 Cookie / Token 配置」）
- [WPS Office](script/wps/README.md)
- [什么值得买](script/smzdm/README.md)
- [WorkBuddy](script/workbuddy/README.md)
- [Trae CN](script/trae/README.md)
- [Agent Router](script/agentrouter/README.md)

---

## 📝 更新日志

### 2026-10-26

- 🏗️ **大规模重构**：抽离 `script/_shared/` 共享基础设施包（日志/HTTP/配置/调度/报告）
- 🔀 **收敛 `_post` 骨架**：trae/workbuddy 复用 `_shared.http_client.post_and_parse`
- ✂️ **拆分大文件**：
  - `wps/daily_benefits.py` 由 2075 行降至 1943 行，福利入口发现逻辑抽到 `benefit_entry.py`
  - `smzdm/api/api.py` 由 2016 行降至 152 行，按业务域拆为 activity/tasks/checkin/follow/baoliao 五个 Mixin，对外 API 不变
-  **修复**：workbuddy/main.py 中 print 改为 logger.error
- ✅ **测试**：新增 send_summary_notification 4 个分支测试，全部 40 个测试通过

### 2026-09-12
- ✨ 新增 Trae CN、Agent Router 自动签到模块
- 🧹 精简账号配置并移除签到前自动同步逻辑

### 2026-09-06
- ✨ 新增 WorkBuddy(CodeBuddy) 自动签到模块，支持令牌过期自动刷新

### 2026-03-11
- ✨ WPS 脚本升级为多页面任务：任务中心 + 天天领福利

更早的变更请参考原仓库 [ZaiZaiCat-Checkin](https://github.com/Cat-zaizai/ZaiZaiCat-Checkin)。

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

## ⚠️ 注意事项

1. 本项目仅供学习交流使用，请勿用于商业用途
2. 使用本项目所造成的一切后果由使用者自行承担
3. 请合理使用自动签到功能，避免对平台造成负担
4. Cookie 等敏感信息请妥善保管，不要泄露给他人
5. 定期更新 Cookie，避免失效影响使用
6. 代码由 AI 辅助生成，可能存在不规范之处

## 📄 开源协议

本项目采用 [MIT License](LICENSE) 开源协议。

## 🙏 致谢

- 感谢原项目作者 [@Cat-zaizai](https://github.com/Cat-zaizai)
- 感谢青龙面板提供的自动化平台[@whyour](https://github.com/whyour)
- 感谢呆呆面板提供的自动化平台[@linzixuanzz](https://github.com/linzixuanzz)

---

**⭐ 如果这个项目对你有帮助，欢迎给个 Star！**
