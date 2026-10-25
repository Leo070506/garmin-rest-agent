import json
import os
import time
from datetime import date, timedelta
from getpass import getpass

from .config import Config
from .normalize import normalize_day
from .preferences import TOPICS, load_preferences, merge_selected, requested_endpoints
from .storage import save_day


def error_code(exc):
    code = getattr(exc, "status_code", None)
    if code is None:
        code = getattr(getattr(exc, "response", None), "status_code", None)
    return code


def checked_call(call):
    """One request only. Stop on auth/rate limits, retain missing endpoint status."""
    try:
        value = call()
        return value, "ok" if value is not None else "missing"
    except Exception as exc:
        code = error_code(exc)
        name = type(exc).__name__
        if code in {401, 403, 429} or "Authentication" in name or "TooManyRequests" in name:
            raise RuntimeError(f"Garmin 认证/权限/限流错误（{code or name}）；已停止，不会循环重试。") from None
        if code in {404, 204} or "NotFound" in name:
            return None, "unavailable"
        raise RuntimeError(f"Garmin 请求失败（{name}）；已停止，稍后再试。") from None


class CommunitySource:
    def __init__(self, cfg: Config, interactive=False, topics=None):
        self.topics = topics or load_preferences(cfg.root, cfg.timezone, cfg.sleep_goal_hours).topics
        try:
            from garminconnect import Garmin
        except ImportError:
            raise ValueError('请先安装社区接入依赖：python -m pip install ".[community]"') from None
        self.cfg = cfg
        tokens = cfg.path("token_dir") / cfg.region
        tokens.mkdir(parents=True, exist_ok=True)
        if interactive:
            email = input("Garmin 邮箱或手机号（仅传给 Garmin）：").strip()
            password = getpass("Garmin 密码（不写入配置或日志）：")
            self.client = Garmin(email, password, is_cn=cfg.region == "cn",
                                 prompt_mfa=lambda: input("Garmin 验证码：").strip(), retry_attempts=1)
        else:
            if not any(tokens.iterdir()):
                raise ValueError("尚未登录；请本人在终端运行 login，再运行同步任务。")
            self.client = Garmin(is_cn=cfg.region == "cn", retry_attempts=1)
        try:
            self.client.login(tokenstore=str(tokens))
        except Exception as exc:
            raise RuntimeError(f"Garmin 登录失败（{type(exc).__name__}）；请本人重新运行 login。") from None
        self.kind = f"community:{cfg.region}"

    def fetch(self, day: str) -> tuple[dict, dict]:
        payload, status = {}, {}
        calls = {
            "sleep": lambda: self.client.get_sleep_data(day),
            "stats": lambda: self.client.get_stats(day),
            "hrv": lambda: self.client.get_hrv_data(day),
            "stress": lambda: self.client.get_stress_data(day),
            "body_battery": lambda: self.client.get_body_battery(day, day),
            "activities": lambda: self.client.get_activities_by_date(day, day),
        }
        for key, call in calls.items():
            if key not in requested_endpoints(self.topics):
                payload[key], status[key] = None, "not_requested"
                continue
            payload[key], status[key] = checked_call(call)
            time.sleep(0.15)
        return payload, status


