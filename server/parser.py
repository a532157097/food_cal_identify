import json
import re

_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")

_FOOD_LIST_KEYS = ("foods", "food_list", "items", "食物", "食物列表")
_TOTAL_KEYS = (
    "total_calories_kcal",
    "total_calories",
    "total_kcal",
    "calories",
    "总热量",
    "热量",
)
_SUMMARY_KEYS = ("summary", "摘要", "description", "描述")
_TIPS_KEYS = ("tips", "suggestion", "建议", "advice")
_NAME_KEYS = ("name", "food", "food_name", "名称", "食物", "食物名称")
_WEIGHT_KEYS = ("weight_g", "weight", "gram", "重量", "克重")
_CALORIE_KEYS = ("calories_kcal", "calories", "kcal", "热量", "卡路里")
_PROTEIN_KEYS = ("protein_g", "protein", "蛋白质")
_FAT_KEYS = ("fat_g", "fat", "脂肪")
_CARB_KEYS = ("carb_g", "carb", "carbohydrate", "carbs", "碳水", "碳水化合物")
_WRAP_KEYS = ("result", "output", "Output", "data", "content", "text", "answer")


def parse_workflow_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("工作流返回无法识别")
    code = payload.get("code", 0)
    if code not in (0, "0", None):
        message = payload.get("msg") or payload.get("message") or "工作流执行失败"
        raise ValueError(message)
    nutrition = unwrap(payload.get("data"), 0)
    if not nutrition:
        raise ValueError("工作流没有返回可识别的内容")
    nutrition["debug_url"] = payload.get("debug_url") or ""
    return nutrition


def unwrap(data, depth):
    if depth > 6 or data is None:
        return None
    if isinstance(data, str):
        text = data.strip()
        if not text:
            return None
        parsed = _try_json(text)
        if parsed is None:
            fenced = _FENCE.search(text)
            if fenced:
                parsed = _try_json(fenced.group(1).strip())
        if parsed is None:
            return _from_text(text)
        return unwrap(parsed, depth + 1)
    if isinstance(data, list):
        if data and isinstance(data[0], dict) and (
            "execute_status" in data[0] or "output" in data[0]
        ):
            return _from_history_item(data[0], depth)
        return normalize({"foods": data})
    if isinstance(data, dict):
        if "execute_status" in data:
            return _from_history_item(data, depth)
        if data.get("execute_id") and not _looks_like_nutrition(data):
            raise ValueError("工作流仍在异步执行，请稍后重试，或把 COZE_IS_ASYNC 设为 1")
        if _looks_like_nutrition(data):
            return normalize(data)
        for key in _WRAP_KEYS:
            if key in data and data[key] not in (None, ""):
                inner = unwrap(data[key], depth + 1)
                if inner:
                    return inner
        return _from_text(json.dumps(data, ensure_ascii=False))
    return _from_text(str(data))


def normalize(data):
    foods_raw = None
    for key in _FOOD_LIST_KEYS:
        if isinstance(data.get(key), list):
            foods_raw = data[key]
            break
    foods = []
    for item in foods_raw or []:
        if isinstance(item, str) and item.strip():
            foods.append(_empty_food(item.strip()))
        elif isinstance(item, dict):
            foods.append(_food(item))
    total = _first_number(data, _TOTAL_KEYS)
    if total is None:
        numbers = [item["calories_kcal"] for item in foods if item["calories_kcal"] is not None]
        total = round(sum(numbers), 1) if numbers else None
    summary = _first_text(data, _SUMMARY_KEYS)
    tips = _first_text(data, _TIPS_KEYS)
    if not summary and foods:
        names = [item["name"] for item in foods if item.get("name")]
        if names:
            summary = "、".join(names)
    if foods_raw is not None and not foods and not summary:
        summary = "没有识别到食物"
    if not foods and not summary:
        return None
    return {
        "foods": foods,
        "total_calories_kcal": total,
        "summary": summary,
        "tips": tips,
    }


def _from_history_item(item, depth):
    status = str(item.get("execute_status") or "")
    if status and status.lower() not in ("success",):
        if status.lower() == "running":
            raise ValueError("工作流仍在运行")
        raise ValueError(item.get("error_message") or "工作流执行失败")
    return unwrap(item.get("output") or item.get("data"), depth + 1)


def _looks_like_nutrition(data):
    if any(isinstance(data.get(key), list) for key in _FOOD_LIST_KEYS):
        return True
    if any(key in data for key in ("总热量", "摘要", "食物列表")):
        return True
    if any(key in data for key in _SUMMARY_KEYS) and not any(key in data for key in _WRAP_KEYS):
        return True
    return False


def _food(item):
    name = _first_text(item, _NAME_KEYS) or "未命名食物"
    food = _empty_food(name)
    food["weight_g"] = _first_number(item, _WEIGHT_KEYS)
    food["calories_kcal"] = _first_number(item, _CALORIE_KEYS)
    food["protein_g"] = _first_number(item, _PROTEIN_KEYS)
    food["fat_g"] = _first_number(item, _FAT_KEYS)
    food["carb_g"] = _first_number(item, _CARB_KEYS)
    food["confidence"] = _confidence(item.get("confidence", item.get("把握")))
    food["note"] = _first_text(item, ("note", "备注", "说明"))
    return food


def _empty_food(name):
    return {
        "name": name,
        "weight_g": None,
        "calories_kcal": None,
        "protein_g": None,
        "fat_g": None,
        "carb_g": None,
        "confidence": None,
        "note": "",
    }


def _from_text(text):
    text = (text or "").strip()
    if not text:
        return None
    return {
        "foods": [],
        "total_calories_kcal": None,
        "summary": text[:1000],
        "tips": "",
    }


def _first_text(data, keys):
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _first_number(data, keys):
    for key in keys:
        if key not in data:
            continue
        number = _to_float(data.get(key))
        if number is not None:
            return number
    return None


def _to_float(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    if isinstance(value, str):
        matched = _NUMBER.search(value.replace(",", ""))
        if not matched:
            return None
        return round(float(matched.group(0)), 2)
    return None


def _confidence(value):
    number = _to_float(value)
    if number is None:
        return None
    if number > 1:
        number = number / 100.0
    if number < 0:
        number = 0.0
    if number > 1:
        number = 1.0
    return round(number, 2)


def _try_json(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None
