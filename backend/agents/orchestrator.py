"""
CodeOracle — Multi-Agent System
7 specialized agents orchestrated for deep codebase understanding.
"""
import json
import re
import time
import uuid
import os
from typing import List, Dict, Any, Optional, Tuple
from loguru import logger
import google.generativeai as genai

from core.config import settings
from core.models import (
    AgentMessage, AgentRole, CodeChunk, DiagramOutput,
    QueryIntent, QueryRequest, QueryResponse, RetrievalResult,
    RepositoryContext, VerificationResult, HealthReport,
)
from rag.pipeline import HybridRetriever


# ─── Base Agent ───────────────────────────────────────────────────────────────

class BaseAgent:
    def __init__(self, role: AgentRole):
        self.role = role
        self.trace: List[AgentMessage] = []

    def _call(self, system: str, messages: List[Dict], max_tokens: int = 2000) -> str:
        # Try Gemini keys first
        gemini_keys = settings.get_api_keys()
        for key in gemini_keys:
            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel(
                    model_name=settings.model_name,
                    system_instruction=system
                )
                gemini_messages = []
                for m in messages:
                    role = "user" if m.get("role") == "user" else "model"
                    gemini_messages.append({"role": role, "parts": [m["content"]]})
                response = model.generate_content(
                    gemini_messages,
                    generation_config=genai.types.GenerationConfig(max_output_tokens=max_tokens)
                )
                return response.text
            except Exception as e:
                logger.warning("Gemini key failed, trying next: {}", str(e))

        # Try Groq as fallback
        if settings.groq_api_key:
            try:
                import httpx
                headers = {
                    "Authorization": f"Bearer {settings.groq_api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "system", "content": system}] + messages,
                    "max_tokens": max_tokens,
                }
                r = httpx.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=60)
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
            except Exception as e:
                logger.warning("Groq fallback failed: {}", str(e))

        # Try OpenRouter as final fallback
        if settings.openrouter_api_key:
            try:
                import httpx
                headers = {
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": "meta-llama/llama-3.3-70b-instruct:free",
                    "messages": [{"role": "system", "content": system}] + messages,
                    "max_tokens": max_tokens,
                }
                r = httpx.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=60)
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
            except Exception as e:
                logger.warning("OpenRouter fallback failed: {}", str(e))

        raise RuntimeError("All API providers exhausted. Please check your API keys in .env")

    def _log(self, content: str, metadata: Dict = None):
        self.trace.append(AgentMessage(
            role=self.role,
            content=content,
            metadata=metadata or {},
        ))


# ─── 1. Retrieval Agent ────────────────────────────────────────────────────────

class RetrievalAgent(BaseAgent):
    """
    Enhances queries, fetches relevant code via hybrid retrieval,
    and expands context using dependency graph.
    """

    SYSTEM = """You are a precise code retrieval specialist.
Your job:
1. Rewrite/expand the user query to maximize retrieval quality
2. Identify what types of code are most relevant (functions, classes, configs)
3. Return ONLY a JSON object with keys: "enhanced_query", "keywords", "intent_type"

Be specific. Focus on technical terms. Never add fluff."""

    def __init__(self, retriever: HybridRetriever):
        super().__init__(AgentRole.RETRIEVAL)
        self.retriever = retriever

    def run(self, query: str, context: RepositoryContext) -> RetrievalResult:
        # Step 1: Enhance query
        enhancement = self._enhance_query(query, context)
        enhanced_q = enhancement.get("enhanced_query", query)

        # Step 2: Retrieve
        result = self.retriever.retrieve(enhanced_q)
        result.query_enhanced = enhanced_q

        self._log(f"Enhanced query: {enhanced_q}. Retrieved {len(result.chunks)} chunks.",
                  {"enhancement": enhancement})
        return result

    def _enhance_query(self, query: str, context: RepositoryContext) -> Dict:
        ctx_hint = f"Repository: {context.repo_name}. Languages: {list(context.languages.keys())}. " \
                   f"Critical modules: {context.critical_modules[:5]}."
        try:
            raw = self._call(
                system=self.SYSTEM,
                messages=[{"role": "user", "content": f"{ctx_hint}\n\nOriginal query: {query}"}],
                max_tokens=300,
            )
            # Extract JSON safely
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.warning(f"Query enhancement failed: {e}")
        return {"enhanced_query": query, "keywords": [], "intent_type": "general"}


