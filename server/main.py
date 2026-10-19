import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .coze_client import CozeError, recognize
from .config import get_settings
from .db import (
    create_session,
    create_user,
    delete_record,
    delete_session,
    find_user_by_token,
    find_user_by_username,
    calendar_month,
    get_energy_day,
    get_record,
    init_db,
    insert_record,
    list_records,
    list_records_on_day,
    replace_record,
    save_energy_day,
)
from .parser import parse_workflow_payload
from .passwords import hash_password, new_token, verify_password

MAX_IMAGE_BYTES = 8 * 1024 * 1024


def create_app():
    settings = get_settings()
    init_db(settings["db_path"])
    upload_dir = Path(settings["upload_dir"])
    upload_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="膳识", version="1.0.0")
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def http_error(_request, exc):
        detail = exc.detail if isinstance(exc.detail, str) else "请求参数不正确"
        return JSONResponse(status_code=exc.status_code, content={"message": detail})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, _exc):
        return JSONResponse(status_code=422, content={"message": "请求参数不正确"})

    @app.get("/api/health")
    def health():
        current = app.state.settings
        configured = bool(current["coze_api_token"] and current["coze_workflow_id"])
        return {
            "status": "ok",
            "coze_configured": configured,
            "mock": current["coze_mock"],
        }

    @app.post("/api/register")
    def register(body: AuthBody):
        username, password = _check_account(body)
        db_path = app.state.settings["db_path"]
        user_id = create_user(db_path, username, hash_password(password), _now())
        if user_id is None:
            raise HTTPException(status_code=400, detail="这个用户名已经注册过了")
        return _issue_session(db_path, user_id, username)

    @app.post("/api/login")
    def login(body: AuthBody):
        username = (body.username or "").strip()
        password = body.password or ""
        db_path = app.state.settings["db_path"]
        user = find_user_by_username(db_path, username)
        if user is None or not verify_password(password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="用户名或密码不正确")
        return _issue_session(db_path, user["id"], user["username"])

    @app.post("/api/logout")
    def logout(authorization: str = Header(default="")):
        token = _read_token(authorization)
        if token:
            delete_session(app.state.settings["db_path"], token)
        return {"ok": True}

    @app.post("/api/identify/submit")
    async def identify_submit(
        background_tasks: BackgroundTasks,
        username: str = Form(""),
        password: str = Form(""),
        file: UploadFile = File(...),
    ):
        db_path = app.state.settings["db_path"]
        user = find_user_by_username(db_path, (username or "").strip())
        if user is None or not verify_password(password or "", user["password_hash"]):
            raise HTTPException(status_code=401, detail="用户名或密码不正确")
        content = await file.read()
        stored_name = _store_image(
            app.state.settings,
            content,
            file.filename or "",
            file.content_type or "",
        )
        background_tasks.add_task(
            _recognize_stored_image,
            app.state.settings,
            stored_name,
            user["id"],
            _now(),
        )
        return {"ok": True, "status": "processing"}

    @app.post("/api/identify")
    async def identify(file: UploadFile = File(...), authorization: str = Header(default="")):
        user = _require_user(app.state.settings["db_path"], authorization)
        content = await file.read()
        return await asyncio.to_thread(
            _identify_sync,
            app.state.settings,
            content,
            file.filename or "",
            file.content_type or "",
            user["id"],
        )

    @app.post("/api/energy")
    def save_energy(body: EnergyBody):
        username = (body.username or "").strip()
        password = body.password or ""
        db_path = app.state.settings["db_path"]
        user = find_user_by_username(db_path, username)
        if user is None or not verify_password(password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="用户名或密码不正确")
        day = _parse_day(body.date) if body.date else _now()[:10]
        resting = _energy_number(body.resting_kcal)
        active = _energy_number(body.active_kcal)
        return save_energy_day(
            db_path,
            user["id"],
            day,
            resting,
            active,
            _now(),
        )

    @app.get("/api/energy")
    def read_energy(date: str = "", authorization: str = Header(default="")):
        user = _require_user(app.state.settings["db_path"], authorization)
        day = _parse_day(date) if date else _now()[:10]
        return get_energy_day(app.state.settings["db_path"], user["id"], day)

    @app.get("/api/records")
    def records(
        limit: int = 20,
        offset: int = 0,
        date: str = "",
        authorization: str = Header(default=""),
    ):
        user = _require_user(app.state.settings["db_path"], authorization)
        if date:
            return list_records_on_day(
                app.state.settings["db_path"],
                user["id"],
                _parse_day(date),
            )
        safe_limit = max(1, min(int(limit), 50))
        safe_offset = max(0, int(offset))
        return list_records(app.state.settings["db_path"], user["id"], safe_limit, safe_offset)

    @app.get("/api/calendar")
    def calendar(month: str = "", authorization: str = Header(default="")):
        user = _require_user(app.state.settings["db_path"], authorization)
        if not month:
            month = _now()[:7]
        return calendar_month(
            app.state.settings["db_path"],
            user["id"],
            _parse_month(month),
        )

    @app.get("/api/records/{record_id}")
    def record_detail(record_id: int, authorization: str = Header(default="")):
        user = _require_user(app.state.settings["db_path"], authorization)
        row = get_record(app.state.settings["db_path"], record_id, user["id"])
        if row is None:
            raise HTTPException(status_code=404, detail="记录不存在")
        return row

    @app.post("/api/records/{record_id}/retake")
    async def retake_record(
        record_id: int,
        file: UploadFile = File(...),
        authorization: str = Header(default=""),
    ):
        user = _require_user(app.state.settings["db_path"], authorization)
        content = await file.read()
        return await asyncio.to_thread(
            _retake_sync,
            app.state.settings,
            content,
            file.filename or "",
            file.content_type or "",
            user["id"],
            record_id,
        )

    @app.delete("/api/records/{record_id}")
    def remove_record(record_id: int, authorization: str = Header(default="")):
        user = _require_user(app.state.settings["db_path"], authorization)
        image_path = delete_record(app.state.settings["db_path"], record_id, user["id"])
        if image_path is None:
            raise HTTPException(status_code=404, detail="记录不存在")
        _remove_upload(app.state.settings["upload_dir"], image_path)
        return {"ok": True}

    app.mount("/uploads", StaticFiles(directory=str(upload_dir)), name="uploads")
    _mount_h5(app)
    return app


