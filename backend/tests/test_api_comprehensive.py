"""
GrayScope 100+ comprehensive API test cases.

Covers:
  - Health check
  - Project CRUD & validation
  - Repository CRUD & validation
  - Analysis task lifecycle (create, status, results, retry, cancel)
  - Aggregation endpoints (summary, findings, tasks, measures, file-tree, source)
  - Global endpoints (findings, tasks, test-cases)
  - Postmortem & knowledge base
  - Settings & models
  - Pagination & edge cases
  - Frontend-backend contract alignment
"""

import json
import pytest


# ═══════════════════════════════════════════════════════════════════
# 1. HEALTH CHECK (2 cases)
# ═══════════════════════════════════════════════════════════════════

class TestHealth:
    def test_001_health_returns_ok(self, client):
        """TC-001: GET /health returns 200 with service status."""
        res = client.get("/api/v1/health")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "grayscope" in data["service"]
        assert data["status"] == "ok"

    def test_002_health_has_parser_info(self, client):
        """TC-002: Health check includes parser availability."""
        res = client.get("/api/v1/health")
        data = res.json()["data"]
        assert "parser_available" in data


# ═══════════════════════════════════════════════════════════════════
# 2. PROJECT CRUD (18 cases)
# ═══════════════════════════════════════════════════════════════════

class TestProjectCreate:
    def test_003_create_project_success(self, client):
        """TC-003: Create a project with name and description."""
        res = client.post("/api/v1/projects", json={"name": "my-proj", "description": "desc"})
        assert res.status_code == 201
        data = res.json()["data"]
        assert data["name"] == "my-proj"
        assert data["description"] == "desc"
        assert data["status"] == "active"
        assert "project_id" in data
        assert "created_at" in data

    def test_004_create_project_without_description(self, client):
        """TC-004: Create a project without description (optional field)."""
        res = client.post("/api/v1/projects", json={"name": "no-desc-proj"})
        assert res.status_code == 201
        assert res.json()["data"]["description"] is None

    def test_005_create_project_duplicate_name(self, client, create_project):
        """TC-005: Duplicate project name returns error."""
        create_project(name="dup-name")
        res = client.post("/api/v1/projects", json={"name": "dup-name"})
        assert res.status_code == 422

    def test_006_create_project_empty_name(self, client):
        """TC-006: Empty name is rejected (min_length=1)."""
        res = client.post("/api/v1/projects", json={"name": ""})
        assert res.status_code == 422

    def test_007_create_project_name_too_long(self, client):
        """TC-007: Name exceeding 64 chars is rejected."""
        res = client.post("/api/v1/projects", json={"name": "x" * 65})
        assert res.status_code == 422

    def test_008_create_project_description_too_long(self, client):
        """TC-008: Description exceeding 512 chars is rejected."""
        res = client.post("/api/v1/projects", json={"name": "ok", "description": "x" * 513})
        assert res.status_code == 422

    def test_009_create_project_missing_name(self, client):
        """TC-009: Missing name field is rejected."""
        res = client.post("/api/v1/projects", json={"description": "no name"})
        assert res.status_code == 422

    def test_010_create_project_name_max_boundary(self, client):
        """TC-010: Name at exactly 64 chars should succeed."""
        res = client.post("/api/v1/projects", json={"name": "a" * 64})
        assert res.status_code == 201

    def test_011_create_project_unicode_name(self, client):
        """TC-011: Unicode project name works."""
        res = client.post("/api/v1/projects", json={"name": "测试项目-中文"})
        assert res.status_code == 201
        assert res.json()["data"]["name"] == "测试项目-中文"


class TestProjectList:
    def test_012_list_projects_empty(self, client):
        """TC-012: List projects when none exist."""
        res = client.get("/api/v1/projects")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["items"] == []
        assert data["total"] == 0

    def test_013_list_projects_returns_items(self, client, create_project):
        """TC-013: List projects returns created items."""
        create_project(name="p1")
        create_project(name="p2")
        res = client.get("/api/v1/projects")
        data = res.json()["data"]
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_014_list_projects_pagination(self, client, create_project):
        """TC-014: Pagination with page_size=1."""
        create_project(name="p1")
        create_project(name="p2")
        res = client.get("/api/v1/projects?page=1&page_size=1")
        data = res.json()["data"]
        assert len(data["items"]) == 1
        assert data["total"] == 2
        assert data["page"] == 1

    def test_015_list_projects_page2(self, client, create_project):
        """TC-015: Get second page."""
        create_project(name="p1")
        create_project(name="p2")
        res = client.get("/api/v1/projects?page=2&page_size=1")
        data = res.json()["data"]
        assert len(data["items"]) == 1
        assert data["page"] == 2

    def test_016_list_projects_response_has_keys(self, client, create_project):
        """TC-016: Response envelope has correct keys (frontend contract)."""
        create_project()
        res = client.get("/api/v1/projects")
        data = res.json()["data"]
        assert "items" in data
        assert "page" in data
        assert "page_size" in data
        assert "total" in data

    def test_017_list_projects_item_has_project_id(self, client, create_project):
        """TC-017: Each item uses project_id key (frontend expects this)."""
        create_project()
        res = client.get("/api/v1/projects")
        item = res.json()["data"]["items"][0]
        assert "project_id" in item
        assert "name" in item
        assert "status" in item
        assert "created_at" in item