# ─── 2. Understanding Agent ────────────────────────────────────────────────────

class UnderstandingAgent(BaseAgent):
    """
    Explains WHY code is designed the way it is.
    Performs dependency-aware reasoning and execution flow analysis.
    """

    SYSTEM = """You are a senior software architect and code explainer.
Your strength: explaining not just WHAT code does, but WHY it's designed that way.

When analyzing code:
- Trace execution flows across modules
- Explain design patterns and architectural decisions
- Identify trade-offs made by the author
- Connect individual components to the bigger picture
- For "why" questions: hypothesize original design intent from context

Always ground your explanations in the actual code provided.
Structure: brief summary → detailed explanation → key insights."""

    def __init__(self):
        super().__init__(AgentRole.UNDERSTANDING)

    def run(self, query: str, intent: QueryIntent, chunks: List[CodeChunk],
            context: RepositoryContext, history: List[Dict]) -> str:

        code_context = self._format_chunks(chunks)
        repo_context = self._format_repo_context(context)

        system = self.SYSTEM
        if intent == QueryIntent.WHY:
            system += "\n\nFOCUS: This is a 'WHY' question. Deeply explain design rationale, not just behavior."
        elif intent == QueryIntent.FLOW:
            system += "\n\nFOCUS: Trace the execution flow step by step across functions and modules."
        elif intent == QueryIntent.IMPACT:
            system += "\n\nFOCUS: Analyze ripple effects. What depends on this? What would break? Risk levels."

        messages = history[-4:] if history else []  # Keep last 2 turns
        messages.append({
            "role": "user",
            "content": f"""## Repository Overview
{repo_context}

## Retrieved Code Context
{code_context}

## Question
{query}"""
        })

        answer = self._call(system=system, messages=messages, max_tokens=3000)
        self._log(f"Generated {intent.value} explanation", {"intent": intent.value})
        return answer

    def _format_chunks(self, chunks: List[CodeChunk]) -> str:
        parts = []
        for i, chunk in enumerate(chunks, 1):
            header = f"### [{i}] {chunk.chunk_type.upper()}: {chunk.name or 'code'} | {chunk.file_path}"
            if chunk.metadata.get("docstring"):
                header += f"\n> {chunk.metadata['docstring']}"
            parts.append(f"{header}\n```{chunk.language.value}\n{chunk.content}\n```")
        return "\n\n".join(parts) if parts else "No code context retrieved."

    def _format_repo_context(self, ctx: RepositoryContext) -> str:
        return (
            f"**{ctx.repo_name}** | "
            f"{ctx.total_files} files, {ctx.total_functions} functions, {ctx.total_classes} classes | "
            f"Languages: {', '.join(ctx.languages.keys())} | "
            f"Critical modules: {', '.join(ctx.critical_modules[:5])}"
        )


# ─── 3. Architecture Agent ────────────────────────────────────────────────────

