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
    recommendations = result.get("recommendations") or []
    if not recommendations:
        return "Mình chưa tìm được gợi ý phù hợp. Bạn thử tăng ngân sách hoặc số ngày nhé."
    lines = []
    for idx, item in enumerate(recommendations, start=1):
        tags = item.get("tags", [])
        tag_text = f"Tags: {', '.join(tags)}" if tags else ""
        lines.append(
            f"{idx}. {item.get('destination')} ({item.get('region')}) - Ước tính: ${item.get('estimated_cost')}. {tag_text}".strip()
        )
    return "Mình gợi ý các điểm sau:\n" + "\n".join(lines)

