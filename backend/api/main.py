"""
CodeOracle — FastAPI Backend
Production-grade REST API with WebSocket support for streaming.
"""
import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from typing import Dict, Any, AsyncGenerator

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from core.config import settings
from core.models import (
    IngestRequest, QueryRequest, QueryResponse,
    RepositoryContext, QueryIntent,
)
from core.ingestion import (
    ingest_repository, get_context, get_orchestrator, list_repos
)


# ─── App Setup ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🔮 CodeOracle starting up...")
    yield
    logger.info("CodeOracle shutting down.")


app = FastAPI(
    title="CodeOracle API",
    description="Explainability-Driven Multi-Agent RAG System for Codebase Understanding",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url, 
        "http://localhost:5173", 
        "http://127.0.0.1:5173", 
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job status tracker
_jobs: Dict[str, Dict[str, Any]] = {}


# ─── Models ───────────────────────────────────────────────────────────────────

class IngestJobResponse(BaseModel):
    job_id: str
    repo_id: str
    status: str
    message: str


class JobStatus(BaseModel):
    job_id: str
    status: str  # "pending", "running", "done", "error"
    message: str
    progress: int  # 0-100
    repo_id: str = ""
    error: str = ""


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"service": "CodeOracle", "status": "operational", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


# ── Repository Ingestion ──────────────────────────────────────────────────────

@app.post("/api/repos/ingest", response_model=IngestJobResponse)
async def start_ingestion(request: IngestRequest, background_tasks: BackgroundTasks):
    """Start async repository ingestion. Returns job_id to track progress."""
    import hashlib
    repo_id = hashlib.md5(request.github_url.encode()).hexdigest()[:12]
    job_id = str(uuid.uuid4())[:8]

    _jobs[job_id] = {
        "status": "pending",
        "message": "Queued",
        "progress": 0,
        "repo_id": repo_id,
        "error": "",
    }

    background_tasks.add_task(_run_ingestion, job_id, repo_id, request)

    return IngestJobResponse(
        job_id=job_id,
        repo_id=repo_id,
        status="pending",
        message="Ingestion started",
    )


async def _run_ingestion(job_id: str, repo_id: str, request: IngestRequest):
    def progress(msg: str, pct: int):
        _jobs[job_id].update({"status": "running", "message": msg, "progress": pct})

    try:
        _jobs[job_id]["status"] = "running"
        ctx = await ingest_repository(request, progress_callback=progress)
        _jobs[job_id].update({
            "status": "done",
            "message": f"Repository '{ctx.repo_name}' ready!",
            "progress": 100,
            "repo_id": repo_id,
        })
    except Exception as e:
        logger.error(f"Ingestion failed for {request.github_url}: {e}")
        _jobs[job_id].update({
            "status": "error",
            "message": "Ingestion failed",
            "error": str(e),
            "progress": 0,
        })


@app.get("/api/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatus(job_id=job_id, **job)


@app.get("/api/repos")
async def list_repositories():
    return {"repos": list(list_repos().values())}


@app.get("/api/repos/{repo_id}")
async def get_repository(repo_id: str):
    ctx = get_context(repo_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Repository not found. Please ingest first.")
    return {
        "repo_id": repo_id,
        "name": ctx.repo_name,
        "url": ctx.repo_url,
        "summary": ctx.repo_summary,
        "stats": {
            "files": ctx.total_files,
            "functions": ctx.total_functions,
            "classes": ctx.total_classes,
            "languages": ctx.languages,
            "avg_complexity": round(ctx.avg_complexity, 2),
            "has_tests": ctx.has_tests,
        },
        "critical_modules": ctx.critical_modules,
        "entry_points": ctx.entry_points,
        "dependency_edges": ctx.dependency_edges[:50],
        "call_edges": ctx.call_edges[:50],
        "ingested_at": ctx.cloned_at.isoformat(),
    }


@app.get("/api/repos/{repo_id}/health")
async def get_repo_health(repo_id: str):
    ctx = get_context(repo_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Repository not found.")
    orchestrator = get_orchestrator(repo_id)
    if not orchestrator:
        raise HTTPException(status_code=404, detail="Orchestrator not ready.")
    health = orchestrator.analyzer.compute_health_report(ctx)
    return health


@app.get("/api/repos/{repo_id}/architecture")
async def get_architecture_diagrams(repo_id: str):
    ctx = get_context(repo_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Repository not found.")
    orchestrator = get_orchestrator(repo_id)
    if not orchestrator:
        raise HTTPException(status_code=404, detail="Orchestrator not ready.")
    diagrams = orchestrator.architecture.generate_architecture(ctx)
    return {"diagrams": [d.model_dump() for d in diagrams]}


# ── Query Endpoint ────────────────────────────────────────────────────────────

@app.post("/api/query", response_model=QueryResponse)
async def query_repository(request: QueryRequest):
    """Main query endpoint — routes through multi-agent pipeline."""
    ctx = get_context(request.repo_id)
    if not ctx:
        raise HTTPException(status_code=404, detail=f"Repository '{request.repo_id}' not found.")

    orchestrator = get_orchestrator(request.repo_id)
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Agent system not ready.")

    try:
        response = await orchestrator.process(request)
        return response
    except Exception as e:
        logger.error("Query processing failed: {}", str(e))
        raise HTTPException(status_code=500, detail="Query processing failed: " + str(e))


# ── WebSocket for streaming ────────────────────────────────────────────────────

@app.websocket("/ws/{repo_id}")
async def websocket_query(websocket: WebSocket, repo_id: str):
    """WebSocket endpoint for real-time query streaming."""
    await websocket.accept()
    logger.info(f"WebSocket connected for repo {repo_id}")

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)

            request = QueryRequest(
                repo_id=repo_id,
                query=payload.get("query", ""),
                mode=QueryIntent(payload["mode"]) if payload.get("mode") else None,
                include_diagrams=payload.get("include_diagrams", False),
                conversation_history=payload.get("history", []),
            )

            # Send "thinking" status
            await websocket.send_text(json.dumps({"type": "status", "message": "Processing..."}))

            try:
                response = await asyncio.wait_for(
                    get_orchestrator(repo_id).process(request),
                    timeout=60.0,
                )
                await websocket.send_text(json.dumps({
                    "type": "response",
                    "data": response.model_dump(mode="json"),
                }))
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Query timed out. Try a more specific question.",
                }))
            except Exception as e:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": str(e),
                }))

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for repo {repo_id}")