class ArchitectureAgent(BaseAgent):
    """
    Generates architecture diagrams, module interaction maps,
    and execution flow sequence diagrams in Mermaid/PlantUML.
    """

    SYSTEM = """You are a software architecture visualization expert.
Generate precise, accurate diagrams based on real code structure.
Output ONLY valid Mermaid diagram code (no markdown fences, no explanation).
Use real names from the codebase. Be accurate, not generic."""

    def __init__(self):
        super().__init__(AgentRole.ARCHITECTURE)

    def generate_architecture(self, context: RepositoryContext) -> List[DiagramOutput]:
        diagrams = []

        # 1. High-level module architecture
        arch_diagram = self._generate_module_diagram(context)
        if arch_diagram:
            diagrams.append(arch_diagram)

        # 2. Dependency graph
        dep_diagram = self._generate_dependency_diagram(context)
        if dep_diagram:
            diagrams.append(dep_diagram)

        # 3. Call graph (top functions)
        call_diagram = self._generate_call_diagram(context)
        if call_diagram:
            diagrams.append(call_diagram)

        return diagrams

    def generate_flow_diagram(self, query: str, chunks: List[CodeChunk],
                               context: RepositoryContext) -> Optional[DiagramOutput]:
        """Generate execution flow sequence diagram for a query."""
        if not chunks:
            return None

        chunk_summary = "\n".join([
            f"- {c.name or 'block'} in {c.file_path} (calls: {', '.join(c.dependencies[:3])})"
            for c in chunks[:8]
        ])

        prompt = f"""Based on this code structure, generate a Mermaid sequence diagram
showing the execution flow relevant to: "{query}"

Components involved:
{chunk_summary}

Generate ONLY the Mermaid sequenceDiagram code. Start with: sequenceDiagram
Rules: 
1. Use safe alphanumeric names for participants.
2. Do NOT use HTML brackets (< or >) in messages.
3. Replace < and > with [ and ] if needed.
4. Escape any quotes in messages.
5. Do not use backslashes (\\)."""

        try:
            raw = self._call(
                system=self.SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
            )
            mermaid = self._clean_mermaid(raw)
            if mermaid:
                return DiagramOutput(
                    diagram_type="sequence",
                    mermaid_code=mermaid,
                    description=f"Execution flow for: {query}",
                    involved_components=[c.name or c.file_path for c in chunks[:5]],
                )
        except Exception as e:
            logger.warning(f"Flow diagram generation failed: {e}")
        return None

    def _generate_module_diagram(self, ctx: RepositoryContext) -> Optional[DiagramOutput]:
        # Build directly from real file structure — no LLM, no syntax errors
        files_by_dir: Dict[str, List[str]] = {}
        for path in list(ctx.files.keys())[:40]:
            parts = path.replace('\\', '/').split('/')
            dir_name = parts[0] if len(parts) > 1 else "root"
            files_by_dir.setdefault(dir_name, []).append(path)

        if not files_by_dir:
            return None

        lines = ["graph TD"]
        seen = set()

        for dir_name, files in list(files_by_dir.items())[:12]:
            dir_id = re.sub(r'[^a-zA-Z0-9]', '_', dir_name)
            dir_label = dir_name.replace('"', "'")
            if dir_id not in seen:
                lines.append(f'    {dir_id}["{dir_label}"]')
                seen.add(dir_id)

        # Connect entry points to their modules
        for ep in ctx.entry_points[:5]:
            ep_clean = ep.replace('\\', '/')
            parts = ep_clean.split('/')
            dir_name = parts[0] if len(parts) > 1 else "root"
            dir_id = re.sub(r'[^a-zA-Z0-9]', '_', dir_name)
            ep_id = re.sub(r'[^a-zA-Z0-9]', '_', ep_clean)
            ep_label = parts[-1].replace('"', "'")
            if ep_id not in seen:
                lines.append(f'    {ep_id}(("{ep_label}"))')
                seen.add(ep_id)
            lines.append(f'    {ep_id} --> {dir_id}')

        # Connect critical modules
        dirs = list(files_by_dir.keys())
        for i in range(min(len(dirs) - 1, 8)):
            src = re.sub(r'[^a-zA-Z0-9]', '_', dirs[i])
            tgt = re.sub(r'[^a-zA-Z0-9]', '_', dirs[i + 1])
            lines.append(f'    {src} --> {tgt}')

        return DiagramOutput(
            diagram_type="architecture",
            mermaid_code="\n".join(lines),
            description=f"Architecture overview of {ctx.repo_name}",
            involved_components=list(files_by_dir.keys()),
        )

    def _generate_dependency_diagram(self, ctx: RepositoryContext) -> Optional[DiagramOutput]:
        # Top 15 most connected files only
        file_degrees: Dict[str, int] = {}
        for edge in ctx.dependency_edges:
            file_degrees[edge["from"]] = file_degrees.get(edge["from"], 0) + 1

        top_files = sorted(file_degrees.items(), key=lambda x: x[1], reverse=True)[:12]
        top_file_set = {f for f, _ in top_files}

        edges = [e for e in ctx.dependency_edges
                 if e["from"] in top_file_set][:25]

        if not edges:
            return None

        lines = ["graph LR"]
        seen_nodes = set()
        for edge in edges:
            src = self._safe_id(edge["from"])
            tgt = self._safe_id(edge["to"])
            
            # Sanitize labels to prevent Mermaid v11 parsing crashes
            src_label = self._sanitize_label(edge["from"].replace('\\', '/').split("/")[-1])
            tgt_label = self._sanitize_label(edge["to"].replace('\\', '/').split("/")[-1])
            
            if src not in seen_nodes:
                lines.append(f'    {src}["{src_label}"]')
                seen_nodes.add(src)
            if tgt not in seen_nodes:
                lines.append(f'    {tgt}["{tgt_label}"]')
                seen_nodes.add(tgt)
            lines.append(f"    {src} --> {tgt}")

        return DiagramOutput(
            diagram_type="dependency",
            mermaid_code="\n".join(lines),
            description="File dependency graph (top connected files)",
            involved_components=[f for f, _ in top_files],
        )

    def _generate_call_diagram(self, ctx: RepositoryContext) -> Optional[DiagramOutput]:
        if not ctx.call_edges:
            return None

        # Top 20 call edges
        edges = ctx.call_edges[:20]
        lines = ["graph TD"]
        seen = set()
        for edge in edges:
            src = self._safe_id(edge["from"])
            tgt = self._safe_id(edge["to"])
            
            # Sanitize labels to prevent Mermaid v11 parsing crashes
            src_label = self._sanitize_label(edge["from"].replace('\\', '/'))
            tgt_label = self._sanitize_label(edge["to"].replace('\\', '/'))
            
            if src not in seen:
                lines.append(f'    {src}["{src_label}"]')
                seen.add(src)
            if tgt not in seen:
                lines.append(f'    {tgt}["{tgt_label}"]')
                seen.add(tgt)
            lines.append(f"    {src} -->|calls| {tgt}")

        return DiagramOutput(
            diagram_type="call_graph",
            mermaid_code="\n".join(lines),
            description="Function call graph",
            involved_components=[e["from"] for e in edges[:10]],
        )

    def _safe_id(self, name: str) -> str:
        import hashlib
        clean_name = re.sub(r'[^a-zA-Z0-9]', '_', name)[:20]
        short_hash = hashlib.md5(name.encode()).hexdigest()[:6]
        return f"node_{clean_name}_{short_hash}"

    def _sanitize_label(self, label: str) -> str:
        s = label.replace('"', "'").replace('<', '(').replace('>', ')').replace('\\', '/')
        s = re.sub(r'[\x00-\x1f\x7f]', '', s)
        return s.strip()

    def _clean_mermaid(self, raw: str) -> str:
        # 1. Try to extract from markdown code blocks first
        match = re.search(r'```(?:mermaid)?\s*(.*?)\s*```', raw, re.DOTALL)
        if match:
            raw = match.group(1).strip()
        else:
            # 2. Fallback: Strip remaining markdown backticks
            raw = re.sub(r'```mermaid\s*', '', raw)
            raw = re.sub(r'```\s*', '', raw)
        
        # 3. Strip conversational filler before the actual diagram code
        lines = raw.split('\n')
        directives = ['graph TD', 'graph LR', 'graph TB', 'flowchart', 'sequenceDiagram', 'classDiagram', 'stateDiagram', 'gantt', 'journey']
        for i, line in enumerate(lines):
            normalized = line.strip().lower()
            if any(normalized.startswith(d.lower()) for d in directives):
                return '\n'.join(lines[i:]).strip()

        # 4. If the content includes any mermaid directive anywhere, return that block
        for i, line in enumerate(lines):
            if any(d.lower() in line.strip().lower() for d in directives):
                return '\n'.join(lines[i:]).strip()

        # Last resort: return stripped raw text.
        return raw.strip()