class PersonalSource:
    def __init__(self, cfg: Config, interactive=False, topics=None):
        self.topics = topics or load_preferences(cfg.root, cfg.timezone, cfg.sleep_goal_hours).topics
        if cfg.region != "global":
            raise ValueError("本版未确认官方 Personal API 的中国区端点；中国区请选择 community。")
        try:
            from garmin_personal_api import GarminPersonalApiClient, PersonalApiAuthenticator
        except ImportError:
            raise ValueError('请先安装官方接入依赖：python -m pip install ".[personal]"') from None
        key = os.environ.get("GARMIN_PERSONAL_API_KEY", "").strip()
        if not key and interactive:
            key = getpass("Garmin Personal API Key（仅本次使用，不保存）：").strip()
        if not key:
            raise ValueError("请在本地配置 GARMIN_PERSONAL_API_KEY；不要把密钥发给 agent。")
        cache = cfg.path("token_dir") / "personal" / "bearer.json"
        try:
            with PersonalApiAuthenticator(bearer_token_cache_file=cache, timeout=30) as auth:
                if auth.base_url != "https://personal.connectapi.garmin.com":
                    raise ValueError("非默认 Personal API 端点被拒绝。")
                token = auth.obtain_token(key)
            self.client = GarminPersonalApiClient(token.access_token, timeout=30)
        except Exception as exc:
            raise RuntimeError(f"Personal API 认证失败（{type(exc).__name__}）。") from None
        # Do not inherit SDK endpoint overrides that might send credentials to another host.
        if self.client.base_url != "https://personal.connectapi.garmin.com":
            self.client.close()
            raise ValueError("检测到 Personal API 的非默认端点配置；请移除该覆盖设置后再运行。")
        self.kind = "personal:global"

    def fetch(self, day: str) -> tuple[dict, dict]:
        payload, status = {}, {}
        calls = {
            "sleep": lambda: self.client.get_daily_sleep(day),
            "stats": lambda: self.client.get_daily_summaries(day, day),
            "hrv": lambda: self.client.get_daily_hrv(day),
            "body_battery": lambda: self.client.get_daily_body_battery(day, day),
        }
        for key, call in calls.items():
            if key not in requested_endpoints(self.topics):
                payload[key], status[key] = None, "not_requested"
                continue
            payload[key], status[key] = checked_call(call)
        payload["stress"], status["stress"] = {}, "from_stats"
        if "activities" not in requested_endpoints(self.topics):
            payload["activities"], status["activities"] = None, "not_requested"
            return payload, status
        # Retrieve all pages; never interpret the first page as the entire day.
        activities = []
        for page in range(20):
            rows, state = checked_call(lambda page=page: self.client.search_activities(
                start=page * 100, limit=100, start_date=day, end_date=day))
            if state != "ok":
                payload["activities"], status["activities"] = None, state
                break
            if not isinstance(rows, list):
                raise ValueError("Personal API 活动响应结构变化；无法确认活动完整性。")
            activities.extend(rows)
            if len(rows) < 100:
                payload["activities"], status["activities"] = activities, "ok"
                break
        else:
            raise ValueError("活动分页超过上限，停止，避免生成不完整的训练总量。")
        return payload, status


def make_source(cfg: Config, interactive=False, topics=None):
    if cfg.source == "browser":
        raise ValueError("网页模式需要 Codex 打开已登录的官方网页，读取本次日期的指标，再运行 import-browser 和 report。"
                         "CLI 不会直接复用浏览器凭据；后台采集可另选 community 方式。")
    if cfg.source == "files":
        raise ValueError("files 模式不访问网络；请导入数据或运行 report。")
    return (CommunitySource if cfg.source == "community" else PersonalSource)(cfg, interactive, topics)


def sync(cfg: Config, through: date, days=42, refresh=False, topics=None) -> dict:
    if not 1 <= days <= 90:
        raise ValueError("单次同步范围必须在 1–90 天之间。")
    selected = topics or load_preferences(cfg.root, cfg.timezone, cfg.sleep_goal_hours).topics
    source = make_source(cfg, topics=selected)
    root = cfg.path("data_dir") / cfg.region
    fetched = skipped = 0
    try:
        for offset in range(days - 1, -1, -1):
            day = through - timedelta(days=offset)
            path = root / f"{day.isoformat()}.json"
            cached = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            # Recent two calendar days are refreshed because sync is eventually consistent.
            if cached and offset >= 2 and not refresh and set(selected).issubset(cached.get("collected_topics", TOPICS)):
                skipped += 1
                continue
            payload, status = source.fetch(day.isoformat())
            normalized = normalize_day(day, payload, cfg.tz, source.kind, status)
            save_day(root, merge_selected(cached, normalized, selected))
            fetched += 1
    finally:
        close = getattr(source.client, "close", None)
        if close:
            close()
    return {"fetched_days": fetched, "cached_days": skipped}
