import json
import urllib.parse
from typing import Any, Dict, List

from app.agents.base import BaseAgent
from app.tools.registry import ToolRegistry
from app.utils.formatting import as_float, as_int


class SingleAgent(BaseAgent):
    def __init__(self, name: str, llm, registry: ToolRegistry):
        super().__init__(name, llm)
        self.registry = registry

    def run(self, context: Dict) -> Dict:
        normalized = self._normalize_request(context.get("request") or {})
        context["normalized"] = normalized

        query = normalized.get("query") or self._build_fallback_query(normalized)
        sources = [
            {"name": "duckduckgo", "url": "https://duckduckgo.com/?"},
            {"name": "vietnamtourism", "url": "https://vietnamtourism.gov.vn/search?"},
        ]

        tool_payloads: List[Dict[str, Any]] = []
        for source in sources:
            search_url = source["url"] + urllib.parse.urlencode({"q": query})
            instructions = (
                "Find Vietnam destinations and short highlights. "
                "Return concise titles and short text."
            )
            tool_args = {"url": search_url, "instructions": instructions}
            tool_result = self.registry.call("chrome_mcp_browse", tool_args)
            context.setdefault("tool_calls", []).append(
                {"tool": "chrome_mcp_browse", "source": source["name"]}
            )
            emit = context.get("emit")
            if callable(emit):
                emit("tool_call", {"tool": "chrome_mcp_browse", "source": source["name"]})
            tool_payloads.append(self._summarize_tool_result(tool_result))

        prompt = self._build_prompt(normalized, tool_payloads)
        answer = self.llm.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a concise Vietnam travel planner. "
                        "Answer in Vietnamese. Use short, practical suggestions."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        if not answer:
            answer = (
                "Mình chưa tìm được gợi ý phù hợp. "
                "Bạn thử tăng ngân sách hoặc bổ sung thêm sở thích nhé."
            )
        context["answer"] = answer
        return {"answer": answer}

    def _normalize_request(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        days = as_int(raw.get("days", 3), 3, min_value=1, max_value=30)
        people = as_int(raw.get("people", 1), 1, min_value=1, max_value=20)
        budget = as_float(raw.get("budget", 300), 300.0, min_value=0.0, max_value=1e7)
        budget_scope = str(raw.get("budget_scope", "total")).lower()
        group_type = str(raw.get("group_type", "group")).lower()
        interests = raw.get("interests", [])
        query = str(raw.get("query", "")).strip()
        if isinstance(interests, str):
            interests = [s.strip() for s in interests.split(",") if s.strip()]
        origin = str(raw.get("origin", "")).strip()
        season = str(raw.get("season", "")).strip()

        budget_usd = budget
        if budget > 5000:
            budget_usd = budget / 25000
        total_budget = budget_usd * people if budget_scope == "per_person" else budget_usd

        return {
            "days": days,
            "people": people,
            "budget": total_budget,
            "budget_scope": budget_scope,
            "group_type": group_type,
            "interests": interests,
            "origin": origin,
            "season": season,
            "query": query,
        }

    def _build_fallback_query(self, normalized: Dict[str, Any]) -> str:
        days = normalized.get("days", 3)
        group_type = normalized.get("group_type", "group")
        interests = normalized.get("interests") or []
        origin = normalized.get("origin") or ""
        season = normalized.get("season") or ""
        query = f"best Vietnam travel destinations for {days} days {group_type}"
        if origin:
            query += f" from {origin}"
        if season:
            query += f" {season} season"
        if interests:
            query += " " + " ".join(interests)
        return query

    def _summarize_tool_result(self, result: Any) -> Dict[str, Any]:
        if not isinstance(result, dict):
            return {"titles": [], "text": ""}
        titles = result.get("eval_titles") or []
        text = result.get("eval_text") or ""
        if isinstance(text, str):
            text = text[:3000]
        return {"titles": titles[:10], "text": text}

    def _build_prompt(self, normalized: Dict[str, Any], tool_payloads: List[Dict[str, Any]]) -> str:
        return (
            "Bạn sẽ gợi ý tối đa 3 điểm đến phù hợp. "
            "Trả lời ngắn gọn, mỗi điểm 1-2 câu, có lý do phù hợp ngân sách/ngày. "
            "Không dùng markdown, không cần JSON.\n"
            f"Ngữ cảnh người dùng: {json.dumps(normalized, ensure_ascii=True)}\n"
            f"Thông tin từ web: {json.dumps(tool_payloads, ensure_ascii=True)}"
        )