# ─── 4. Code Analysis Agent ───────────────────────────────────────────────────

class CodeAnalysisAgent(BaseAgent):
    """
    Detects bugs, code smells, anti-patterns.
    Suggests optimizations and refactoring.
    """

    SYSTEM = """You are a senior code reviewer with expertise in multiple languages.
Analyze code for:
- Bugs and logical errors
- Security vulnerabilities
- Performance bottlenecks
- Code smells (God objects, long methods, magic numbers, etc.)
- Anti-patterns
- Missing error handling

For each issue:
1. Name the issue
2. Explain why it's a problem
3. Show the fix
4. Rate severity: CRITICAL / HIGH / MEDIUM / LOW

Be specific and actionable. Reference actual code lines."""

    def __init__(self):
        super().__init__(AgentRole.ANALYZER)

    def analyze(self, chunks: List[CodeChunk], context: RepositoryContext) -> str:
        code_context = "\n\n".join([
            f"### {c.file_path} — {c.name or 'code'}\n```\n{c.content}\n```"
            for c in chunks[:6]
        ])

        messages = [{
            "role": "user",
            "content": f"Analyze this code from {context.repo_name}:\n\n{code_context}",
        }]
        result = self._call(system=self.SYSTEM, messages=messages, max_tokens=2500)
        self._log("Code analysis complete")
        return result

    def compute_health_report(self, context: RepositoryContext) -> HealthReport:
        """Compute repository health metrics."""
        # Complexity score (inverse: lower complexity = higher score)
        max_complexity = 50
        avg_c = min(context.avg_complexity, max_complexity)
        complexity_score = max(0, 100 - (avg_c / max_complexity) * 100)

        # Coupling score (based on dependency edges per file)
        if context.total_files > 0:
            avg_deps = len(context.dependency_edges) / context.total_files
            coupling_score = max(0, 100 - min(avg_deps * 10, 100))
        else:
            coupling_score = 100

        # Test coverage estimate
        test_score = 80 if context.has_tests else 10
        test_score += min(context.test_coverage_estimate * 100, 20)

        # Maintainability (average of complexity + coupling + doc coverage)
        doc_coverage = sum(
            1 for fn in context.functions.values() if fn.docstring
        ) / max(context.total_functions, 1) * 100
        maintainability_score = (complexity_score + coupling_score + doc_coverage) / 3

        overall = (complexity_score * 0.3 + coupling_score * 0.25 +
                   maintainability_score * 0.25 + test_score * 0.2)

        issues = []
        if complexity_score < 50:
            issues.append({"type": "complexity", "severity": "HIGH",
                           "message": f"High avg cyclomatic complexity: {context.avg_complexity:.1f}"})
        if coupling_score < 50:
            issues.append({"type": "coupling", "severity": "MEDIUM",
                           "message": "High inter-file coupling detected"})
        if not context.has_tests:
            issues.append({"type": "testing", "severity": "HIGH",
                           "message": "No test files detected"})
        if doc_coverage < 30:
            issues.append({"type": "documentation", "severity": "MEDIUM",
                           "message": f"Low docstring coverage: {doc_coverage:.0f}%"})

        recommendations = []
        if complexity_score < 60:
            recommendations.append("Break down complex functions (>10 cyclomatic complexity)")
        if coupling_score < 60:
            recommendations.append("Introduce abstraction layers to reduce direct dependencies")
        if not context.has_tests:
            recommendations.append("Add unit tests — aim for >70% coverage")
        if doc_coverage < 50:
            recommendations.append("Add docstrings to public functions and classes")

        return HealthReport(
            overall_score=round(overall, 1),
            complexity_score=round(complexity_score, 1),
            coupling_score=round(coupling_score, 1),
            maintainability_score=round(maintainability_score, 1),
            test_coverage_score=round(test_score, 1),
            issues=issues,
            recommendations=recommendations,
        )


