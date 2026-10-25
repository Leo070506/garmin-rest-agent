"""Build a self-contained SKILL bundle from the one maintained Python source tree."""
import shutil
import zipfile
from pathlib import Path


def build(root: Path, output: Path):
    skill = output / "garmin-rest-coach"
    if skill.exists():
        raise FileExistsError(f"Choose a fresh output directory: {skill}")
    shutil.copytree(root / "skills" / "garmin-rest-coach", skill)
    shutil.copy2(root / "LICENSE", skill / "LICENSE")
    target = skill / "scripts" / "garmin_rest_agent"
    shutil.copytree(root / "src" / "garmin_rest_agent", target,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    archive = output / "garmin-rest-coach.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(skill.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(output))
    print(archive)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    build(Path(__file__).resolve().parents[1], args.output.resolve())
