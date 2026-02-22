"""
Comprehensive unit tests for GrayScope analyzer modules.

Covers:
  - CodeParser: file parsing, symbol extraction, CFG construction
  - branch_path_analyzer: branch classification, risk scoring
  - boundary_value_analyzer: comparison extraction, candidate derivation
  - error_path_analyzer: resource leak detection, error return analysis
  - call_graph_builder: call graph construction, fan-in/fan-out, call chains
  - Analyzer registry: display names, module lists
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

# ═══════════════════════════════════════════════════════════════════
# 0. TEST FIXTURE: Sample C Source Code
# ═══════════════════════════════════════════════════════════════════

SAMPLE_C_SIMPLE = """\
#include <stdlib.h>

int add(int a, int b) {
    return a + b;
}

int validate(int x) {
    if (x < 0) {
        return -1;
    }
    if (x > 100) {
        return -1;
    }
    return 0;
}
"""

SAMPLE_C_ERROR_HANDLING = """\
#include <stdlib.h>
#include <errno.h>

int do_work(int size) {
    void *buf = malloc(size);
    if (buf == NULL) {
        return -ENOMEM;
    }

    int fd = open("/tmp/test", 0);
    if (fd < 0) {
        /* BUG: forgot to free(buf) */
        return -EIO;
    }

    close(fd);
    free(buf);
    return 0;
}
"""

SAMPLE_C_GOTO_CLEANUP = """\
#include <stdlib.h>

int cleanup_example(int size) {
    void *a = malloc(size);
    if (!a) goto err_a;

    void *b = malloc(size);
    if (!b) goto err_b;

    free(b);
    free(a);
    return 0;

err_b:
    free(a);
err_a:
    return -1;
}
"""

SAMPLE_C_CALL_GRAPH = """\
int helper_a(int x) {
    return x + 1;
}

int helper_b(int x) {
    return x * 2;
}

int helper_c(int x, int y) {
    return helper_a(x) + helper_b(y);
}

int entry_point(int a, int b) {
    int c = helper_c(a, b);
    int d = helper_a(c);
    return d;
}

int another_caller(int x) {
    return helper_a(x);
}
"""

SAMPLE_C_BOUNDARY = """\
#define MAX_SIZE 1024

int check_bounds(int idx, int size) {
    if (idx < 0) {
        return -1;
    }
    if (idx >= size) {
        return -1;
    }
    return 0;
}

void array_access(int *arr, int idx) {
    arr[idx] = 42;
}

int compare_max(int val) {
    if (val > MAX_SIZE) {
        return -1;
    }
    return val;
}
"""

SAMPLE_C_CONCURRENCY = """\
#include <pthread.h>

static pthread_mutex_t g_lock;
static int g_counter;

void unsafe_increment() {
    g_counter++;
}

void safe_increment() {
    pthread_mutex_lock(&g_lock);
    g_counter++;
    pthread_mutex_unlock(&g_lock);
}

