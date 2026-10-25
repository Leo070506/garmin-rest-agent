import argparse
import json
import sys
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
from importlib import metadata, util
from pathlib import Path

from . import __version__
from .analysis import build_evidence, report_window
from .browser import connection_plan, import_browser
from .config import Config, load_config
from .demo import demo_days
from .normalize import normalize_day
from .preferences import (
    GOALS,
    WEEKDAYS,
    interactive_setup,
    load_preferences,
    save_preferences,
    schedule_plan,
    validate,
)
from .report import save_report
from .sources import make_source, sync
from .storage import project_lock, read_days, save_day

DEFAULT_CONFIG = '''timezone = "Asia/Shanghai"
region = "cn"
source = "community"
data_dir = "data"
report_dir = "reports"
token_dir = "tokens"
sleep_goal_hours = 7.5
baseline_days = 28
minimum_baseline_samples = 7

codex_command = "codex"
codex_timeout_seconds = 180
'''


def generate(cfg, kind, as_of, use_codex=False, topics=None):
    preferences = load_preferences(cfg.root, cfg.timezone, cfg.sleep_goal_hours)
    if topics is not None:
        preferences = validate(replace(preferences, topics=tuple(topics)))
    cfg = replace(cfg, timezone=preferences.timezone, sleep_goal_hours=preferences.sleep_goal_hours)
    start, _ = report_window(kind, as_of)
    rows = read_days(cfg.path("data_dir") / cfg.region,
                     start - timedelta(days=cfg.baseline_days + 1), as_of)
    if not rows:
        raise ValueError("没有本地数据。请先登录并 sync，或先运行 demo。")
    evidence = build_evidence(rows, cfg, kind, as_of, preferences)
    folder = save_report(cfg.path("report_dir"), evidence)
    if use_codex:
        from .codex import narrate
        narrate(cfg, evidence, folder)
    return folder


def parser():
    p = argparse.ArgumentParser(description="Garmin Rest Agent / 佳息：本地睡眠与训练报告")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--config", type=Path, default=Path("config.toml"))
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="创建配置，不登录、不联网")
    init.add_argument("--source", choices=["browser", "community", "personal"], default="community")
    init.add_argument("--region", choices=["cn", "global"], default="cn")
    sub.add_parser("connection-plan", help="显示官方网页登录入口；不会宣称已验证登录")
    sub.add_parser("login", help="由本人在终端交互登录；密码不保存")
    sub.add_parser("doctor", help="只检查本地环境，不显示凭据")
    sub.add_parser("setup", help="交互式首次引导；保存偏好，不启用任务")
    sub.add_parser("profile", help="读取已保存偏好及首次设置状态")
    sub.add_parser("schedule-plan", help="依据偏好预览汇报计划，不创建任务")
    c = sub.add_parser("configure", help="由 Codex 根据用户答案保存/修改偏好，不启用任务")
    c.add_argument("--topics", help="逗号分隔，可多选：sleep,recovery,activity,training,steps")
    c.add_argument("--frequency", choices=["daily", "weekly", "both", "manual"])
    c.add_argument("--daily-time")
    c.add_argument("--weekly-day", choices=WEEKDAYS)
    c.add_argument("--weekly-time")
    c.add_argument("--timezone")
    c.add_argument("--detail", choices=["brief", "detailed"])
    c.add_argument("--goal", choices=GOALS)
    c.add_argument("--sleep-goal-hours", type=float)
    s = sub.add_parser("sync", help="获取只读指标；最近两天重新同步")
    s.add_argument("--days", type=int, default=42)
    s.add_argument("--through", type=date.fromisoformat)
    s.add_argument("--refresh", action="store_true", help="重新读取范围内的所有日期")
    for command in ("report", "run"):
        r = sub.add_parser(command, help="生成本地报告" if command == "report" else "同步后生成报告，供计划任务运行")
        r.add_argument("--kind", choices=["morning", "weekly"], default="morning")
        r.add_argument("--as-of", type=date.fromisoformat, help="报告生成日（用户配置的本地时区）")
        r.add_argument("--codex", action="store_true", help="调用已登录的 Codex CLI 解读证据，消耗其额度")
        r.add_argument("--topics", help="仅本次覆盖主题，不改变用户偏好")
    d = sub.add_parser("demo", help="合成数据离线演示；不会读取 Garmin 或调用 AI")
    d.add_argument("--output", type=Path, default=Path("demo-local"))
    d.add_argument("--as-of", type=date.fromisoformat, default=date(2026, 10, 26))
    im = sub.add_parser("import-json", help="导入标准原始数据包，格式见 docs/data-contract.md")
    im.add_argument("input", type=Path)
    web = sub.add_parser("import-browser", help="导入 Codex 从官方网页可见内容读取的少量指标")
    web.add_argument("input", type=Path)
    return p


