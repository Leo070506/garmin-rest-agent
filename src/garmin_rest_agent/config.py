import tomllib
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class Config:
    root: Path
    timezone: str = "Asia/Shanghai"
    region: str = "cn"
    source: str = "community"
    data_dir: str = "data"
    report_dir: str = "reports"
    token_dir: str = "tokens"
    sleep_goal_hours: float = 7.5
    baseline_days: int = 28
    minimum_baseline_samples: int = 7
    codex_command: str = "codex"
    codex_timeout_seconds: int = 180

    def path(self, key: str) -> Path:
        return (self.root / getattr(self, key)).resolve()

    @property
    def tz(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("找不到时区；Windows 用户请安装 tzdata。") from exc


def load_config(path: Path) -> Config:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"配置文件不存在：{path}；请先运行 init。")
    obj = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    cfg = Config(root=path.parent, **obj)
    if cfg.region not in {"cn", "global"} or cfg.source not in {"browser", "community", "personal", "files"}:
        raise ValueError("region 或 source 无效。")
    if not 1 <= cfg.sleep_goal_hours <= 16 or not 7 <= cfg.baseline_days <= 90:
        raise ValueError("睡眠目标或基线天数超出配置范围。")
    if not 3 <= cfg.minimum_baseline_samples <= cfg.baseline_days:
        raise ValueError("minimum_baseline_samples 必须在 3 与 baseline_days 之间。")
    if not 30 <= cfg.codex_timeout_seconds <= 900:
        raise ValueError("codex_timeout_seconds 必须在 30–900 之间。")
    _ = cfg.tz
    return cfg
