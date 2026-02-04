from typing import Any, Dict


def as_int(value: Any, default: int, min_value: int = 1, max_value: int = 60) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(parsed, max_value))


def as_float(value: Any, default: float, min_value: float = 0.0, max_value: float = 1e9) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(parsed, max_value))


def format_recommendations_text(result: Dict[str, Any]) -> str:
    answer = result.get("answer")
    if isinstance(answer, str) and answer.strip():
        return answer.strip()
    return "Mình chưa tìm được gợi ý phù hợp. Bạn thử tăng ngân sách hoặc bổ sung thêm sở thích nhé."