def execute(args):
    if args.command == "init":
        target = args.config.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as stream:
            stream.write(DEFAULT_CONFIG.replace('source = "community"', f'source = "{args.source}"')
                         .replace('region = "cn"', f'region = "{args.region}"'))
        print(f"已创建 {target}，接入方式为 {args.source}；请先查看 README 的连接说明。")
        return
    if args.command == "demo":
        root = args.output.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        config_path = root / "config.toml"
        if config_path.exists():
            cfg = load_config(config_path)
            if cfg.source != "files":
                raise ValueError("demo 不能使用真实配置目录，请换一个全新的 --output。")
        else:
            cfg = Config(root=root, source="files")
            config_path.write_text(DEFAULT_CONFIG.replace('source = "community"', 'source = "files"'),
                                   encoding="utf-8")
        with project_lock(cfg.path("data_dir")):
            existing = read_days(cfg.path("data_dir") / cfg.region, date.min, date.max)
            if any(not x.get("is_demo", False) for x in existing):
                raise ValueError("demo 目录中存在真实数据，拒绝混用。")
            for row in demo_days(args.as_of, cfg.tz):
                save_day(cfg.path("data_dir") / cfg.region, row)
            for kind in ("morning", "weekly"):
                print(generate(cfg, kind, args.as_of))
        print("合成示例已生成，未访问 Garmin，未发送任何 AI 请求。")
        return
    if args.command in {"setup", "configure", "profile", "schedule-plan"}:
        cfg_path = args.config.expanduser().resolve()
        cfg = load_config(cfg_path) if cfg_path.exists() else Config(root=cfg_path.parent)
        current = load_preferences(cfg.root, cfg.timezone, cfg.sleep_goal_hours)
        if args.command == "profile":
            print(json.dumps(asdict(current), ensure_ascii=False, indent=2))
            return
        if args.command == "schedule-plan":
            plan = schedule_plan(current)
            plan.update(collection_method=cfg.source, system_scheduler_supported=cfg.source in {"community", "personal"})
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return
        if args.command == "setup":
            selected = interactive_setup(current)
        else:
            updates = {key: getattr(args, key) for key in ["frequency", "daily_time", "weekly_day",
                       "weekly_time", "timezone", "detail", "goal", "sleep_goal_hours"]
                       if getattr(args, key) is not None}
            if args.topics is not None:
                updates["topics"] = tuple(x.strip() for x in args.topics.split(","))
            if not updates:
                raise ValueError("configure 至少需要一个用户选定的设置。")
            selected = validate(replace(current, configured=True, **updates))
        if not cfg_path.exists():
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(DEFAULT_CONFIG, encoding="utf-8")
        save_preferences(cfg.root, selected)
        print(json.dumps({"preferences": asdict(selected), "schedule": schedule_plan(selected)},
                         ensure_ascii=False, indent=2))
        return
    cfg = load_config(args.config)
    preferences = load_preferences(cfg.root, cfg.timezone, cfg.sleep_goal_hours)
    cfg = replace(cfg, timezone=preferences.timezone, sleep_goal_hours=preferences.sleep_goal_hours)
    today = datetime.now(cfg.tz).date()
    if args.command == "connection-plan":
        print(json.dumps(connection_plan(cfg), ensure_ascii=False, indent=2))
        return
    if args.command == "doctor":
        packages = {}
        for name, module in [("garminconnect", "garminconnect"),
                             ("garmin-connect-personal-api-python", "garmin_personal_api")]:
            try:
                packages[name] = metadata.version(name)
            except metadata.PackageNotFoundError:
                packages[name] = "source import" if util.find_spec(module) else "not installed"
        print(json.dumps({"version": __version__, "python": sys.version.split()[0],
                          "timezone": cfg.timezone, "region": cfg.region, "source": cfg.source,
                          "today_local": today.isoformat(), "data_dir": str(cfg.path("data_dir")),
                          "dependencies": packages, "codex_command": cfg.codex_command},
                         ensure_ascii=False, indent=2))
        return
    with project_lock(cfg.path("data_dir")):
        if args.command == "import-browser":
            packet = json.loads(args.input.read_text(encoding="utf-8-sig"))
            print(json.dumps(import_browser(packet, cfg), ensure_ascii=False, indent=2))
        elif args.command == "login":
            source = make_source(cfg, interactive=True)
            close = getattr(source.client, "close", None)
            if close:
                close()
            print("登录成功。会话仅留在本地；请勿分享 tokens 目录。")
        elif args.command == "sync":
            if args.through and args.through > today:
                raise ValueError("不能同步未来日期。")
            print(json.dumps(sync(cfg, args.through or today, args.days, args.refresh), ensure_ascii=False))
        elif args.command in {"report", "run"}:
            as_of = args.as_of or today
            selected_topics = tuple(x.strip() for x in args.topics.split(",")) if args.topics else None
            if selected_topics is not None:
                validate(replace(preferences, topics=selected_topics))
            if args.command == "run" and cfg.source != "files":
                if as_of > today:
                    raise ValueError("不能同步未来日期。")
                print(json.dumps(sync(cfg, as_of, min(90, cfg.baseline_days + 14), topics=selected_topics),
                                 ensure_ascii=False))
            print(generate(cfg, args.kind, as_of, args.codex, selected_topics))
        elif args.command == "import-json":
            obj = json.loads(args.input.read_text(encoding="utf-8-sig"))
            incoming = obj.get("days") if isinstance(obj, dict) else None
            if not isinstance(incoming, list) or not incoming:
                raise ValueError("需要包含非空 days 数组的数据包。")
            prepared = []
            for raw in incoming:
                day = date.fromisoformat(raw["date"])
                payload = raw["payload"]
                if not isinstance(payload, dict):
                    raise ValueError("payload 必须是对象。")
                status = {k: "ok" if k in payload else "missing" for k in
                          ["sleep", "stats", "hrv", "stress", "body_battery", "activities"]}
                prepared.append(normalize_day(day, payload, cfg.tz, f"import:{cfg.region}", status))
            for row in prepared:
                save_day(cfg.path("data_dir") / cfg.region, row)
            print(f"已导入 {len(prepared)} 天；姓名、GPS 和原始身份字段未保存。")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        execute(args)
        return 0
    except KeyboardInterrupt:
        print("已取消。", file=sys.stderr)
        return 130
    except Exception as exc:
        # Unexpected errors are summarized too; third-party errors may contain tokens or payloads.
        if isinstance(exc, (ValueError, RuntimeError, FileExistsError)):
            message = str(exc) if not isinstance(exc, FileExistsError) else "目标配置已存在，未覆盖。"
        else:
            message = f"操作失败（{type(exc).__name__}）；检查输入和依赖，未打印敏感响应。"
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
