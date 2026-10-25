import json
import os
import tempfile
from contextlib import contextmanager
from datetime import date
from pathlib import Path


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".pending-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(obj, stream, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def save_day(root: Path, day: dict) -> None:
    key = date.fromisoformat(day["date"]).isoformat()
    write_json(root / f"{key}.json", day)


def read_days(root: Path, start: date, end: date) -> list[dict]:
    rows = []
    for path in sorted(root.glob("????-??-??.json")):
        try:
            day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if start <= day <= end:
            obj = json.loads(path.read_text(encoding="utf-8"))
            if obj.get("date") != path.stem or obj.get("schema_version") != 1:
                raise ValueError(f"缓存日期或版本不匹配：{path.name}")
            rows.append(obj)
    return rows


@contextmanager
def project_lock(root: Path):
    """Exclude concurrent sync/report runs; never silently remove another run's lock."""
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".run.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError("另一个任务正在运行，或遗留了 .run.lock；确认没有运行任务后再移除锁文件。") from exc
    try:
        with os.fdopen(fd, "w", encoding="ascii") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)
