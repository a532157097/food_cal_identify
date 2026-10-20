# -*- coding: utf-8 -*-
"""识别接口自动化脚本：调用接口后用 sqlite 交叉核对，结束时恢复数据库文件。"""

import argparse
import base64
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="食物热量识别接口与数据库交叉验证")
    parser.add_argument("--db", default=str(Path(__file__).resolve().parent / "tmp_food_cal.db"))
    parser.add_argument("--upload-dir", default=str(Path(__file__).resolve().parent / "tmp_uploads"))
    return parser.parse_args(argv)


def expect(condition, message):
    if not condition:
        raise AssertionError(message)


def count_rows(db_path):
    connection = sqlite3.connect(str(db_path))
    try:
        return connection.execute("SELECT COUNT(*) FROM identify_record").fetchone()[0]
    finally:
        connection.close()


def query_row(db_path, record_id):
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(
            "SELECT * FROM identify_record WHERE id = ?",
            (record_id,),
        ).fetchone()
    finally:
        connection.close()


def count_uploads():
    upload_dir = Path(os.environ["FOOD_UPLOAD_DIR"])
    if not upload_dir.exists():
        return 0
    return len([item for item in upload_dir.iterdir() if item.is_file()])


def count_sessions(db_path):
    connection = sqlite3.connect(str(db_path))
    try:
        return connection.execute("SELECT COUNT(*) FROM auth_session").fetchone()[0]
    finally:
        connection.close()


def query_user(db_path, username):
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(
            "SELECT id, username, password_hash FROM user_account WHERE username = ?",
            (username,),
        ).fetchone()
    finally:
        connection.close()


