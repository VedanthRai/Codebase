"""
CodeOracle — Repository Ingestion Service
Clones repos, runs static analysis, builds RAG index, generates repo summary.
"""
import hashlib
import shutil
import asyncio
import os
from pathlib import Path
from typing import Dict, Optional, Callable
from loguru import logger
import git

from core.config import settings
from core.models import RepositoryContext, IngestRequest
from analysis.static_engine import StaticAnalysisEngine
from rag.pipeline import HybridRetriever
from agents.orchestrator import AgentOrchestrator
import google.generativeai as genai


# In-memory store (replace with Redis/DB in production)
_repos: Dict[str, RepositoryContext] = {}
_retrievers: Dict[str, HybridRetriever] = {}
_orchestrators: Dict[str, AgentOrchestrator] = {}


def _make_repo_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


async def ingest_repository(
    request: IngestRequest,
    progress_callback: Optional[Callable[[str, int], None]] = None,
) -> RepositoryContext:
    """
    Full ingestion pipeline:
    1. Clone repository
    2. Static analysis
    3. Build RAG index
    4. Generate repo summary via LLM
    5. Store context for querying
    """
    repo_id = _make_repo_id(request.github_url)

    def progress(msg: str, pct: int = 0):
        logger.info(f"[{repo_id}] {msg} ({pct}%)")
        if progress_callback:
            progress_callback(msg, pct)

    progress("Cloning repository...", 5)
    repo_path = await _clone_repo(request.github_url, repo_id, request.branch)

    progress("Analyzing code structure...", 25)
    engine = StaticAnalysisEngine()
    loop = asyncio.get_event_loop()
    ctx, chunks = await loop.run_in_executor(
        None, engine.analyze_repository, repo_path, repo_id, request.github_url
    )

    progress(f"Indexing {len(chunks)} code chunks...", 50)
    retriever = HybridRetriever(repo_id)
    await loop.run_in_executor(None, retriever.index, chunks, ctx)

    progress("Generating repository intelligence...", 75)
    ctx.repo_summary = await _generate_repo_summary(ctx)

    progress("Finalizing...", 95)
    _repos[repo_id] = ctx
    _retrievers[repo_id] = retriever

    _orchestrators[repo_id] = AgentOrchestrator(retriever, ctx)

    progress("Ready!", 100)
    logger.info(f"Repository {ctx.repo_name} ingested successfully (id={repo_id})")
    return ctx


async def _clone_repo(url: str, repo_id: str, branch: str = "main") -> str:
    repo_path = Path(settings.repos_dir) / repo_id

    if repo_path.exists():
        logger.info(f"Repository already cloned at {repo_path}, updating...")
        try:
            repo = git.Repo(repo_path)
            repo.remotes.origin.pull()
            return str(repo_path)
        except Exception:
            shutil.rmtree(repo_path)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: git.Repo.clone_from(url, str(repo_path), depth=1, branch=branch)
    )
    return str(repo_path)


async def _generate_repo_summary(ctx: RepositoryContext) -> str:
    """Use Gemini to generate an intelligent repository summary."""
    genai.configure(api_key=settings.gemini_api_key)

    prompt = f"""Analyze this repository and provide a concise architectural summary.

Repository: {ctx.repo_name}
Files: {ctx.total_files}
Functions: {ctx.total_functions}
Classes: {ctx.total_classes}
Languages: {ctx.languages}
Critical modules (by import frequency): {ctx.critical_modules[:8]}
Entry points: {ctx.entry_points[:5]}
README excerpt:
{ctx.readme_content[:1500]}

Provide a 3-4 paragraph summary covering:
1. What this system does (purpose)
2. Main architectural patterns used
3. Key components and their roles
4. Notable design decisions"""

    try:
        model_name = settings.model_name
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt, generation_config=genai.types.GenerationConfig(max_output_tokens=600))
        return response.text
    except Exception as e:
        logger.warning(f"Summary generation failed: {e}")
        return f"Repository with {ctx.total_files} files using {list(ctx.languages.keys())}."


def get_context(repo_id: str) -> Optional[RepositoryContext]:
    return _repos.get(repo_id)


def get_orchestrator(repo_id: str) -> Optional[AgentOrchestrator]:
    return _orchestrators.get(repo_id)


def list_repos() -> Dict[str, Dict]:
    return {
        repo_id: {
            "repo_id": repo_id,
            "name": ctx.repo_name,
            "url": ctx.repo_url,
            "files": ctx.total_files,
            "functions": ctx.total_functions,
            "languages": ctx.languages,
            "ingested_at": ctx.cloned_at.isoformat(),
        }
        for repo_id, ctx in _repos.items()
    }