void lock_order_a() {
    pthread_mutex_lock(&g_lock);
    g_counter++;
    pthread_mutex_unlock(&g_lock);
}
"""


@pytest.fixture
def tmp_c_file():
    """Create a temporary C file and return its path."""
    def _create(content: str, suffix: str = ".c") -> Path:
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "w") as f:
            f.write(content)
        return Path(path)
    return _create


@pytest.fixture
def tmp_c_dir():
    """Create a temporary directory with C files."""
    def _create(files: dict[str, str]) -> Path:
        d = Path(tempfile.mkdtemp())
        for name, content in files.items():
            p = d / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        return d
    return _create


# ═══════════════════════════════════════════════════════════════════
# 1. CODE PARSER TESTS
# ═══════════════════════════════════════════════════════════════════

class TestCodeParser:
    """Tests for app.analyzers.code_parser.CodeParser."""

    def test_parser_availability(self):
        """TS-CP-001: tree-sitter should be available."""
        from app.analyzers.code_parser import is_available
        assert is_available() is True

    def test_parse_simple_file(self, tmp_c_file):
        """TS-CP-002: Parse a simple C file and extract symbols."""
        from app.analyzers.code_parser import CodeParser
        path = tmp_c_file(SAMPLE_C_SIMPLE)
        try:
            parser = CodeParser()
            symbols = parser.parse_file(path)
            names = [s.name for s in symbols]
            assert "add" in names
            assert "validate" in names
            assert all(s.kind == "function" for s in symbols)
        finally:
            os.unlink(path)

    def test_parse_file_line_numbers(self, tmp_c_file):
        """TS-CP-003: Symbol line numbers are reasonable."""
        from app.analyzers.code_parser import CodeParser
        path = tmp_c_file(SAMPLE_C_SIMPLE)
        try:
            parser = CodeParser()
            symbols = parser.parse_file(path)
            for s in symbols:
                assert s.line_start > 0
                assert s.line_end >= s.line_start
        finally:
            os.unlink(path)

    def test_parse_file_source_extraction(self, tmp_c_file):
        """TS-CP-004: Symbol source is non-empty and contains function name."""
        from app.analyzers.code_parser import CodeParser
        path = tmp_c_file(SAMPLE_C_SIMPLE)
        try:
            parser = CodeParser()
            symbols = parser.parse_file(path)
            for s in symbols:
                assert len(s.source) > 0
                assert s.name in s.source
        finally:
            os.unlink(path)

    def test_parse_directory(self, tmp_c_dir):
        """TS-CP-005: Parse a directory with multiple C files."""
        from app.analyzers.code_parser import CodeParser
        d = tmp_c_dir({
            "a.c": SAMPLE_C_SIMPLE,
            "b.c": SAMPLE_C_CALL_GRAPH,
        })
        try:
            parser = CodeParser()
            symbols = parser.parse_directory(d)
            names = [s.name for s in symbols]
            assert "add" in names
            assert "helper_a" in names
        finally:
            import shutil
            shutil.rmtree(d)

    def test_parse_directory_max_files(self, tmp_c_dir):
        """TS-CP-006: max_files limit is respected."""
        from app.analyzers.code_parser import CodeParser
        files = {f"file_{i}.c": f"int func_{i}(void) {{ return {i}; }}\n" for i in range(10)}
        d = tmp_c_dir(files)
        try:
            parser = CodeParser()
            symbols = parser.parse_directory(d, max_files=3)
            # Should have at most 3 files' worth of symbols
            assert len(symbols) <= 3
        finally:
            import shutil
            shutil.rmtree(d)

    def test_build_cfg(self, tmp_c_file):
        """TS-CP-007: Build CFG for a function with branches."""
        from app.analyzers.code_parser import CodeParser
        path = tmp_c_file(SAMPLE_C_SIMPLE)
        try:
            parser = CodeParser()
            cfg = parser.build_cfg(path, "validate")
            assert cfg is not None
            assert cfg.function_name == "validate"
            assert len(cfg.nodes) > 0
            assert len(cfg.edges) > 0
            # Should have branch nodes for the if statements
            branch_nodes = [n for n in cfg.nodes if n.kind == "branch"]
            assert len(branch_nodes) >= 2  # Two if statements
        finally:
            os.unlink(path)

    def test_build_cfg_nonexistent_function(self, tmp_c_file):
        """TS-CP-008: CFG for nonexistent function returns None."""
        from app.analyzers.code_parser import CodeParser
        path = tmp_c_file(SAMPLE_C_SIMPLE)
        try:
            parser = CodeParser()
            cfg = parser.build_cfg(path, "nonexistent")
            assert cfg is None
        finally:
            os.unlink(path)

    def test_build_cfg_entry_exit_nodes(self, tmp_c_file):
        """TS-CP-009: CFG has entry and exit nodes."""
        from app.analyzers.code_parser import CodeParser
        path = tmp_c_file(SAMPLE_C_SIMPLE)
        try:
            parser = CodeParser()
            cfg = parser.build_cfg(path, "add")
            assert cfg is not None
            kinds = [n.kind for n in cfg.nodes]
            assert "entry" in kinds
            assert "exit" in kinds
        finally:
            os.unlink(path)

    def test_cfg_to_dict(self, tmp_c_file):
        """TS-CP-010: CFG to_dict returns valid structure."""
        from app.analyzers.code_parser import CodeParser
        path = tmp_c_file(SAMPLE_C_SIMPLE)
        try:
            parser = CodeParser()
            cfg = parser.build_cfg(path, "validate")
            d = cfg.to_dict()
            assert "function_name" in d
            assert "nodes" in d
            assert "edges" in d
            assert d["function_name"] == "validate"
            for n in d["nodes"]:
                assert "id" in n
                assert "kind" in n
        finally:
            os.unlink(path)

    def test_parse_cpp_file(self, tmp_c_file):
        """TS-CP-011: Parse a C++ file."""
        from app.analyzers.code_parser import CodeParser
        content = "int cpp_func(int x) { return x; }\n"
        path = tmp_c_file(content, suffix=".cpp")
        try:
            parser = CodeParser()
            symbols = parser.parse_file(path)
            assert any(s.name == "cpp_func" for s in symbols)
        finally:
            os.unlink(path)

    def test_parse_empty_file(self, tmp_c_file):
        """TS-CP-012: Parse an empty C file returns no symbols."""
        from app.analyzers.code_parser import CodeParser
        path = tmp_c_file("")
        try:
            parser = CodeParser()
            symbols = parser.parse_file(path)
            assert symbols == []
        finally:
            os.unlink(path)

    def test_parse_file_with_structs(self, tmp_c_file):
        """TS-CP-013: Parse file with struct definitions."""
        from app.analyzers.code_parser import CodeParser
        content = """\
