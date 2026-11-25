import json
import os
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent


def setup_stdout():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def load_config(path=None):
    p = Path(path) if path else SKILL_DIR / "config.json"
    if not p.exists():
        p = SKILL_DIR / "config.example.json"
    return json.loads(p.read_text(encoding="utf-8"))


def resolve(path_str):
    """상대경로는 스킬 디렉터리 기준."""
    p = Path(path_str)
    return p if p.is_absolute() else SKILL_DIR / p


def secret(env_name):
    v = os.environ.get(env_name)
    if not v:
        raise RuntimeError(f"환경변수 {env_name} 가 설정되지 않았습니다")
    return v
