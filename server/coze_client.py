import json
import mimetypes
import time
from pathlib import Path

import httpx

MOCK_NUTRITION = {
    "foods": [
        {
            "name": "白米饭",
            "weight_g": 200,
            "calories_kcal": 232,
            "protein_g": 5.2,
            "fat_g": 0.6,
            "carb_g": 51.6,
            "confidence": 0.92,
        },
        {
            "name": "清炒西兰花",
            "weight_g": 120,
            "calories_kcal": 42,
            "protein_g": 3.4,
            "fat_g": 1.2,
            "carb_g": 5.1,
            "confidence": 0.81,
        },
    ],
    "total_calories_kcal": 274,
    "summary": "这是一份米饭配西兰花，热量主要来自白米饭。",
    "tips": "示例数据：当前是模拟模式。配置 Coze 令牌和工作流后会返回真实识别结果。",
}


class CozeError(Exception):
    pass


def build_image_value(file_id, style):
    if style == "object":
        return {"file_id": file_id}
    return json.dumps({"file_id": file_id}, ensure_ascii=False)


def recognize(settings, path):
    last_error = None
    for attempt in range(4):
        try:
            return _recognize_once(settings, path)
        except (CozeError, httpx.HTTPError, OSError) as exc:
            last_error = exc
            if attempt == 3:
                raise
    raise last_error


def _recognize_once(settings, path):
    if settings["coze_mock"]:
        return {
            "code": 0,
            "data": json.dumps(MOCK_NUTRITION, ensure_ascii=False),
            "debug_url": "",
            "msg": "",
        }
    token = settings["coze_api_token"]
    workflow_id = settings["coze_workflow_id"]
    if not token or not workflow_id:
        raise CozeError(
            "还没有配置 Coze。请在 server/.env 填写 COZE_API_TOKEN 和 COZE_WORKFLOW_ID，"
            "或临时把 COZE_MOCK 设为 1 查看示例结果"
        )
    client = CozeClient(settings)
    file_id = client.upload(path)
    return client.run(file_id)


class CozeClient(object):
    def __init__(self, settings):
        self.base = settings["coze_api_base"]
        self.token = settings["coze_api_token"]
        self.workflow_id = settings["coze_workflow_id"]
        self.image_param = settings["coze_image_param"]
        self.style = settings["coze_image_value_style"]
        self.timeout = settings["coze_timeout"]
        self.is_async = settings["coze_is_async"]

    def upload(self, path):
        image_path = Path(path)
        content_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
        with image_path.open("rb") as handle:
            response = httpx.post(
                self.base + "/v1/files/upload",
                headers={"Authorization": "Bearer " + self.token},
                files={"file": (image_path.name, handle, content_type)},
                timeout=self.timeout,
            )
        body = self._json(response)
        if body.get("code") not in (0, None):
            raise CozeError(body.get("msg") or "上传图片到 Coze 失败")
        file_id = (body.get("data") or {}).get("id")
        if not file_id:
            raise CozeError("Coze 没有返回文件编号")
        return file_id

    def run(self, file_id):
        body = {
            "workflow_id": self.workflow_id,
            "parameters": {
                self.image_param: build_image_value(file_id, self.style),
            },
        }
        if self.is_async:
            body["is_async"] = True
        response = self._post("/v1/workflow/run", body)
        if response.get("code") not in (0, None):
            raise CozeError(response.get("msg") or "工作流调用失败")
        execute_id = _extract_execute_id(response.get("data"))
        if execute_id:
            return self._poll(execute_id, response.get("debug_url") or "")
        return response

    def _poll(self, execute_id, debug_url):
        deadline = time.time() + self.timeout
        path = "/v1/workflows/%s/run_histories/%s" % (self.workflow_id, execute_id)
        last_message = "工作流仍在执行"
        while time.time() < deadline:
            response = self._get(path)
            if response.get("code") not in (0, None):
                raise CozeError(response.get("msg") or "查询工作流结果失败")
            rows = response.get("data") or []
            if isinstance(rows, dict):
                rows = [rows]
            if isinstance(rows, list) and rows:
                item = rows[0]
                status = str(item.get("execute_status") or "")
                lowered = status.lower()
                if lowered == "success":
                    return {
                        "code": 0,
                        "data": item.get("output"),
                        "debug_url": item.get("debug_url") or debug_url,
                        "msg": "",
                    }
                if lowered in ("fail", "failed"):
                    raise CozeError(item.get("error_message") or "工作流执行失败")
                if status:
                    last_message = "工作流状态：" + status
            time.sleep(1.5)
        raise CozeError(last_message + "，已超过等待时间")

    def _post(self, path, body):
        response = httpx.post(
            self.base + path,
            headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=self.timeout,
        )
        return self._json(response)

    def _get(self, path):
        response = httpx.get(
            self.base + path,
            headers={"Authorization": "Bearer " + self.token},
            timeout=self.timeout,
        )
        return self._json(response)

    def _json(self, response):
        try:
            body = response.json()
        except Exception:
            raise CozeError("Coze 返回了无法解析的内容（HTTP %s）" % response.status_code)
        if response.status_code >= 400 and body.get("code") in (0, None):
            raise CozeError(body.get("msg") or ("Coze 请求失败 HTTP %s" % response.status_code))
        return body


def _extract_execute_id(data):
    if isinstance(data, dict) and data.get("execute_id") and "foods" not in data:
        return data.get("execute_id")
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
        except ValueError:
            return None
        if (
            isinstance(parsed, dict)
            and parsed.get("execute_id")
            and "foods" not in parsed
            and "output" not in parsed
            and "result" not in parsed
        ):
            return parsed.get("execute_id")
    return None