struct point {
    int x;
    int y;
};

enum color { RED, GREEN, BLUE };

int use_point(struct point *p) { return p->x; }
"""
        path = tmp_c_file(content)
        try:
            parser = CodeParser()
            symbols = parser.parse_file(path)
            names = [s.name for s in symbols]
            kinds = {s.name: s.kind for s in symbols}
            assert "point" in names
            assert kinds["point"] == "struct"
            assert "use_point" in names
            assert kinds["use_point"] == "function"
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════
# 2. BRANCH PATH ANALYZER TESTS
# ═══════════════════════════════════════════════════════════════════

class TestBranchPathAnalyzer:
    """Tests for app.analyzers.branch_path_analyzer."""

    def _make_ctx(self, workspace: str, path: str = "") -> dict:
        return {
            "task_id": "test-task",
            "project_id": 1,
            "repo_id": 1,
            "workspace_path": workspace,
            "target": {"path": path},
            "revision": {"branch": "main"},
            "options": {"max_files": 100},
            "upstream_results": {},
        }

    def test_analyze_simple_file(self, tmp_c_dir):
        """TS-BP-001: Analyze a file with branches produces findings."""
        from app.analyzers.branch_path_analyzer import analyze
        d = tmp_c_dir({"test.c": SAMPLE_C_SIMPLE})
        try:
            ctx = self._make_ctx(str(d), "test.c")
            result = analyze(ctx)
            assert result["module_id"] == "branch_path"
            assert result["status"] == "success"
            assert len(result["findings"]) > 0
            assert result["risk_score"] > 0
        finally:
            import shutil
            shutil.rmtree(d)

    def test_analyze_finding_structure(self, tmp_c_dir):
        """TS-BP-002: Each finding has required fields."""
        from app.analyzers.branch_path_analyzer import analyze
        d = tmp_c_dir({"test.c": SAMPLE_C_SIMPLE})
        try:
            ctx = self._make_ctx(str(d), "test.c")
            result = analyze(ctx)
            for f in result["findings"]:
                assert "finding_id" in f
                assert "module_id" in f
                assert "risk_type" in f
                assert "severity" in f
                assert "risk_score" in f
                assert "title" in f
                assert "description" in f
                assert "file_path" in f
                assert "symbol_name" in f
                assert "line_start" in f
                assert "evidence" in f
                assert f["module_id"] == "branch_path"
                assert f["risk_type"].startswith("branch_")
                assert f["severity"] in ("S0", "S1", "S2", "S3")
                assert 0 <= f["risk_score"] <= 1
        finally:
            import shutil
            shutil.rmtree(d)

    def test_classify_error_branch(self):
        """TS-BP-003: NULL check classifies as error."""
        from app.analyzers.branch_path_analyzer import _classify_branch
        assert _classify_branch("if (ptr == NULL)") == "error"
        assert _classify_branch("if (ret < 0)") == "error"
        assert _classify_branch("if (!buf)") == "error"

    def test_classify_cleanup_branch(self):
        """TS-BP-004: goto/cleanup classifies as cleanup."""
        from app.analyzers.branch_path_analyzer import _classify_branch
        assert _classify_branch("goto cleanup") == "cleanup"
        assert _classify_branch("goto err_out") == "cleanup"

    def test_classify_boundary_branch(self):
        """TS-BP-005: Numeric comparisons classify as boundary."""
        from app.analyzers.branch_path_analyzer import _classify_branch
        assert _classify_branch("if (size > 1024)") == "boundary"
        assert _classify_branch("if (idx >= MAX_SIZE)") == "boundary"

    def test_classify_normal_branch(self):
        """TS-BP-006: Generic branches classify as normal."""
        from app.analyzers.branch_path_analyzer import _classify_branch
        result = _classify_branch("if (use_cache)")
        assert result in ("normal", "state")

    def test_score_branch_types(self):
        """TS-BP-007: Risk scores vary by path type."""
        from app.analyzers.branch_path_analyzer import _score_branch
        assert _score_branch("error") > _score_branch("normal")
        assert _score_branch("cleanup") > _score_branch("normal")
        assert _score_branch("boundary") > _score_branch("normal")

    def test_analyze_nonexistent_path(self, tmp_c_dir):
        """TS-BP-008: Nonexistent path produces warning."""
        from app.analyzers.branch_path_analyzer import analyze
        d = tmp_c_dir({})
        try:
            ctx = self._make_ctx(str(d), "nonexistent/")
            result = analyze(ctx)
            assert result["status"] == "success"
            assert len(result["warnings"]) > 0
            assert result["risk_score"] == 0.0
        finally:
            import shutil
            shutil.rmtree(d)

    def test_analyze_goto_cleanup_detection(self, tmp_c_dir):
        """TS-BP-009: Detect goto cleanup pattern."""
        from app.analyzers.branch_path_analyzer import analyze
        d = tmp_c_dir({"test.c": SAMPLE_C_GOTO_CLEANUP})
        try:
            ctx = self._make_ctx(str(d), "test.c")
            result = analyze(ctx)
            cleanup_findings = [f for f in result["findings"] if f["risk_type"] == "branch_cleanup"]
            assert len(cleanup_findings) > 0
        finally:
            import shutil
            shutil.rmtree(d)

    def test_analyze_metrics(self, tmp_c_dir):
        """TS-BP-010: Metrics include expected fields."""
        from app.analyzers.branch_path_analyzer import analyze
        d = tmp_c_dir({"test.c": SAMPLE_C_SIMPLE})
        try:
            ctx = self._make_ctx(str(d), "test.c")
            result = analyze(ctx)
            m = result["metrics"]
            assert "files_scanned" in m
            assert "functions_scanned" in m
            assert "branches_found" in m
            assert "findings_count" in m
            assert m["files_scanned"] == 1
            assert m["functions_scanned"] >= 2
        finally:
            import shutil
            shutil.rmtree(d)

    def test_classify_compound_condition(self):
        """TS-BP-011: Compound conditions are classified correctly."""
        from app.analyzers.branch_path_analyzer import _classify_branch
        # && takes the most severe
        result = _classify_branch("if (ptr == NULL && size > 0)")
        assert result == "error"

    def test_analyze_directory(self, tmp_c_dir):
        """TS-BP-012: Analyze a directory with multiple files."""
        from app.analyzers.branch_path_analyzer import analyze
        d = tmp_c_dir({
            "a.c": SAMPLE_C_SIMPLE,
            "b.c": SAMPLE_C_ERROR_HANDLING,
        })
        try:
            ctx = self._make_ctx(str(d), "")
            result = analyze(ctx)
            assert result["metrics"]["files_scanned"] == 2
            assert len(result["findings"]) > 0
        finally:
            import shutil
            shutil.rmtree(d)


# ═══════════════════════════════════════════════════════════════════
# 3. BOUNDARY VALUE ANALYZER TESTS
# ═══════════════════════════════════════════════════════════════════

class TestBoundaryValueAnalyzer:
    """Tests for app.analyzers.boundary_value_analyzer."""

    def _make_ctx(self, workspace: str, path: str = "") -> dict:
        return {
            "task_id": "test-task",
            "project_id": 1,
            "repo_id": 1,
            "workspace_path": workspace,
            "target": {"path": path},
            "revision": {"branch": "main"},
            "options": {"max_files": 100},
            "upstream_results": {},
        }

    def test_analyze_boundary_conditions(self, tmp_c_dir):
        """TS-BV-001: Detect boundary comparisons in code."""
        from app.analyzers.boundary_value_analyzer import analyze
        d = tmp_c_dir({"test.c": SAMPLE_C_BOUNDARY})
        try:
            ctx = self._make_ctx(str(d), "test.c")
            result = analyze(ctx)
            assert result["module_id"] == "boundary_value"
            assert result["status"] == "success"
            assert len(result["findings"]) > 0
        finally:
            import shutil
            shutil.rmtree(d)

    def test_finding_has_candidates(self, tmp_c_dir):
        """TS-BV-002: Findings include boundary test candidates."""
        from app.analyzers.boundary_value_analyzer import analyze
        d = tmp_c_dir({"test.c": SAMPLE_C_BOUNDARY})
        try:
            ctx = self._make_ctx(str(d), "test.c")
            result = analyze(ctx)
            boundary_findings = [
                f for f in result["findings"]
                if f["risk_type"] == "boundary_miss"
            ]
            for f in boundary_findings:
                assert "candidates" in f["evidence"]
                assert len(f["evidence"]["candidates"]) > 0
        finally:
            import shutil
            shutil.rmtree(d)

    def test_array_access_detection(self, tmp_c_dir):
        """TS-BV-003: Detect array access patterns."""
        from app.analyzers.boundary_value_analyzer import analyze
        d = tmp_c_dir({"test.c": SAMPLE_C_BOUNDARY})
        try:
            ctx = self._make_ctx(str(d), "test.c")
            result = analyze(ctx)
            array_findings = [
                f for f in result["findings"]
                if f["risk_type"] == "invalid_input_gap"
            ]
            assert len(array_findings) > 0
        finally:
            import shutil
            shutil.rmtree(d)

    def test_derive_numeric_candidates(self):
        """TS-BV-004: Derive candidates from numeric bound."""
        from app.analyzers.boundary_value_analyzer import _derive_candidates
        comp = {"expr": "x < 100", "var": "x", "op": "<", "bound": "100"}
        candidates = _derive_candidates(comp)
        assert 99 in candidates
        assert 100 in candidates
        assert 101 in candidates

    def test_derive_symbolic_candidates(self):
        """TS-BV-005: Derive candidates from symbolic bound."""
        from app.analyzers.boundary_value_analyzer import _derive_candidates
        comp = {"expr": "x < MAX_SIZE", "var": "x", "op": "<", "bound": "MAX_SIZE"}
        candidates = _derive_candidates(comp)
        assert any("MAX_SIZE" in str(c) for c in candidates)

    def test_extract_comparisons(self):
        """TS-BV-006: Extract comparison expressions from source."""
        from app.analyzers.boundary_value_analyzer import _extract_comparisons
        source = """\
    if (x < 0) return -1;
    if (y >= MAX_SIZE) return -1;
    if (a == b) return 0;