def _mount_h5(app):
    dist = os.environ.get("H5_DIST_DIR", "").strip()
    if not dist:
        return
    root = Path(dist)
    index_file = root / "index.html"
    if not index_file.is_file():
        return
    assets_dir = root / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="h5-assets")

    @app.get("/", include_in_schema=False)
    def h5_index():
        return FileResponse(str(index_file))


class AuthBody(BaseModel):
    username: str = ""
    password: str = ""


class EnergyBody(BaseModel):
    username: str = ""
    password: str = ""
    date: str = ""
    resting_kcal: float = 0
    active_kcal: float = 0


_SHANGHAI = timezone(timedelta(hours=8))
_DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")


def _now():
    return datetime.now(_SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")


def _energy_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="热量需要是数字")
    if number < 0 or number > 20000:
        raise HTTPException(status_code=400, detail="热量需要在 0 到 20000 之间")
    return number


def _parse_day(value):
    if not _DAY_PATTERN.match(value or ""):
        raise HTTPException(status_code=400, detail="日期格式应为 YYYY-MM-DD")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="日期不正确")
    return value


def _parse_month(value):
    if not _MONTH_PATTERN.match(value or ""):
        raise HTTPException(status_code=400, detail="月份格式应为 YYYY-MM")
    try:
        parsed = datetime.strptime(value, "%Y-%m")
    except ValueError:
        raise HTTPException(status_code=400, detail="月份不正确")
    now = datetime.now(_SHANGHAI)
    current = now.year * 12 + now.month - 1
    asked = parsed.year * 12 + parsed.month - 1
    if asked > current or asked < current - 11:
        raise HTTPException(status_code=400, detail="只能查看最近一年的月份")
    return value


def _check_account(body):
    username = (body.username or "").strip()
    password = body.password or ""
    if len(username) < 3 or len(username) > 20:
        raise HTTPException(status_code=400, detail="用户名需要 3 到 20 个字符")
    if any(char.isspace() for char in username):
        raise HTTPException(status_code=400, detail="用户名不能包含空格")
    if len(password) < 6 or len(password) > 32:
        raise HTTPException(status_code=400, detail="密码需要 6 到 32 个字符")
    return username, password


def _read_token(authorization):
    if not authorization:
        return ""
    prefix = "bearer "
    if authorization.lower().startswith(prefix):
        return authorization[len(prefix):].strip()
    return ""


