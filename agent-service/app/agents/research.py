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
                emit("tool_result", self._summarize_tool_result(tool_result, search_url))

        candidates = self._extract_candidates(tool_results, normalized, emit=emit)
        if not candidates:
            if callable(emit):
                emit("agent_note", {"agent": self.name, "note": "No candidates extracted; retrying with relaxed parsing."})
            candidates = self._extract_candidates(tool_results, normalized, relaxed=True, emit=emit)

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

    def _extract_candidates(
        self, tool_results: List[Any], normalized: Dict, relaxed: bool = False, emit=None
    ) -> List[Dict]:
        tool_text = self._flatten_text(tool_results)
        titles = self._collect_titles(tool_results)
        if not tool_text:
            if callable(emit):
                emit("agent_note", {"agent": self.name, "note": "Tool text is empty; cannot extract candidates."})
            return []
        prompt = (
            "Extract 5-8 Vietnam travel destinations from the tool result. "
            "Return JSON array with fields: name, region, min_days, max_days, "
            "base_cost_per_day (USD), best_for (array), tags (array). "
            f"User context: {json.dumps(normalized, ensure_ascii=True)}. "
            f"Tool titles: {json.dumps(titles, ensure_ascii=True)[:1200]}\n"
            f"Tool results: {json.dumps(tool_results, ensure_ascii=True)[:4000]}\n"
            f"Tool text: {tool_text[:3000]}"
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
            if callable(emit):
                emit(
                    "agent_note",
                    {"agent": self.name, "note": "LLM extraction returned empty. Check AGENT2 credentials/model."},
                )
            return self._candidates_from_titles(titles, normalized) or self._heuristic_candidates(tool_text, normalized)
        data = self._safe_json_parse(response)
        if isinstance(data, list):
            return [self._normalize_candidate(item) for item in data if isinstance(item, dict) and item.get("name")]
        if callable(emit):
            emit(
                "agent_note",
                {"agent": self.name, "note": "LLM returned non-JSON. Falling back to heuristic extraction."},
            )
        return self._candidates_from_titles(titles, normalized) or self._heuristic_candidates(tool_text, normalized)

    def _safe_json_parse(self, text: str) -> Any:
        try:
            return json.loads(text)
        except Exception:
            pass
        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if fenced:
            try:
                return json.loads(fenced.group(1))
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

    def _heuristic_candidates(self, text: str, normalized: Dict) -> List[Dict]:
        if not text:
            return []
        pattern = re.compile(r"\b([A-Z][\w\-]+(?:\s+[A-Z][\w\-]+){0,3})\b")
        stopwords = {
            "Vietnam",
            "Viet",
            "Travel",
            "Trips",
            "Trip",
            "Guide",
            "Best",
            "Top",
            "Places",
            "Destinations",
            "Things",
            "Day",
            "Days",
            "Family",
            "Group",
            "Vacation",
            "DuckDuckGo",
            "Google",
            "Bing",
            "Search",
            "Latest",
            "RootWebArea",
        }
        seen = set()
        names = []
        for match in pattern.findall(text):
            name = match.strip()
            if name in stopwords or len(name) < 3:
                continue
            lowered = name.lower()
            if any(word in lowered for word in ["duckduckgo", "google", "bing", "search"]):
                continue
            if any(char.isdigit() for char in name):
                continue
            if name not in seen:
                seen.add(name)
                names.append(name)
            if len(names) >= 8:
                break
        defaults = {
            "region": "",
            "min_days": max(2, int(normalized.get("days", 3)) - 1),
            "max_days": max(3, int(normalized.get("days", 3)) + 1),
            "base_cost_per_day": 40,
            "best_for": [normalized.get("group_type", "group")],
            "tags": normalized.get("interests", []),
        }
        return [
            {"name": name, **defaults}
            for name in names
        ]

    def _flatten_text(self, data: Any, limit: int = 300) -> str:
        chunks: List[str] = []

        def walk(value: Any):
            if isinstance(value, str):
                text = value.strip()
                if len(text) >= 20:
                    chunks.append(text)
                return
            if isinstance(value, dict):
                if "snapshot_text" in value and isinstance(value["snapshot_text"], str):
                    chunks.append(value["snapshot_text"])
                if "eval_text" in value and isinstance(value["eval_text"], str):
                    chunks.append(value["eval_text"])
                if "eval_titles" in value and isinstance(value["eval_titles"], list):
                    for title in value["eval_titles"]:
                        if isinstance(title, str):
                            chunks.append(title)
                for v in value.values():
                    walk(v)
                return
            if isinstance(value, Iterable):
                for v in value:
                    walk(v)

        walk(data)
        return "\n".join(chunks[:limit])

    def _collect_titles(self, data: Any) -> List[str]:
        titles: List[str] = []

        def walk(value: Any):
            if isinstance(value, dict):
                if "eval_titles" in value and isinstance(value["eval_titles"], list):
                    for title in value["eval_titles"]:
                        if isinstance(title, str) and title.strip():
                            titles.append(title.strip())
                for v in value.values():
                    walk(v)
            elif isinstance(value, list):
                for v in value:
                    walk(v)

        walk(data)
        return titles[:50]

    def _candidates_from_titles(self, titles: List[str], normalized: Dict) -> List[Dict]:
        cleaned: List[str] = []
        for title in titles:
            base = re.split(r"\s-\s|\s\|\s|\s\(\d{4}\)\s", title)[0]
            base = re.sub(r"\b(in|at|for)\s+Vietnam\b", "", base, flags=re.IGNORECASE).strip()
            base = re.sub(r"\b(Vietnam|Travel|Trip|Guide|Best|Top|Places|Destinations)\b", "", base, flags=re.IGNORECASE).strip()
            base = re.sub(r"\s{2,}", " ", base)
            if len(base) < 4 or any(char.isdigit() for char in base):
                continue
            cleaned.append(base)
            if len(cleaned) >= 8:
                break

        defaults = {
            "region": "",
            "min_days": max(2, int(normalized.get("days", 3)) - 1),
            "max_days": max(3, int(normalized.get("days", 3)) + 1),
            "base_cost_per_day": 40,
            "best_for": [normalized.get("group_type", "group")],
            "tags": normalized.get("interests", []),
        }
        return [{"name": name, **defaults} for name in cleaned]

    def _summarize_tool_result(self, tool_result: Any, url: str) -> Dict:
        if isinstance(tool_result, dict) and "error" in tool_result:
            return {"tool": "chrome_mcp_browse", "url": url, "status": "error", "error": tool_result.get("error")}
        if isinstance(tool_result, dict):
            status = tool_result.get("status", "ok")
            result = tool_result.get("result", tool_result)
            text = self._flatten_text(result)
            return {
                "tool": "chrome_mcp_browse",
                "url": url,
                "status": status,
                "keys": list(result.keys()) if isinstance(result, dict) else [],
                "text_length": len(text),
            }
        return {"tool": "chrome_mcp_browse", "url": url, "status": "unknown"}