@app.get("/api/repos/{repo_id}/suggest")
async def suggest_questions(repo_id: str):
    """Return AI-suggested questions for a repository."""
    ctx = get_context(repo_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Repository not found.")
    orchestrator = get_orchestrator(repo_id)
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Agent system not ready.")
    questions = orchestrator.suggester.suggest(ctx)
    return {"questions": questions}


# ── Utility Endpoints ─────────────────────────────────────────────────────────

@app.get("/api/repos/{repo_id}/files")
async def list_files(repo_id: str, language: str = None):
    ctx = get_context(repo_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Repository not found.")
    files = [
        {
            "path": path,
            "language": info.language.value,
            "functions": len(info.functions),
            "classes": len(info.classes),
            "complexity": round(info.complexity, 1),
            "lines": info.size_lines,
        }
        for path, info in ctx.files.items()
        if not language or info.language.value == language
    ]
    return {"files": sorted(files, key=lambda x: x["complexity"], reverse=True)}


@app.get("/api/repos/{repo_id}/graph")
async def get_dependency_graph(repo_id: str):
    ctx = get_context(repo_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Repository not found.")

    # Build nodes with metadata
    nodes = [
        {
            "id": path,
            "label": path.split("/")[-1],
            "language": info.language.value,
            "complexity": info.complexity,
            "functions": len(info.functions),
            "group": path.split("/")[0] if "/" in path else "root",
        }
        for path, info in ctx.files.items()
    ]

    edges = [
        {"source": e["from"], "target": e["to"], "type": "dependency"}
        for e in ctx.dependency_edges[:100]
    ]

    return {"nodes": nodes, "edges": edges}
