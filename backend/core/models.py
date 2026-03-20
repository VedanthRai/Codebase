"""
CodeOracle — Core Data Models
All structured data types used across the system.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime


# ─── Enums ────────────────────────────────────────────────────────────────────

class Language(str, Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    CPP = "cpp"
    C = "c"
    CSHARP = "csharp"
    RUBY = "ruby"
    PHP = "php"
    SWIFT = "swift"
    GO = "go"
    RUST = "rust"
    UNKNOWN = "unknown"


class QueryIntent(str, Enum):
    EXPLAIN = "explain"          # What does X do?
    WHY = "why"                  # Why is X designed this way?
    FLOW = "flow"                # How does execution flow through X?
    IMPACT = "impact"            # What happens if I change X?
    DEBUG = "debug"              # Why is X failing?
    ARCHITECTURE = "architecture" # Show me the architecture
    HEALTH = "health"            # How healthy is this codebase?
    GENERAL = "general"          # General question


class AgentRole(str, Enum):
    RETRIEVAL = "retrieval"
    UNDERSTANDING = "understanding"
    ARCHITECTURE = "architecture"
    ANALYZER = "analyzer"
    ASSISTANT = "assistant"
    VERIFIER = "verifier"
    REFLECTION = "reflection"


# ─── Code Structure Models ─────────────────────────────────────────────────────

class FunctionInfo(BaseModel):
    name: str
    file_path: str
    start_line: int
    end_line: int
    docstring: Optional[str] = None
    calls: List[str] = Field(default_factory=list)       # function names it calls
    called_by: List[str] = Field(default_factory=list)   # function names that call it
    parameters: List[str] = Field(default_factory=list)
    return_type: Optional[str] = None
    complexity: int = 1
    language: Language = Language.UNKNOWN


class ClassInfo(BaseModel):
    name: str
    file_path: str
    start_line: int
    end_line: int
    docstring: Optional[str] = None
    methods: List[str] = Field(default_factory=list)
    inherits_from: List[str] = Field(default_factory=list)
    language: Language = Language.UNKNOWN


class FileInfo(BaseModel):
    path: str
    language: Language
    imports: List[str] = Field(default_factory=list)
    exports: List[str] = Field(default_factory=list)
    functions: List[str] = Field(default_factory=list)
    classes: List[str] = Field(default_factory=list)
    size_lines: int = 0
    complexity: float = 0.0
    summary: Optional[str] = None


class CodeChunk(BaseModel):
    """A chunk of code ready for embedding."""
    chunk_id: str
    content: str
    file_path: str
    chunk_type: str  # "function", "class", "module", "block"
    name: Optional[str] = None
    start_line: int = 0
    end_line: int = 0
    language: Language = Language.UNKNOWN
    metadata: Dict[str, Any] = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list)


# ─── Repository Context ────────────────────────────────────────────────────────

class RepositoryContext(BaseModel):
    """Global context maintained across all agents."""
    repo_id: str
    repo_url: str
    repo_name: str
    cloned_at: datetime = Field(default_factory=datetime.utcnow)

    # Structure
    files: Dict[str, FileInfo] = Field(default_factory=dict)
    functions: Dict[str, FunctionInfo] = Field(default_factory=dict)
    classes: Dict[str, ClassInfo] = Field(default_factory=dict)

    # Graph data (serializable)
    dependency_edges: List[Dict[str, str]] = Field(default_factory=list)
    call_edges: List[Dict[str, str]] = Field(default_factory=list)

    # Intelligence
    repo_summary: str = ""
    critical_modules: List[str] = Field(default_factory=list)
    entry_points: List[str] = Field(default_factory=list)
    architecture_notes: str = ""

    # Health metrics
    total_files: int = 0
    total_functions: int = 0
    total_classes: int = 0
    avg_complexity: float = 0.0
    languages: Dict[str, int] = Field(default_factory=dict)

    # README / docs
    readme_content: str = ""
    has_tests: bool = False
    test_coverage_estimate: float = 0.0


# ─── Agent Models ─────────────────────────────────────────────────────────────

class RetrievalResult(BaseModel):
    chunks: List[CodeChunk]
    query_enhanced: str
    retrieval_method: str  # "semantic", "keyword", "hybrid", "graph-expanded"
    scores: List[float] = Field(default_factory=list)


class AgentMessage(BaseModel):
    role: AgentRole
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class VerificationResult(BaseModel):
    is_grounded: bool
    confidence_score: float  # 0.0 - 1.0
    hallucination_flags: List[str] = Field(default_factory=list)
    grounding_evidence: List[str] = Field(default_factory=list)
    revised_response: Optional[str] = None


class DiagramOutput(BaseModel):
    diagram_type: str  # "architecture", "sequence", "dependency", "class"
    mermaid_code: str
    plantuml_code: Optional[str] = None
    description: str
    involved_components: List[str] = Field(default_factory=list)


class HealthReport(BaseModel):
    overall_score: float  # 0-100
    complexity_score: float
    coupling_score: float
    maintainability_score: float
    test_coverage_score: float
    issues: List[Dict[str, str]] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


# ─── API Models ───────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    github_url: str
    branch: str = "main"
    include_tests: bool = True
    max_files: Optional[int] = None


class QueryRequest(BaseModel):
    repo_id: str
    query: str
    mode: Optional[QueryIntent] = None
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    include_diagrams: bool = False


class QueryResponse(BaseModel):
    query_id: str
    original_query: str
    enhanced_query: str
    intent: QueryIntent
    response: str
    verification: VerificationResult
    diagrams: List[DiagramOutput] = Field(default_factory=list)
    retrieved_chunks: List[CodeChunk] = Field(default_factory=list)
    agent_trace: List[AgentMessage] = Field(default_factory=list)
    processing_time_ms: float
