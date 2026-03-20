"""
CodeOracle — Static Analysis Engine
AST parsing, call graph, dependency graph, complexity metrics.
Supports Python, JavaScript/TypeScript natively; extensible for others.
"""
import ast
import os
import re
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
import networkx as nx
from loguru import logger

from core.models import (
    FileInfo, FunctionInfo, ClassInfo, Language,
    RepositoryContext, CodeChunk
)
from core.config import settings


# ─── Language Detection ────────────────────────────────────────────────────────

LANGUAGE_MAP = {
    ".py": Language.PYTHON,
    ".js": Language.JAVASCRIPT,
    ".jsx": Language.JAVASCRIPT,
    ".ts": Language.TYPESCRIPT,
    ".tsx": Language.TYPESCRIPT,
    ".java": Language.JAVA,
    ".cpp": Language.CPP,
    ".cc": Language.CPP,
    ".h": Language.CPP,
    ".hpp": Language.CPP,
    ".c": Language.C,
    ".cs": Language.CSHARP,
    ".rb": Language.RUBY,
    ".php": Language.PHP,
    ".swift": Language.SWIFT,
    ".go": Language.GO,
    ".rs": Language.RUST,
}

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".next", "target", "vendor", ".tox",
    "coverage", ".mypy_cache", ".pytest_cache",
}

SKIP_EXTENSIONS = {
    ".lock", ".log", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".ico", ".woff", ".ttf", ".eot", ".map", ".min.js",
    ".pyc", ".pyo", ".class", ".jar", ".war",
}


# ─── Python Analyzer ──────────────────────────────────────────────────────────

class PythonAnalyzer:
    """Deep Python AST analysis."""

    def analyze_file(self, path: str, content: str) -> Tuple[FileInfo, List[FunctionInfo], List[ClassInfo]]:
        file_info = FileInfo(
            path=path,
            language=Language.PYTHON,
            size_lines=content.count('\n') + 1,
        )
        functions: List[FunctionInfo] = []
        classes: List[ClassInfo] = []

        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            logger.warning(f"Syntax error in {path}: {e}")
            return file_info, functions, classes

        # Collect imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    file_info.imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    file_info.imports.append(node.module)

        # Analyze top-level functions and classes
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                fn = self._analyze_function(node, path)
                functions.append(fn)
                file_info.functions.append(fn.name)

            elif isinstance(node, ast.ClassDef):
                cls = self._analyze_class(node, path)
                classes.append(cls)
                file_info.classes.append(cls.name)

        # Cyclomatic complexity estimate
        file_info.complexity = self._estimate_complexity(tree)

        return file_info, functions, classes

    def _analyze_function(self, node: ast.FunctionDef, file_path: str) -> FunctionInfo:
        # Extract calls
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)

        # Docstring
        docstring = ast.get_docstring(node)

        # Parameters
        params = [arg.arg for arg in node.args.args]

        # Complexity (count branches)
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler,
                                   ast.With, ast.Assert, ast.comprehension)):
                complexity += 1

        return FunctionInfo(
            name=node.name,
            file_path=file_path,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            docstring=docstring,
            calls=list(set(calls)),
            parameters=params,
            complexity=complexity,
            language=Language.PYTHON,
        )

    def _analyze_class(self, node: ast.ClassDef, file_path: str) -> ClassInfo:
        methods = []
        for item in ast.walk(node):
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(item.name)

        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(base.attr)

        return ClassInfo(
            name=node.name,
            file_path=file_path,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            docstring=ast.get_docstring(node),
            methods=methods,
            inherits_from=bases,
            language=Language.PYTHON,
        )

    def _estimate_complexity(self, tree: ast.AST) -> float:
        count = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler,
                                   ast.With, ast.comprehension, ast.Lambda)):
                count += 1
        return float(count)


# ─── JavaScript Analyzer ──────────────────────────────────────────────────────

