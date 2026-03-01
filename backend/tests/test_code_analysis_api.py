"""
Tests for Code Analysis Pipeline API endpoints.

Covers all 14 endpoints:
- POST /code-analysis/start
- GET /code-analysis/{id}/status
- GET /code-analysis/{id}/results
- GET /code-analysis/{id}/call-graph
- GET /code-analysis/{id}/risks
- GET /code-analysis/{id}/narratives
- GET /code-analysis/{id}/function-dictionary
- GET /code-analysis/{id}/risk-cards
- GET /code-analysis/{id}/what-if
- GET /code-analysis/{id}/test-matrix
- GET /code-analysis/{id}/protocol-state-machine
- GET /code-analysis/{id}/export
- DELETE /code-analysis/{id}
- GET /code-analysis/
"""

import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.v1 import code_analysis_api

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_tasks():
    """Clear analysis tasks before and after each test."""
    code_analysis_api._analysis_tasks.clear()
    yield
    code_analysis_api._analysis_tasks.clear()


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace with sample files."""
    with tempfile.TemporaryDirectory() as tmp:
        # Create a sample C file
        c_file = Path(tmp) / "sample.c"
        c_file.write_text("""
int helper(int x) { return x + 1; }
int main(void) { return helper(0); }
""")
        yield tmp


@pytest.fixture
def mock_analysis_result():
    """Create a mock AnalysisResult object."""
    from dataclasses import dataclass
    
    class MockProgress:
        current_step = "completed"
        total_steps = 5
        steps_completed = 5
        error = None
        
        def to_dict(self):
            return {
                "current_step": self.current_step,
                "total_steps": self.total_steps,
                "steps_completed": self.steps_completed,
                "error": self.error,
            }
    
    class MockResult:
        progress = MockProgress()
        risk_findings = [
            {
                "finding_id": "FR-0001",
                "risk_type": "error_path_resource_leak",
                "severity": "S1",
                "risk_score": 0.8,
                "title": "Test finding",
                "description": "Test description",
                "file_path": "test.c",
                "symbol_name": "test_func",
            }
        ]
        risk_summary = {
            "total_findings": 1,
            "severity_distribution": {"S1": 1},
        }
        narratives = {
            "flow_narratives": [{"chain": ["main", "helper"], "story": "A test story"}],
            "function_dictionary": {"helper": {"business_name": "Helper Function"}},
            "risk_cards": [{"id": "RC-1", "scenario": "Test scenario"}],
            "what_if_scenarios": [{"scenario": "What if X"}],
            "test_matrix": {"test_cases": [{"id": "TC-1"}]},
        }
        graph_dict = {
            "nodes": {"main": {"name": "main"}},
            "edges": [],
            "protocol_state_machine": {"states": {}, "transitions": []},
        }
        
        def to_dict(self):
            return {
                "progress": self.progress.to_dict(),
                "risk_findings": self.risk_findings,
                "risk_summary": self.risk_summary,
                "narratives": self.narratives,
                "graph": self.graph_dict,
            }
    
    return MockResult()


def _insert_mock_task(analysis_id, status, result=None, error=None, workspace_path="/tmp"):
    """Helper to insert a mock task into storage."""
    code_analysis_api._analysis_tasks[analysis_id] = {
        "status": status,
        "started_at": "2024-01-01T00:00:00",
        "completed_at": "2024-01-01T00:01:00" if status != "running" else None,
        "result": result,
        "error": error,
        "workspace_path": workspace_path,
    }


# ═══════════════════════════════════════════════════════════════════
# 1. START ANALYSIS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestStartAnalysis:
    """Tests for POST /code-analysis/start."""

    def test_start_analysis_success(self, temp_workspace):
        """POST /code-analysis/start returns 202 + analysis_id."""
        response = client.post("/api/v1/code-analysis/start", json={
            "workspace_path": temp_workspace,
            "enable_ai": False,
            "max_files": 10,
        })
        
        assert response.status_code == 202
        data = response.json()
        assert data["code"] == "OK"
        assert "analysis_id" in data["data"]
        # Status may be "running" or "completed" depending on how fast the task finishes
        assert data["data"]["status"] in ("running", "completed")

    def test_start_analysis_invalid_path(self):
        """Invalid workspace path returns 400."""
        response = client.post("/api/v1/code-analysis/start", json={
            "workspace_path": "/nonexistent/path/xyz",
        })
        
        assert response.status_code == 400

    def test_start_analysis_creates_task(self, temp_workspace):
        """Task is created in storage."""
        response = client.post("/api/v1/code-analysis/start", json={
            "workspace_path": temp_workspace,
            "enable_ai": False,
        })
        
        data = response.json()
        analysis_id = data["data"]["analysis_id"]
        
        assert analysis_id in code_analysis_api._analysis_tasks
        task = code_analysis_api._analysis_tasks[analysis_id]
        # Status may be "running" or "completed" depending on how fast the task finishes
        assert task["status"] in ("running", "completed")
        assert task["workspace_path"] == temp_workspace


# ═══════════════════════════════════════════════════════════════════
# 2. GET STATUS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestGetStatus:
    """Tests for GET /code-analysis/{id}/status."""

    def test_get_status_not_found(self):
        """Non-existent ID returns 404."""
        response = client.get("/api/v1/code-analysis/nonexistent-id/status")
        
        assert response.status_code == 404

    def test_get_status_running(self, mock_analysis_result):
        """Running task returns progress."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "running", mock_analysis_result)
        
        response = client.get(f"/api/v1/code-analysis/{analysis_id}/status")
        
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "running"
        assert data["analysis_id"] == analysis_id

    def test_get_status_completed(self, mock_analysis_result):
        """Completed task returns full progress."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "completed", mock_analysis_result)
        
        response = client.get(f"/api/v1/code-analysis/{analysis_id}/status")
        
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "completed"
        assert "progress" in data


# ═══════════════════════════════════════════════════════════════════
# 3. GET RESULTS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestGetResults:
    """Tests for GET /code-analysis/{id}/results."""

    def test_get_results_not_found(self):
        """Non-existent ID returns 404."""
        response = client.get("/api/v1/code-analysis/nonexistent-id/results")
        
        assert response.status_code == 404

    def test_get_results_running(self, mock_analysis_result):
        """Running task returns status=running."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "running", mock_analysis_result)
        
        response = client.get(f"/api/v1/code-analysis/{analysis_id}/results")
        
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "running"

    def test_get_results_completed(self, mock_analysis_result):
        """Completed task returns full results."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "completed", mock_analysis_result)
        
        response = client.get(f"/api/v1/code-analysis/{analysis_id}/results")
        
        assert response.status_code == 200
        data = response.json()["data"]
        assert "risk_findings" in data
        assert "narratives" in data

    def test_get_results_failed(self, mock_analysis_result):
        """Failed task returns error."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "failed", None, error="Test error")
        
        response = client.get(f"/api/v1/code-analysis/{analysis_id}/results")
        
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "failed"
        assert data["error"] == "Test error"


