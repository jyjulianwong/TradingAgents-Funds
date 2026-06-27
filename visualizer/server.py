"""FastAPI server for the TradingAgents Visualizer.

Serves the static Three.js frontend and exposes a WebSocket endpoint that
streams agent-lifecycle events from the CLI thread via the bridge module.
"""

import asyncio
import threading
import time
import urllib.request
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import bridge

app = FastAPI(title="TradingAgents Visualizer")
STATIC_DIR = Path(__file__).parent / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    q = bridge.subscribe()
    try:
        await ws.send_json({"type": "workflow_idle"})
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=25.0)
                await ws.send_json(event)
            except asyncio.TimeoutError:
                try:
                    await ws.send_json({"type": "ping"})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        bridge.unsubscribe(q)


_server_thread: threading.Thread | None = None


def start(port: int = 7842) -> int:
    """Start the visualizer server in a background daemon thread.

    Blocks until the server is accepting connections (up to 3 seconds) and
    returns the port number.  If the port is already in use, tries up to 5
    consecutive ports before giving up.
    """
    global _server_thread

    def _find_free_port(start: int) -> int:
        import socket
        for p in range(start, start + 5):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", p))
                    return p
                except OSError:
                    continue
        return start  # fall back; uvicorn will error if still busy

    port = _find_free_port(port)

    def _run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        bridge.set_server_loop(loop)
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            loop="none",
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)
        loop.run_until_complete(server.serve())

    _server_thread = threading.Thread(target=_run, daemon=True, name="viz-server")
    _server_thread.start()

    # Poll until the server is accepting requests (max 3 s).
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
            return port
        except Exception:
            time.sleep(0.1)

    return port
