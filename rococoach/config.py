import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def get_mode() -> str:
    load_dotenv(ROOT / ".env", override=False)
    mode = os.getenv("ROCOCOACH_MODE", "mock").strip().lower()
    if mode != "mock":
        raise ValueError("当前版本仅支持 mock 模式，请将 ROCOCOACH_MODE 设置为 mock。")
    return mode