# ═══════════════════════════════════════════════════════════════════
# 4. SPECIALIZED ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════════

class TestCallGraph:
    """Tests for GET /code-analysis/{id}/call-graph."""

    def test_get_call_graph_not_found(self):
        """No result returns 404."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "completed", None)
        
        response = client.get(f"/api/v1/code-analysis/{analysis_id}/call-graph")
        
        assert response.status_code == 404


class TestRiskFindings:
    """Tests for GET /code-analysis/{id}/risks."""

    def test_get_risks_not_found(self):
        """No result returns 404."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "completed", None)
        
        response = client.get(f"/api/v1/code-analysis/{analysis_id}/risks")
        
        assert response.status_code == 404

    def test_get_risks_with_severity_filter(self, mock_analysis_result):
        """Severity filter works."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "completed", mock_analysis_result)
        
        response = client.get(f"/api/v1/code-analysis/{analysis_id}/risks?severity=S1")
        
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 1

    def test_get_risks_with_type_filter(self, mock_analysis_result):
        """Risk type filter works."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "completed", mock_analysis_result)
        
        response = client.get(
            f"/api/v1/code-analysis/{analysis_id}/risks?risk_type=error_path_resource_leak"
        )
        
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 1

    def test_get_risks_filter_empty_result(self, mock_analysis_result):
        """Filter returns empty when no match."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "completed", mock_analysis_result)
        
        response = client.get(f"/api/v1/code-analysis/{analysis_id}/risks?severity=S0")
        
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 0


class TestNarratives:
    """Tests for narrative endpoints."""

    def test_get_narratives(self, mock_analysis_result):
        """GET /narratives returns all narratives."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "completed", mock_analysis_result)
        
        response = client.get(f"/api/v1/code-analysis/{analysis_id}/narratives")
        
        assert response.status_code == 200
        data = response.json()["data"]
        assert "flow_narratives" in data or "function_dictionary" in data

    def test_get_function_dictionary(self, mock_analysis_result):
        """GET /function-dictionary returns dict."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "completed", mock_analysis_result)
        
        response = client.get(f"/api/v1/code-analysis/{analysis_id}/function-dictionary")
        
        assert response.status_code == 200

    def test_get_risk_cards(self, mock_analysis_result):
        """GET /risk-cards returns cards list."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "completed", mock_analysis_result)
        
        response = client.get(f"/api/v1/code-analysis/{analysis_id}/risk-cards")
        
        assert response.status_code == 200
        data = response.json()["data"]
        assert "cards" in data

    def test_get_what_if_scenarios(self, mock_analysis_result):
        """GET /what-if returns scenarios."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "completed", mock_analysis_result)
        
        response = client.get(f"/api/v1/code-analysis/{analysis_id}/what-if")
        
        assert response.status_code == 200
        data = response.json()["data"]
        assert "scenarios" in data

    def test_get_test_matrix(self, mock_analysis_result):
        """GET /test-matrix returns matrix."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "completed", mock_analysis_result)
        
        response = client.get(f"/api/v1/code-analysis/{analysis_id}/test-matrix")
        
        assert response.status_code == 200


