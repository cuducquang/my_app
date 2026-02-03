import json
from typing import Dict

from app.agents.base import BaseAgent
from app.utils.formatting import as_float, as_int


class IntakeAgent(BaseAgent):
    def run(self, context: Dict) -> Dict:
        raw = context["request"]
        days = as_int(raw.get("days", 3), 3, min_value=1, max_value=30)
        people = as_int(raw.get("people", 1), 1, min_value=1, max_value=20)
        budget = as_float(raw.get("budget", 300), 300.0, min_value=0.0, max_value=1e7)
        budget_scope = raw.get("budget_scope", "total").lower()
        group_type = raw.get("group_type", "group").lower()
        interests = raw.get("interests", [])
        query = raw.get("query", "")
        if isinstance(interests, str):
            interests = [s.strip() for s in interests.split(",") if s.strip()]
        origin = raw.get("origin", "")
        season = raw.get("season", "")

        budget_usd = budget
        if budget > 5000:
            budget_usd = budget / 25000
            self._add_llm_note(
                context,
                f"Budget looks like VND. Converted {budget} VND to {budget_usd:.2f} USD.",
            )

        total_budget = budget_usd * people if budget_scope == "per_person" else budget_usd
        normalized = {
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
        self._add_llm_note(context, f"Normalize user request: {json.dumps(normalized, ensure_ascii=True)}")
        return {"normalized": normalized}