class JavaScriptAnalyzer:
    """Regex-based JavaScript/TypeScript analysis (tree-sitter optional)."""

    FUNC_PATTERNS = [
        r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(',
        r'(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\(',
        r'(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?(?:\w+\s*)=>\s*[{(]',
        r'\b(?!(?:if|else|for|while|switch|catch|return)\b)(\w+)\s*\([^)]*\)\s*\{',  # method shorthand
    ]
    CLASS_PATTERN = r'(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?'
    IMPORT_PATTERN = r'import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]'
    CALL_PATTERN = r'(\w+)\s*\('

    def analyze_file(self, path: str, content: str) -> Tuple[FileInfo, List[FunctionInfo], List[ClassInfo]]:
        lang = Language.TYPESCRIPT if path.endswith(('.ts', '.tsx')) else Language.JAVASCRIPT
        file_info = FileInfo(
            path=path,
            language=lang,
            size_lines=content.count('\n') + 1,
        )
        functions: List[FunctionInfo] = []
        classes: List[ClassInfo] = []

        # Imports
        for m in re.finditer(self.IMPORT_PATTERN, content):
            file_info.imports.append(m.group(1))

        # Functions
        for pattern in self.FUNC_PATTERNS:
            for m in re.finditer(pattern, content, re.MULTILINE):
                name = m.group(1)
                line = content[:m.start()].count('\n') + 1
                fn = FunctionInfo(
                    name=name,
                    file_path=path,
                    start_line=line,
                    end_line=line + 20,  # estimate
                    language=lang,
                )
                functions.append(fn)
                file_info.functions.append(name)

        # Classes
        for m in re.finditer(self.CLASS_PATTERN, content, re.MULTILINE):
            name = m.group(1)
            line = content[:m.start()].count('\n') + 1
            cls = ClassInfo(
                name=name,
                file_path=path,
                start_line=line,
                end_line=line + 50,
                inherits_from=[m.group(2)] if m.group(2) else [],
                language=lang,
            )
            classes.append(cls)
            file_info.classes.append(name)

        file_info.complexity = len(re.findall(r'\b(if|else|for|while|switch|catch|&&|\|\|)\b', content)) * 0.5

        return file_info, functions, classes


# ─── Generic Analyzer ─────────────────────────────────────────────────────────

class GenericAnalyzer:
    """Regex-based generic analysis for C++, Java, Go, Rust, etc."""

    # Matches word() { ... } with support for return types, throws, etc. before {
    FUNC_PATTERN = r'\b(?!(?:if|else|for|while|switch|catch|return|new|class|struct|interface|trait|record)\b)([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)\s*(?:[^{;=]*)\{'
    CLASS_PATTERN = r'\b(?:class|struct|interface|trait|record)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
    IMPORT_PATTERN = r'^(?:#include|import|use|require)\s+[<"\'\s]?([a-zA-Z0-9_\.\/]+)[>"\'\s]?;?'

    def analyze_file(self, path: str, content: str, lang: Language) -> Tuple[FileInfo, List[FunctionInfo], List[ClassInfo]]:
        file_info = FileInfo(
            path=path,
            language=lang,
            size_lines=content.count('\n') + 1,
        )
        functions: List[FunctionInfo] = []
        classes: List[ClassInfo] = []

        # Imports
        for m in re.finditer(self.IMPORT_PATTERN, content, re.MULTILINE):
            file_info.imports.append(m.group(1))

        # Functions
        for m in re.finditer(self.FUNC_PATTERN, content):
            name = m.group(1)
            line = content[:m.start()].count('\n') + 1
            fn = FunctionInfo(
                name=name,
                file_path=path,
                start_line=line,
                end_line=line + 15,  # Estimate end line
                language=lang,
            )
            functions.append(fn)
            file_info.functions.append(name)

        # Classes & Structs
        for m in re.finditer(self.CLASS_PATTERN, content):
            name = m.group(1)
            line = content[:m.start()].count('\n') + 1
            cls = ClassInfo(
                name=name,
                file_path=path,
                start_line=line,
                end_line=line + 40,  # Estimate end line
                language=lang,
            )
            classes.append(cls)
            file_info.classes.append(name)

        file_info.complexity = len(re.findall(r'\b(if|else|for|while|switch|catch|match)\b', content)) * 0.5

        return file_info, functions, classes


# ─── Code Chunker ─────────────────────────────────────────────────────────────

class CodeChunker:
    """Creates semantically meaningful chunks for embedding."""

    def __init__(self, chunk_size: int = 800, overlap: int = 150):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_file(self, path: str, content: str, language: Language,
                   functions: List[FunctionInfo], classes: List[ClassInfo]) -> List[CodeChunk]:
        chunks: List[CodeChunk] = []
        lines = content.splitlines(keepends=True)

        # 1. Function-level chunks (highest quality)
        covered_lines: Set[int] = set()
        for fn in functions:
            fn_lines = lines[fn.start_line - 1:fn.end_line]
            fn_content = "".join(fn_lines)
            if len(fn_content.strip()) < 10:
                continue
            chunk_id = self._make_id(path, fn.name, fn.start_line)
            chunks.append(CodeChunk(
                chunk_id=chunk_id,
                content=fn_content,
                file_path=path,
                chunk_type="function",
                name=fn.name,
                start_line=fn.start_line,
                end_line=fn.end_line,
                language=language,
                metadata={
                    "docstring": fn.docstring or "",
                    "calls": fn.calls,
                    "params": fn.parameters,
                    "complexity": fn.complexity,
                },
                dependencies=fn.calls,
            ))
            covered_lines.update(range(fn.start_line, fn.end_line + 1))

        # 2. Class-level chunks
        for cls in classes:
            cls_lines = lines[cls.start_line - 1:cls.end_line]
            cls_content = "".join(cls_lines)
            if len(cls_content.strip()) < 10:
                continue
            chunk_id = self._make_id(path, cls.name, cls.start_line)
            chunks.append(CodeChunk(
                chunk_id=chunk_id,
                content=cls_content[:self.chunk_size * 2],  # cap very large classes
                file_path=path,
                chunk_type="class",
                name=cls.name,
                start_line=cls.start_line,
                end_line=cls.end_line,
                language=language,
                metadata={
                    "docstring": cls.docstring or "",
                    "methods": cls.methods,
                    "inherits": cls.inherits_from,
                },
                dependencies=cls.inherits_from,
            ))
            covered_lines.update(range(cls.start_line, cls.end_line + 1))

        # 3. Module-level chunk (uncovered lines + file header)
        uncovered = []
        for i, line in enumerate(lines):
            if (i + 1) not in covered_lines:
                uncovered.append(line)

        # Slide window on uncovered content
        uncovered_content = "".join(uncovered)
        if uncovered_content.strip():
            for i in range(0, len(uncovered_content), self.chunk_size - self.overlap):
                chunk_content = uncovered_content[i:i + self.chunk_size]
                if len(chunk_content.strip()) < 20:
                    continue
                chunk_id = self._make_id(path, "module", i)
                chunks.append(CodeChunk(
                    chunk_id=chunk_id,
                    content=chunk_content,
                    file_path=path,
                    chunk_type="module",
                    language=language,
                    metadata={"offset": i},
                ))

        return chunks

    def _make_id(self, path: str, name: str, line: int) -> str:
        raw = f"{path}::{name}::{line}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]


# ─── Main Static Analysis Engine ──────────────────────────────────────────────

class StaticAnalysisEngine:
    """Orchestrates full repository static analysis."""

    def __init__(self):
        self.python_analyzer = PythonAnalyzer()
        self.js_analyzer = JavaScriptAnalyzer()
        self.generic_analyzer = GenericAnalyzer()
        self.chunker = CodeChunker(
            chunk_size=settings.chunk_size,
            overlap=settings.chunk_overlap,
        )

    def analyze_repository(self, repo_path: str, repo_id: str, repo_url: str) -> RepositoryContext:
        """Full repository analysis — returns rich RepositoryContext."""
        logger.info(f"Starting static analysis of {repo_path}")

        repo_name = Path(repo_path).name
        ctx = RepositoryContext(
            repo_id=repo_id,
            repo_url=repo_url,
            repo_name=repo_name,
        )

        all_chunks: List[CodeChunk] = []
        seen_chunk_ids: Set[str] = set()
        call_graph = nx.DiGraph()
        dep_graph = nx.DiGraph()

        # Collect README
        for readme_name in ["README.md", "README.rst", "README.txt", "README"]:
            readme_path = Path(repo_path) / readme_name
            if readme_path.exists():
                ctx.readme_content = readme_path.read_text(errors="ignore")[:5000]
                break

        # Walk files
        for file_path in self._walk_repo(repo_path):
            rel_path = Path(file_path).relative_to(repo_path).as_posix()
            lang = self._detect_language(file_path)

            try:
                content = Path(file_path).read_text(errors="ignore")
            except Exception as e:
                logger.warning(f"Cannot read {file_path}: {e}")
                continue

            if len(content) > settings.max_file_size_kb * 1024:
                logger.debug(f"Skipping large file: {rel_path}")
                continue

            # Analyze
            file_info, functions, classes = self._analyze_file(rel_path, content, lang)
            ctx.files[rel_path] = file_info

            # Store functions and classes
            for fn in functions:
                ctx.functions[f"{rel_path}::{fn.name}"] = fn
                call_graph.add_node(fn.name, file=rel_path)

            for cls in classes:
                ctx.classes[f"{rel_path}::{cls.name}"] = cls

            # Dependency graph
            dep_graph.add_node(rel_path)
            for imp in file_info.imports:
                dep_graph.add_edge(rel_path, imp)

            # Chunk for RAG
            chunks = self.chunker.chunk_file(rel_path, content, lang, functions, classes)
            for c in chunks:
                if c.chunk_id not in seen_chunk_ids:
                    seen_chunk_ids.add(c.chunk_id)
                    all_chunks.append(c)

            # Language stats
            ctx.languages[lang.value] = ctx.languages.get(lang.value, 0) + 1

        # Build call graph edges
        for key, fn in ctx.functions.items():
            for called in fn.calls:
                # Find called function in context
                for other_key, other_fn in ctx.functions.items():
                    if other_fn.name == called and other_key != key:
                        call_graph.add_edge(fn.name, other_fn.name)
                        ctx.call_edges.append({"from": fn.name, "to": other_fn.name,
                                                "from_file": fn.file_path, "to_file": other_fn.file_path})

        # Dependency edges
        for u, v in dep_graph.edges():
            ctx.dependency_edges.append({"from": u, "to": v})

        # Identify critical modules (high in-degree in dep graph)
        in_degrees = dict(dep_graph.in_degree())
        sorted_by_importance = sorted(in_degrees.items(), key=lambda x: x[1], reverse=True)
        ctx.critical_modules = [k for k, _ in sorted_by_importance[:10] if in_degrees.get(k, 0) > 1]

        # Entry points (no in-degree in call graph)
        ctx.entry_points = [n for n in call_graph.nodes()
                            if call_graph.in_degree(n) == 0 and call_graph.out_degree(n) > 0][:10]

        # Metrics
        ctx.total_files = len(ctx.files)
        ctx.total_functions = len(ctx.functions)
        ctx.total_classes = len(ctx.classes)
        complexities = [f.complexity for f in ctx.functions.values()]
        ctx.avg_complexity = sum(complexities) / max(len(complexities), 1)

        # Test detection
        ctx.has_tests = any(
            "test" in f.lower() or "spec" in f.lower()
            for f in ctx.files.keys()
        )

        logger.info(
            f"Analysis complete: {ctx.total_files} files, "
            f"{ctx.total_functions} functions, {ctx.total_classes} classes"
        )

        return ctx, all_chunks

    def _walk_repo(self, repo_path: str):
        for root, dirs, files in os.walk(repo_path):
            # Prune skip dirs
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
            for f in files:
                full_path = os.path.join(root, f)
                ext = Path(f).suffix.lower()
                if ext in SKIP_EXTENSIONS:
                    continue
                if ext in LANGUAGE_MAP:
                    yield full_path

    def _detect_language(self, path: str) -> Language:
        ext = Path(path).suffix.lower()
        return LANGUAGE_MAP.get(ext, Language.UNKNOWN)

    def _analyze_file(self, path: str, content: str, lang: Language):
        if lang == Language.PYTHON:
            return self.python_analyzer.analyze_file(path, content)
        elif lang in (Language.JAVASCRIPT, Language.TYPESCRIPT):
            return self.js_analyzer.analyze_file(path, content)
        else:
            return self.generic_analyzer.analyze_file(path, content, lang)