# ─── 5. Verifier Agent ────────────────────────────────────────────────────────

class VerifierAgent(BaseAgent):
    """
    Checks if responses are grounded in retrieved code.
    Detects hallucinations and provides confidence scores.
    CRITICAL for production reliability.
    """

    SYSTEM = """You are a fact-checker for AI-generated code explanations.
Given:
1. A question
2. Retrieved code snippets  
3. An AI-generated answer

Evaluate:
- Is every claim in the answer supported by the code snippets?
- Are there any invented function names, classes, or behaviors?
- Does the answer contradict the actual code?

Respond with ONLY valid JSON:
{
  "is_grounded": true/false,
  "confidence_score": 0.0-1.0,
  "hallucination_flags": ["list of suspicious claims"],
  "grounding_evidence": ["evidence statements"],
  "needs_revision": true/false
}"""

    def __init__(self):
        super().__init__(AgentRole.VERIFIER)

    def verify(self, query: str, answer: str, chunks: List[CodeChunk]) -> VerificationResult:
        if not chunks:
            return VerificationResult(
                is_grounded=False,
                confidence_score=0.3,
                hallucination_flags=["No code context available for verification"],
                grounding_evidence=[],
            )

        code_context = "\n".join([
            f"[{c.name or c.file_path}]: {c.content[:300]}"
            for c in chunks[:5]
        ])

        try:
            raw = self._call(
                system=self.SYSTEM,
                messages=[{
                    "role": "user",
                    "content": f"Question: {query}\n\nCode:\n{code_context}\n\nAnswer:\n{answer}",
                }],
                max_tokens=600,
            )
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                result = VerificationResult(
                    is_grounded=data.get("is_grounded", True),
                    confidence_score=data.get("confidence_score", 0.8),
                    hallucination_flags=data.get("hallucination_flags", []),
                    grounding_evidence=data.get("grounding_evidence", []),
                )
                self._log(f"Verification: grounded={result.is_grounded}, score={result.confidence_score}")
                return result
        except Exception as e:
            logger.warning(f"Verification failed: {e}")

        return VerificationResult(is_grounded=True, confidence_score=0.7, grounding_evidence=[])