def insert_calorie_row(db_path, user_id, created_at, kcal):
    connection = sqlite3.connect(str(db_path))
    try:
        cursor = connection.execute(
            """
            INSERT INTO identify_record (
                image_path, foods_json, total_calories_kcal, summary, tips,
                raw_response, debug_url, created_at, user_id
            ) VALUES ('/uploads/calendar-test.jpg', '[]', ?, '', '', '', '', ?, ?)
            """,
            (kcal, created_at, user_id),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def set_created_at(db_path, record_id, created_at):
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute(
            "UPDATE identify_record SET created_at = ? WHERE id = ?",
            (created_at, record_id),
        )
        connection.commit()
    finally:
        connection.close()


def delete_ids(db_path, record_ids):
    connection = sqlite3.connect(str(db_path))
    try:
        for record_id in record_ids:
            connection.execute("DELETE FROM identify_record WHERE id = ?", (record_id,))
        connection.commit()
    finally:
        connection.close()


def day_sums(db_path, user_id, month):
    year, mon = [int(part) for part in month.split("-")]
    if mon == 12:
        end = "%04d-01-01 00:00:00" % (year + 1)
    else:
        end = "%04d-%02d-01 00:00:00" % (year, mon + 1)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT substr(created_at, 1, 10) AS day,
                   SUM(COALESCE(total_calories_kcal, 0)) AS kcal,
                   COUNT(*) AS c
            FROM identify_record
            WHERE user_id = ? AND created_at >= ? AND created_at < ?
            GROUP BY day
            """,
            (user_id, month + "-01 00:00:00", end),
        ).fetchall()
        return {row["day"]: (float(row["kcal"]), int(row["c"])) for row in rows}
    finally:
        connection.close()


def count_user_rows(db_path, user_id):
    connection = sqlite3.connect(str(db_path))
    try:
        return connection.execute(
            "SELECT COUNT(*) FROM identify_record WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]
    finally:
        connection.close()


def restore_database(db_path, before_bytes):
    for suffix in ("-wal", "-shm"):
        extra = Path(str(db_path) + suffix)
        if extra.exists():
            extra.unlink()
    if before_bytes is None:
        if db_path.exists():
            db_path.unlink()
        return
    db_path.write_bytes(before_bytes)


def check_parser():
    from server.parser import parse_workflow_payload

    nutrition = {
        "foods": [{"name": "鸡蛋", "calories_kcal": 70, "weight_g": 50}],
        "summary": "一枚鸡蛋",
        "total_calories_kcal": 70,
    }
    wrapped = parse_workflow_payload(
        {
            "code": 0,
            "debug_url": "https://www.coze.cn/work_flow?execute_id=1",
            "data": json.dumps({"output": json.dumps(nutrition, ensure_ascii=False)}, ensure_ascii=False),
        }
    )
    expect(wrapped["foods"][0]["name"] == "鸡蛋", "结束节点 output 未解析出鸡蛋")
    expect(wrapped["debug_url"].startswith("https://"), "调试链接没有保留")

    fenced = parse_workflow_payload(
        {
            "code": 0,
            "data": "```json\n"
            + json.dumps({"foods": [{"name": "苹果", "calories_kcal": 52}], "summary": "一个苹果"}, ensure_ascii=False)
            + "\n```",
        }
    )
    expect(fenced["foods"][0]["name"] == "苹果", "代码块 JSON 未解析")
    expect(fenced["total_calories_kcal"] == 52, "缺少总热量时没有按分项求和")

    chinese = parse_workflow_payload(
        {
            "code": 0,
            "data": json.dumps(
                {
                    "食物列表": [
                        {
                            "食物名称": "番茄炒蛋",
                            "重量": "180克",
                            "热量": "210千卡",
                            "蛋白质": "12.5",
                            "脂肪": "14",
                            "碳水": "8",
                            "把握": "88%",
                        }
                    ],
                    "总热量": "210千卡",
                    "摘要": "一份番茄炒蛋",
                    "建议": "可以再加一份蔬菜",
                },
                ensure_ascii=False,
            ),
        }
    )
    food = chinese["foods"][0]
    expect(food["name"] == "番茄炒蛋", "中文食物名称未解析")
    expect(food["weight_g"] == 180, "中文重量未解析")
    expect(food["calories_kcal"] == 210, "中文热量未解析")
    expect(food["protein_g"] == 12.5, "蛋白质未解析")
    expect(food["confidence"] == 0.88, "把握百分比未换算")
    expect(chinese["total_calories_kcal"] == 210, "中文总热量未解析")
    expect(chinese["tips"] == "可以再加一份蔬菜", "建议未解析")

    sample = [
        {"food_name": "白米饭", "weight": 120, "note": "图片估算", "calories": 130, "protein": 2.6, "carb": 28, "fat": 0.3},
        {"food_name": "煎鸡胸肉", "weight": 100, "note": "图片估算", "calories": 165, "protein": 23, "carb": 0, "fat": 6},
        {"food_name": "清炒油麦菜", "weight": 150, "note": "图片估算", "calories": 45, "protein": 2, "carb": 4, "fat": 2.5},
    ]
    actual = parse_workflow_payload({"code": 0, "data": json.dumps(sample, ensure_ascii=False)})
    expect(actual["foods"][0]["name"] == "白米饭", "food_name 未解析")
    expect(actual["foods"][1]["weight_g"] == 100, "weight 未解析")
    expect(actual["foods"][1]["calories_kcal"] == 165, "calories 未解析")
    expect(actual["foods"][1]["protein_g"] == 23, "protein 未解析")
    expect(actual["foods"][1]["carb_g"] == 0, "为零的碳水被丢掉了")
    expect(actual["foods"][0]["carb_g"] == 28, "carb 未解析")
    expect(actual["foods"][2]["fat_g"] == 2.5, "fat 未解析")
    expect(actual["foods"][0]["note"] == "图片估算", "note 未保留")
    expect(actual["total_calories_kcal"] == 340, "数组结果没有按热量求和")
    expect(actual["summary"] == "白米饭、煎鸡胸肉、清炒油麦菜", "没有用食物名称生成摘要")

    envelope = {
        "content_type": 1,
        "data": json.dumps(sample, ensure_ascii=False),
        "original_result": None,
        "type_for_model": 2,
    }
    wrapped_sample = parse_workflow_payload({"code": 0, "data": envelope})
    expect(wrapped_sample["foods"][2]["name"] == "清炒油麦菜", "工作流 data 字段里的数组未解析")
    expect(wrapped_sample["total_calories_kcal"] == 340, "工作流包装结果的总热量不对")

    empty = parse_workflow_payload(
        {"code": 0, "data": {"content_type": 1, "data": "[]", "original_result": None, "type_for_model": 2}}
    )
    expect(empty["foods"] == [], "空数组不应该编造食物")
    expect(empty["summary"] == "没有识别到食物", "空数组没有给出说明")

    plain = parse_workflow_payload({"code": 0, "data": "这张图里像是一碗面"})
    expect(plain["foods"] == [], "纯文本不应该编造食物分项")
    expect("一碗面" in plain["summary"], "纯文本没有放进摘要")

    try:
        parse_workflow_payload({"code": 4000, "msg": "token invalid"})
        raise AssertionError("工作流错误码应该抛出")
    except ValueError as exc:
        expect("token invalid" in str(exc), "没有带回工作流错误信息")
    print("解析用例通过")


def check_image_parameter():
    from server.coze_client import CozeError, build_image_value, recognize

    string_value = build_image_value("file-1", "json_string")
    expect(json.loads(string_value)["file_id"] == "file-1", "图片参数字符串格式不正确")
    object_value = build_image_value("file-2", "object")
    expect(object_value["file_id"] == "file-2", "图片参数对象格式不正确")
    try:
        recognize(
            {"coze_mock": False, "coze_api_token": "", "coze_workflow_id": ""},
            Path("missing.jpg"),
        )
        raise AssertionError("未配置 Coze 时应该失败")
    except CozeError as exc:
        expect("COZE_API_TOKEN" in str(exc), "缺少配置时的提示不完整")
    print("Coze 参数用例通过")


def check_legacy_database():
    legacy = Path(__file__).resolve().parent / "tmp_legacy_food_cal.db"
    before_bytes = legacy.read_bytes() if legacy.exists() else None
    connection = None
    try:
        if legacy.exists():
            legacy.unlink()
        connection = sqlite3.connect(str(legacy))
        connection.execute(
            """
            CREATE TABLE identify_record (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_path TEXT NOT NULL,
                foods_json TEXT NOT NULL,
                total_calories_kcal REAL,
                summary TEXT NOT NULL DEFAULT '',
                tips TEXT NOT NULL DEFAULT '',
                raw_response TEXT NOT NULL DEFAULT '',
                debug_url TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO identify_record (image_path, foods_json, created_at) VALUES (?, ?, ?)",
            ("/uploads/old.png", "[]", "2026-01-01 00:00:00"),
        )
        connection.execute(
            """
            CREATE TABLE energy_daily (
                user_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                resting_kcal REAL NOT NULL,
                active_kcal REAL NOT NULL,
                total_kcal REAL NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, day)
            )
            """
        )
        connection.execute(
            "INSERT INTO energy_daily (user_id, day, resting_kcal, active_kcal, total_kcal, updated_at) VALUES (1, '2026-01-01', 1, 1, 2, '2026-01-01 00:00:00')"
        )
        connection.commit()
        connection.close()
        connection = None
        from server.db import init_db, list_records

        init_db(str(legacy))
        connection = sqlite3.connect(str(legacy))
        columns = [row[1] for row in connection.execute("PRAGMA table_info(identify_record)")]
        kept = connection.execute("SELECT COUNT(*) FROM identify_record").fetchone()[0]
        old_status = connection.execute("SELECT status FROM identify_record").fetchone()[0]
        energy_left = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'energy_daily'"
        ).fetchone()
        connection.close()
        connection = None
        expect("user_id" in columns, "旧数据库没有补上 user_id")
        expect("status" in columns, "旧数据库没有补上 status")
        expect(old_status == "done", "旧记录的状态不是已完成")
        expect(kept == 1, "迁移把旧记录删掉了")
        expect(energy_left is None, "旧库里的消耗表没有删掉")
        listed = list_records(str(legacy), 1, 20, 0)
        expect(listed["total"] == 0, "没有主人的旧记录出现在用户列表里")
        print("旧库迁移通过")
    finally:
        if connection is not None:
            connection.close()
        if before_bytes is None:
            if legacy.exists():
                legacy.unlink()
        else:
            legacy.write_bytes(before_bytes)