class TestProjectGet:
    def test_018_get_project_by_id(self, client, create_project):
        """TC-018: Get project by ID."""
        proj = create_project()
        pid = proj["project_id"]
        res = client.get(f"/api/v1/projects/{pid}")
        assert res.status_code == 200
        assert res.json()["data"]["name"] == "test-project"

    def test_019_get_project_not_found(self, client):
        """TC-019: Get nonexistent project returns 404."""
        res = client.get("/api/v1/projects/99999")
        assert res.status_code == 404

    def test_020_get_project_invalid_id(self, client):
        """TC-020: Get project with non-integer ID returns 422."""
        res = client.get("/api/v1/projects/abc")
        assert res.status_code == 422


# ═══════════════════════════════════════════════════════════════════
# 3. REPOSITORY CRUD (18 cases)
# ═══════════════════════════════════════════════════════════════════

class TestRepoCreate:
    def test_021_create_repo_success(self, client, create_project):
        """TC-021: Create repo with valid data."""
        proj = create_project()
        pid = proj["project_id"]
        res = client.post(f"/api/v1/projects/{pid}/repos", json={
            "name": "my-repo",
            "git_url": "https://github.com/test/repo.git",
        })
        assert res.status_code == 201
        data = res.json()["data"]
        assert data["name"] == "my-repo"
        assert data["git_url"] == "https://github.com/test/repo.git"
        assert data["default_branch"] == "main"
        assert data["last_sync_status"] == "never"
        assert "repo_id" in data
        assert "project_id" in data

    def test_022_create_repo_custom_branch(self, client, create_project):
        """TC-022: Create repo with custom default branch."""
        proj = create_project()
        pid = proj["project_id"]
        res = client.post(f"/api/v1/projects/{pid}/repos", json={
            "name": "dev-repo",
            "git_url": "git@github.com:test/repo.git",
            "default_branch": "develop",
        })
        assert res.status_code == 201
        assert res.json()["data"]["default_branch"] == "develop"

    def test_023_create_repo_project_not_found(self, client):
        """TC-023: Create repo for nonexistent project."""
        res = client.post("/api/v1/projects/99999/repos", json={
            "name": "repo", "git_url": "https://example.com/repo.git"
        })
        assert res.status_code == 404

    def test_024_create_repo_empty_name(self, client, create_project):
        """TC-024: Repo with empty name is rejected."""
        proj = create_project()
        res = client.post(f"/api/v1/projects/{proj['project_id']}/repos", json={
            "name": "", "git_url": "https://example.com/repo.git"
        })
        assert res.status_code == 422

    def test_025_create_repo_missing_git_url(self, client, create_project):
        """TC-025: Repo without git_url is rejected."""
        proj = create_project()
        res = client.post(f"/api/v1/projects/{proj['project_id']}/repos", json={
            "name": "repo"
        })
        assert res.status_code == 422

    def test_026_create_repo_duplicate_name_same_project(self, client, create_project):
        """TC-026: Duplicate repo name in same project is rejected."""
        proj = create_project()
        pid = proj["project_id"]
        client.post(f"/api/v1/projects/{pid}/repos", json={
            "name": "dup-repo", "git_url": "https://example.com/1.git"
        })
        res = client.post(f"/api/v1/projects/{pid}/repos", json={
            "name": "dup-repo", "git_url": "https://example.com/2.git"
        })
        assert res.status_code == 422  # Duplicate name rejected gracefully

    def test_027_create_repo_same_name_different_project(self, client, create_project):
        """TC-027: Same repo name in different projects is allowed."""
        p1 = create_project(name="proj1")
        p2 = create_project(name="proj2")
        r1 = client.post(f"/api/v1/projects/{p1['project_id']}/repos", json={
            "name": "shared-name", "git_url": "https://example.com/1.git"
        })
        r2 = client.post(f"/api/v1/projects/{p2['project_id']}/repos", json={
            "name": "shared-name", "git_url": "https://example.com/2.git"
        })
        assert r1.status_code == 201
        assert r2.status_code == 201

    def test_028_create_repo_ssh_url(self, client, create_project):
        """TC-028: SSH-style git URL works."""
        proj = create_project()
        res = client.post(f"/api/v1/projects/{proj['project_id']}/repos", json={
            "name": "ssh-repo", "git_url": "git@github.com:org/repo.git"
        })
        assert res.status_code == 201


class TestRepoList:
    def test_029_list_repos_empty(self, client, create_project):
        """TC-029: List repos for project with no repos."""
        proj = create_project()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/repos")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data == [] or (isinstance(data, list) and len(data) == 0)

    def test_030_list_repos_returns_array(self, client, create_repo):
        """TC-030: List repos returns array (frontend expects array)."""
        proj, repo = create_repo()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/repos")
        assert res.status_code == 200
        data = res.json()["data"]
        assert isinstance(data, list)
        assert len(data) == 1

    def test_031_list_repos_item_has_repo_id(self, client, create_repo):
        """TC-031: Repo items use repo_id key (frontend contract)."""
        proj, repo = create_repo()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/repos")
        item = res.json()["data"][0]
        assert "repo_id" in item
        assert "project_id" in item
        assert "name" in item
        assert "git_url" in item
        assert "default_branch" in item
        assert "last_sync_status" in item

    def test_032_list_repos_project_not_found(self, client):
        """TC-032: List repos for nonexistent project."""
        res = client.get("/api/v1/projects/99999/repos")
        assert res.status_code == 404

    def test_033_list_repos_multiple(self, client, create_project):
        """TC-033: Multiple repos for same project."""
        proj = create_project()
        pid = proj["project_id"]
        client.post(f"/api/v1/projects/{pid}/repos", json={"name": "r1", "git_url": "https://a.com/1.git"})
        client.post(f"/api/v1/projects/{pid}/repos", json={"name": "r2", "git_url": "https://a.com/2.git"})
        client.post(f"/api/v1/projects/{pid}/repos", json={"name": "r3", "git_url": "https://a.com/3.git"})
        res = client.get(f"/api/v1/projects/{pid}/repos")
        assert len(res.json()["data"]) == 3

    def test_034_list_repos_isolation(self, client, create_project):
        """TC-034: Repos from one project don't appear in another."""
        p1 = create_project(name="iso-p1")
        p2 = create_project(name="iso-p2")
        client.post(f"/api/v1/projects/{p1['project_id']}/repos", json={"name": "r1", "git_url": "https://a.com/1.git"})
        res = client.get(f"/api/v1/projects/{p2['project_id']}/repos")
        assert len(res.json()["data"]) == 0


