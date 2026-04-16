"""FastAPI application — serves the WebSocket API and the built React frontend."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ag.core.config import Config, load_config
from ag.server.ws_handler import WSSession

# Built Vite frontend lives here after `npm run build`
_UI_DIST = Path(__file__).parent.parent.parent / "ui" / "dist"


def create_app(cfg: Config | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        cfg: Optional pre-loaded Config. Loads from default path if None.

    Returns:
        Configured FastAPI application instance.
    """
    if cfg is None:
        cfg = load_config()

    app = FastAPI(
        title="Antigravity",
        description="Multi-provider AI coding assistant — WebSocket + Model Manager API",
        version="0.1.0",
    )

    # Allow Vite dev server (port 5173) to connect during development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _ollama_url = cfg.providers.get("ollama", {}).get("base_url", "http://localhost:11434")

    # ── WebSocket chat ────────────────────────────────────────────────────────

    @app.websocket("/ws/chat")
    async def chat_ws(websocket: WebSocket) -> None:
        """One persistent WebSocket per browser tab — full agent session."""
        session = WSSession(ws=websocket, cfg=cfg)
        await session.run()

    # ── Health ────────────────────────────────────────────────────────────────

    @app.get("/api/health")
    async def health() -> dict:
        """Quick health check."""
        return {"status": "ok", "version": "0.1.0"}

    # ── Model management ──────────────────────────────────────────────────────

    from ag.server.model_manager import (
        delete_model,
        get_active_model,
        list_installed,
        merge_catalog,
        pull_model,
        set_active_model,
    )

    @app.get("/api/models")
    async def list_models() -> dict:
        """Curated catalog merged with installed Ollama models + active model."""
        installed = await list_installed(_ollama_url)
        catalog = merge_catalog(installed)
        active_model, active_provider = get_active_model()
        if not active_model:
            first = next((m["id"] for m in catalog if m["installed"]), "")
            if first:
                set_active_model(first)
                active_model = first
        return {
            "models": catalog,
            "active_model": active_model,
            "active_provider": active_provider,
        }

    @app.post("/api/models/activate")
    async def activate_model(request: Request) -> dict:
        """Set the globally active model — all new WS sessions pick this up."""
        data = await request.json()
        model_id = data.get("model_id", "").strip()
        provider = data.get("provider", "ollama")
        if not model_id:
            raise HTTPException(status_code=400, detail="model_id is required")
        set_active_model(model_id, provider)
        return {"ok": True, "active_model": model_id, "provider": provider}

    @app.post("/api/models/pull")
    async def pull_model_endpoint(request: Request) -> StreamingResponse:
        """Stream pull progress as Server-Sent Events.

        SSE format:  data: {"status":"...", "completed":N, "total":N}
        Final event: data: {"status":"done"}
        """
        data = await request.json()
        model_id = data.get("model_id", "").strip()
        if not model_id:
            raise HTTPException(status_code=400, detail="model_id is required")

        async def _stream():
            async for chunk in pull_model(model_id, _ollama_url):
                yield f"data: {json.dumps(chunk)}\n\n"
            yield 'data: {"status":"done"}\n\n'

        return StreamingResponse(
            _stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.delete("/api/models/{model_name:path}")
    async def delete_model_endpoint(model_name: str) -> dict:
        """Delete a model from Ollama."""
        return await delete_model(model_name, _ollama_url)

    # ── Code runner ───────────────────────────────────────────────────────────

    from ag.server.runner import run_code, kill_process, _SANDBOX_DIR
    from fastapi.staticfiles import StaticFiles as _StaticFiles

    @app.post("/api/run")
    async def run_endpoint(request: Request) -> StreamingResponse:
        """Execute code and stream output as SSE.

        Request body: {code, language, filename?}
        SSE events:   data: {"type":"stdout"|"stderr"|"system"|"exit", "data":"...", "pid":N}
        """
        data = await request.json()
        code = data.get("code", "")
        language = data.get("language", "python")
        filename = data.get("filename", "main")

        async def _sse():
            async for event in run_code(code, language, filename):
                yield f"data: {json.dumps(event)}\n\n"
            yield 'data: {"type":"stream_end"}\n\n'

        return StreamingResponse(
            _sse(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/run/kill")
    async def kill_endpoint(request: Request) -> dict:
        """Kill a running process by PID."""
        data = await request.json()
        pid = int(data.get("pid", 0))
        if not pid:
            raise HTTPException(status_code=400, detail="pid is required")
        return kill_process(pid)

    # Serve HTML output files (for browser-rendered programs)
    app.mount(
        "/run",
        _StaticFiles(directory=str(_SANDBOX_DIR), html=True),
        name="run_output",
    )



    # ── Serve built React frontend ────────────────────────────────────────────

    if _UI_DIST.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=str(_UI_DIST / "assets")),
            name="assets",
        )

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str) -> FileResponse:
            """SPA fallback — serve index.html for all non-API routes."""
            return FileResponse(str(_UI_DIST / "index.html"))

    return app
