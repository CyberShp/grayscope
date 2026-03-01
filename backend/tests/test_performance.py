"""
Performance Tests

Validates response times and throughput:
  - Health endpoint < 100ms
  - Project list < 200ms
  - Graph build time benchmarks
  - Risk analysis time benchmarks
  - Concurrent request handling
  - Large result serialization
"""

import asyncio
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ═══════════════════════════════════════════════════════════════════
# 1. RESPONSE TIME TESTS
# ═══════════════════════════════════════════════════════════════════

class TestResponseTime:
    """API endpoint response time benchmarks."""
    
    @pytest.fixture(scope="class")
    def client(self):
        from app.main import app
        return TestClient(app)
    
    def test_health_response_time(self, client):
        """Health endpoint responds in < 100ms."""
        start = time.perf_counter()
        response = client.get("/api/v1/health")
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        assert response.status_code in (200, 503)
        assert elapsed_ms < 100, f"Health endpoint took {elapsed_ms:.2f}ms (limit: 100ms)"
    
    def test_projects_list_response_time(self, client):
        """Project list responds in < 200ms."""
        start = time.perf_counter()
        response = client.get("/api/v1/projects")
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        assert response.status_code == 200
        assert elapsed_ms < 200, f"Projects list took {elapsed_ms:.2f}ms (limit: 200ms)"
    
    def test_settings_response_time(self, client):
        """Settings endpoint responds in < 150ms."""
        start = time.perf_counter()
        response = client.get("/api/v1/settings")
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        assert response.status_code == 200
        assert elapsed_ms < 150, f"Settings took {elapsed_ms:.2f}ms (limit: 150ms)"
    
    def test_models_list_response_time(self, client):
        """Models list responds in < 500ms (includes external API call)."""
        start = time.perf_counter()
        response = client.get("/api/v1/models")
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        assert response.status_code == 200
        # This endpoint may call external API (e.g., deepseek) so allow more time
        assert elapsed_ms < 500, f"Models list took {elapsed_ms:.2f}ms (limit: 500ms)"


# ═══════════════════════════════════════════════════════════════════
# 2. GRAPH BUILD TIME
# ═══════════════════════════════════════════════════════════════════

class TestGraphBuildTime:
    """FusedGraphBuilder performance benchmarks."""
    
    @pytest.fixture
    def sample_c_code(self):
        """Generate sample C code for testing."""
        return """
#include <stdio.h>
int process(int x) {
    if (x > 0) {
        return x * 2;
    }
    return 0;
}
int main() {
    return process(42);
}
"""
    
    @pytest.fixture
    def multi_file_workspace(self, sample_c_code):
        """Create workspace with multiple files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(10):
                file_path = Path(tmpdir) / f"file_{i}.c"
                file_path.write_text(sample_c_code)
            yield tmpdir
    
    def test_small_workspace_build_time(self, multi_file_workspace):
        """10 files should build in < 5s."""
        try:
            from app.analyzers.fused_graph_builder import FusedGraphBuilder
        except ImportError:
            pytest.skip("FusedGraphBuilder not available")
        
        builder = FusedGraphBuilder()
        
        start = time.perf_counter()
        graph = builder.build(multi_file_workspace)
        elapsed = time.perf_counter() - start
        
        assert elapsed < 5, f"Build took {elapsed:.2f}s (limit: 5s)"
    
    def test_graph_serialization_time(self, multi_file_workspace):
        """Graph to_dict() should be fast."""
        try:
            from app.analyzers.fused_graph_builder import FusedGraphBuilder
        except ImportError:
            pytest.skip("FusedGraphBuilder not available")
        
        builder = FusedGraphBuilder()
        graph = builder.build(multi_file_workspace)
        
        start = time.perf_counter()
        data = graph.to_dict()
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        assert elapsed_ms < 500, f"Serialization took {elapsed_ms:.2f}ms (limit: 500ms)"


# ═══════════════════════════════════════════════════════════════════
# 3. RISK ANALYSIS TIME
# ═══════════════════════════════════════════════════════════════════

class TestRiskAnalysisTime:
    """FusedRiskAnalyzer performance benchmarks."""
    
    @pytest.fixture
    def sample_graph(self):
        """Create a sample graph for testing."""
        try:
            from app.analyzers.fused_graph_builder import FusedGraph, FusedNode, FusedEdge, Branch
        except ImportError:
            pytest.skip("FusedGraph not available")
        
        # Build nodes dict
        nodes = {}
        for i in range(100):
            nodes[f"func_{i}"] = FusedNode(
                name=f"func_{i}",
                file_path=f"file_{i % 10}.c",
                line_start=1,
                line_end=10,
                source="",
                params=[],
                comments=[],
                branches=[Branch(condition=f"x > {i}", line=5, branch_type="if")],
                lock_ops=[],
                shared_var_access=[],
                protocol_ops=[],
                is_entry_point=False,
                entry_point_type="none"
            )
        
        # Build edges list
        edges = []
        for i in range(100):
            for j in range(2):
                edges.append(FusedEdge(
                    caller=f"func_{i}",
                    callee=f"func_{(i + j + 1) % 100}",
                    call_site_line=5,
                    branch_context="",
                    lock_held=[],
                    arg_mapping=[],
                    data_flow_tags=[]
                ))
        
        return FusedGraph(
            nodes=nodes,
            edges=edges,
            call_chains=[],
            global_vars=set(),
            protocol_state_machine={}
        )
    
    def test_risk_analysis_time(self, sample_graph):
        """Risk analysis of 100 nodes should complete in < 10s."""
        try:
            from app.analyzers.fused_risk_analyzer import FusedRiskAnalyzer
        except ImportError:
            pytest.skip("FusedRiskAnalyzer not available")
        
        analyzer = FusedRiskAnalyzer(sample_graph)
        
        start = time.perf_counter()
        risks = analyzer.analyze()
        elapsed = time.perf_counter() - start
        
        assert elapsed < 10, f"Analysis took {elapsed:.2f}s (limit: 10s)"


# ═══════════════════════════════════════════════════════════════════
# 4. CONCURRENT REQUESTS
# ═══════════════════════════════════════════════════════════════════

class TestConcurrentRequests:
    """Concurrent request handling."""
    
    @pytest.fixture(scope="class")
    def client(self):
        from app.main import app
        return TestClient(app)
    
    def test_concurrent_health_checks(self, client):
        """20 concurrent health checks don't crash."""
        def make_request():
            return client.get("/api/v1/health")
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(make_request) for _ in range(20)]
            results = [f.result() for f in futures]
        
        # All requests should complete
        assert len(results) == 20
        # Most should succeed
        success_count = sum(1 for r in results if r.status_code in (200, 503))
        assert success_count >= 18, f"Only {success_count}/20 requests succeeded"
    
    def test_concurrent_project_list(self, client):
        """20 concurrent project list requests."""
        def make_request():
            return client.get("/api/v1/projects")
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(make_request) for _ in range(20)]
            results = [f.result() for f in futures]
        
        success_count = sum(1 for r in results if r.status_code == 200)
        assert success_count >= 18, f"Only {success_count}/20 requests succeeded"
    
    def test_mixed_concurrent_requests(self, client):
        """Mix of different endpoints concurrently."""
        endpoints = [
            "/api/v1/health",
            "/api/v1/projects",
            "/api/v1/settings",
            "/api/v1/models",
            "/api/v1/code-analysis",
        ]
        
        def make_request(endpoint):
            return client.get(endpoint)
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(make_request, endpoints[i % len(endpoints)])
                for i in range(20)
            ]
            results = [f.result() for f in futures]
        
        # All requests should complete without 500 errors
        error_count = sum(1 for r in results if r.status_code >= 500)
        assert error_count == 0, f"{error_count} requests resulted in 5xx errors"