# ═══════════════════════════════════════════════════════════════════
# 4. ANALYSIS TASK LIFECYCLE (28 cases)
# ═══════════════════════════════════════════════════════════════════

class TestTaskCreate:
    def test_035_create_task_success(self, client, create_repo):
        """TC-035: Create a full analysis task."""
        proj, repo = create_repo()
        res = client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"],
            "repo_id": repo["repo_id"],
            "task_type": "full",
            "analyzers": ["branch_path"],
            "target": {"path": "test_samples/"},
        })
        assert res.status_code == 201
        data = res.json()["data"]
        assert "task_id" in data
        assert data["task_type"] == "full"
        assert data["status"] in ("success", "failed", "partial_failed", "running", "pending")

    def test_036_create_task_multiple_analyzers(self, client, create_repo):
        """TC-036: Task with multiple analyzer modules."""
        proj, repo = create_repo()
        res = client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"],
            "repo_id": repo["repo_id"],
            "task_type": "full",
            "analyzers": ["branch_path", "boundary_value", "error_path", "call_graph"],
        })
        assert res.status_code == 201

    def test_037_create_task_all_analyzers(self, client, create_repo):
        """TC-037: Task with all 7 standard analyzers."""
        proj, repo = create_repo()
        all_mods = ["branch_path", "boundary_value", "error_path", "call_graph", "concurrency", "diff_impact", "coverage_map"]
        res = client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"],
            "repo_id": repo["repo_id"],
            "task_type": "full",
            "analyzers": all_mods,
        })
        assert res.status_code == 201

    def test_038_create_task_invalid_analyzer(self, client, create_repo):
        """TC-038: Invalid analyzer module is rejected."""
        proj, repo = create_repo()
        res = client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"],
            "repo_id": repo["repo_id"],
            "task_type": "full",
            "analyzers": ["nonexistent_module"],
        })
        assert res.status_code == 422

    def test_039_create_task_empty_analyzers(self, client, create_repo):
        """TC-039: Empty analyzers list is rejected (min_length=1)."""
        proj, repo = create_repo()
        res = client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"],
            "repo_id": repo["repo_id"],
            "task_type": "full",
            "analyzers": [],
        })
        assert res.status_code == 422

    def test_040_create_task_invalid_task_type(self, client, create_repo):
        """TC-040: Invalid task type is rejected."""
        proj, repo = create_repo()
        res = client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"],
            "repo_id": repo["repo_id"],
            "task_type": "invalid",
            "analyzers": ["branch_path"],
        })
        assert res.status_code == 422

    def test_041_create_task_file_type(self, client, create_repo):
        """TC-041: File-level analysis task."""
        proj, repo = create_repo()
        res = client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"],
            "repo_id": repo["repo_id"],
            "task_type": "file",
            "analyzers": ["branch_path"],
            "target": {"path": "src/main.c"},
        })
        assert res.status_code == 201

    def test_042_create_task_function_type(self, client, create_repo):
        """TC-042: Function-level analysis task."""
        proj, repo = create_repo()
        res = client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"],
            "repo_id": repo["repo_id"],
            "task_type": "function",
            "analyzers": ["branch_path"],
            "target": {"path": "src/main.c", "functions": ["main", "init"]},
        })
        assert res.status_code == 201

    def test_043_create_task_diff_requires_commits(self, client, create_repo):
        """TC-043: Diff task without commits is rejected."""
        proj, repo = create_repo()
        res = client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"],
            "repo_id": repo["repo_id"],
            "task_type": "diff",
            "analyzers": ["branch_path"],
        })
        assert res.status_code == 422

    def test_044_create_task_diff_with_commits(self, client, create_repo):
        """TC-044: Diff task with both commits succeeds."""
        proj, repo = create_repo()
        res = client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"],
            "repo_id": repo["repo_id"],
            "task_type": "diff",
            "analyzers": ["branch_path"],
            "revision": {"base_commit": "abc123", "head_commit": "def456"},
        })
        assert res.status_code == 201

    def test_045_create_task_idempotency(self, client, create_repo):
        """TC-045: Same idempotency key returns same task."""
        proj, repo = create_repo()
        payload = {
            "project_id": proj["project_id"],
            "repo_id": repo["repo_id"],
            "task_type": "full",
            "analyzers": ["branch_path"],
            "idempotency_key": "unique-key-123",
        }
        r1 = client.post("/api/v1/analysis/tasks", json=payload)
        r2 = client.post("/api/v1/analysis/tasks", json=payload)
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["data"]["task_id"] == r2.json()["data"]["task_id"]

    def test_046_create_task_missing_project_id(self, client, create_repo):
        """TC-046: Missing project_id is rejected."""
        _, repo = create_repo()
        res = client.post("/api/v1/analysis/tasks", json={
            "repo_id": repo["repo_id"],
            "task_type": "full",
            "analyzers": ["branch_path"],
        })
        assert res.status_code == 422

    def test_047_create_task_missing_repo_id(self, client, create_repo):
        """TC-047: Missing repo_id is rejected."""
        proj, _ = create_repo()
        res = client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"],
            "task_type": "full",
            "analyzers": ["branch_path"],
        })
        assert res.status_code == 422

    def test_048_create_task_default_options(self, client, create_repo):
        """TC-048: Default AI and options are applied."""
        proj, repo = create_repo()
        res = client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"],
            "repo_id": repo["repo_id"],
            "task_type": "full",
            "analyzers": ["branch_path"],
        })
        assert res.status_code == 201

    def test_049_create_task_custom_ai_config(self, client, create_repo):
        """TC-049: Custom AI configuration."""
        proj, repo = create_repo()
        res = client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"],
            "repo_id": repo["repo_id"],
            "task_type": "full",
            "analyzers": ["branch_path"],
            "ai": {"provider": "deepseek", "model": "deepseek-coder", "prompt_profile": "default-v1"},
        })
        assert res.status_code == 201


