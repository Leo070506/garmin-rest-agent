# 官方网页登录与网页读取

此路径在用户自己的 Codex 和浏览器里运行，不是第三方 OAuth 授权服务。中国区用
`https://connect.garmin.cn/modern/`，国际区用 `https://connect.garmin.com/modern/`。
浏览器会话不导出给本地脚本，不从磁盘、开发者工具、网络记录提取 Cookie/token。

## 首次连接

1. 沿用已知区域；不清楚才询问“中国区还是国际区”。用户要网页登录就选 browser。
   新配置运行 `python TOOL --config CONFIG init --source browser --region cn`，再运行 `connection-plan`。
   已有配置不覆盖；用户明确切换接入方式时仅修改 source/region，保留其他设置与历史。
2. 使用当前环境的浏览器工具打开 plan 返回的官方 URL，并展示给用户完成登录。
   在无浏览器工具时，提供可点击的官方入口并说明尚不能自动读取页面，不宣称已连接。
   用户在官方页面输入账号、密码和验证码；不要接管输入或要求把凭据发进聊天。
3. 用户说“已登录”后检查页面。仍在登录页就说明未完成；有验证码或风险验证时交给用户。
   不能仅根据“已登录”或页面标题判断读取成功，不承诺保持永久登录。
4. 按 onboarding.md 选择关注主题和时间，只进入相关页面。确认网页显示的记录日期、指标标签和单位，
   至少读取一项用户选中的带日期指标，才回显“已能读取中国区佳明网页数据”。
   看不到指标时说明“网页已登录，但尚未验证数据读取”，保留设置供下次继续。
5. 导入并生成一份首报，核对日期和数字；再回显计划并处理用户已授权的定时汇报。

## 日常读取

重用当前同一用户的已登录页面；根据当前 DOM/可访问性内容导航，网页结构会变，不假定固定选择器。
只读取页面上实际可见的日期和数值，不调用隐藏接口，不分析全量个人页面，不复制活动标题或位置。
读取主题、报告期和历史范围以用户请求为准。首次只读本期；个人基线需要的额外历史要说明范围，
用户已请求历史趋势时可按该范围读取。页面不能完整取得 28 天就用已有覆盖，不伪造完整基线。

晨报睡眠取今早醒来日期；运动和步数取昨天。周报取上一完整周一至周日。
“睡眠 7小时30分”换算为 `sleep_hours=7.5`，距离公里、活动时长分钟、HRV 毫秒。
睡眠分数不是睡眠小时，周平均 HRV 不是昨夜夜间 HRV；页面没有的指标用 null。
睡眠起止仅在日期与时区都明确时记录；不要根据时间文字猜测跨日日期。
活动只有确认日期筛选、分页和当日所有记录后才标记 `activities_complete=true`；未完整读取不填零次运动。

## 网页指标包

把必要数值写到用户数据目录的临时 `browser-readings.json`，不保存网页截图、原始 DOM 或凭据。
`page_url` 仅保存官方来源入口或页面路径，去掉查询、片段、个人标识；导入后不会持久化此 URL。
每项记录需明确主题和日期，来自不同主题页面的同一天可分成两条记录，导入时合并。

```json
{
  "schema_version": 1,
  "region": "cn",
  "days": [{
    "date": "2026-10-25",
    "date_confirmed": true,
    "page_url": "https://connect.garmin.cn/modern/",
    "topics": ["sleep"],
    "measurements": {"sleep_hours": 7.5, "sleep_score": 82}
  }]
}
```

可选数值：`deep_minutes`、`rem_minutes`、`resting_hr`、`hrv_ms`、`stress_mean`、
`body_battery_max`、`body_battery_min`、`steps`；均需对应已选主题。
可选 `sleep_start` / `sleep_end` 为含时区的 ISO 日期时间。
活动记录：`activities: [{"type":"running","duration_min":30,"distance_km":5,"average_hr":140}]`，
另用顶层 `activities_complete` 表示该日期已完整读取；活动类型无法映射时用 `other`。

```text
python TOOL --config CONFIG import-browser BROWSER_READINGS_JSON
python TOOL --config CONFIG report --kind morning
```

脚本校验结构和数值，不认证网页或验证抄录真伪；需由当前 agent 核对实际页面。
不要在网页模式调用 `login`、`sync`、`run` 或嵌套 `--codex`；它们不能使用该浏览器会话。

## 定时与重新连接

网页模式只能由**有浏览器访问能力**的 Codex 自动化执行“打开页面→核对日期→读取→导入→报告”。
先验证该调度环境的浏览器能力；当前聊天可访问不代表后台也可访问。Windows 纯 CLI 安装器会拒绝此模式。
不具备时让用户选择手动报告，或另行连接 community 适配器用于后台采集；不要悄悄切换。
登录失效时通知用户重新打开官方网页完成登录；不反复尝试、不更换区域、不读取凭据、不发过期数据冒充新报告。