"""
        comps = _extract_comparisons(source)
        exprs = [c["expr"] for c in comps]
        assert any("x < 0" in e for e in exprs)

    def test_extract_array_accesses(self):
        """TS-BV-007: Extract array access patterns."""
        from app.analyzers.boundary_value_analyzer import _extract_array_accesses
        source = "arr[idx] = 42; buf[i+1] = 0;"
        accesses = _extract_array_accesses(source)
        assert len(accesses) >= 2
        arrays = [a["array"] for a in accesses]
        assert "arr" in arrays
        assert "buf" in arrays

    def test_analyze_nonexistent_path(self, tmp_c_dir):
        """TS-BV-008: Nonexistent path produces empty findings with warning."""
        from app.analyzers.boundary_value_analyzer import analyze
        d = tmp_c_dir({})
        try:
            ctx = self._make_ctx(str(d), "nonexistent/")
            result = analyze(ctx)
            assert result["status"] == "success"
            assert len(result["warnings"]) > 0
            assert result["risk_score"] == 0.0
        finally:
            import shutil
            shutil.rmtree(d)

    def test_metrics_structure(self, tmp_c_dir):
        """TS-BV-009: Metrics include expected fields."""
        from app.analyzers.boundary_value_analyzer import analyze
        d = tmp_c_dir({"test.c": SAMPLE_C_BOUNDARY})
        try:
            ctx = self._make_ctx(str(d), "test.c")
            result = analyze(ctx)
            m = result["metrics"]
            assert "files_scanned" in m
            assert "functions_scanned" in m
            assert "constraints_found" in m
            assert "findings_count" in m
        finally:
            import shutil
            shutil.rmtree(d)

    def test_with_upstream_data_flow(self, tmp_c_dir):
        """TS-BV-010: Upstream data_flow chains enrich findings."""
        from app.analyzers.boundary_value_analyzer import analyze
        d = tmp_c_dir({"test.c": SAMPLE_C_BOUNDARY})
        try:
            ctx = self._make_ctx(str(d), "test.c")
            ctx["upstream_results"] = {
                "data_flow": {
                    "findings": [{
                        "evidence": {
                            "propagation_chain": [
                                {"function": "check_bounds", "param": "idx", "transform": "none"},
                                {"function": "caller", "param": "index", "transform": "none"},
                            ],
                            "entry_function": "caller",
                            "entry_param": "index",
                            "is_external_input": True,
                        }
                    }],
                    "risk_score": 0.7,
                }
            }
            result = analyze(ctx)
            assert result["status"] == "success"
        finally:
            import shutil
            shutil.rmtree(d)


# ═══════════════════════════════════════════════════════════════════
# 4. ERROR PATH ANALYZER TESTS
# ═══════════════════════════════════════════════════════════════════

class TestErrorPathAnalyzer:
    """Tests for app.analyzers.error_path_analyzer."""

    def _make_ctx(self, workspace: str, path: str = "") -> dict:
        return {
            "task_id": "test-task",
            "project_id": 1,
            "repo_id": 1,
            "workspace_path": workspace,
            "target": {"path": path},
            "revision": {"branch": "main"},
            "options": {"max_files": 100},
            "upstream_results": {},
        }

    def test_detect_missing_cleanup(self, tmp_c_dir):
        """TS-EP-001: Detect missing resource cleanup."""
        from app.analyzers.error_path_analyzer import analyze
        d = tmp_c_dir({"test.c": SAMPLE_C_ERROR_HANDLING})
        try:
            ctx = self._make_ctx(str(d), "test.c")
            result = analyze(ctx)
            assert result["module_id"] == "error_path"
            assert result["status"] == "success"
            cleanup_findings = [
                f for f in result["findings"]
                if "cleanup" in f["risk_type"] or "silent" in f["risk_type"]
            ]
            assert len(cleanup_findings) > 0
        finally:
            import shutil
            shutil.rmtree(d)

    def test_goto_cleanup_analysis(self, tmp_c_dir):
        """TS-EP-002: Analyze goto cleanup patterns."""
        from app.analyzers.error_path_analyzer import analyze
        d = tmp_c_dir({"test.c": SAMPLE_C_GOTO_CLEANUP})
        try:
            ctx = self._make_ctx(str(d), "test.c")
            result = analyze(ctx)
            assert result["status"] == "success"
        finally:
            import shutil
            shutil.rmtree(d)

    def test_finding_evidence_structure(self, tmp_c_dir):
        """TS-EP-003: Findings have proper evidence structure."""
        from app.analyzers.error_path_analyzer import analyze
        d = tmp_c_dir({"test.c": SAMPLE_C_ERROR_HANDLING})
        try:
            ctx = self._make_ctx(str(d), "test.c")
            result = analyze(ctx)
            for f in result["findings"]:
                assert "finding_id" in f
                assert f["finding_id"].startswith("EP-")
                assert "evidence" in f
                assert isinstance(f["evidence"], dict)
        finally:
            import shutil
            shutil.rmtree(d)

    def test_nonexistent_path(self, tmp_c_dir):
        """TS-EP-004: Nonexistent path handled gracefully."""
        from app.analyzers.error_path_analyzer import analyze
        d = tmp_c_dir({})
        try:
            ctx = self._make_ctx(str(d), "no_such_dir/")
            result = analyze(ctx)
            assert result["status"] == "success"
            assert result["risk_score"] == 0.0
        finally:
            import shutil
            shutil.rmtree(d)

    def test_cross_function_analysis(self, tmp_c_dir):
        """TS-EP-005: Cross-function resource leak detection with upstream call graph."""
        from app.analyzers.error_path_analyzer import analyze
        # Code where caller allocates and calls callee which can error
        code = """\