class TestTaskStatus:
    def test_050_get_task_status(self, client, create_task):
        """TC-050: Get task status after creation."""
        _, _, task = create_task()
        res = client.get(f"/api/v1/analysis/tasks/{task['task_id']}")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "task_id" in data
        assert "status" in data
        assert "progress" in data
        assert "module_status" in data

    def test_051_get_task_status_not_found(self, client):
        """TC-051: Task status for nonexistent task."""
        res = client.get("/api/v1/analysis/tasks/nonexistent-task-id")
        assert res.status_code == 404

    def test_052_task_progress_fields(self, client, create_task):
        """TC-052: Progress has correct structure."""
        _, _, task = create_task()
        res = client.get(f"/api/v1/analysis/tasks/{task['task_id']}")
        progress = res.json()["data"]["progress"]
        assert "total_modules" in progress
        assert "finished_modules" in progress
        assert "failed_modules" in progress


class TestTaskResults:
    def test_053_get_task_results(self, client, create_task):
        """TC-053: Get task analysis results."""
        _, _, task = create_task()
        res = client.get(f"/api/v1/analysis/tasks/{task['task_id']}/results")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "task_id" in data
        assert "modules" in data
        assert isinstance(data["modules"], list)

    def test_054_task_results_not_found(self, client):
        """TC-054: Results for nonexistent task."""
        res = client.get("/api/v1/analysis/tasks/no-such-task/results")
        assert res.status_code == 404

    def test_055_task_results_module_summary(self, client, create_task):
        """TC-055: Module result summaries have correct fields."""
        _, _, task = create_task()
        res = client.get(f"/api/v1/analysis/tasks/{task['task_id']}/results")
        modules = res.json()["data"]["modules"]
        if modules:
            mod = modules[0]
            assert "module" in mod
            assert "status" in mod
            assert "finding_count" in mod


class TestTaskRetryCancel:
    def test_056_cancel_pending_task(self, client, create_task):
        """TC-056: Cancel works only for cancellable statuses."""
        _, _, task = create_task()
        res = client.post(f"/api/v1/analysis/tasks/{task['task_id']}/cancel", json={})
        # May succeed or fail depending on task already finished
        assert res.status_code in (200, 202, 409)

    def test_057_cancel_nonexistent_task(self, client):
        """TC-057: Cancel nonexistent task returns 404."""
        res = client.post("/api/v1/analysis/tasks/no-such-task/cancel", json={})
        assert res.status_code == 404

    def test_058_retry_task(self, client, create_task):
        """TC-058: Retry a task (may succeed or fail depending on state)."""
        _, _, task = create_task()
        res = client.post(f"/api/v1/analysis/tasks/{task['task_id']}/retry", json={"modules": []})
        assert res.status_code in (200, 202, 409)

    def test_059_retry_nonexistent_task(self, client):
        """TC-059: Retry nonexistent task returns 404."""
        res = client.post("/api/v1/analysis/tasks/no-such-task/retry", json={})
        assert res.status_code == 404

    def test_059a_generate_sfmea(self, client, create_task):
        """POST /analysis/tasks/{task_id}/sfmea returns 200 and generated count."""
        _, _, task = create_task()
        res = client.post(f"/api/v1/analysis/tasks/{task['task_id']}/sfmea", json={})
        assert res.status_code == 200
        data = res.json()
        assert "data" in data
        assert "generated" in data["data"]

    def test_059b_generate_sfmea_not_found(self, client):
        """POST sfmea for nonexistent task returns 404."""
        res = client.post("/api/v1/analysis/tasks/no-such-task/sfmea", json={})
        assert res.status_code == 404


