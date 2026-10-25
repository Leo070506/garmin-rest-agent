# 佳息 · Garmin Rest Agent for Codex

**让 Codex 用你的佳明数据，写一份有依据的晨间休息报告和每周恢复与训练报告。**

本地运行，数据由用户保管；第一版只面向 Codex。包含可分发 skill、Python 工具、合成示例和定时运行脚本。
独立开源项目，与 Garmin 无隶属关系。MIT 许可证不替代 Garmin 的接口使用条款。

## 安装到 Codex

需要 Codex 和 Python **3.12+**。网页模式还需要 Codex 能访问用户登录的浏览器。

**直接让 Codex 安装**，把下面这句话发给它：

```text
使用 skill-installer，从 https://github.com/Leo070506/garmin-rest-agent/tree/main/codex-skills/garmin-rest-coach 安装这个 skill。
```

也可下载 [v0.1.0 Skill 安装包](https://github.com/Leo070506/garmin-rest-agent/releases/download/v0.1.0/garmin-rest-coach.zip)，
把里面的 `garmin-rest-coach` 文件夹放入 `~/.codex/skills/`；设置了 `CODEX_HOME` 时使用其下的 `skills/`。
Windows 的默认位置是 `%USERPROFILE%\.codex\skills\`。不要覆盖已有同名 skill。
Windows 对应 Python 环境还需 `python -m pip install tzdata`。只使用网页模式无需安装 Garmin SDK。

安装后重新打开 Codex 聊天，输入：

```text
使用 $garmin-rest-coach，帮我连接中国区佳明，设置我关注的数据、汇报频率和时间。
```

默认从官方网页登录开始，由用户自行登录，再核对数据、保存偏好、生成首报。
首次调用才会开始引导；安装不会直接开启对话或自动启用汇报。
该版本是预览版：离线功能已测试，真实中国区登录、网页到首报全流程和后台浏览器访问仍需实测。

[下载与版本说明](https://github.com/Leo070506/garmin-rest-agent/releases/tag/v0.1.0) ·
[反馈问题](https://github.com/Leo070506/garmin-rest-agent/issues)

## 1. 不登录，先看演示

需要 Python **3.12+**。在项目目录运行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m garmin_rest_agent demo --output demo-local
```

打开 `demo-local/reports/morning-2026-10-26/report.html` 或同目录的周报。
演示使用 50 天**合成数据**，不读取账号、不调用 Codex、不产生模型费用。
macOS/Linux 把 `.venv\Scripts\python.exe` 换为 `.venv/bin/python`。

## 首次使用：由 Codex 引导个性化设置

安装 skill 后，在 Codex 点击 skill 或说“帮我设置佳明报告”。第一次调用先完成连接：

1. 选择账号区域，中国区打开 [佳明 Connect](https://connect.garmin.cn/modern/)。
2. Codex 打开可访问的浏览器页面，用户在官方网页自行登录，不在聊天里输入密码或验证码。
3. 登录后核对所选主题的一项带日期指标，确认能读取，再生成第一份报告。

网页登录模式由 Codex 读取**网页可见内容**，不导出 Cookie，不是第三方 OAuth 授权。
当前 Codex 需要有浏览器访问能力；若只能打开外部浏览器而无法读取，必须说明尚未连接成功。
网页可能改版、会话可能过期；本版已验证离线导入和报告，**尚未完整实测网页登录到首报的全流程**。

第一次使用还会检查偏好并询问：

1. 关注哪些数据（可多选）：睡眠、恢复、日常运动、训练、步数。
2. 多久汇报：每天、每周、每天加每周、仅手动。
3. 每日几点；每周几、几点；按哪个时区。可选目标、简短/详细报告和个人睡眠目标。

选择保存到用户配置目录的 `preferences.json`，后续沿用，也可说“以后只看睡眠和步数”
或“改成每周一晚上八点”。只选睡眠不会展开训练指标；晨报的步数取昨天，不拿今天尚未完成的数据比较。
修改主题保留历史数据，不清空未选项；只修改 JSON 不会自动更改已有任务。

skill 安装本身不能主动开启对话；**首次调用时引导**。先回显用户的具体安排，再启用/更新实际任务。
保存偏好不等于定时任务已启用。完整规则在 skill 的 `references/onboarding.md`。

也可在终端运行 `python -m garmin_rest_agent setup`，或让 Codex 根据回答执行：

```powershell
.\.venv\Scripts\python.exe -m garmin_rest_agent configure --topics sleep,recovery,steps --frequency both --daily-time 08:00 --weekly-day Monday --weekly-time 20:00 --detail brief --goal recovery
.\.venv\Scripts\python.exe -m garmin_rest_agent profile
.\.venv\Scripts\python.exe -m garmin_rest_agent schedule-plan
```

最后一条只预览，不安装任务。`report --topics steps` 仅覆盖本次关注内容，不修改长期偏好。
可直接打开 [睡眠＋步数的合成示例](examples/personalized-sleep-steps/report.html) 查看按主题筛选的报告。

## 2. 中国区：连接自己的佳明

### 网页登录，由当前 Codex 读取

让 Codex 使用 skill 的 [网页连接流程](skills/garmin-rest-coach/references/browser.md)。本地工具入口为：

```powershell
python -m garmin_rest_agent --config private/config.toml init --source browser --region cn
python -m garmin_rest_agent --config private/config.toml connection-plan
```

`connection-plan` 返回官方入口，不会自行验证登录或宣称连接成功。Codex 打开网页供用户登录后，
只转录选中主题的日期与数值，用 `import-browser` 导入，再运行 `report`。
工具不读取浏览器内部凭据、隐藏接口或整份账号导出。不具备可见日期的指标不会被当作当日数据。
网页模式的定时汇报要求**定时运行的 Codex 本身也有浏览器访问能力**；否则用手动报告或下面的后台适配器。

### 可选后台适配器，由本人在终端登录

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[community]"
.\.venv\Scripts\python.exe -m garmin_rest_agent init
.\.venv\Scripts\python.exe -m garmin_rest_agent setup
```

编辑 `config.toml`，确认 `region="cn"`、`source="community"`，时区与 Garmin 账号一致。
在**本人终端**登录，然后同步：

```powershell
.\.venv\Scripts\python.exe -m garmin_rest_agent login
.\.venv\Scripts\python.exe -m garmin_rest_agent sync --days 42
.\.venv\Scripts\python.exe -m garmin_rest_agent report --kind morning
.\.venv\Scripts\python.exe -m garmin_rest_agent report --kind weekly
```

密码隐藏输入，项目不保存密码。社区 SDK 把会话 token 存到本地 `tokens/cn/`，供之后运行复用。
**不要把密码、验证码、token 或数据目录发给 agent、上传仓库。** 浏览器登录不会自动建立 CLI 会话。
认证/权限/限流失败就停止，不提供绕验证或无限重登功能。

接入依赖 [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) 的 `is_cn=True`。
本版核对了已发布 SDK 的接口并用替身测试；**尚未完成真实中国区登录实测**。
社区接口可能随佳明服务变动而失效，有适配器不等于保证所有账号均能连接。

## 3. 在 Codex 里用 skill 解读

在项目内对 Codex 说：

> 使用 skills/garmin-rest-coach/SKILL.md，先引导我设置关注内容、频率和汇报时间，再生成报告。
> 先用本地工具计算，再解读 evidence.json，给出可核对的结论和建议。不要再启动另一个 Codex。

不需要额外模型 API Key；由当前 Codex 对话的模型解读。把证据交给 Codex 会按当前账户/工作区
的模型和数据规则处理，不能理解为模型在本机离线推理。
数据工具本地去掉姓名、GPS、账号 ID 和运动自定义标题，只把少量指标交给解读步骤。

分发自包含 skill：

```powershell
.\.venv\Scripts\python.exe scripts/build_skill.py --output skill-release
```

生成 `skill-release/garmin-rest-coach.zip`，内含完整计算引擎。把解压后的目录放入 Codex 的
skills 目录，例如 `~/.codex/skills/`，重新打开聊天。不要覆盖已有同名 skill。
用户配置和凭据必须放在 skill 外。Skill 依然需要用户在对应 Python 环境安装所选 Garmin 依赖。
也可先让 Codex 直接读取本项目的 SKILL.md，无需全局安装。

仓库的 `skills/` 是维护用模板；`codex-skills/garmin-rest-coach/` 是包含完整引擎的安装目录，
由上述构建脚本生成。发布更新时从模板和 `src/` 重新构建并同步安装目录，勿手工维护两套计算逻辑。

## 4. 无人值守的 Codex 报告

如果安装了 **Codex CLI** 并由本人完成 `codex login`，可执行：

```powershell
.\.venv\Scripts\python.exe -m garmin_rest_agent run --kind morning --codex
.\.venv\Scripts\python.exe -m garmin_rest_agent run --kind weekly --codex
```

工具先同步、计算、保存基础报告，再通过 `codex exec` 把数字证据送进现有 Codex，保存
`agent-report.md` 和 `agent-report.html`。沿用用户当前的模型与认证配置，不强制换模型。
会消耗该 Codex 配置对应的额度或费用；没有独立的“免费 AI”承诺。
Codex 在单独临时工作目录里、只读沙箱下执行；不传入 Garmin 原始数据或 token 文件，
不使用跳过审批/沙箱的参数。不从正在分析的 Codex 对话里再次加 `--codex`，以免重复调用。

没有 CLI 时仍可在 Codex app 中用 skill 完成解读。CLI 缺失、超时、登录或额度错误时保留
基础报告，返回失败状态，不静默重试。**CLI 进程协议经过替身测试；未自动启动真实付费模型。**
[官方非交互说明](https://learn.chatgpt.com/docs/non-interactive-mode)。

## 5. 每天晨报、周一周报

Windows 先预览：

```powershell
powershell -File scripts/install_schedule.ps1 -UseCodex
```

不会安装任务。确认时间和模型额度消耗后，本人追加 `-Install`。
此脚本适用于 community/personal 后台采集；browser 模式会拒绝安装纯 CLI 任务。
默认按已保存的偏好选择每日/每周/两者及其时间；仅手动模式不会创建任务。
Windows 本地时区应与偏好时区一致。电脑需开机且用户已登录；
错过时间可补跑，不能保证关机/休眠时准点生成。无 `-UseCodex` 时只生成基础报告。
脚本不保存 Windows 密码、不提权、不唤醒电脑，不发邮件或消息，也不会覆盖现有同名任务。
任务计划的环境需要能找到 Codex CLI，或在配置中指定 `codex_command` 的完整路径。
修改偏好后先预览，再用 `-Install -UpdateExisting` 更新同项目任务；不再需要的同项目任务会取消。
不修改其他项目/程序的任务。可用 `-MorningAt` / `-WeeklyAt` 临时覆盖偏好中的时间。

也可在 Codex 的受支持自动化功能里使用 [docs/codex-automations.md](docs/codex-automations.md) 的
提示词，让自动化调用本地工具并在同一次 Codex 运行内解读。**安装 skill 不等于启用计划任务。**
其他系统的调度和限制见 [docs/scheduling.md](docs/scheduling.md)。本项目没有替你注册任何任务。

## 国际区：可选官方 Personal API

配置 `region="global"`、`source="personal"`，安装 `python -m pip install -e ".[personal]"`。
本人在 [Garmin Connect](https://connect.garmin.com/app/settings/personalApiToken) 创建 Personal API Key，
接受条款并在本地配置 `GARMIN_PERSONAL_API_KEY`。项目使用官方 SDK、把 token 缓存在本地。
**本版未确认中国区官方 Personal API 地址，不会猜地址或把中国区凭据发到国际区。**
个人 API 用于各用户读取自己的数据；多人托管服务需另行核对 Garmin Business 接入要求。
参考：[官方个人 API](https://developer.garmin.com/gc-developer-program/personal/personal-api/)。

## 日期与判断规则

- 晨报 `--as-of 2026-10-25`：睡眠为 25 日醒来的那一觉；白天活动为 24 日。
- 周报 `--as-of 2026-10-26`：上一完整周 19–25 日。星期日运行仍分析上一完整周。
- 不传日期时按配置时区确定今天。睡眠从 GMT 时间戳转换一次，避免中国区重复加八小时。
- 个人基线为报告期之前 28 天，至少 7 天有效样本才比较。报告期不混入自己的基线。
- 缺失不补零。无活动记录不等于没有运动；覆盖不足不作完整周总量比较。
- 运动分钟不是生理训练负荷。没有 HRV 的手表仍可生成睡眠报告。
- 不造综合恢复分、不诊断疾病、不根据一次分数增加高强度训练。

## 报告文件

| 文件 | 用途 |
|---|---|
| `report.md` / `report.html` | 可编辑基础报告，无外部网页资源 |
| `evidence.json` | 数字、逐项覆盖率、个人基线和限制 |
| `agent-prompt.md` | 给 Codex 的解读输入 |
| `generation.json` | 基础报告生成时间 |
| `agent-report.md` / `agent-report.html` | 可选 Codex 解读报告 |
| `codex-generation.json` | 可选 CLI 解读来源；AI 正文没有独立事实审核 |

默认保存在 `reports/<kind>-<生成日期>/`。先同步手表再运行。
接口采集时间不等于手表同步时间；缺少昨晚睡眠时明确等待数据，不偷用前一晚冒充。
数据、token、报告已加入 `.gitignore`；已经提交的文件不受其保护，发布前仍需检查内容。
不同账号使用不同配置和数据目录。本版不提供多人登录服务器。

## 开发与后续版本

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m garmin_rest_agent doctor
```

核心：`sources / 网页指标导入 → normalize → analysis → evidence/report → Codex`。
测试使用合成数据和替身，不读取真实健康数据。真实 Garmin 登录、真实 CLI 模型调用仍需用户本地验证。
导入合同见 [docs/data-contract.md](docs/data-contract.md)，设计边界见 [docs/architecture.md](docs/architecture.md)。
DeepSeek、WorkBuddy、消息推送和托管网页列为后续方向，本版不宣称支持。