# ─── 6. Reflection Agent ──────────────────────────────────────────────────────

class ReflectionAgent(BaseAgent):
    """
    Iteratively improves answers by reflecting on gaps and weaknesses.
    Triggered when confidence is low or answer is incomplete.
    """

    SYSTEM = """You are a critical self-reviewer for technical explanations.
Given a draft answer and the original question, identify:
1. What's missing or unclear?
2. What could be explained better?
3. Are there edge cases not covered?

Then produce an IMPROVED version of the answer.
Format: First write <CRITIQUE>...</CRITIQUE>, then <IMPROVED>...</IMPROVED>"""

    def __init__(self):
        super().__init__(AgentRole.REFLECTION)

    def reflect(self, query: str, draft_answer: str, verification: VerificationResult) -> str:
        if verification.confidence_score > 0.85 and verification.is_grounded:
            return draft_answer  # Good enough, no need to reflect

        prompt = f"""Question: {query}

Draft Answer:
{draft_answer}

Issues found by verifier:
{', '.join(verification.hallucination_flags) if verification.hallucination_flags else 'None'}
Confidence: {verification.confidence_score}

Improve this answer."""

        try:
            raw = self._call(
                system=self.SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2500,
            )
            # Extract improved section
            match = re.search(r'<IMPROVED>(.*?)</IMPROVED>', raw, re.DOTALL)
            if match:
                improved = match.group(1).strip()
                self._log("Answer improved via reflection")
                return improved
        except Exception as e:
            logger.warning(f"Reflection failed: {e}")

        return draft_answer


# ─── 7. Summary Agent ─────────────────────────────────────────────────────────

class SummaryAgent(BaseAgent):
    """
    Generates a concise TL;DR and bullet-point key takeaways for any response.
    Helps users quickly grasp the most important points.
    """

    SYSTEM = """You are a technical summarizer. Given a detailed code explanation, produce:
1. A one-sentence TL;DR
2. 3-5 bullet-point key takeaways

Respond ONLY with valid JSON:
{
  "tldr": "one sentence summary",
  "takeaways": ["point 1", "point 2", "point 3"]
}"""

    def __init__(self):
        super().__init__(AgentRole.ASSISTANT)

    def summarize(self, response_text: str) -> Dict:
        if len(response_text) < 200:
            return {"tldr": "", "takeaways": []}
        try:
            raw = self._call(
                system=self.SYSTEM,
                messages=[{"role": "user", "content": response_text[:3000]}],
                max_tokens=400,
            )
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.warning(f"Summary generation failed: {e}")
        return {"tldr": "", "takeaways": []}


# ─── 8. Question Suggester ─────────────────────────────────────────────────────

