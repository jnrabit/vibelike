"""
Code analysis utilities for workflow phases.

Extracted from WorkflowAgent to enable reuse and testing.
Functions for:
- Extracting project structure
- Reading file contents
- Detecting hallucinations
- Building code overviews
"""

import json
import ast
from pathlib import Path
from typing import Dict, List, Tuple


def _get_project_root() -> Path:
    """
    Get the vibelike project root directory.
    
    Looks for pyproject.toml as anchor. Starts from workflow/ and goes up.
    
    Returns:
        Path to project root
    """
    # Start from workflow/ parent (i.e., vibelike/)
    current = Path(__file__).resolve().parent.parent
    
    # Check if current has pyproject.toml
    if (current / "pyproject.toml").exists():
        return current
    
    # Otherwise search upwards
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    
    raise RuntimeError(f"Could not find project root (pyproject.toml) starting from {Path(__file__).resolve().parent.parent}")


def gather_project_info() -> Dict:
    """
    Gather basic project metadata (pyproject.toml, README, etc.).
    
    Returns:
        Dictionary with project info
    """
    root = _get_project_root()
    info = {
        "root": str(root),
        "type": "python",
        "has_pyproject": (root / "pyproject.toml").exists(),
        "has_poetry_lock": (root / "poetry.lock").exists(),
        "has_setup_py": (root / "setup.py").exists(),
    }
    return info


def authoritative_file_list() -> str:
    """
    Get list of all Python files in project.
    
    Returns:
        Formatted string of all .py files
    """
    root = _get_project_root()
    py_files = sorted(root.rglob("*.py"))
    
    # Filter out common ignored dirs
    ignore_dirs = {".git", "__pycache__", ".venv", "venv", "build", "dist", ".egg-info"}
    filtered = [f for f in py_files if not any(p in f.parts for p in ignore_dirs)]
    
    lines = []
    for f in filtered[:100]:  # Limit to first 100 files
        rel_path = f.relative_to(root)
        lines.append(f"  - {rel_path}")
    
    if len(filtered) > 100:
        lines.append(f"  ... and {len(filtered) - 100} more files")
    
    return "\n".join(lines)


def extract_code_overview(max_files: int = 25) -> str:
    """
    Extract high-level code structure from project.
    
    Uses AST to extract function/class definitions without full content.
    
    Args:
        max_files: Max number of files to analyze
        
    Returns:
        Formatted code overview
    """
    root = _get_project_root()
    py_files = sorted(root.rglob("*.py"))[:max_files]
    
    overview = []
    for fpath in py_files:
        try:
            with open(fpath) as f:
                content = f.read()
            tree = ast.parse(content)
            
            # Extract top-level functions and classes
            rel_path = fpath.relative_to(root)
            overview.append(f"\n📄 {rel_path}")
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.col_offset == 0:
                    overview.append(f"  └─ def {node.name}(...)")
                elif isinstance(node, ast.ClassDef) and node.col_offset == 0:
                    overview.append(f"  └─ class {node.name}")
        except Exception as e:
            pass
    
    return "\n".join(overview)


def detect_hallucinated_files(text: str, project_root: Path = None) -> List[str]:
    """
    Detect if text mentions files that don't exist.
    
    Args:
        text: Text to analyze
        project_root: Root directory (default: vibelike root)
        
    Returns:
        List of filenames that are hallucinated
    """
    if project_root is None:
        project_root = _get_project_root()
    
    # Get list of real files
    real_files = {f.name for f in project_root.rglob("*.py")}
    
    # Look for file mentions (simple heuristic: "filename.py" patterns)
    import re
    mentioned_files = re.findall(r'\b\w+\.py\b', text)
    
    hallucinated = [f for f in set(mentioned_files) if f not in real_files]
    return hallucinated


def load_monolith(project_root: Path = None, max_lines: int = 2000) -> str:
    """
    Load project documentation or architecture summary.
    
    Looks for:
    - MONOLITH.md
    - ARCHITECTURE.md
    - README.md
    
    Args:
        project_root: Root directory
        max_lines: Max lines to include
        
    Returns:
        Monolith content or empty string
    """
    if project_root is None:
        project_root = _get_project_root()
    
    candidates = [
        project_root / "MONOLITH.md",
        project_root / "ARCHITECTURE.md",
        project_root / "README.md",
    ]
    
    for fpath in candidates:
        if fpath.exists():
            try:
                with open(fpath) as f:
                    content = f.read()
                # Limit to first max_lines
                lines = content.split('\n')[:max_lines]
                return '\n'.join(lines)
            except Exception:
                continue
    
    return ""


def extract_skeleton(path: Path) -> str:
    """
    Extract skeleton (function/class defs) from a Python file without full content.
    
    Args:
        path: File path
        
    Returns:
        Skeleton representation
    """
    try:
        with open(path) as f:
            content = f.read()
        
        lines = content.split('\n')
        skeleton = []
        
        for i, line in enumerate(lines):
            # Keep: imports, class/def signatures, decorators
            if any(line.strip().startswith(kw) for kw in ['import ', 'from ', 'class ', 'def ', '@', '#']):
                skeleton.append(line)
        
        return '\n'.join(skeleton[:100])  # Limit to first 100 lines
    except Exception:
        return ""


def read_focused_files(task: str, project_root: Path = None, star_budget: int = 10000) -> str:
    """
    Read relevant project files based on task description.
    
    Uses keyword matching to find relevant files.
    
    Args:
        task: Task description
        project_root: Root directory
        star_budget: Max tokens to include
        
    Returns:
        Concatenated file contents
    """
    if project_root is None:
        project_root = _get_project_root()
    
    # Simple keyword extraction from task
    keywords = set(task.lower().split())
    keywords = {kw for kw in keywords if len(kw) > 3}
    
    # Find matching files
    py_files = list(project_root.rglob("*.py"))
    scored_files = []
    
    for fpath in py_files:
        name_lower = fpath.name.lower()
        # Score based on filename match
        score = sum(1 for kw in keywords if kw in name_lower)
        if score > 0:
            scored_files.append((score, fpath))
    
    # Sort by score and read top files
    scored_files.sort(reverse=True)
    
    result = []
    total_len = 0
    for _, fpath in scored_files[:5]:  # Limit to 5 files
        try:
            with open(fpath) as f:
                content = f.read()
            if total_len + len(content) > star_budget:
                result.append(f"... truncated (budget exceeded)")
                break
            result.append(f"\n{'='*60}\n{fpath.name}\n{'='*60}\n{content}")
            total_len += len(content)
        except Exception:
            continue
    
    return "\n".join(result) if result else "[No relevant files found]"
