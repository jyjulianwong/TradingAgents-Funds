"""TradingAgents Research Archive Dashboard.

Bloomberg Terminal-style file browser for ~/.tradingagents/.
Run:  python server.py [port]
"""

import json
import os
import re
import shutil
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(os.environ.get("TRADINGAGENTS_DIR", Path.home() / ".tradingagents")).resolve()
LOGS_DIR = BASE_DIR / "logs"
EVENTS_DIR = BASE_DIR / "visualizer_events"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="TradingAgents Dashboard", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_SIGNAL_RE = re.compile(
    r"(?:FINAL\s+RATING[:\*\s]+\*{0,2}(Overweight|Underweight|Buy|Sell|Hold)\b"
    r"|\b(BUY|SELL|HOLD|OVERWEIGHT|UNDERWEIGHT)\b)",
    re.IGNORECASE,
)


def _safe_path(base: Path, *parts: str) -> Path:
    """Resolve and verify path stays inside base (prevents directory traversal)."""
    resolved = base.joinpath(*parts).resolve()
    base_str = str(base) + os.sep
    if str(resolved) != str(base) and not str(resolved).startswith(base_str):
        raise HTTPException(status_code=400, detail="Invalid path")
    return resolved


def _extract_signal(date_dir: Path) -> str | None:
    """Try to extract BUY/SELL/HOLD/OVERWEIGHT/UNDERWEIGHT from the final decision file."""
    for candidate in ("reports/final_trade_decision.md", "final_trade_decision.md"):
        f = date_dir / candidate
        if f.exists():
            try:
                text = f.read_text(encoding="utf-8", errors="replace")[:3000]
            except OSError:
                return None
            m = _SIGNAL_RE.search(text)
            if m:
                return (m.group(1) or m.group(2)).upper()
    return None


# ── Routes ───────────────────────────────────────────────────────────────────


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/reports")
async def list_reports() -> dict:
    """Return {ticker: [{date, signal, file_count}]} tree."""
    if not LOGS_DIR.exists():
        return {}
    result: dict = {}
    for ticker_dir in sorted(LOGS_DIR.iterdir()):
        if not ticker_dir.is_dir():
            continue
        runs = []
        for date_dir in sorted(ticker_dir.iterdir(), reverse=True):
            if not date_dir.is_dir():
                continue
            file_count = sum(1 for f in date_dir.rglob("*") if f.is_file())
            runs.append(
                {
                    "date": date_dir.name,
                    "signal": _extract_signal(date_dir),
                    "file_count": file_count,
                }
            )
        if runs:
            result[ticker_dir.name] = runs
    return result


@app.get("/api/reports/{ticker}/{date}")
async def get_run(ticker: str, date: str) -> dict:
    """List all files in a run."""
    run_dir = _safe_path(LOGS_DIR, ticker, date)
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="Run not found")
    files = sorted(str(f.relative_to(run_dir)) for f in run_dir.rglob("*") if f.is_file())
    return {
        "ticker": ticker,
        "date": date,
        "signal": _extract_signal(run_dir),
        "files": files,
    }


@app.get("/api/reports/{ticker}/{date}/content")
async def get_file_content(
    ticker: str, date: str, path: str = Query(...)
) -> PlainTextResponse:
    run_dir = _safe_path(LOGS_DIR, ticker, date)
    file_path = _safe_path(run_dir, path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return PlainTextResponse(file_path.read_text(encoding="utf-8", errors="replace"))


@app.delete("/api/reports/{ticker}/{date}")
async def delete_run(ticker: str, date: str) -> dict:
    run_dir = _safe_path(LOGS_DIR, ticker, date)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    shutil.rmtree(run_dir)
    ticker_dir = _safe_path(LOGS_DIR, ticker)
    if ticker_dir.exists() and not any(ticker_dir.iterdir()):
        ticker_dir.rmdir()
    return {"deleted": f"{ticker}/{date}"}


@app.delete("/api/reports/{ticker}/{date}/file")
async def delete_file(
    ticker: str, date: str, path: str = Query(...)
) -> dict:
    run_dir = _safe_path(LOGS_DIR, ticker, date)
    file_path = _safe_path(run_dir, path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    file_path.unlink()
    return {"deleted": path}


@app.get("/api/events")
async def list_events() -> list:
    if not EVENTS_DIR.exists():
        return []
    result = []
    for f in sorted(EVENTS_DIR.glob("*.jsonl"), reverse=True):
        stat = f.stat()
        result.append({"name": f.name, "size": stat.st_size, "mtime": stat.st_mtime})
    return result


@app.get("/api/events/{filename}")
async def get_event_file(filename: str) -> list:
    file_path = _safe_path(EVENTS_DIR, filename)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    lines = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError:
                lines.append({"ts": "", "event": {"type": "unknown", "raw": line}})
    return lines


@app.delete("/api/events/{filename}")
async def delete_event_file(filename: str) -> dict:
    file_path = _safe_path(EVENTS_DIR, filename)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    file_path.unlink()
    return {"deleted": filename}


@app.get("/api/base-dir")
async def get_base_dir() -> dict:
    """Return the resolved base directory path."""
    return {"path": str(BASE_DIR)}


@app.get("/api/isin-names")
async def get_isin_names() -> dict:
    """Parse ISIN-to-fund-name mapping from default_config.py comments."""
    config_path = Path(__file__).parent.parent / "tradingagents" / "default_config.py"
    if not config_path.exists():
        return {}
    text = config_path.read_text(encoding="utf-8")
    pattern = re.compile(r'"([A-Z0-9]{12})"\s*:.*?#\s*([^(\n]+)')
    return {m.group(1): m.group(2).strip() for m in pattern.finditer(text)}


@app.get("/api/stats")
async def get_stats() -> dict:
    tickers = runs = 0
    if LOGS_DIR.exists():
        for td in LOGS_DIR.iterdir():
            if td.is_dir():
                tickers += 1
                runs += sum(1 for dd in td.iterdir() if dd.is_dir())
    event_logs = len(list(EVENTS_DIR.glob("*.jsonl"))) if EVENTS_DIR.exists() else 0
    return {"tickers": tickers, "runs": runs, "event_logs": event_logs}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7843
    print(f"\n  TradingAgents Research Archive  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