class QuestionSuggesterAgent(BaseAgent):
    """
    Proactively suggests relevant follow-up questions based on the repository context.
    """

    SYSTEM = """You are a developer assistant. Given a repository's structure and summary,
suggest 6 insightful questions a developer would want to ask about this codebase.
Focus on architecture, design decisions, potential issues, and key flows.

Respond ONLY with valid JSON:
{"questions": ["question 1", "question 2", "question 3", "question 4", "question 5", "question 6"]}"""

    def __init__(self):
        super().__init__(AgentRole.ASSISTANT)

    def suggest(self, context: RepositoryContext) -> List[str]:
        prompt = f"""Repository: {context.repo_name}
Languages: {list(context.languages.keys())}
Files: {context.total_files}, Functions: {context.total_functions}, Classes: {context.total_classes}
Critical modules: {context.critical_modules[:6]}
Entry points: {context.entry_points[:4]}
Summary: {context.repo_summary[:500]}"""

        try:
            raw = self._call(
                system=self.SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return data.get("questions", [])
        except Exception as e:
            logger.warning(f"Question suggestion failed: {e}")
        return []


# ─── 9. Assistant Agent (Orchestrator) ────────────────────────────────────────

class AssistantAgent(BaseAgent):
    """
    Main conversational interface.
    Detects intent and routes to specialist agents.
    """

    INTENT_SYSTEM = """Classify the developer's query intent.
Return ONLY one of: explain, why, flow, impact, debug, architecture, health, general"""

    def __init__(self):
        super().__init__(AgentRole.ASSISTANT)

    def detect_intent(self, query: str) -> QueryIntent:
        # Fast heuristic first
        q = query.lower()
        if any(w in q for w in ["why", "reason", "design", "purpose", "rationale"]):
            return QueryIntent.WHY
        if any(w in q for w in ["flow", "sequence", "trace", "follow", "path", "execution"]):
            return QueryIntent.FLOW
        if any(w in q for w in ["impact", "change", "break", "affect", "depend", "if i"]):
            return QueryIntent.IMPACT
        if any(w in q for w in ["bug", "error", "fail", "crash", "debug", "fix", "wrong"]):
            return QueryIntent.DEBUG
        if any(w in q for w in ["architecture", "diagram", "structure", "overview", "map"]):
            return QueryIntent.ARCHITECTURE
        if any(w in q for w in ["health", "quality", "score", "complexity", "maintainab"]):
            return QueryIntent.HEALTH
        if any(w in q for w in ["what", "explain", "describe", "how does", "tell me"]):
            return QueryIntent.EXPLAIN

        # LLM fallback for ambiguous queries
        try:
            raw = self._call(
                system=self.INTENT_SYSTEM,
                messages=[{"role": "user", "content": query}],
                max_tokens=20,
            ).strip().lower()
            for intent in QueryIntent:
                if intent.value in raw:
                    return intent
        except Exception:
            pass
        return QueryIntent.GENERAL


# ─── Orchestrator ─────────────────────────────────────────────────────────────

class AgentOrchestrator:
    """
    Coordinates all 7 agents in the optimal pipeline for each query type.
    """

    def __init__(self, retriever: HybridRetriever, context: RepositoryContext):
        self.context = context

        genai.configure(api_key=settings.gemini_api_key)
        self.assistant = AssistantAgent()
        self.retrieval = RetrievalAgent(retriever)
        self.understanding = UnderstandingAgent()
        self.architecture = ArchitectureAgent()
        self.analyzer = CodeAnalysisAgent()
        self.verifier = VerifierAgent()
        self.reflection = ReflectionAgent()
        self.summarizer = SummaryAgent()
        self.suggester = QuestionSuggesterAgent()

    async def process(self, request: QueryRequest) -> QueryResponse:
        start_time = time.time()
        query_id = str(uuid.uuid4())[:8]
        all_trace: List[AgentMessage] = []

        # 1. Detect intent
        intent = request.mode or self.assistant.detect_intent(request.query)
        all_trace.extend(self.assistant.trace)
        self.assistant.trace.clear()

        # 2. Retrieve relevant code
        retrieval_result = self.retrieval.run(request.query, self.context)
        all_trace.extend(self.retrieval.trace)
        self.retrieval.trace.clear()

        # 3. Route to appropriate agent pipeline
        response_text = ""
        diagrams: List[DiagramOutput] = []

        if intent == QueryIntent.ARCHITECTURE:
            diagrams = self.architecture.generate_architecture(self.context)
            response_text = self._architecture_summary(self.context)

        elif intent == QueryIntent.HEALTH:
            health = self.analyzer.compute_health_report(self.context)
            response_text = self._health_summary(health)

        elif intent in (QueryIntent.FLOW, QueryIntent.IMPACT, QueryIntent.DEBUG):
            response_text = self.understanding.run(
                request.query, intent,
                retrieval_result.chunks, self.context,
                request.conversation_history,
            )
            if intent == QueryIntent.FLOW and request.include_diagrams:
                flow_diag = self.architecture.generate_flow_diagram(
                    request.query, retrieval_result.chunks, self.context
                )
                if flow_diag:
                    diagrams.append(flow_diag)

        elif intent == QueryIntent.DEBUG:
            analysis = self.analyzer.analyze(retrieval_result.chunks, self.context)
            understanding = self.understanding.run(
                request.query, intent,
                retrieval_result.chunks, self.context,
                request.conversation_history,
            )
            response_text = f"{understanding}\n\n---\n### Code Analysis\n{analysis}"

        else:  # explain, why, general
            response_text = self.understanding.run(
                request.query, intent,
                retrieval_result.chunks, self.context,
                request.conversation_history,
            )

        all_trace.extend(self.understanding.trace)
        self.understanding.trace.clear()

        # 4. Verify response
        verification = self.verifier.verify(
            request.query, response_text, retrieval_result.chunks
        )
        all_trace.extend(self.verifier.trace)
        self.verifier.trace.clear()

        # 5. Reflect & improve if needed
        if verification.confidence_score < 0.75 or not verification.is_grounded:
            response_text = self.reflection.reflect(
                request.query, response_text, verification
            )
            all_trace.extend(self.reflection.trace)
            self.reflection.trace.clear()

        elapsed_ms = (time.time() - start_time) * 1000

        # 6. Generate TL;DR summary
        summary_data = self.summarizer.summarize(response_text)

        # 7. Suggest follow-up questions
        suggested = self.suggester.suggest(self.context)

        return QueryResponse(
            query_id=query_id,
            original_query=request.query,
            enhanced_query=retrieval_result.query_enhanced,
            intent=intent,
            response=response_text,
            verification=verification,
            diagrams=diagrams,
            retrieved_chunks=retrieval_result.chunks[:5],
            agent_trace=all_trace,
            processing_time_ms=round(elapsed_ms, 1),
            tldr=summary_data.get("tldr", ""),
            takeaways=summary_data.get("takeaways", []),
            suggested_questions=suggested,
        )

    def _architecture_summary(self, ctx: RepositoryContext) -> str:
        return f"""## Architecture Overview: {ctx.repo_name}

**Repository Stats:**
- {ctx.total_files} files across {len(ctx.languages)} languages
- {ctx.total_functions} functions, {ctx.total_classes} classes
- Languages: {', '.join(f'{k} ({v})' for k, v in ctx.languages.items())}

**Critical Modules:**
{chr(10).join(f'- `{m}`' for m in ctx.critical_modules[:8])}

**Entry Points:**
{chr(10).join(f'- `{e}`' for e in ctx.entry_points[:5])}

{ctx.repo_summary if ctx.repo_summary else ''}

*Diagrams generated below show module relationships, dependencies, and call flow.*"""

    def _health_summary(self, health: HealthReport) -> str:
        emoji = "🟢" if health.overall_score > 70 else "🟡" if health.overall_score > 50 else "🔴"
        return f"""## Repository Health Report {emoji}

**Overall Score: {health.overall_score}/100**

| Metric | Score |
|--------|-------|
| Complexity | {health.complexity_score}/100 |
| Coupling | {health.coupling_score}/100 |
| Maintainability | {health.maintainability_score}/100 |
| Test Coverage | {health.test_coverage_score}/100 |

### Issues Found
{chr(10).join(f'- **[{i["severity"]}]** {i["message"]}' for i in health.issues) if health.issues else '- None detected ✓'}

### Recommendations
{chr(10).join(f'- {r}' for r in health.recommendations) if health.recommendations else '- Looking good!'}"""
