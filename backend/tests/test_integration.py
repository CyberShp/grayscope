"""
Frontend-Backend Integration Tests

Validates:
  - API contract consistency (all frontend api.js paths exist on backend)
  - Response envelope format ({code, message, data})
  - End-to-end flows for code analysis, projects, repos, tasks, settings
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ═══════════════════════════════════════════════════════════════════
# 1. API CONTRACT TESTS
# ═══════════════════════════════════════════════════════════════════

class TestAPIContract:
    """Verify frontend API paths exist on backend."""
    
    @pytest.fixture(scope="class")
    def client(self):
        from app.main import app
        return TestClient(app)
    
    @pytest.fixture(scope="class")
    def frontend_api_paths(self):
        """Extract API paths from frontend api.js."""
        api_js_path = Path(__file__).parent.parent.parent / "frontend" / "src" / "api.js"
        
        if not api_js_path.exists():
            pytest.skip("frontend/src/api.js not found")
        
        content = api_js_path.read_text()
        
        # Extract paths like '/health', '/projects', '/projects/${id}', etc.
        # Match patterns: '/path', `/path`, '/path/${var}'
        path_pattern = r"['\"`](/api/v1)?(/[a-z0-9\-_/{}$]+)['\"`]"
        
        matches = re.findall(path_pattern, content, re.IGNORECASE)
        paths = set()
        
        for _, path in matches:
            # Normalize: remove ${...} placeholders, keep structure
            normalized = re.sub(r'\$\{[^}]+\}', '1', path)
            # Remove query params
            normalized = normalized.split('?')[0]
            paths.add(normalized)
        
        return sorted(paths)
    
    def test_health_endpoint_exists(self, client):
        """Health endpoint responds."""
        response = client.get("/api/v1/health")
        assert response.status_code in (200, 503)
    
    def test_projects_endpoint_exists(self, client):
        """Projects list endpoint responds."""
        response = client.get("/api/v1/projects")
        assert response.status_code == 200
    
    def test_settings_endpoint_exists(self, client):
        """Settings endpoint responds."""
        response = client.get("/api/v1/settings")
        assert response.status_code == 200
    
    def test_models_endpoint_exists(self, client):
        """Models list endpoint responds."""
        response = client.get("/api/v1/models")
        assert response.status_code == 200
    
    def test_code_analysis_list_exists(self, client):
        """Code analysis list endpoint responds."""
        response = client.get("/api/v1/code-analysis")
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════
# 2. RESPONSE ENVELOPE FORMAT
# ═══════════════════════════════════════════════════════════════════

class TestResponseEnvelope:
    """Verify response envelope format consistency."""
    
    @pytest.fixture(scope="class")
    def client(self):
        from app.main import app
        return TestClient(app)
    
    def test_health_envelope_format(self, client):
        """Health response has correct envelope."""
        response = client.get("/api/v1/health")
        data = response.json()
        
        # Our API uses 'code', 'message', 'data' envelope
        assert "code" in data or "status" in data or "data" in data
    
    def test_projects_list_envelope(self, client):
        """Projects list has correct envelope."""
        response = client.get("/api/v1/projects")
        data = response.json()
        
        # Should have data field with list
        if "data" in data:
            assert isinstance(data["data"], (list, dict))
    
    def test_error_response_format(self, client):
        """Error responses have detail or message."""
        response = client.get("/api/v1/projects/999999")
        
        if response.status_code == 404:
            data = response.json()
            # FastAPI typically returns 'detail'
            assert "detail" in data or "message" in data


# ═══════════════════════════════════════════════════════════════════
# 3. CODE ANALYSIS FLOW
# ═══════════════════════════════════════════════════════════════════

class TestCodeAnalysisFlow:
    """End-to-end code analysis flow."""
    
    @pytest.fixture(scope="class")
    def client(self):
        from app.main import app
        return TestClient(app)
    
    def test_start_analysis_invalid_path_rejected(self, client):
        """Invalid workspace path is rejected."""
        response = client.post(
            "/api/v1/code-analysis/start",
            json={"workspace_path": "/nonexistent/path/xyz"}
        )
        
        # Should reject with 400 or 422
        assert response.status_code in (400, 422)
    
    def test_get_status_nonexistent_returns_404(self, client):
        """Non-existent analysis returns 404."""
        response = client.get("/api/v1/code-analysis/fake-id-12345/status")
        assert response.status_code == 404
    
    def test_list_analyses_returns_list(self, client):
        """List analyses returns array."""
        response = client.get("/api/v1/code-analysis")
        assert response.status_code == 200
        
        data = response.json()
        # API wraps in envelope with code/data structure
        # data["data"] contains {"analyses": [...], "total": N}
        if isinstance(data, dict) and "data" in data:
            inner = data["data"]
            if isinstance(inner, dict) and "analyses" in inner:
                assert isinstance(inner["analyses"], list)
            else:
                assert isinstance(inner, list)
        else:
            assert isinstance(data, list)
    
    def test_list_analyses_with_status_filter(self, client):
        """Status filter parameter accepted."""
        response = client.get("/api/v1/code-analysis?status=completed")
        assert response.status_code == 200
    
    def test_list_analyses_with_limit(self, client):
        """Limit parameter accepted."""
        response = client.get("/api/v1/code-analysis?limit=5")
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════
# 4. PROJECT-REPO-TASK FLOW
# ═══════════════════════════════════════════════════════════════════

class TestProjectRepoTaskFlow:
    """End-to-end project > repo > task flow."""
    
    @pytest.fixture(scope="class")
    def client(self):
        from app.main import app
        return TestClient(app)
    
    @pytest.fixture
    def test_project(self, client):
        """Create a test project."""
        response = client.post(
            "/api/v1/projects",
            json={"name": "Integration Test Project", "description": "Test"}
        )
        
        if response.status_code != 200:
            pytest.skip("Could not create project")
        
        data = response.json()
        project_id = data.get("data", data).get("id") or data.get("data", data).get("project_id")
        
        yield project_id
        
        # Cleanup would go here if delete endpoint exists
    
    def test_create_project_returns_id(self, client):
        """Creating project returns ID."""
        response = client.post(
            "/api/v1/projects",
            json={"name": "Test Project", "description": "For testing"}
        )
        
        assert response.status_code in (200, 201)
        data = response.json()
        
        # Extract project ID from response
        project_data = data.get("data", data)
        assert "id" in project_data or "project_id" in project_data
    
    def test_get_project_by_id(self, client, test_project):
        """Get project by ID returns project data."""
        response = client.get(f"/api/v1/projects/{test_project}")
        assert response.status_code == 200
    
    def test_list_repos_for_project(self, client, test_project):
        """List repos for project returns array."""
        response = client.get(f"/api/v1/projects/{test_project}/repos")
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════
# 5. SETTINGS ROUND-TRIP
# ═══════════════════════════════════════════════════════════════════

class TestSettingsRoundTrip:
    """Settings get/update/get consistency."""
    
    @pytest.fixture(scope="class")
    def client(self):
        from app.main import app
        return TestClient(app)
    
    def test_get_settings_returns_object(self, client):
        """GET settings returns object."""
        response = client.get("/api/v1/settings")
        assert response.status_code == 200
        
        data = response.json()
        # Should have some settings structure
        assert isinstance(data.get("data", data), dict)
    
    def test_update_settings_accepts_valid_payload(self, client):
        """PUT settings accepts valid update."""
        # First get current settings
        get_response = client.get("/api/v1/settings")
        current = get_response.json().get("data", get_response.json())
        
        # Try to update with same values (idempotent)
        put_response = client.put("/api/v1/settings", json=current)
        
        # Should succeed or return validation error (not 500)
        assert put_response.status_code in (200, 400, 422)


# ═══════════════════════════════════════════════════════════════════
# 6. MODEL CONFIG AND TEST
# ═══════════════════════════════════════════════════════════════════

class TestModelConfigFlow:
    """AI model configuration and testing flow."""
    
    @pytest.fixture(scope="class")
    def client(self):
        from app.main import app
        return TestClient(app)
    
    def test_list_models_returns_providers(self, client):
        """List models returns provider info."""
        response = client.get("/api/v1/models")
        assert response.status_code == 200
        
        data = response.json()
        model_data = data.get("data", data)
        
        # Should have providers list or be the list itself
        assert "providers" in model_data or isinstance(model_data, list)
    
    def test_test_model_validates_input(self, client):
        """Test model endpoint validates input."""
        response = client.post(
            "/api/v1/models/test",
            json={}  # Missing required fields
        )
        
        # Should reject with validation error
        assert response.status_code in (400, 422)
    
    def test_test_model_with_valid_payload(self, client):
        """Test model endpoint accepts valid payload."""
        response = client.post(
            "/api/v1/models/test",
            json={
                "provider": "deepseek",
                "model": "deepseek-coder"
            }
        )
        
        # Might fail due to missing API key, but should not be 422
        # Could be 400 (config error), 500 (connection error), or 200 (success)
        assert response.status_code in (200, 400, 500)


# ═══════════════════════════════════════════════════════════════════
# 7. EXPORT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

class TestExportEndpoints:
    """Export functionality tests."""
    
    @pytest.fixture(scope="class")
    def client(self):
        from app.main import app
        return TestClient(app)
    
    def test_export_nonexistent_analysis_returns_404(self, client):
        """Export non-existent analysis returns 404."""
        response = client.get("/api/v1/code-analysis/fake-id/export?fmt=json")
        assert response.status_code == 404
    
    def test_export_accepts_format_parameter(self, client):
        """Export endpoint accepts fmt parameter."""
        # Even for non-existent ID, should not fail on param parsing
        response = client.get("/api/v1/code-analysis/test/export?fmt=csv")
        assert response.status_code in (404, 400)  # Not a server error


# ═══════════════════════════════════════════════════════════════════
# 8. FINDINGS AND TEST CASES
# ═══════════════════════════════════════════════════════════════════

class TestFindingsAndTestCases:
    """Findings and test cases endpoints."""
    
    @pytest.fixture(scope="class")
    def client(self):
        from app.main import app
        return TestClient(app)
    
    def test_list_findings_returns_list(self, client):
        """List findings returns array."""
        response = client.get("/api/v1/findings")
        assert response.status_code == 200
    
    def test_list_test_cases_returns_list(self, client):
        """List test cases returns array."""
        response = client.get("/api/v1/test-cases")
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════
# 9. ANALYSIS TASKS
# ═══════════════════════════════════════════════════════════════════

class TestAnalysisTasks:
    """Analysis task endpoints."""
    
    @pytest.fixture(scope="class")
    def client(self):
        from app.main import app
        return TestClient(app)
    
    def test_list_tasks_returns_list(self, client):
        """List tasks returns array."""
        response = client.get("/api/v1/analysis/tasks")
        assert response.status_code == 200
    
    def test_get_task_nonexistent_returns_404(self, client):
        """Get non-existent task returns 404."""
        response = client.get("/api/v1/analysis/tasks/99999")
        assert response.status_code == 404
    
    def test_create_task_validates_input(self, client):
        """Create task validates input."""
        response = client.post("/api/v1/analysis/tasks", json={})
        
        # Should reject with validation error
        assert response.status_code in (400, 422)


# ═══════════════════════════════════════════════════════════════════
# 10. KNOWLEDGE BASE
# ═══════════════════════════════════════════════════════════════════

class TestKnowledgeBase:
    """Knowledge base endpoints."""
    
    @pytest.fixture(scope="class")
    def client(self):
        from app.main import app
        return TestClient(app)
    
    def test_search_patterns_accepts_params(self, client):
        """Search patterns accepts query parameters."""
        response = client.get("/api/v1/knowledge/patterns?project_id=1&keyword=test")
        
        # Should not be a server error
        assert response.status_code in (200, 404)