# ═══════════════════════════════════════════════════════════════════
# 5. LARGE RESULT SERIALIZATION
# ═══════════════════════════════════════════════════════════════════

class TestLargeResultSerialization:
    """Serialization performance for large results."""
    
    def test_large_findings_list_serialization(self):
        """Serializing 1000 findings should be fast."""
        import json
        
        findings = [
            {
                "finding_id": f"F-{i:05d}",
                "risk_type": "boundary_miss",
                "severity": ["critical", "high", "medium", "low"][i % 4],
                "description": f"Finding {i} description with some details",
                "call_chain": [f"func_{j}" for j in range(5)],
                "evidence": {"line": i, "code": f"x > {i}"},
            }
            for i in range(1000)
        ]
        
        start = time.perf_counter()
        json_str = json.dumps(findings)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        assert elapsed_ms < 500, f"Serialization took {elapsed_ms:.2f}ms (limit: 500ms)"
        assert len(json_str) > 0
    
    def test_large_graph_serialization(self):
        """Serializing large graph should be fast."""
        import json
        
        graph_data = {
            "nodes": [
                {
                    "id": f"node_{i}",
                    "type": "function",
                    "data": {"branches": [{"type": "if"} for _ in range(3)]}
                }
                for i in range(500)
            ],
            "edges": [
                {"source": f"node_{i}", "target": f"node_{(i+1) % 500}"}
                for i in range(1000)
            ]
        }
        
        start = time.perf_counter()
        json_str = json.dumps(graph_data)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        assert elapsed_ms < 200, f"Graph serialization took {elapsed_ms:.2f}ms (limit: 200ms)"


# ═══════════════════════════════════════════════════════════════════
# 6. STRESS TESTS (Optional - longer running)
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.slow
class TestStress:
    """Stress tests - run with pytest -m slow."""
    
    @pytest.fixture(scope="class")
    def client(self):
        from app.main import app
        return TestClient(app)
    
    def test_sustained_load(self, client):
        """100 requests in sequence don't degrade."""
        times = []
        
        for _ in range(100):
            start = time.perf_counter()
            response = client.get("/api/v1/health")
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)
            assert response.status_code in (200, 503)
        
        avg_time = sum(times) / len(times)
        max_time = max(times)
        
        # Average should stay reasonable
        assert avg_time < 50, f"Average response time {avg_time:.2f}ms > 50ms"
        # No extreme outliers
        assert max_time < 500, f"Max response time {max_time:.2f}ms > 500ms"
