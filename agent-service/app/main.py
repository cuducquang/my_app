import json
import queue
import threading
import time
from typing import Any, Dict

from flasgger import Swagger, swag_from
from flask import Flask, jsonify, request, g
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from app.config import load_config
from app.orchestrator import Orchestrator
from app.services.eureka import eureka_register
from app.tools.plugins import load_skill_plugins
from app.tools.registry import ToolRegistry
from app.utils.formatting import format_recommendations_text
from app.utils.logging import REQUEST_ID_HEADER, get_logger
from app.clients.mcp import MCPClient


CONFIG = load_config()
logger = get_logger()


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    Swagger(
        app,
        template={
            "info": {
                "title": "Agent Service API",
                "description": "Multi-agent trip recommendation service",
                "version": "2.0.0",
            },
            "basePath": "/",
            "schemes": ["http", "https"],
        },
    )

    @app.before_request
    def assign_request_id() -> None:
        g.request_id = request.headers.get(REQUEST_ID_HEADER) or str(time.time_ns())

    @app.after_request
    def add_request_id_header(response):  # type: ignore[no-untyped-def]
        response.headers[REQUEST_ID_HEADER] = g.request_id or ""
        return response

    @app.errorhandler(Exception)
    def handle_exception(error):  # type: ignore[no-untyped-def]
        if isinstance(error, HTTPException):
            return error
        logger.exception("unhandled error: %s", error)
        return jsonify({"error": "internal_error", "request_id": g.request_id}), 500

    registry = ToolRegistry()
    def chrome_mcp_browse(url: str, instructions: str = "") -> Dict[str, Any]:
        if not CONFIG.chrome_mcp_url:
            return {"status": "not_configured", "message": "CHROME_MCP_URL is not set", "url": url}
        client = MCPClient(CONFIG.chrome_mcp_url)
        return client.call_tool(CONFIG.chrome_mcp_tool, {"url": url, "instructions": instructions})

    registry.register_simple(
        name="chrome_mcp_browse",
        description="Use Chrome MCP to browse a page (if configured)",
        schema={"url": "string", "instructions": "string"},
        handler=chrome_mcp_browse,
    )

    skills_dir = "app/skills"
    loaded_skills = load_skill_plugins(registry, skills_dir)
    orchestrator = Orchestrator(CONFIG, registry)

    @app.route("/")
    def root() -> Any:
        return jsonify(
            {
                "service": "agent-service",
                "status": "running",
                "endpoints": ["/health", "/recommendations", "/plan", "/openapi.json"],
                "skills_loaded": loaded_skills,
            }
        )

    @app.route("/health")
    def health() -> Any:
        return jsonify({"status": "ok"})

    @app.route("/recommendations", methods=["POST"])
    @swag_from(
        {
            "tags": ["Agent"],
            "summary": "Generate trip recommendations",
            "parameters": [
                {
                    "name": "body",
                    "in": "body",
                    "required": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "days": {"type": "integer"},
                            "budget": {"type": "number"},
                            "budget_scope": {"type": "string"},
                            "people": {"type": "integer"},
                            "group_type": {"type": "string"},
                            "interests": {"type": "array", "items": {"type": "string"}},
                            "origin": {"type": "string"},
                            "season": {"type": "string"},
                        },
                    },
                }
            ],
            "responses": {
                200: {"description": "Recommendations generated"},
                400: {"description": "Invalid request"},
            },
        }
    )
    def recommendations() -> Any:
        payload = request.get_json(silent=True)
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            return jsonify({"error": "payload must be a JSON object"}), 400
        result = orchestrator.run(payload)
        return jsonify(result)

    def stream_recommendations(payload: Dict[str, Any]):
        q: "queue.Queue[Dict[str, Any]]" = queue.Queue()

        def emit(event: str, data: Dict[str, Any]):
            q.put({"event": event, "data": data})

        def worker():
            try:
                result = orchestrator.run_with_stream(payload, emit)
                message = format_recommendations_text(result)
                for token in message.split():
                    emit("token", {"text": token + " "})
                    time.sleep(0.02)
                emit("final", result)
            except Exception as exc:
                emit("error", {"message": str(exc)})
            finally:
                emit("done", {})

        threading.Thread(target=worker, daemon=True).start()

        while True:
            item = q.get()
            event = item.get("event", "message")
            data = json.dumps(item.get("data", {}))
            yield f"event: {event}\ndata: {data}\n\n"
            if event == "done":
                break

    @app.route("/recommendations/stream", methods=["POST"])
    def recommendations_stream() -> Any:
        payload = request.get_json(silent=True)
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            return jsonify({"error": "payload must be a JSON object"}), 400

        return app.response_class(
            stream_recommendations(payload),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.route("/plan", methods=["POST"])
    def plan() -> Any:
        payload = request.get_json(silent=True)
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            return jsonify({"error": "payload must be a JSON object"}), 400
        result = orchestrator.run(payload)
        return jsonify(result)

    @app.route("/openapi.json")
    def openapi_spec() -> Any:
        return jsonify(app.extensions["swagger"].get_apispecs())

    return app


app = create_app()


if __name__ == "__main__":
    threading.Thread(target=eureka_register, args=(CONFIG,), daemon=True).start()
    app.run(host="0.0.0.0", port=CONFIG.port)