class TestTaskExport:
    def test_060_export_json(self, client, create_task):
        """TC-060: Export task results as JSON."""
        _, _, task = create_task()
        res = client.get(f"/api/v1/analysis/tasks/{task['task_id']}/export?fmt=json")
        assert res.status_code == 200
        assert "application/json" in res.headers.get("content-type", "")

    def test_061_export_csv(self, client, create_task):
        """TC-061: Export task results as CSV."""
        _, _, task = create_task()
        res = client.get(f"/api/v1/analysis/tasks/{task['task_id']}/export?fmt=csv")
        assert res.status_code == 200
        assert "text/csv" in res.headers.get("content-type", "")

    def test_062_export_findings(self, client, create_task):
        """TC-062: Export raw findings JSON."""
        _, _, task = create_task()
        res = client.get(f"/api/v1/analysis/tasks/{task['task_id']}/export?fmt=findings")
        assert res.status_code == 200

    def test_062a_export_critical(self, client, create_task):
        """Export only critical combinations (JSON)."""
        _, _, task = create_task()
        res = client.get(f"/api/v1/analysis/tasks/{task['task_id']}/export?fmt=critical")
        assert res.status_code == 200
        assert "application/json" in res.headers.get("content-type", "")
        data = res.json()
        assert "critical_combinations" in data
        assert "export_format" in data

    def test_062a2_export_html(self, client, create_task):
        """Export single-page HTML report."""
        _, _, task = create_task()
        res = client.get(f"/api/v1/analysis/tasks/{task['task_id']}/export?fmt=html")
        assert res.status_code == 200
        assert "text/html" in res.headers.get("content-type", "")
        assert b"GrayScope" in res.content or "GrayScope" in res.text

    def test_062a3_export_sfmea(self, client, create_task):
        """Export SFMEA entries as CSV."""
        _, _, task = create_task()
        res = client.get(f"/api/v1/analysis/tasks/{task['task_id']}/export?fmt=sfmea")
        assert res.status_code == 200
        assert "text/csv" in res.headers.get("content-type", "")
        assert b"failure_mode" in res.content or "failure_mode" in res.text

    def test_062b_coverage_import_summary(self, client, create_task):
        """北向接口：POST 写入 summary 格式覆盖率."""
        _, _, task = create_task()
        res = client.post(
            f"/api/v1/analysis/tasks/{task['task_id']}/coverage",
            json={
                "source_system": "test_platform",
                "revision": "abc123",
                "format": "summary",
                "files": {
                    "src/storage/volume.c": {
                        "lines_total": 100,
                        "lines_hit": 65,
                        "branches_total": 20,
                        "branches_hit": 12,
                        "functions": {"open_volume": True, "close_volume": False},
                    }
                },
            },
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["import_id"] >= 1
        assert data["task_id"] == task["task_id"]
        assert data["format"] == "summary"
        assert data["source_system"] == "test_platform"

    def test_062c_coverage_import_granular(self, client, create_task):
        """北向接口：POST 写入 granular 格式覆盖率."""
        _, _, task = create_task()
        res = client.post(
            f"/api/v1/analysis/tasks/{task['task_id']}/coverage",
            json={
                "format": "granular",
                "covered": [
                    {"file": "src/foo.c", "symbol": "bar", "line": 10, "branch_id": "b0"}
                ],
            },
        )
        assert res.status_code == 200
        assert res.json()["data"]["format"] == "granular"

    def test_062d_coverage_get_no_import(self, client, create_task):
        """北向接口：GET 无导入时返回 has_data false."""
        _, _, task = create_task()
        res = client.get(f"/api/v1/analysis/tasks/{task['task_id']}/coverage")
        assert res.status_code == 200
        assert res.json()["data"]["has_data"] is False
        assert res.json()["data"]["latest"] is None

    def test_062e_coverage_get_after_import(self, client, create_task):
        """北向接口：GET 导入后有 latest 元数据."""
        _, _, task = create_task()
        client.post(
            f"/api/v1/analysis/tasks/{task['task_id']}/coverage",
            json={"format": "summary", "files": {"a.c": {"lines_total": 1, "lines_hit": 1}}},
        )
        res = client.get(f"/api/v1/analysis/tasks/{task['task_id']}/coverage")
        assert res.status_code == 200
        assert res.json()["data"]["has_data"] is True
        assert res.json()["data"]["latest"]["format"] == "summary"

    def test_062f_coverage_import_task_not_found(self, client):
        """北向接口：POST 任务不存在返回 404."""
        res = client.post(
            "/api/v1/analysis/tasks/nonexistent-uuid/coverage",
            json={"format": "summary", "files": {}},
        )
        assert res.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# 5. AGGREGATION ENDPOINTS (22 cases)
# ═══════════════════════════════════════════════════════════════════

class TestProjectSummary:
    def test_063_project_summary_empty(self, client, create_project):
        """TC-063: Summary for project with no tasks."""
        proj = create_project()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/summary")
        assert res.status_code == 200

    def test_064_project_summary_with_task(self, client, create_task):
        """TC-064: Summary for project with a completed task."""
        proj, _, _ = create_task()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/summary")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "task_count" in data
        assert "finding_count" in data
        assert "modules" in data
        assert "recent_tasks" in data
        assert "trends" in data

    def test_065_project_summary_nonexistent(self, client):
        """TC-065: Summary for nonexistent project returns empty data."""
        res = client.get("/api/v1/projects/99999/summary")
        assert res.status_code == 200
        assert res.json()["data"] == {}


class TestProjectFindings:
    def test_066_project_findings_empty(self, client, create_project):
        """TC-066: Findings for project with no tasks."""
        proj = create_project()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/findings")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["findings"] == []
        assert data["total"] == 0

    def test_067_project_findings_with_task(self, client, create_task):
        """TC-067: Findings for project with completed task."""
        proj, _, _ = create_task()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/findings")
        assert res.status_code == 200
        assert "findings" in res.json()["data"]

    def test_068_project_findings_filter_severity(self, client, create_task):
        """TC-068: Filter findings by severity."""
        proj, _, _ = create_task()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/findings?severity=S0")
        assert res.status_code == 200

    def test_069_project_findings_filter_module(self, client, create_task):
        """TC-069: Filter findings by module."""
        proj, _, _ = create_task()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/findings?module_id=branch_path")
        assert res.status_code == 200


class TestProjectTasks:
    def test_070_project_tasks_empty(self, client, create_project):
        """TC-070: Tasks list for project with no tasks."""
        proj = create_project()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/tasks")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["tasks"] == []
        assert data["total"] == 0

    def test_071_project_tasks_with_task(self, client, create_task):
        """TC-071: Tasks list for project with a completed task."""
        proj, _, _ = create_task()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/tasks")
        data = res.json()["data"]
        assert data["total"] >= 1
        assert len(data["tasks"]) >= 1

    def test_072_project_tasks_filter_status(self, client, create_task):
        """TC-072: Filter tasks by status."""
        proj, _, _ = create_task()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/tasks?status=success")
        assert res.status_code == 200

    def test_073_project_tasks_item_structure(self, client, create_task):
        """TC-073: Task item has correct structure."""
        proj, _, _ = create_task()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/tasks")
        tasks = res.json()["data"]["tasks"]
        if tasks:
            t = tasks[0]
            assert "task_id" in t
            assert "status" in t
            assert "progress" in t


class TestProjectMeasures:
    def test_074_project_measures_empty(self, client, create_project):
        """TC-074: Measures for project with no tasks."""
        proj = create_project()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/measures")
        assert res.status_code == 200

    def test_075_project_measures_with_task(self, client, create_task):
        """TC-075: Measures for project with completed task."""
        proj, _, _ = create_task()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/measures")
        assert res.status_code == 200
        assert "files" in res.json()["data"]


class TestProjectFileTree:
    def test_076_project_file_tree_empty(self, client, create_project):
        """TC-076: File tree for project with no tasks."""
        proj = create_project()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/file-tree")
        assert res.status_code == 200
        assert "files" in res.json()["data"]

    def test_077_project_file_tree_with_task(self, client, create_task):
        """TC-077: File tree for project with completed task."""
        proj, _, _ = create_task()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/file-tree")
        assert res.status_code == 200


class TestProjectSource:
    def test_078_project_source_file(self, client, create_task):
        """TC-078: Get source file content."""
        proj, _, _ = create_task()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/source?path=test_samples/storage_module.c")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "content" in data
        assert "findings" in data
        assert "path" in data

    def test_079_project_source_missing_path(self, client, create_project):
        """TC-079: Source endpoint without path parameter."""
        proj = create_project()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/source")
        assert res.status_code == 422

    def test_080_project_source_nonexistent_file(self, client, create_task):
        """TC-080: Source for nonexistent file returns fallback message."""
        proj, _, _ = create_task()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/source?path=no/such/file.c")
        assert res.status_code == 200
        assert "未找到" in res.json()["data"]["content"]


# ═══════════════════════════════════════════════════════════════════
# 6. GLOBAL ENDPOINTS (14 cases)
# ═══════════════════════════════════════════════════════════════════

class TestGlobalFindings:
    def test_081_global_findings_empty(self, client):
        """TC-081: Global findings when no tasks exist."""
        res = client.get("/api/v1/findings")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "findings" in data
        assert "total" in data

    def test_082_global_findings_with_task(self, client, create_task):
        """TC-082: Global findings with a completed task."""
        create_task()
        res = client.get("/api/v1/findings")
        assert res.status_code == 200

    def test_083_global_findings_filter_project(self, client, create_task):
        """TC-083: Filter global findings by project_id."""
        proj, _, _ = create_task()
        res = client.get(f"/api/v1/findings?project_id={proj['project_id']}")
        assert res.status_code == 200

    def test_084_global_findings_pagination(self, client, create_task):
        """TC-084: Paginate global findings."""
        create_task()
        res = client.get("/api/v1/findings?page=1&page_size=5")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "page" in data
        assert "page_size" in data


class TestGlobalTasks:
    def test_085_global_tasks_empty(self, client):
        """TC-085: Global task list when empty."""
        res = client.get("/api/v1/analysis/tasks")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "tasks" in data
        assert "total" in data

    def test_086_global_tasks_with_data(self, client, create_task):
        """TC-086: Global task list with data."""
        create_task()
        res = client.get("/api/v1/analysis/tasks")
        data = res.json()["data"]
        assert data["total"] >= 1

    def test_087_global_tasks_filter_project(self, client, create_task):
        """TC-087: Filter global tasks by project."""
        proj, _, _ = create_task()
        res = client.get(f"/api/v1/analysis/tasks?project_id={proj['project_id']}")
        assert res.status_code == 200

    def test_088_global_tasks_pagination(self, client, create_task):
        """TC-088: Paginate global tasks."""
        create_task()
        res = client.get("/api/v1/analysis/tasks?page=1&page_size=5")
        data = res.json()["data"]
        assert data["page"] == 1
        assert data["page_size"] == 5


class TestGlobalTestCases:
    def test_089_global_test_cases_empty(self, client):
        """TC-089: Global test cases when empty."""
        res = client.get("/api/v1/test-cases")
        assert res.status_code == 200

    def test_090_global_test_cases_with_data(self, client, create_task):
        """TC-090: Global test cases with analysis data."""
        create_task()
        res = client.get("/api/v1/test-cases")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "test_cases" in data
        assert "total" in data

    def test_091_project_test_cases(self, client, create_task):
        """TC-091: Project-level test cases."""
        proj, _, _ = create_task()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/test-cases")
        assert res.status_code == 200


class TestFindingTestSuggestion:
    def test_092_test_suggestion_not_found(self, client):
        """TC-092: Test suggestion for nonexistent finding."""
        res = client.get("/api/v1/findings/nonexistent-id/test-suggestion")
        assert res.status_code == 200
        assert res.json()["data"]["suggestion"] is None


class TestTestCaseGenerate:
    def test_093_generate_test_cases(self, client, create_task):
        """TC-093: Generate test cases for a project."""
        proj, _, _ = create_task()
        res = client.post(f"/api/v1/projects/{proj['project_id']}/test-cases/generate")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "generated" in data
        assert "tasks_processed" in data


# ═══════════════════════════════════════════════════════════════════
# 7. SETTINGS & MODELS (6 cases)
# ═══════════════════════════════════════════════════════════════════

class TestSettings:
    def test_094_get_settings(self, client):
        """TC-094: Get system settings."""
        res = client.get("/api/v1/settings")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "quality_gate" in data
        assert "system" in data

    def test_095_update_settings(self, client):
        """TC-095: Update settings (placeholder)."""
        res = client.put("/api/v1/settings", json={})
        assert res.status_code == 200

    def test_096_settings_quality_gate_fields(self, client):
        """TC-096: Quality gate settings have correct fields."""
        res = client.get("/api/v1/settings")
        qg = res.json()["data"]["quality_gate"]
        assert "max_risk_score" in qg
        assert "max_s0_count" in qg
        assert "max_s1_count" in qg


class TestModels:
    def test_097_list_models(self, client):
        """TC-097: List available AI models."""
        res = client.get("/api/v1/models")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "providers" in data

    def test_098_test_model_invalid_provider(self, client):
        """TC-098: Test model with invalid provider."""
        res = client.post("/api/v1/models/test", json={"provider": "nonexistent", "model": "test"})
        assert res.status_code in (200, 422, 503)


# ═══════════════════════════════════════════════════════════════════
# 8. POSTMORTEM & KNOWLEDGE (6 cases)
# ═══════════════════════════════════════════════════════════════════

class TestPostmortem:
    def test_099_create_postmortem(self, client, create_repo):
        """TC-099: Create postmortem analysis."""
        proj, repo = create_repo()
        res = client.post("/api/v1/postmortem", json={
            "project_id": proj["project_id"],
            "repo_id": repo["repo_id"],
            "defect": {"title": "Memory leak in pool_insert", "severity": "S1"},
        })
        assert res.status_code == 201

    def test_100_create_postmortem_missing_title(self, client, create_repo):
        """TC-100: Postmortem without defect title is rejected."""
        proj, repo = create_repo()
        res = client.post("/api/v1/postmortem", json={
            "project_id": proj["project_id"],
            "repo_id": repo["repo_id"],
            "defect": {"severity": "S1"},
        })
        assert res.status_code == 422


class TestKnowledge:
    def test_101_search_patterns_empty(self, client, create_project):
        """TC-101: Search patterns when none exist."""
        proj = create_project()
        res = client.get(f"/api/v1/knowledge/patterns?project_id={proj['project_id']}")
        assert res.status_code == 200

    def test_102_match_knowledge_empty(self, client, create_task):
        """TC-102: Match knowledge when no patterns exist."""
        proj, _, task = create_task()
        res = client.post(
            f"/api/v1/knowledge/match?project_id={proj['project_id']}&task_id={task['task_id']}"
        )
        assert res.status_code == 200


# ═══════════════════════════════════════════════════════════════════
# 9. RESPONSE ENVELOPE (4 cases)
# ═══════════════════════════════════════════════════════════════════

class TestResponseEnvelope:
    def test_103_success_envelope(self, client):
        """TC-103: Successful responses have standard envelope."""
        res = client.get("/api/v1/health")
        body = res.json()
        assert body["code"] == "OK"
        assert body["message"] == "success"
        assert "data" in body

    def test_104_error_envelope(self, client):
        """TC-104: Error responses have standard envelope."""
        res = client.get("/api/v1/projects/99999")
        body = res.json()
        assert body["code"] != "OK"
        assert "message" in body

    def test_105_create_envelope(self, client):
        """TC-105: Creation responses have standard envelope."""
        res = client.post("/api/v1/projects", json={"name": "env-test"})
        body = res.json()
        assert body["code"] == "OK"
        assert "data" in body

    def test_106_data_unwrap_contract(self, client, create_project):
        """TC-106: Frontend api.js unwraps data correctly (data.data -> actual payload)."""
        create_project()
        res = client.get("/api/v1/projects")
        body = res.json()
        # Frontend does: data.data !== undefined ? data.data : data
        # So body.data should be the actual payload
        assert body["data"] is not None
        assert "items" in body["data"]


# ═══════════════════════════════════════════════════════════════════
# 10. EDGE CASES & ROBUSTNESS (10 cases)
# ═══════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_107_invalid_json_body(self, client):
        """TC-107: Invalid JSON body returns error."""
        res = client.post("/api/v1/projects", content="not json", headers={"Content-Type": "application/json"})
        assert res.status_code == 422

    def test_108_extra_fields_ignored(self, client):
        """TC-108: Extra fields in request body are ignored."""
        res = client.post("/api/v1/projects", json={"name": "extra-test", "extra_field": "ignored"})
        assert res.status_code == 201

    def test_109_concurrent_project_creation(self, client):
        """TC-109: Create multiple projects rapidly."""
        results = []
        for i in range(5):
            r = client.post("/api/v1/projects", json={"name": f"rapid-{i}"})
            results.append(r.status_code)
        assert all(s == 201 for s in results)

    def test_110_large_description(self, client):
        """TC-110: Description at max boundary (512 chars)."""
        res = client.post("/api/v1/projects", json={"name": "big-desc", "description": "a" * 512})
        assert res.status_code == 201

    def test_111_special_characters_in_name(self, client):
        """TC-111: Special characters in project name."""
        res = client.post("/api/v1/projects", json={"name": "test_proj-v2.1"})
        assert res.status_code == 201
        assert res.json()["data"]["name"] == "test_proj-v2.1"

    def test_112_pagination_beyond_total(self, client, create_project):
        """TC-112: Requesting page beyond total pages returns empty."""
        create_project()
        res = client.get("/api/v1/projects?page=100&page_size=20")
        assert res.status_code == 200
        assert len(res.json()["data"]["items"]) == 0

    def test_113_pagination_invalid_page(self, client):
        """TC-113: Page=0 is rejected (ge=1)."""
        res = client.get("/api/v1/projects?page=0")
        assert res.status_code == 422

    def test_114_pagination_negative_page_size(self, client):
        """TC-114: Negative page_size is rejected."""
        res = client.get("/api/v1/projects?page_size=-1")
        assert res.status_code == 422

    def test_115_pagination_oversized_page(self, client):
        """TC-115: page_size > 100 is rejected for projects."""
        res = client.get("/api/v1/projects?page_size=101")
        assert res.status_code == 422

    def test_116_nonexistent_endpoint(self, client):
        """TC-116: Nonexistent endpoint returns 404/405."""
        res = client.get("/api/v1/nonexistent")
        assert res.status_code in (404, 405)


# ═══════════════════════════════════════════════════════════════════
# 11. TEST CASE STATUS MANAGEMENT (4 cases)
# ═══════════════════════════════════════════════════════════════════

class TestTestCaseStatus:
    def test_117_update_test_case_status_not_found(self, client):
        """TC-117: Update status for nonexistent test case."""
        res = client.put("/api/v1/test-cases/99999/status?status=adopted")
        assert res.status_code == 200  # Returns ok with error field

    def test_118_update_test_case_valid_statuses(self, client):
        """TC-118: Valid status values are accepted by endpoint."""
        for status in ["pending", "adopted", "ignored", "executed"]:
            res = client.put(f"/api/v1/test-cases/99999/status?status={status}")
            assert res.status_code == 200


# ═══════════════════════════════════════════════════════════════════
# 12. FRONTEND CONTRACT TESTS (8 cases)
# ═══════════════════════════════════════════════════════════════════

class TestFrontendContract:
    """Tests that verify the backend API matches what the frontend expects."""

    def test_119_project_list_has_items_key(self, client, create_project):
        """TC-119: Frontend store uses data.items to parse projects."""
        create_project()
        res = client.get("/api/v1/projects")
        assert "items" in res.json()["data"]

    def test_120_project_item_has_project_id_not_id(self, client, create_project):
        """TC-120: Frontend uses p.project_id for option values."""
        create_project()
        items = client.get("/api/v1/projects").json()["data"]["items"]
        assert "project_id" in items[0]

    def test_121_repo_list_is_array(self, client, create_repo):
        """TC-121: Frontend expects repos as direct array."""
        proj, _ = create_repo()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/repos")
        data = res.json()["data"]
        assert isinstance(data, list)

    def test_122_repo_item_has_repo_id(self, client, create_repo):
        """TC-122: Frontend uses r.repo_id for option values."""
        proj, _ = create_repo()
        repos = client.get(f"/api/v1/projects/{proj['project_id']}/repos").json()["data"]
        assert "repo_id" in repos[0]

    def test_123_repo_item_has_git_url(self, client, create_repo):
        """TC-123: Frontend displays r.git_url as label fallback."""
        proj, _ = create_repo()
        repos = client.get(f"/api/v1/projects/{proj['project_id']}/repos").json()["data"]
        assert "git_url" in repos[0]

    def test_124_task_status_has_module_status(self, client, create_task):
        """TC-124: Frontend reads module_status dict from task."""
        _, _, task = create_task()
        res = client.get(f"/api/v1/analysis/tasks/{task['task_id']}")
        assert "module_status" in res.json()["data"]

    def test_125_summary_has_modules_array(self, client, create_task):
        """TC-125: Frontend reads modules array from summary."""
        proj, _, _ = create_task()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/summary")
        data = res.json()["data"]
        if data:
            assert "modules" in data

    def test_126_findings_response_has_total(self, client, create_task):
        """TC-126: Frontend reads total for pagination."""
        proj, _, _ = create_task()
        res = client.get(f"/api/v1/projects/{proj['project_id']}/findings")
        assert "total" in res.json()["data"]