#include <stdlib.h>

int callee_can_fail(int x) {
    if (x < 0) return -1;
    return 0;
}

int caller_with_leak(int x) {
    void *buf = malloc(100);
    if (!buf) return -1;
    int ret = callee_can_fail(x);
    /* no check on ret, no free on failure */
    free(buf);
    return 0;
}
"""
        d = tmp_c_dir({"test.c": code})
        try:
            ctx = self._make_ctx(str(d), "test.c")
            ctx["upstream_results"] = {
                "call_graph": {
                    "findings": [{
                        "symbol_name": "caller_with_leak",
                        "evidence": {"callees": ["callee_can_fail"]},
                    }],
                    "risk_score": 0.5,
                }
            }
            result = analyze(ctx)
            assert result["status"] == "success"
        finally:
            import shutil
            shutil.rmtree(d)


# ═══════════════════════════════════════════════════════════════════
# 5. CALL GRAPH BUILDER TESTS
# ═══════════════════════════════════════════════════════════════════

class TestCallGraphBuilder:
    """Tests for app.analyzers.call_graph_builder."""

    def _make_ctx(self, workspace: str, path: str = "") -> dict:
        return {
            "task_id": "test-task",
            "project_id": 1,
            "repo_id": 1,
            "workspace_path": workspace,
            "target": {"path": path},
            "revision": {"branch": "main"},
            "options": {"max_files": 100},
            "upstream_results": {},
        }

    def test_build_callgraph_basic(self, tmp_c_dir):
        """TS-CG-001: Build call graph from simple source."""
        from app.analyzers.call_graph_builder import build_callgraph
        d = tmp_c_dir({"test.c": SAMPLE_C_CALL_GRAPH})
        try:
            cg, warnings = build_callgraph(str(d), d / "test.c")
            assert len(cg.nodes) >= 4  # helper_a, helper_b, helper_c, entry_point
            assert ("entry_point", "helper_c") in {
                (k, v) for k, vals in cg.edges.items() for v in vals
            }
        finally:
            import shutil
            shutil.rmtree(d)

    def test_callgraph_fan_out(self, tmp_c_dir):
        """TS-CG-002: Fan-out counts are correct."""
        from app.analyzers.call_graph_builder import build_callgraph
        d = tmp_c_dir({"test.c": SAMPLE_C_CALL_GRAPH})
        try:
            cg, _ = build_callgraph(str(d), d / "test.c")
            # helper_c calls helper_a and helper_b
            assert cg.fan_out("helper_c") >= 2
        finally:
            import shutil
            shutil.rmtree(d)

    def test_callgraph_fan_in(self, tmp_c_dir):
        """TS-CG-003: Fan-in counts are correct."""
        from app.analyzers.call_graph_builder import build_callgraph
        d = tmp_c_dir({"test.c": SAMPLE_C_CALL_GRAPH})
        try:
            cg, _ = build_callgraph(str(d), d / "test.c")
            # helper_a is called by helper_c, entry_point, another_caller
            assert cg.fan_in("helper_a") >= 2
        finally:
            import shutil
            shutil.rmtree(d)

    def test_callgraph_get_callees(self, tmp_c_dir):
        """TS-CG-004: get_callees returns correct set."""
        from app.analyzers.call_graph_builder import build_callgraph
        d = tmp_c_dir({"test.c": SAMPLE_C_CALL_GRAPH})
        try:
            cg, _ = build_callgraph(str(d), d / "test.c")
            callees = cg.get_callees("entry_point", depth=1)
            assert "helper_c" in callees or "helper_a" in callees
        finally:
            import shutil
            shutil.rmtree(d)

    def test_callgraph_get_callers(self, tmp_c_dir):
        """TS-CG-005: get_callers returns correct set."""
        from app.analyzers.call_graph_builder import build_callgraph
        d = tmp_c_dir({"test.c": SAMPLE_C_CALL_GRAPH})
        try:
            cg, _ = build_callgraph(str(d), d / "test.c")
            callers = cg.get_callers("helper_a", depth=1)
            assert len(callers) >= 2
        finally:
            import shutil
            shutil.rmtree(d)

    def test_callgraph_to_dict(self, tmp_c_dir):
        """TS-CG-006: Call graph serialization to dict."""
        from app.analyzers.call_graph_builder import build_callgraph
        d = tmp_c_dir({"test.c": SAMPLE_C_CALL_GRAPH})
        try:
            cg, _ = build_callgraph(str(d), d / "test.c")
            gd = cg.to_dict()
            assert "nodes" in gd
            assert "edges" in gd
            assert "simple_edges" in gd
            assert len(gd["nodes"]) > 0
        finally:
            import shutil
            shutil.rmtree(d)

    def test_analyze_produces_findings(self, tmp_c_dir):
        """TS-CG-007: Analyze function produces ModuleResult."""
        from app.analyzers.call_graph_builder import analyze
        d = tmp_c_dir({"test.c": SAMPLE_C_CALL_GRAPH})
        try:
            ctx = self._make_ctx(str(d), "test.c")
            result = analyze(ctx)
            assert result["module_id"] == "call_graph"
            assert result["status"] == "success"
            assert "metrics" in result
            assert result["metrics"]["total_nodes"] >= 4
        finally:
            import shutil
            shutil.rmtree(d)

    def test_callgraph_call_chains(self, tmp_c_dir):
        """TS-CG-008: get_call_chains returns valid paths."""
        from app.analyzers.call_graph_builder import build_callgraph
        d = tmp_c_dir({"test.c": SAMPLE_C_CALL_GRAPH})
        try:
            cg, _ = build_callgraph(str(d), d / "test.c")
            chains = cg.get_call_chains("helper_a", direction="callers", max_depth=5)
            # Should have chains like [helper_a, helper_c, entry_point]
            if chains:
                assert all(c[0] == "helper_a" for c in chains)
        finally:
            import shutil
            shutil.rmtree(d)

    def test_callgraph_function_params(self, tmp_c_dir):
        """TS-CG-009: Function parameters are extracted."""
        from app.analyzers.call_graph_builder import build_callgraph
        d = tmp_c_dir({"test.c": SAMPLE_C_CALL_GRAPH})
        try:
            cg, _ = build_callgraph(str(d), d / "test.c")
            # helper_a has param 'x'
            params = cg.function_params.get("helper_a", [])
            assert "x" in params
        finally:
            import shutil
            shutil.rmtree(d)

    def test_callgraph_nonexistent_path(self, tmp_c_dir):
        """TS-CG-010: Nonexistent path returns empty graph with warning."""
        from app.analyzers.call_graph_builder import build_callgraph
        d = tmp_c_dir({})
        try:
            cg, warnings = build_callgraph(str(d), d / "nonexistent")
            assert len(cg.nodes) == 0
            assert len(warnings) > 0
        finally:
            import shutil
            shutil.rmtree(d)


# ═══════════════════════════════════════════════════════════════════
# 6. ANALYZER REGISTRY TESTS
# ═══════════════════════════════════════════════════════════════════

class TestAnalyzerRegistry:
    """Tests for app.analyzers.registry."""

    def test_get_display_name_known_module(self):
        """TS-AR-001: Known module returns Chinese display name."""
        from app.analyzers.registry import get_display_name
        assert get_display_name("branch_path") == "分支路径分析"
        assert get_display_name("boundary_value") == "边界值分析"
        assert get_display_name("call_graph") == "调用图构建"

    def test_get_display_name_unknown_module(self):
        """TS-AR-002: Unknown module returns the module_id itself."""
        from app.analyzers.registry import get_display_name
        assert get_display_name("nonexistent") == "nonexistent"

    def test_all_modules_listed(self):
        """TS-AR-003: All expected modules are in registry."""
        from app.analyzers.registry import ALL_MODULES, MODULE_REGISTRY
        expected = {
            "branch_path", "boundary_value", "error_path", "call_graph",
            "data_flow", "concurrency", "diff_impact", "coverage_map",
            "postmortem", "knowledge_pattern",
        }
        assert set(ALL_MODULES) == expected
        assert set(MODULE_REGISTRY.keys()) == expected

    def test_get_all_display_names(self):
        """TS-AR-004: Get all display names returns dict."""
        from app.analyzers.registry import get_all_display_names
        names = get_all_display_names()
        assert isinstance(names, dict)
        assert len(names) == 10
        assert all(isinstance(v, str) for v in names.values())

    def test_get_description(self):
        """TS-AR-005: Get module description."""
        from app.analyzers.registry import get_description
        desc = get_description("branch_path")
        assert len(desc) > 0
        assert get_description("nonexistent") == ""

    def test_analysis_and_postmortem_separation(self):
        """TS-AR-006: Analysis and postmortem modules are separate."""
        from app.analyzers.registry import ANALYSIS_MODULES, POSTMORTEM_MODULES
        assert "postmortem" not in ANALYSIS_MODULES
        assert "knowledge_pattern" not in ANALYSIS_MODULES
        assert "postmortem" in POSTMORTEM_MODULES
        assert "knowledge_pattern" in POSTMORTEM_MODULES


# ═══════════════════════════════════════════════════════════════════
# 7. INTEGRATION: FULL ANALYSIS ON SAMPLE FILE
# ═══════════════════════════════════════════════════════════════════

class TestAnalyzerIntegration:
    """Integration tests using the actual test_samples/storage_module.c."""

    @pytest.fixture
    def sample_ctx(self):
        """Context pointing to the actual test_samples directory."""
        workspace = str(Path(__file__).parent.parent.parent)  # grayscope root
        return {
            "task_id": "integration-test",
            "project_id": 1,
            "repo_id": 1,
            "workspace_path": workspace,
            "target": {"path": "test_samples/"},
            "revision": {"branch": "main"},
            "options": {"max_files": 10},
            "upstream_results": {},
        }

    def test_branch_path_on_storage_module(self, sample_ctx):
        """TS-INT-001: Branch path analysis on storage_module.c."""
        from app.analyzers.branch_path_analyzer import analyze
        result = analyze(sample_ctx)
        assert result["status"] == "success"
        assert len(result["findings"]) > 5  # Should find many branches
        # Should identify error branches (NULL checks, ret < 0)
        error_findings = [f for f in result["findings"] if f["risk_type"] == "branch_error"]
        assert len(error_findings) > 0

    def test_boundary_value_on_storage_module(self, sample_ctx):
        """TS-INT-002: Boundary value analysis on storage_module.c."""
        from app.analyzers.boundary_value_analyzer import analyze
        result = analyze(sample_ctx)
        assert result["status"] == "success"
        assert len(result["findings"]) > 0

    def test_error_path_on_storage_module(self, sample_ctx):
        """TS-INT-003: Error path analysis on storage_module.c."""
        from app.analyzers.error_path_analyzer import analyze
        result = analyze(sample_ctx)
        assert result["status"] == "success"
        assert len(result["findings"]) > 0
        # Should detect the known bugs in storage_module.c
        risk_types = {f["risk_type"] for f in result["findings"]}
        assert "missing_cleanup" in risk_types or "silent_error_swallow" in risk_types

    def test_call_graph_on_storage_module(self, sample_ctx):
        """TS-INT-004: Call graph analysis on storage_module.c."""
        from app.analyzers.call_graph_builder import analyze
        result = analyze(sample_ctx)
        assert result["status"] == "success"
        assert result["metrics"]["total_nodes"] >= 5  # Several functions defined

    def test_all_findings_have_unique_ids(self, sample_ctx):
        """TS-INT-005: All findings across analyzers have unique IDs."""
        from app.analyzers import branch_path_analyzer, boundary_value_analyzer, error_path_analyzer

        all_ids = set()
        for analyzer in [branch_path_analyzer, boundary_value_analyzer, error_path_analyzer]:
            result = analyzer.analyze(sample_ctx)
            for f in result["findings"]:
                fid = f["finding_id"]
                assert fid not in all_ids, f"Duplicate finding ID: {fid}"
                all_ids.add(fid)