def check_api(db_path):
    from fastapi.testclient import TestClient
    import server.main as server_main

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    with TestClient(server_main.app) as client:
        health = client.get("/api/health")
        expect(health.status_code == 200, "健康检查失败")
        expect(health.json()["status"] == "ok", "健康检查状态不正确")
        expect(health.json()["mock"] is True, "测试应运行在模拟模式")

        before_count = count_rows(db_path)
        guest_calendar = client.get("/api/calendar")
        expect(guest_calendar.status_code == 401, "未登录不应该能看月历")
        guest_day = client.get("/api/records", params={"date": "2026-10-16"})
        expect(guest_day.status_code == 401, "未登录不应该能按日期查记录")
        guest = client.post("/api/identify", files={"file": ("meal.png", png, "image/png")})
        expect(guest.status_code == 401, "未登录不应该能上传")
        expect(count_rows(db_path) == before_count, "未登录上传后数据库条数变了")

        registered = client.post("/api/register", json={"username": "meal_alice", "password": "pass1234"})
        expect(registered.status_code == 200, "注册失败: %s" % registered.text)
        alice = query_user(db_path, "meal_alice")
        expect(alice is not None, "数据库里没有新用户")
        expect("pass1234" not in alice["password_hash"], "密码被明文写进数据库")
        token = registered.json()["token"]
        headers = {"Authorization": "Bearer " + token}

        again = client.post("/api/register", json={"username": "meal_alice", "password": "pass1234"})
        expect(again.status_code == 400, "重复用户名应该被拒绝")
        bad_login = client.post("/api/login", json={"username": "meal_alice", "password": "wrong123"})
        expect(bad_login.status_code == 401, "错误密码应该登录失败")
        logged_in = client.post("/api/login", json={"username": "meal_alice", "password": "pass1234"})
        expect(logged_in.status_code == 200, "正确密码登录失败")
        headers = {"Authorization": "Bearer " + logged_in.json()["token"]}
        removed_energy = client.post(
            "/api/energy",
            json={
                "username": "meal_alice",
                "password": "pass1234",
                "date": "2026-10-16",
                "resting_kcal": 1,
                "active_kcal": 1,
            },
        )
        expect(removed_energy.status_code == 404, "消耗写入接口应该已经去掉")
        removed_energy_read = client.get("/api/energy", params={"date": "2026-10-16"}, headers=headers)
        expect(removed_energy_read.status_code == 404, "消耗读取接口应该已经去掉")
        energy_conn = sqlite3.connect(str(db_path))
        try:
            energy_table = energy_conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'energy_daily'"
            ).fetchone()
        finally:
            energy_conn.close()
        expect(energy_table is None, "数据库里还留着消耗表")

        empty = client.post(
            "/api/identify",
            files={"file": ("empty.png", b"", "image/png")},
            headers=headers,
        )
        expect(empty.status_code == 400, "空图片应该被拒绝")
        expect("空" in empty.json()["message"], "空图片提示不正确")
        expect(count_rows(db_path) == before_count, "拒绝空图片后数据库条数变了")

        invalid = client.post(
            "/api/identify",
            files={"file": ("note.txt", b"hello", "text/plain")},
            headers=headers,
        )
        expect(invalid.status_code == 400, "非图片应该被拒绝")
        expect("jpg" in invalid.json()["message"], "非图片提示不正确")
        expect(count_rows(db_path) == before_count, "拒绝非图片后数据库条数变了")

        created = client.post(
            "/api/identify",
            files={"file": ("meal.png", png, "image/png")},
            headers=headers,
        )
        expect(created.status_code == 200, "识别接口失败: %s" % created.text)
        body = created.json()
        expect(body.get("status") == "processing", "页面识别应该立刻返回处理中")
        expect(body.get("id"), "页面识别没有返回记录编号")
        expect("foods" not in body and "token" not in body, "页面识别不应该等待识别结果或返回登录令牌")
        expect(count_rows(db_path) == before_count + 1, "识别提交后数据库没有新增")

        row = query_row(db_path, body["id"])
        expect(row is not None, "数据库里找不到这条识别记录")
        expect(row["user_id"] == alice["id"], "记录没有记到当前用户名下")
        expect(row["status"] == "done", "页面识别完成后状态没有变成完成")
        expect(row["total_calories_kcal"] == 274, "页面识别热量和模拟结果不一致")
        stored_foods = json.loads(row["foods_json"])
        expect(stored_foods[0]["name"] == "白米饭", "页面识别食物和模拟结果不一致")
        expect("模拟" in row["tips"], "模拟结果提示缺失")
        image_file = Path(os.environ["FOOD_UPLOAD_DIR"]) / Path(row["image_path"]).name
        expect(image_file.is_file(), "上传图片没有落到磁盘")

        detail = client.get("/api/records/%s" % body["id"], headers=headers)
        expect(detail.status_code == 200, "记录详情失败")
        expect(detail.json()["id"] == row["id"], "详情编号和数据库不一致")
        expect(detail.json()["image_url"] == row["image_path"], "详情图片和数据库不一致")
        expect(detail.json()["foods"][1]["name"] == "清炒西兰花", "详情缺少第二种食物")
        expect(detail.json()["total_calories_kcal"] == row["total_calories_kcal"], "详情热量和数据库不一致")

        listed = client.get("/api/records", params={"limit": 50, "offset": 0}, headers=headers)
        expect(listed.status_code == 200, "记录列表失败")
        expect(listed.json()["total"] == count_user_rows(db_path, alice["id"]), "列表总数和该用户的数据库记录不一致")

        other = client.post("/api/register", json={"username": "meal_bob", "password": "pass5678"})
        expect(other.status_code == 200, "第二个用户注册失败")
        bob_headers = {"Authorization": "Bearer " + other.json()["token"]}
        kept_estimate_at = query_row(db_path, body["id"])["created_at"]
        kept_estimate_image = query_row(db_path, body["id"])["image_path"]
        guest_estimate = client.post("/api/records/%s/reestimate" % body["id"])
        expect(guest_estimate.status_code == 401, "未登录不应该能重新估算")
        expect(query_row(db_path, body["id"])["total_calories_kcal"] == 274, "未登录重新估算改掉了热量")
        bob_estimate = client.post("/api/records/%s/reestimate" % body["id"], headers=bob_headers)
        expect(bob_estimate.status_code == 404, "其他用户能重新估算别人的记录")
        expect(query_row(db_path, body["id"])["image_path"] == kept_estimate_image, "其他用户重新估算后原图片变了")
        estimated = client.post("/api/records/%s/reestimate" % body["id"], headers=headers)
        expect(estimated.status_code == 200, "重新估算失败: %s" % estimated.text)
        expect(estimated.json()["status"] == "processing", "重新估算应该先返回处理中")
        expect(estimated.json()["id"] == body["id"], "重新估算不应该新建记录")
        estimated_row = query_row(db_path, body["id"])
        expect(estimated_row["status"] == "done", "重新估算后没有识别完成")
        expect(estimated_row["created_at"] == kept_estimate_at, "重新估算改掉了记录时间")
        expect(estimated_row["image_path"] == kept_estimate_image, "重新估算换掉了原图片")
        expect(estimated_row["total_calories_kcal"] == 274, "重新估算的热量和模拟结果不一致")
        expect(json.loads(estimated_row["foods_json"])[0]["name"] == "白米饭", "重新估算的食物和模拟结果不一致")
        expect(count_rows(db_path) == before_count + 1, "重新估算多写了一条记录")
        busy_conn = sqlite3.connect(str(db_path))
        try:
            busy_conn.execute(
                "UPDATE identify_record SET status = 'processing' WHERE id = ?",
                (body["id"],),
            )
            busy_conn.commit()
        finally:
            busy_conn.close()
        busy_estimate = client.post("/api/records/%s/reestimate" % body["id"], headers=headers)
        expect(busy_estimate.status_code == 400, "正在识别时不应该再次估算")
        expect(query_row(db_path, body["id"])["status"] == "processing", "拒绝再次估算后状态变了")
        expect(query_row(db_path, body["id"])["total_calories_kcal"] == 274, "拒绝再次估算后热量变了")
        restore_conn = sqlite3.connect(str(db_path))
        try:
            restore_conn.execute(
                "UPDATE identify_record SET status = 'done' WHERE id = ?",
                (body["id"],),
            )
            restore_conn.commit()
        finally:
            restore_conn.close()
        expect(query_row(db_path, body["id"])["status"] == "done", "估算测试没有把记录恢复成已完成")
        bob_list = client.get("/api/records", headers=bob_headers)
        expect(bob_list.json()["total"] == 0, "其他用户看到了别人的记录")
        bob_detail = client.get("/api/records/%s" % body["id"], headers=bob_headers)
        expect(bob_detail.status_code == 404, "其他用户能打开别人的记录")
        bob_delete = client.delete("/api/records/%s" % body["id"], headers=bob_headers)
        expect(bob_delete.status_code == 404, "其他用户能删除别人的记录")
        expect(query_row(db_path, body["id"]) is not None, "其他用户删除后原记录没了")

        kept_at = query_row(db_path, body["id"])["created_at"]
        kept_image = query_row(db_path, body["id"])["image_path"]
        guest_retake = client.post(
            "/api/records/%s/retake" % body["id"],
            files={"file": ("again.png", png, "image/png")},
        )
        expect(guest_retake.status_code == 401, "未登录不应该能重拍")
        empty_retake = client.post(
            "/api/records/%s/retake" % body["id"],
            files={"file": ("empty.png", b"", "image/png")},
            headers=headers,
        )
        expect(empty_retake.status_code == 400, "空图片重拍应该被拒绝")
        expect(query_row(db_path, body["id"])["image_path"] == kept_image, "失败的重拍改掉了原图片")
        expect(query_row(db_path, body["id"])["created_at"] == kept_at, "失败的重拍改掉了时间")
        bob_retake = client.post(
            "/api/records/%s/retake" % body["id"],
            files={"file": ("again.png", png, "image/png")},
            headers=bob_headers,
        )
        expect(bob_retake.status_code == 404, "其他用户能重拍别人的记录")
        expect(query_row(db_path, body["id"])["image_path"] == kept_image, "其他用户重拍后原图片变了")
        retaken = client.post(
            "/api/records/%s/retake" % body["id"],
            files={"file": ("again.png", png, "image/png")},
            headers=headers,
        )
        expect(retaken.status_code == 200, "重拍失败: %s" % retaken.text)
        expect(retaken.json()["id"] == body["id"], "重拍后记录编号变了")
        expect(retaken.json()["created_at"] == kept_at, "重拍接口返回的时间变了")
        retaken_row = query_row(db_path, body["id"])
        expect(retaken_row["created_at"] == kept_at, "重拍后数据库里的时间变了")
        expect(retaken_row["image_path"] == retaken.json()["image_url"], "重拍后图片地址和数据库不一致")
        expect(retaken_row["image_path"] != kept_image, "重拍后图片没有换成新的")
        expect(retaken_row["total_calories_kcal"] == retaken.json()["total_calories_kcal"], "重拍热量和数据库不一致")
        expect(count_rows(db_path) == before_count + 1, "重拍不应该新增记录")
        expect(not image_file.exists(), "重拍后旧图片还在")
        image_file = Path(os.environ["FOOD_UPLOAD_DIR"]) / Path(retaken_row["image_path"]).name
        expect(image_file.is_file(), "重拍后的新图片没有落到磁盘")

        import calendar as calendar_mod
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone(timedelta(hours=8)))
        today = now.strftime("%Y-%m-%d")
        month = now.strftime("%Y-%m")
        other_day = month + ("-14" if today.endswith("-15") else "-15")
        set_created_at(db_path, body["id"], today + " 08:00:00")
        early_id = insert_calorie_row(db_path, alice["id"], today + " 07:30:00", 100)
        late_id = insert_calorie_row(db_path, alice["id"], today + " 18:00:00", 1800)
        exact_id = insert_calorie_row(db_path, alice["id"], other_day + " 12:00:00", 2000)
        extra_ids = [early_id, late_id, exact_id]
        try:
            bad_day = client.get("/api/records", params={"date": "2026-02-31"}, headers=headers)
            expect(bad_day.status_code == 400, "非法日期应该被拒绝")
            bad_month = client.get("/api/calendar", params={"month": "2026-13"}, headers=headers)
            expect(bad_month.status_code == 400, "非法月份应该被拒绝")

            day = client.get("/api/records", params={"date": today}, headers=headers)
            expect(day.status_code == 200, "按日期查询失败")
            day_body = day.json()
            expect([item["id"] for item in day_body["items"]] == [early_id, body["id"], late_id], "当天记录没有按时间从早到晚排列")
            expect(day_body["total_calories_kcal"] == 2174, "当天总热量和数据库不一致")
            sql_today = day_sums(db_path, alice["id"], month).get(today)
            expect(sql_today == (2174.0, 3), "当天汇总和数据库分组不一致")

            plain = client.get("/api/records", params={"limit": 50, "offset": 0}, headers=headers)
            expect(plain.json()["items"][0]["id"] == exact_id, "不带日期时仍按记录编号从新到旧返回")

            calendar = client.get("/api/calendar", params={"month": month}, headers=headers)
            expect(calendar.status_code == 200, "月历接口失败")
            days = calendar.json()["days"]
            expect(len(days) == calendar_mod.monthrange(now.year, now.month)[1], "月历天数不对")
            sql_days = day_sums(db_path, alice["id"], month)
            for item in days:
                sql_value = sql_days.get(item["date"], (0.0, 0))
                expect(item["total_calories_kcal"] == sql_value[0], "月历 %s 热量和数据库不一致" % item["date"])
                expect(item["count"] == sql_value[1], "月历 %s 条数和数据库不一致" % item["date"])
                expect("burn_kcal" not in item and "burn_saved" not in item, "月历还带着消耗字段")
            exact = client.get("/api/records", params={"date": other_day}, headers=headers)
            expect(exact.json()["total_calories_kcal"] == 2000, "2000 千卡的日期汇总不正确")

            future_index = now.year * 12 + now.month
            future_year, future_mon = divmod(future_index, 12)
            future_month = "%04d-%02d" % (future_year, future_mon + 1)
            future = client.get("/api/calendar", params={"month": future_month}, headers=headers)
            expect(future.status_code == 400, "未来月份应该被拒绝")
            oldest_index = now.year * 12 + now.month - 1 - 12
            oldest_year, oldest_mon = divmod(oldest_index, 12)
            too_old = "%04d-%02d" % (oldest_year, oldest_mon + 1)
            rejected = client.get("/api/calendar", params={"month": too_old}, headers=headers)
            expect(rejected.status_code == 400, "超过一年的月份应该被拒绝")
            expect("一年" in rejected.json()["message"], "超范围月份提示不正确")
            edge_index = now.year * 12 + now.month - 1 - 11
            edge_year, edge_mon = divmod(edge_index, 12)
            edge_month = "%04d-%02d" % (edge_year, edge_mon + 1)
            edge = client.get("/api/calendar", params={"month": edge_month}, headers=headers)
            expect(edge.status_code == 200, "最早可看的月份应该能打开")
            expect(len(edge.json()["days"]) == calendar_mod.monthrange(edge_year, edge_mon + 1)[1], "最早月份的天数不对")

            bob_day = client.get("/api/records", params={"date": today}, headers=bob_headers)
            expect(bob_day.json()["total"] == 0, "其他用户看到了别人当天的记录")
            bob_calendar = client.get("/api/calendar", params={"month": month}, headers=bob_headers)
            expect(all(item["count"] == 0 for item in bob_calendar.json()["days"]), "其他用户的月历出现了别人的热量")
            expect(day_sums(db_path, query_user(db_path, "meal_bob")["id"], month) == {}, "数据库里第二个用户不该有记录")
        finally:
            delete_ids(db_path, extra_ids)

        removed = client.delete("/api/records/%s" % body["id"], headers=headers)
        expect(removed.status_code == 200, "删除记录失败")
        expect(count_rows(db_path) == before_count, "删除后数据库条数没有回到原值")
        expect(query_row(db_path, body["id"]) is None, "删除后数据库仍能查到记录")
        expect(not image_file.exists(), "删除后图片文件还在")
        missing = client.get("/api/records/%s" % body["id"], headers=headers)
        expect(missing.status_code == 404, "已删除记录仍能访问")

        sessions_before_submit = count_sessions(db_path)
        rows_before_submit = count_rows(db_path)
        uploads_before_submit = count_uploads()
        wrong_submit = client.post(
            "/api/identify/submit",
            data={"username": "meal_alice", "password": "wrong123"},
            files={"file": ("meal.png", png, "image/png")},
        )
        expect(wrong_submit.status_code == 401, "密码错误不应该能提交识别")
        expect(count_rows(db_path) == rows_before_submit, "密码错误时多出了识别记录")
        expect(count_uploads() == uploads_before_submit, "密码错误时留下了图片")
        empty_submit = client.post(
            "/api/identify/submit",
            data={"username": "meal_alice", "password": "pass1234"},
            files={"file": ("empty.png", b"", "image/png")},
        )
        expect(empty_submit.status_code == 400, "空图片提交应该被拒绝")
        expect(count_rows(db_path) == rows_before_submit, "空图片提交后多出了记录")
        submitted = client.post(
            "/api/identify/submit",
            data={"username": "meal_alice", "password": "pass1234"},
            files={"file": ("meal.png", png, "image/png")},
        )
        expect(submitted.status_code == 200, "提交识别失败: %s" % submitted.text)
        submitted_body = submitted.json()
        expect(submitted_body.get("status") == "processing", "提交接口应该立刻返回处理中")
        expect(submitted_body.get("id"), "提交接口没有返回记录编号")
        expect("foods" not in submitted_body and "token" not in submitted_body, "提交接口不应该返回识别结果或登录令牌")
        expect(count_sessions(db_path) == sessions_before_submit, "提交识别不应该新建登录")
        expect(count_rows(db_path) == rows_before_submit + 1, "提交后没有立刻写入记录")
        submit_id = submitted_body["id"]
        submit_row = query_row(db_path, submit_id)
        expect(submit_row["user_id"] == alice["id"], "提交的识别没有记到对应用户名下")
        expect(submit_row["status"] == "done", "后台识别成功后状态没有变成完成")
        expect(submit_row["total_calories_kcal"] == 274, "后台识别热量和模拟结果不一致")
        expect(json.loads(submit_row["foods_json"])[0]["name"] == "白米饭", "后台识别食物和模拟结果不一致")
        submit_image = Path(os.environ["FOOD_UPLOAD_DIR"]) / Path(submit_row["image_path"]).name
        expect(submit_image.is_file(), "后台识别的图片没有落到磁盘")
        removed_submit = client.delete("/api/records/%s" % submit_id, headers=headers)
        expect(removed_submit.status_code == 200, "清理提交记录失败")
        expect(count_rows(db_path) == rows_before_submit, "清理后数据库条数没有回到提交前")
        expect(not submit_image.exists(), "清理后提交的图片还在")

        from server.coze_client import CozeError

        def fail_recognize(settings, image_path):
            raise CozeError("工作流超时")

        original_recognize = server_main.recognize
        server_main.recognize = fail_recognize
        try:
            failed = client.post(
                "/api/identify/submit",
                data={"username": "meal_alice", "password": "pass1234"},
                files={"file": ("meal.png", png, "image/png")},
            )
        finally:
            server_main.recognize = original_recognize
        expect(failed.status_code == 200, "失败的提交不应该把记录丢掉: %s" % failed.text)
        failed_id = failed.json()["id"]
        failed_row = query_row(db_path, failed_id)
        expect(failed_row is not None, "识别失败后记录被删掉了")
        expect(failed_row["status"] == "failed", "识别失败后状态不正确")
        expect(failed_row["user_id"] == alice["id"], "失败记录没有记到对应用户名下")
        expect(failed_row["summary"] == "工作流超时", "失败原因没有留在记录里")
        expect(failed_row["total_calories_kcal"] is None, "失败记录不应该有热量")
        failed_image = Path(os.environ["FOOD_UPLOAD_DIR"]) / Path(failed_row["image_path"]).name
        expect(failed_image.is_file(), "识别失败后图片被删掉了")
        kept_failed_at = failed_row["created_at"]
        kept_failed_image = failed_row["image_path"]
        guest_retry = client.post("/api/records/%s/reprocess" % failed_id)
        expect(guest_retry.status_code == 401, "未登录不应该能重新处理")
        expect(query_row(db_path, failed_id)["status"] == "failed", "未登录重新处理改掉了失败状态")
        bob_retry = client.post("/api/records/%s/reprocess" % failed_id, headers=bob_headers)
        expect(bob_retry.status_code == 404, "其他用户能重新处理别人的记录")
        expect(query_row(db_path, failed_id)["status"] == "failed", "其他用户重新处理后原状态变了")
        retried = client.post("/api/records/%s/reprocess" % failed_id, headers=headers)
        expect(retried.status_code == 200, "重新处理失败: %s" % retried.text)
        expect(retried.json()["status"] == "processing", "重新处理应该先返回处理中")
        expect(retried.json()["id"] == failed_id, "重新处理不应该新建记录")
        retried_row = query_row(db_path, failed_id)
        expect(retried_row["status"] == "done", "重新处理后没有识别完成")
        expect(retried_row["created_at"] == kept_failed_at, "重新处理改掉了记录时间")
        expect(retried_row["image_path"] == kept_failed_image, "重新处理换掉了原图片")
        expect(retried_row["total_calories_kcal"] == 274, "重新处理的热量和模拟结果不一致")
        expect(json.loads(retried_row["foods_json"])[0]["name"] == "白米饭", "重新处理的食物和模拟结果不一致")
        expect(failed_image.is_file(), "重新处理后原图片不在了")
        expect(count_rows(db_path) == rows_before_submit + 1, "重新处理多写了一条记录")
        again_retry = client.post("/api/records/%s/reprocess" % failed_id, headers=headers)
        expect(again_retry.status_code == 400, "已完成的记录不应该重新处理")
        expect(query_row(db_path, failed_id)["total_calories_kcal"] == 274, "拒绝重新处理后热量变了")
        removed_failed = client.delete("/api/records/%s" % failed_id, headers=headers)
        expect(removed_failed.status_code == 200, "清理失败记录失败")
        expect(not failed_image.exists(), "清理后失败记录的图片还在")
        expect(count_rows(db_path) == rows_before_submit, "清理失败记录后数据库条数没有回到提交前")

        import io
        from PIL import Image
        from pillow_heif import register_heif_opener

        register_heif_opener()
        heif_buf = io.BytesIO()
        Image.new("RGB", (12, 8), (200, 30, 30)).save(heif_buf, format="HEIF")
        heic_submit = client.post(
            "/api/identify/submit",
            data={"username": "meal_alice", "password": "pass1234"},
            files={"file": ("meal.heic", heif_buf.getvalue(), "image/heic")},
        )
        expect(heic_submit.status_code == 200, "苹果照片提交失败: %s" % heic_submit.text)
        heic_id = heic_submit.json()["id"]
        heic_row = query_row(db_path, heic_id)
        expect(heic_row is not None, "苹果照片没有留下记录")
        expect(heic_row["image_path"].endswith(".jpg"), "苹果照片没有转成网页能显示的 JPEG")
        expect(heic_row["user_id"] == alice["id"], "苹果照片没有记到对应用户名下")
        shown = client.get("/api/records/%s" % heic_id, headers=headers)
        expect(shown.status_code == 200, "处理记录详情打不开")
        expect(shown.json()["image_url"] == heic_row["image_path"], "详情里的图片和数据库不一致")
        image_resp = client.get(heic_row["image_path"])
        expect(image_resp.status_code == 200, "处理记录的图片文件打不开")
        expect(image_resp.content[:3] == b"\xff\xd8\xff", "打开的图片不是 JPEG")
        heic_file = Path(os.environ["FOOD_UPLOAD_DIR"]) / Path(heic_row["image_path"]).name
        expect(heic_file.read_bytes()[:3] == b"\xff\xd8\xff", "磁盘上的图片和接口不一致")
        removed_heic = client.delete("/api/records/%s" % heic_id, headers=headers)
        expect(removed_heic.status_code == 200, "清理苹果照片记录失败")
        expect(not heic_file.exists(), "清理后苹果照片还在")
        expect(count_rows(db_path) == rows_before_submit, "清理苹果照片后数据库条数没有回到提交前")

        def fail_page_recognize(settings, image_path):
            raise CozeError("工作流超时")

        original_page_recognize = server_main.recognize
        server_main.recognize = fail_page_recognize
        try:
            failed_page = client.post(
                "/api/identify",
                files={"file": ("meal.png", png, "image/png")},
                headers=headers,
            )
        finally:
            server_main.recognize = original_page_recognize
        expect(failed_page.status_code == 200, "页面识别失败时不应该把记录丢掉: %s" % failed_page.text)
        expect(failed_page.json().get("status") == "processing", "失败的页面识别应该先返回处理中")
        failed_page_id = failed_page.json()["id"]
        failed_page_row = query_row(db_path, failed_page_id)
        expect(failed_page_row["status"] == "failed", "页面识别失败后状态不正确")
        expect(failed_page_row["summary"] == "工作流超时", "页面识别失败原因没有留在记录里")
        expect(failed_page_row["total_calories_kcal"] is None, "页面识别失败不应该有热量")
        failed_page_image = Path(os.environ["FOOD_UPLOAD_DIR"]) / Path(failed_page_row["image_path"]).name
        expect(failed_page_image.is_file(), "页面识别失败后图片被删掉了")
        removed_page = client.delete("/api/records/%s" % failed_page_id, headers=headers)
        expect(removed_page.status_code == 200, "清理页面失败记录失败")
        expect(not failed_page_image.exists(), "清理后页面失败记录的图片还在")
        expect(count_rows(db_path) == rows_before_submit, "清理页面失败记录后数据库条数没有回到提交前")

        client.post("/api/logout", headers=headers)
        expired = client.get("/api/records", headers=headers)
        expect(expired.status_code == 401, "退出后旧令牌还能查记录")
    print("接口与数据库交叉验证通过")


def main(argv=None):
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    db_path = Path(args.db)
    upload_dir = Path(args.upload_dir)
    before_bytes = db_path.read_bytes() if db_path.exists() else None
    os.environ["FOOD_DB_PATH"] = str(db_path)
    os.environ["FOOD_UPLOAD_DIR"] = str(upload_dir)
    os.environ["COZE_MOCK"] = "1"
    os.environ["COZE_API_TOKEN"] = ""
    os.environ["COZE_WORKFLOW_ID"] = ""

    try:
        check_parser()
        check_image_parameter()
        check_legacy_database()
        check_api(db_path)
    finally:
        restore_database(db_path, before_bytes)
        shutil.rmtree(upload_dir, ignore_errors=True)
        if before_bytes is None:
            expect(not db_path.exists(), "测试数据库没有删掉")
        else:
            expect(db_path.read_bytes() == before_bytes, "测试结束后数据库没有恢复")
        print("数据库已恢复")


if __name__ == "__main__":
    main()
