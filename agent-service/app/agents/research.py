from typing import Dict

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
        candidates = self.registry.call("destination_catalog", {})
        context.setdefault("tool_calls", []).append({"tool": "destination_catalog", "args": {}})
        emit = context.get("emit")
        if callable(emit):
            emit("tool_call", {"tool": "destination_catalog", "args": {}})

        normalized = context["normalized"]
        days = normalized["days"]
        budget = normalized["budget"]
        people = normalized["people"]
        group_type = normalized["group_type"]

        filtered = []
        for item in candidates:
            if days < item["min_days"] or days > item["max_days"]:
                continue
            est_cost = estimate_trip_cost(days, people, item["base_cost_per_day"], group_type)
            if est_cost <= budget * 1.2:
                filtered.append({**item, "estimated_cost": est_cost})

        self._add_llm_note(context, f"Candidate list size={len(filtered)} for group_type={group_type}")
        return {"plan": steps, "candidates": filtered}