class TestProtocolStateMachine:
    """Tests for GET /code-analysis/{id}/protocol-state-machine."""

    def test_get_protocol_state_machine_not_found(self):
        """No result returns 404."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "completed", None)
        
        response = client.get(f"/api/v1/code-analysis/{analysis_id}/protocol-state-machine")
        
        assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# 5. EXPORT TESTS
# ═══════════════════════════════════════════════════════════════════

class TestExport:
    """Tests for GET /code-analysis/{id}/export."""

    def test_export_not_found(self):
        """No result returns 404."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "completed", None)
        
        response = client.get(f"/api/v1/code-analysis/{analysis_id}/export")
        
        assert response.status_code == 404

    def test_export_json_default(self, mock_analysis_result):
        """Default export is JSON."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "completed", mock_analysis_result)
        
        # Mock the service methods
        with patch.object(
            code_analysis_api.CodeAnalysisService,
            "export_full_report_json",
            return_value='{"test": "data"}',
        ):
            response = client.get(f"/api/v1/code-analysis/{analysis_id}/export")
        
            assert response.status_code == 200
            assert "application/json" in response.headers["content-type"]

    def test_export_csv(self, mock_analysis_result):
        """CSV export works."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "completed", mock_analysis_result)
        
        with patch.object(
            code_analysis_api.CodeAnalysisService,
            "export_test_matrix_csv",
            return_value="col1,col2\nval1,val2",
        ):
            response = client.get(f"/api/v1/code-analysis/{analysis_id}/export?fmt=csv")
        
            assert response.status_code == 200
            assert "text/csv" in response.headers["content-type"]

    def test_export_risk_cards(self, mock_analysis_result):
        """Risk cards JSON export works."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "completed", mock_analysis_result)
        
        with patch.object(
            code_analysis_api.CodeAnalysisService,
            "export_risk_cards_json",
            return_value='[{"id": "RC-1"}]',
        ):
            response = client.get(f"/api/v1/code-analysis/{analysis_id}/export?fmt=risk-cards")
        
            assert response.status_code == 200

    def test_export_function_dict(self, mock_analysis_result):
        """Function dictionary export works."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "completed", mock_analysis_result)
        
        with patch.object(
            code_analysis_api.CodeAnalysisService,
            "export_function_dictionary_json",
            return_value='{"helper": {}}',
        ):
            response = client.get(f"/api/v1/code-analysis/{analysis_id}/export?fmt=function-dict")
        
            assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════
# 6. DELETE AND LIST TESTS
# ═══════════════════════════════════════════════════════════════════

class TestDeleteAnalysis:
    """Tests for DELETE /code-analysis/{id}."""

    def test_delete_not_found(self):
        """Delete non-existent returns 404."""
        response = client.delete("/api/v1/code-analysis/nonexistent-id")
        
        assert response.status_code == 404

    def test_delete_success(self, mock_analysis_result):
        """Delete removes task."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "completed", mock_analysis_result)
        
        response = client.delete(f"/api/v1/code-analysis/{analysis_id}")
        
        assert response.status_code == 200
        assert analysis_id not in code_analysis_api._analysis_tasks

    def test_delete_and_get_404(self, mock_analysis_result):
        """Deleted task returns 404 on get."""
        analysis_id = str(uuid.uuid4())
        _insert_mock_task(analysis_id, "completed", mock_analysis_result)
        
        client.delete(f"/api/v1/code-analysis/{analysis_id}")
        response = client.get(f"/api/v1/code-analysis/{analysis_id}/status")
        
        assert response.status_code == 404


class TestListAnalyses:
    """Tests for GET /code-analysis/."""

    def test_list_empty(self):
        """Empty list returns correctly."""
        response = client.get("/api/v1/code-analysis/")
        
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["analyses"] == []
        assert data["total"] == 0

    def test_list_with_tasks(self, mock_analysis_result):
        """List returns all tasks."""
        _insert_mock_task("id-1", "completed", mock_analysis_result)
        _insert_mock_task("id-2", "running", mock_analysis_result)
        
        response = client.get("/api/v1/code-analysis/")
        
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 2
        assert len(data["analyses"]) == 2

    def test_list_with_status_filter(self, mock_analysis_result):
        """Status filter works."""
        _insert_mock_task("id-1", "completed", mock_analysis_result)
        _insert_mock_task("id-2", "running", mock_analysis_result)
        _insert_mock_task("id-3", "failed", None, "Error")
        
        response = client.get("/api/v1/code-analysis/?status=completed")
        
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 1
        assert data["analyses"][0]["status"] == "completed"

    def test_list_respects_limit(self, mock_analysis_result):
        """Limit parameter works."""
        for i in range(5):
            _insert_mock_task(f"id-{i}", "completed", mock_analysis_result)
        
        response = client.get("/api/v1/code-analysis/?limit=3")
        
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["analyses"]) == 3
        assert data["total"] == 5
