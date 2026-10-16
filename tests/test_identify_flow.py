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
        connection.commit()
        connection.close()
        connection = None
        from server.db import init_db, list_records

        init_db(str(legacy))
        connection = sqlite3.connect(str(legacy))
        columns = [row[1] for row in connection.execute("PRAGMA table_info(identify_record)")]
        kept = connection.execute("SELECT COUNT(*) FROM identify_record").fetchone()[0]
        connection.close()
        connection = None
        expect("user_id" in columns, "旧数据库没有补上 user_id")
        expect(kept == 1, "迁移把旧记录删掉了")
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
        expect(body["foods"][0]["name"] == "白米饭", "接口没有返回白米饭")
        expect(body["total_calories_kcal"] == 274, "接口总热量不是 274")
        expect("模拟" in body["tips"], "模拟结果提示缺失")
        expect(count_rows(db_path) == before_count + 1, "识别成功后数据库没有新增")

        row = query_row(db_path, body["id"])
        expect(row is not None, "数据库里找不到这条识别记录")
        expect(row["user_id"] == alice["id"], "记录没有记到当前用户名下")
        expect(row["total_calories_kcal"] == body["total_calories_kcal"], "接口热量和数据库不一致")
        expect(row["summary"] == body["summary"], "接口摘要和数据库不一致")
        stored_foods = json.loads(row["foods_json"])
        expect(stored_foods[0]["name"] == body["foods"][0]["name"], "接口食物和数据库不一致")
        expect(row["image_path"] == body["image_url"], "图片地址和数据库不一致")
        image_file = Path(os.environ["FOOD_UPLOAD_DIR"]) / Path(row["image_path"]).name
        expect(image_file.is_file(), "上传图片没有落到磁盘")

        detail = client.get("/api/records/%s" % body["id"], headers=headers)
        expect(detail.status_code == 200, "记录详情失败")
        expect(detail.json()["id"] == row["id"], "详情编号和数据库不一致")
        expect(detail.json()["foods"][1]["name"] == "清炒西兰花", "详情缺少第二种食物")

        listed = client.get("/api/records", params={"limit": 50, "offset": 0}, headers=headers)
        expect(listed.status_code == 200, "记录列表失败")
        expect(listed.json()["total"] == count_user_rows(db_path, alice["id"]), "列表总数和该用户的数据库记录不一致")

        other = client.post("/api/register", json={"username": "meal_bob", "password": "pass5678"})
        expect(other.status_code == 200, "第二个用户注册失败")
        bob_headers = {"Authorization": "Bearer " + other.json()["token"]}
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
