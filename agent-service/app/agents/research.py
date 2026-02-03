import json
import re
import urllib.parse
from typing import Dict, List, Any, Iterable

from app.agents.base import BaseAgent
from app.tools.registry import ToolRegistry
from app.utils.estimation import estimate_trip_cost


class ResearchAgent(BaseAgent):
    def __init__(self, name: str, llm, registry: ToolRegistry):
        super().__init__(name, llm)
        self.registry = registry

    def run(self, context: Dict) -> Dict:
        steps = [
            "Gather candidate destinations",
            "Estimate costs and filter by budget/days",
            "Score based on group type and interests",
            "Present top recommendations with itinerary hints",
        ]
        emit = context.get("emit")

        normalized = context["normalized"]
        days = normalized["days"]
        budget = normalized["budget"]
        people = normalized["people"]
        group_type = normalized["group_type"]
        interests = normalized["interests"]
        region = normalized.get("origin") or ""
        season = normalized.get("season") or ""
        user_query = normalized.get("query") or ""

        query = user_query.strip() or f"best travel destinations in Vietnam for {days} days {group_type} budget"
        if region:
            query += f" from {region}"
        if season:
            query += f" {season} season"
        if interests:
            query += " " + " ".join(interests)

        sources = [
            "https://duckduckgo.com/?",
            "https://www.google.com/search?",
            "https://www.bing.com/search?",
            "https://vietnamtourism.gov.vn/search?",
        ]
        tool_results: List[Any] = []
        for base in sources:
            search_url = base + urllib.parse.urlencode({"q": query})
            instructions = "Find top Vietnam travel destinations with brief hints and seasonality."
            if "vietnamtourism.gov.vn" in base:
                instructions = (
                    "Use the Vietnam Tourism site to extract official destinations, "
                    "best seasons, and suggested duration. Summarize key highlights."
                )
            tool_args = {"url": search_url, "instructions": instructions}
            tool_result = self.registry.call("chrome_mcp_browse", tool_args)
            tool_results.append(tool_result)
            context.setdefault("tool_calls", []).append({"tool": "chrome_mcp_browse", "args": tool_args})
            if callable(emit):
                emit("tool_call", {"tool": "chrome_mcp_browse", "args": tool_args})

        candidates = self._extract_candidates(tool_results, normalized)
        if not candidates:
            if callable(emit):
                emit("agent_note", {"agent": self.name, "note": "No candidates extracted; retrying with relaxed parsing."})
            candidates = self._extract_candidates(tool_results, normalized, relaxed=True)

        filtered = []
        for item in candidates:
            if days < item["min_days"] or days > item["max_days"]:
                continue
            est_cost = estimate_trip_cost(days, people, item["base_cost_per_day"], group_type)
            if est_cost <= budget * 1.2:
                filtered.append({**item, "estimated_cost": est_cost})

        if not filtered and candidates:
            filtered = candidates[:5]
        self._add_llm_note(context, f"Candidate list size={len(filtered)} for group_type={group_type}")
        return {"plan": steps, "candidates": filtered}

    def _extract_candidates(self, tool_results: List[Any], normalized: Dict, relaxed: bool = False) -> List[Dict]:
        tool_text = self._flatten_text(tool_results)
        prompt = (
            "Extract 5-8 Vietnam travel destinations from the tool result. "
            "Return JSON array with fields: name, region, min_days, max_days, "
            "base_cost_per_day (USD), best_for (array), tags (array). "
            f"User context: {json.dumps(normalized, ensure_ascii=True)}. "
            f"Tool results: {json.dumps(tool_results, ensure_ascii=True)[:6000]}\n"
            f"Tool text: {tool_text[:4000]}"
        )
        if relaxed:
            prompt = (
                "Based on the tool results, produce 5-8 Vietnam travel destinations. "
                "If fields are missing, use reasonable defaults. "
                "Return ONLY a JSON array with fields: name, region, min_days, max_days, "
                "base_cost_per_day, best_for, tags. "
                f"User context: {json.dumps(normalized, ensure_ascii=True)}. "
                f"Tool results: {json.dumps(tool_results, ensure_ascii=True)[:8000]}"
            )
        response = self.llm.chat(
            [
                {"role": "system", "content": "You extract structured travel data."},
                {"role": "user", "content": prompt},
            ]
        )
        if not response:
            return []
        data = self._safe_json_parse(response)
        if isinstance(data, list):
            return [self._normalize_candidate(item) for item in data if isinstance(item, dict) and item.get("name")]
        return []

    def _safe_json_parse(self, text: str) -> Any:
        try:
            return json.loads(text)
        except Exception:
            pass
        match = re.search(r"\[[\s\S]*\]", text)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
        return None

    def _normalize_candidate(self, item: Dict) -> Dict:
        return {
            "name": item.get("name"),
            "region": item.get("region", ""),
            "min_days": int(item.get("min_days", 2)),
            "max_days": int(item.get("max_days", 5)),
            "base_cost_per_day": float(item.get("base_cost_per_day", 40)),
            "best_for": item.get("best_for", []),
            "tags": item.get("tags", []),
        }

    def _flatten_text(self, data: Any, limit: int = 300) -> str:
        chunks: List[str] = []

        def walk(value: Any):
            if isinstance(value, str):
                text = value.strip()
                if len(text) >= 20:
                    chunks.append(text)
                return
            if isinstance(value, dict):
                for v in value.values():
                    walk(v)
                return
            if isinstance(value, Iterable):
                for v in value:
                    walk(v)

        walk(data)
        return "\n".join(chunks[:limit])

