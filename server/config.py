import os
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent


def _load_env_file():
    path = SERVER_DIR / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _flag(name, default="0"):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def get_settings():
    _load_env_file()
    try:
        timeout = float(os.environ.get("COZE_TIMEOUT_SECONDS", "120"))
    except ValueError:
        timeout = 120.0
    style = os.environ.get("COZE_IMAGE_VALUE_STYLE", "json_string").strip() or "json_string"
    return {
        "db_path": os.environ.get("FOOD_DB_PATH", str(SERVER_DIR / "data" / "food.db")),
        "upload_dir": os.environ.get("FOOD_UPLOAD_DIR", str(SERVER_DIR / "uploads")),
        "coze_api_base": os.environ.get("COZE_API_BASE", "https://api.coze.cn").rstrip("/"),
        "coze_api_token": os.environ.get("COZE_API_TOKEN", "").strip(),
        "coze_workflow_id": os.environ.get("COZE_WORKFLOW_ID", "").strip(),
        "coze_image_param": os.environ.get("COZE_IMAGE_PARAM", "image").strip() or "image",
        "coze_image_value_style": style,
        "coze_timeout": timeout,
        "coze_is_async": _flag("COZE_IS_ASYNC"),
        "coze_mock": _flag("COZE_MOCK"),
    }
