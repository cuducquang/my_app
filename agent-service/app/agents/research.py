import json
import urllib.parse
from typing import Dict, List

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

        query = f"best travel destinations in Vietnam for {days} days {group_type} budget"
        if interests:
            query += " " + " ".join(interests)
        search_url = "https://duckduckgo.com/?" + urllib.parse.urlencode({"q": query})

        tool_args = {"url": search_url, "instructions": "Find top travel destinations with brief hints."}
        tool_result = self.registry.call("chrome_mcp_browse", tool_args)
        context.setdefault("tool_calls", []).append({"tool": "chrome_mcp_browse", "args": tool_args})
        if callable(emit):
            emit("tool_call", {"tool": "chrome_mcp_browse", "args": tool_args})

        candidates = self._extract_candidates(tool_result, normalized)

        filtered = []
        for item in candidates:
            if days < item["min_days"] or days > item["max_days"]:
                continue
            est_cost = estimate_trip_cost(days, people, item["base_cost_per_day"], group_type)
            if est_cost <= budget * 1.2:
                filtered.append({**item, "estimated_cost": est_cost})

        self._add_llm_note(context, f"Candidate list size={len(filtered)} for group_type={group_type}")
        return {"plan": steps, "candidates": filtered}

    def _extract_candidates(self, tool_result: Dict, normalized: Dict) -> List[Dict]:
        prompt = (
            "Extract 5-8 Vietnam travel destinations from the tool result. "
            "Return JSON array with fields: name, region, min_days, max_days, "
            "base_cost_per_day (USD), best_for (array), tags (array). "
            f"User context: {json.dumps(normalized, ensure_ascii=True)}. "
            f"Tool result: {json.dumps(tool_result, ensure_ascii=True)[:8000]}"
        )
        response = self.llm.chat(
            [
                {"role": "system", "content": "You extract structured travel data."},
                {"role": "user", "content": prompt},
            ]
        )
        if not response:
            return []
        try:
            data = json.loads(response)
            if isinstance(data, list):
                return [
                    {
                        "name": item.get("name"),
                        "region": item.get("region", ""),
                        "min_days": int(item.get("min_days", 2)),
                        "max_days": int(item.get("max_days", 5)),
                        "base_cost_per_day": float(item.get("base_cost_per_day", 40)),
                        "best_for": item.get("best_for", []),
                        "tags": item.get("tags", []),
                    }
                    for item in data
                    if item.get("name")
                ]
        except Exception:
            return []
        return []