def _require_user(db_path, authorization):
    user = find_user_by_token(db_path, _read_token(authorization))
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def _issue_session(db_path, user_id, username):
    token = new_token()
    create_session(db_path, token, user_id, _now())
    return {"token": token, "username": username}


def _identify_sync(settings, content, filename, content_type, user_id):
    stored_name, nutrition, raw = _save_and_recognize(settings, content, filename, content_type)
    record_id = insert_record(
        settings["db_path"],
        {
            "image_path": "/uploads/" + stored_name,
            "foods": nutrition["foods"],
            "total_calories_kcal": nutrition["total_calories_kcal"],
            "summary": nutrition["summary"],
            "tips": nutrition["tips"],
            "raw_response": raw,
            "debug_url": nutrition.get("debug_url") or "",
            "created_at": _now(),
            "user_id": user_id,
        },
    )
    return get_record(settings["db_path"], record_id, user_id)


def _retake_sync(settings, content, filename, content_type, user_id, record_id):
    existing = get_record(settings["db_path"], record_id, user_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    stored_name, nutrition, raw = _save_and_recognize(settings, content, filename, content_type)
    replaced = replace_record(
        settings["db_path"],
        record_id,
        user_id,
        {
            "image_path": "/uploads/" + stored_name,
            "foods": nutrition["foods"],
            "total_calories_kcal": nutrition["total_calories_kcal"],
            "summary": nutrition["summary"],
            "tips": nutrition["tips"],
            "raw_response": raw,
            "debug_url": nutrition.get("debug_url") or "",
        },
    )
    if replaced is None:
        _remove_upload(settings["upload_dir"], "/uploads/" + stored_name)
        raise HTTPException(status_code=404, detail="记录不存在")
    _remove_upload(settings["upload_dir"], replaced["old_image_path"])
    return get_record(settings["db_path"], record_id, user_id)


def _store_image(settings, content, filename, content_type):
    if not content:
        raise HTTPException(status_code=400, detail="图片是空的")
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="图片不能超过 8MB")
    extension = _detect_extension(filename, content_type, content)
    if not extension:
        raise HTTPException(status_code=400, detail="请上传 jpg、png、webp、gif 或 heic 图片")
    upload_dir = Path(settings["upload_dir"])
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = uuid.uuid4().hex + extension
    (upload_dir / stored_name).write_bytes(content)
    return stored_name


def _nutrition_from_file(settings, stored_name):
    stored_path = Path(settings["upload_dir"]) / stored_name
    try:
        payload = recognize(settings, stored_path)
        nutrition = parse_workflow_payload(payload)
    except (CozeError, ValueError) as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
    raw = json.dumps(payload, ensure_ascii=False)
    if len(raw) > 20000:
        raw = raw[:20000]
    return nutrition, raw


def _recognize_stored_image(settings, stored_name, user_id, created_at):
    try:
        nutrition, raw = _nutrition_from_file(settings, stored_name)
    except Exception:
        return
    insert_record(
        settings["db_path"],
        {
            "image_path": "/uploads/" + stored_name,
            "foods": nutrition["foods"],
            "total_calories_kcal": nutrition["total_calories_kcal"],
            "summary": nutrition["summary"],
            "tips": nutrition["tips"],
            "raw_response": raw,
            "debug_url": nutrition.get("debug_url") or "",
            "created_at": created_at,
            "user_id": user_id,
        },
    )


def _save_and_recognize(settings, content, filename, content_type):
    stored_name = _store_image(settings, content, filename, content_type)
    nutrition, raw = _nutrition_from_file(settings, stored_name)
    return stored_name, nutrition, raw


def _remove_upload(upload_dir, image_path):
    name = Path(image_path).name
    if not name or name in (".", ".."):
        return
    target = Path(upload_dir) / name
    if target.is_file():
        target.unlink()


def _detect_extension(filename, content_type, content):
    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if content.startswith(b"GIF87a") or content.startswith(b"GIF89a"):
        return ".gif"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return ".webp"
    if b"ftyp" in content[:32]:
        return ".heic"
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/heic": ".heic",
        "image/heif": ".heic",
    }
    lowered = (content_type or "").split(";")[0].strip().lower()
    if lowered in mapping:
        return mapping[lowered]
    name = (filename or "").lower()
    for extension in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"):
        if name.endswith(extension):
            return ".jpg" if extension == ".jpeg" else ".heic" if extension == ".heif" else extension
    return None


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
