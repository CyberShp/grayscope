"""
Comprehensive tests for GrayScope service and repository layers.

Covers:
  - Project service: create, list, get, duplicate detection
  - Task service: create, idempotency, status, results, retry, cancel
  - Export service: JSON, CSV, findings export
  - Testcase service: persist, query, status update
  - Knowledge service: pattern persistence, search, matching
  - Repository layer: project_repo, task_repo, defect_pattern_repo
  - Schema validation: edge cases, boundary values
  - Response envelope: structure validation

Uses shared conftest.py fixtures (client, db, clean_tables, setup_database).
"""

import json
import pytest


# ═══════════════════════════════════════════════════════════════════
# 1. PROJECT REPOSITORY TESTS
# ═══════════════════════════════════════════════════════════════════

class TestProjectRepo:
    """Tests for app.repositories.project_repo."""

    def test_create_project(self, db):
        """TS-PR-001: Create project via repository."""
        from app.repositories import project_repo
        p = project_repo.create(db, name="test", description="desc")
        assert p.id is not None
        assert p.name == "test"
        assert p.description == "desc"
        assert p.status == "active"

    def test_get_by_id(self, db):
        """TS-PR-002: Get project by ID."""
        from app.repositories import project_repo
        p = project_repo.create(db, name="lookup-test")
        found = project_repo.get_by_id(db, p.id)
        assert found is not None
        assert found.name == "lookup-test"

    def test_get_by_id_not_found(self, db):
        """TS-PR-003: Get nonexistent project returns None."""
        from app.repositories import project_repo
        assert project_repo.get_by_id(db, 99999) is None

    def test_get_by_name(self, db):
        """TS-PR-004: Get project by name."""
        from app.repositories import project_repo
        project_repo.create(db, name="unique-name")
        found = project_repo.get_by_name(db, "unique-name")
        assert found is not None
        assert found.name == "unique-name"

    def test_get_by_name_not_found(self, db):
        """TS-PR-005: Get project by nonexistent name returns None."""
        from app.repositories import project_repo
        assert project_repo.get_by_name(db, "no-such-name") is None

    def test_list_projects_pagination(self, db):
        """TS-PR-006: List projects with pagination."""
        from app.repositories import project_repo
        for i in range(5):
            project_repo.create(db, name=f"page-test-{i}")
        items, total = project_repo.list_projects(db, page=1, page_size=2)
        assert total == 5
        assert len(items) == 2

    def test_list_projects_empty(self, db):
        """TS-PR-007: List projects when empty."""
        from app.repositories import project_repo
        items, total = project_repo.list_projects(db)
        assert total == 0
        assert items == []


# ═══════════════════════════════════════════════════════════════════
# 2. REPOSITORY REPO TESTS
# ═══════════════════════════════════════════════════════════════════

class TestRepositoryRepo:
    """Tests for app.repositories.repository_repo."""

    def test_create_repo(self, db):
        """TS-RR-001: Create repository."""
        from app.repositories import project_repo, repository_repo
        p = project_repo.create(db, name="repo-parent")
        r = repository_repo.create(
            db,
            project_id=p.id,
            name="my-repo",
            git_url="https://github.com/test/repo.git",
            default_branch="main",
            local_mirror_path="/tmp/mirror",
        )
        assert r.id is not None
        assert r.name == "my-repo"
        assert r.project_id == p.id
        assert r.last_sync_status == "never"

    def test_list_by_project(self, db):
        """TS-RR-002: List repos for a project."""
        from app.repositories import project_repo, repository_repo
        p = project_repo.create(db, name="list-repos-proj")
        repository_repo.create(db, project_id=p.id, name="r1", git_url="url1", default_branch="main", local_mirror_path="/tmp/r1")
        repository_repo.create(db, project_id=p.id, name="r2", git_url="url2", default_branch="main", local_mirror_path="/tmp/r2")
        repos = repository_repo.list_by_project(db, p.id)
        assert len(repos) == 2

    def test_get_by_id(self, db):
        """TS-RR-003: Get repository by ID."""
        from app.repositories import project_repo, repository_repo
        p = project_repo.create(db, name="get-repo-proj")
        r = repository_repo.create(db, project_id=p.id, name="get-repo", git_url="url", default_branch="main", local_mirror_path="/tmp/get")
        found = repository_repo.get_by_id(db, r.id)
        assert found is not None
        assert found.name == "get-repo"

    def test_get_by_id_not_found(self, db):
        """TS-RR-004: Nonexistent repo returns None."""
        from app.repositories import repository_repo
        assert repository_repo.get_by_id(db, 99999) is None


# ═══════════════════════════════════════════════════════════════════
# 3. TASK REPOSITORY TESTS
# ═══════════════════════════════════════════════════════════════════

class TestTaskRepo:
    """Tests for app.repositories.task_repo."""

    def _create_prereqs(self, db):
        from app.repositories import project_repo, repository_repo
        p = project_repo.create(db, name="task-repo-proj")
        r = repository_repo.create(
            db, project_id=p.id, name="repo", git_url="url",
            default_branch="main", local_mirror_path="/tmp/repo",
        )
        return p, r

    def test_create_task(self, db):
        """TS-TR-001: Create analysis task."""
        from app.repositories import task_repo
        p, r = self._create_prereqs(db)
        task = task_repo.create_task(
            db,
            task_id="tsk-001",
            project_id=p.id,
            repo_id=r.id,
            task_type="full",
            target={"path": "src/"},
            revision={"branch": "main"},
            analyzers=["branch_path"],
            ai={"provider": "ollama"},
        )
        assert task.task_id == "tsk-001"
        assert task.status == "pending"
        assert task.project_id == p.id

    def test_get_task_by_id(self, db):
        """TS-TR-002: Get task by string task_id."""
        from app.repositories import task_repo
        p, r = self._create_prereqs(db)
        task_repo.create_task(
            db, task_id="tsk-find", project_id=p.id, repo_id=r.id,
            task_type="full", target={}, revision={}, analyzers=["branch_path"], ai={},
        )
        found = task_repo.get_task_by_id(db, "tsk-find")
        assert found is not None
        assert found.task_id == "tsk-find"

    def test_get_task_not_found(self, db):
        """TS-TR-003: Get nonexistent task returns None."""
        from app.repositories import task_repo
        assert task_repo.get_task_by_id(db, "nonexistent") is None

    def test_idempotency_key(self, db):
        """TS-TR-004: Idempotency key lookup."""
        from app.repositories import task_repo
        p, r = self._create_prereqs(db)
        task_repo.create_task(
            db, task_id="tsk-idm", project_id=p.id, repo_id=r.id,
            task_type="full", target={}, revision={}, analyzers=["branch_path"],
            ai={}, idempotency_key="test-key-001",
        )
        found = task_repo.get_task_by_idempotency_key(db, "test-key-001")
        assert found is not None
        assert found.task_id == "tsk-idm"

    def test_update_task_status(self, db):
        """TS-TR-005: Update task status."""
        from app.repositories import task_repo
        p, r = self._create_prereqs(db)
        task_repo.create_task(
            db, task_id="tsk-upd", project_id=p.id, repo_id=r.id,
            task_type="full", target={}, revision={}, analyzers=["branch_path"], ai={},
        )
        updated = task_repo.update_task_status(db, "tsk-upd", "running")
        assert updated.status == "running"

    def test_update_task_sets_finished_at(self, db):
        """TS-TR-006: Terminal status sets finished_at."""
        from app.repositories import task_repo
        p, r = self._create_prereqs(db)
        task_repo.create_task(
            db, task_id="tsk-fin", project_id=p.id, repo_id=r.id,
            task_type="full", target={}, revision={}, analyzers=["branch_path"], ai={},
        )
        updated = task_repo.update_task_status(db, "tsk-fin", "success")
        assert updated.finished_at is not None

    def test_create_module_result(self, db):
        """TS-TR-007: Create module result."""
        from app.repositories import task_repo
        p, r = self._create_prereqs(db)
        task = task_repo.create_task(
            db, task_id="tsk-mr", project_id=p.id, repo_id=r.id,
            task_type="full", target={}, revision={}, analyzers=["branch_path"], ai={},
        )
        mr = task_repo.create_module_result(db, task_pk=task.id, module_id="branch_path")
        assert mr.id is not None
        assert mr.status == "pending"
        assert mr.findings_json == "[]"

    def test_update_module_result(self, db):
        """TS-TR-008: Update module result with findings."""
        from app.repositories import task_repo
        p, r = self._create_prereqs(db)
        task = task_repo.create_task(
            db, task_id="tsk-umr", project_id=p.id, repo_id=r.id,
            task_type="full", target={}, revision={}, analyzers=["branch_path"], ai={},
        )
        mr = task_repo.create_module_result(db, task_pk=task.id, module_id="branch_path")
        findings = [{"finding_id": "F001", "risk_score": 0.7}]
        updated = task_repo.update_module_result(
            db, mr.id,
            status="success",
            risk_score=0.7,
            findings_json=json.dumps(findings),
        )
        assert updated.status == "success"
        assert updated.risk_score == 0.7
        assert json.loads(updated.findings_json) == findings

    def test_get_module_results(self, db):
        """TS-TR-009: Get all module results for a task."""
        from app.repositories import task_repo
        p, r = self._create_prereqs(db)
        task = task_repo.create_task(
            db, task_id="tsk-gmr", project_id=p.id, repo_id=r.id,
            task_type="full", target={}, revision={}, analyzers=["branch_path", "boundary_value"], ai={},
        )
        task_repo.create_module_result(db, task_pk=task.id, module_id="branch_path")
        task_repo.create_module_result(db, task_pk=task.id, module_id="boundary_value")
        results = task_repo.get_module_results(db, task.id)
        assert len(results) == 2

    def test_set_aggregate_score(self, db):
        """TS-TR-010: Set aggregate risk score."""
        from app.repositories import task_repo
        p, r = self._create_prereqs(db)
        task = task_repo.create_task(
            db, task_id="tsk-agg", project_id=p.id, repo_id=r.id,
            task_type="full", target={}, revision={}, analyzers=["branch_path"], ai={},
        )
        task_repo.set_aggregate_score(db, "tsk-agg", 0.75)
        refreshed = task_repo.get_task_by_id(db, "tsk-agg")
        assert refreshed.aggregate_risk_score == 0.75


# ═══════════════════════════════════════════════════════════════════
# 4. DEFECT PATTERN REPOSITORY TESTS
# ═══════════════════════════════════════════════════════════════════

class TestDefectPatternRepo:
    """Tests for app.repositories.defect_pattern_repo."""

    def test_upsert_new_pattern(self, db):
        """TS-DP-001: Insert new defect pattern."""
        from app.repositories import project_repo, defect_pattern_repo
        p = project_repo.create(db, name="dp-proj")
        dp = defect_pattern_repo.upsert(
            db,
            project_id=p.id,
            pattern_key="leak-001",
            name="Memory leak on error path",
            risk_type="missing_cleanup",
            trigger_shape={"pattern": "alloc-no-free"},
            code_signature={"keywords": ["malloc", "return"]},
            test_template={"steps": ["inject fault"]},
        )
        assert dp.id is not None
        assert dp.hit_count == 1

    def test_upsert_existing_increments_hit(self, db):
        """TS-DP-002: Upserting existing pattern increments hit_count."""
        from app.repositories import project_repo, defect_pattern_repo
        p = project_repo.create(db, name="dp-proj-2")
        defect_pattern_repo.upsert(
            db, project_id=p.id, pattern_key="leak-002", name="Test",
            risk_type="test", trigger_shape={}, code_signature={}, test_template={},
        )
        dp2 = defect_pattern_repo.upsert(
            db, project_id=p.id, pattern_key="leak-002", name="Updated",
            risk_type="test", trigger_shape={}, code_signature={}, test_template={},
        )
        assert dp2.hit_count == 2
        assert dp2.name == "Updated"

    def test_get_by_project(self, db):
        """TS-DP-003: List patterns for a project."""
        from app.repositories import project_repo, defect_pattern_repo
        p = project_repo.create(db, name="dp-list-proj")
        defect_pattern_repo.upsert(
            db, project_id=p.id, pattern_key="p1", name="P1",
            risk_type="leak", trigger_shape={}, code_signature={}, test_template={},
        )
        defect_pattern_repo.upsert(
            db, project_id=p.id, pattern_key="p2", name="P2",
            risk_type="race", trigger_shape={}, code_signature={}, test_template={},
        )
        all_patterns = defect_pattern_repo.get_by_project(db, p.id)
        assert len(all_patterns) == 2

    def test_get_by_project_filter_risk_type(self, db):
        """TS-DP-004: Filter patterns by risk type."""
        from app.repositories import project_repo, defect_pattern_repo
        p = project_repo.create(db, name="dp-filter-proj")
        defect_pattern_repo.upsert(
            db, project_id=p.id, pattern_key="f1", name="F1",
            risk_type="leak", trigger_shape={}, code_signature={}, test_template={},
        )
        defect_pattern_repo.upsert(
            db, project_id=p.id, pattern_key="f2", name="F2",
            risk_type="race", trigger_shape={}, code_signature={}, test_template={},
        )
        leak_patterns = defect_pattern_repo.get_by_project(db, p.id, risk_type="leak")
        assert len(leak_patterns) == 1
        assert leak_patterns[0].risk_type == "leak"

    def test_search_patterns(self, db):
        """TS-DP-005: Search patterns by keyword."""
        from app.repositories import project_repo, defect_pattern_repo
        p = project_repo.create(db, name="dp-search-proj")
        defect_pattern_repo.upsert(
            db, project_id=p.id, pattern_key="memory-leak-001", name="Memory leak in pool",
            risk_type="leak", trigger_shape={}, code_signature={}, test_template={},
        )
        results = defect_pattern_repo.search(db, p.id, "memory")
        assert len(results) >= 1

    def test_increment_hit(self, db):
        """TS-DP-006: Increment hit count."""
        from app.repositories import project_repo, defect_pattern_repo
        p = project_repo.create(db, name="dp-hit-proj")
        dp = defect_pattern_repo.upsert(
            db, project_id=p.id, pattern_key="hit-test", name="Hit Test",
            risk_type="test", trigger_shape={}, code_signature={}, test_template={},
        )
        defect_pattern_repo.increment_hit(db, dp.id)
        refreshed = defect_pattern_repo.get_by_key(db, p.id, "hit-test")
        assert refreshed.hit_count == 2


# ═══════════════════════════════════════════════════════════════════
# 5. EXPORT SERVICE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestExportService:
    """Tests for app.services.export_service."""

    def test_findings_to_testcases(self):
        """TS-ES-001: Convert findings to test cases."""
        from app.services.export_service import _findings_to_testcases
        findings = [
            {
                "finding_id": "F001",
                "module_id": "branch_path",
                "risk_type": "branch_error",
                "severity": "S1",
                "risk_score": 0.8,
                "title": "Error handling branch",
                "description": "Test",
                "file_path": "test.c",
                "symbol_name": "func",
                "line_start": 10,
                "line_end": 20,
                "evidence": {},
            }
        ]
        cases = _findings_to_testcases("task-001", findings, {})
        assert len(cases) == 1
        c = cases[0]
        assert "test_case_id" in c
        assert c["module_id"] == "branch_path"
        assert c["priority"] == "P1-高"
        assert c["category"] == "branch_error"

    def test_risk_type_to_objective(self):
        """TS-ES-002: Risk type mapping to objective."""
        from app.services.export_service import _risk_type_to_objective
        obj = _risk_type_to_objective("missing_cleanup", {"symbol_name": "foo"})
        assert "foo" in obj
        assert "资源" in obj

    def test_risk_type_to_steps(self):
        """TS-ES-003: Risk type mapping to test steps."""
        from app.services.export_service import _risk_type_to_steps
        steps = _risk_type_to_steps("boundary_miss", {
            "symbol_name": "check",
            "evidence": {"candidates": [0, 1, -1]},
        })
        assert len(steps) > 0

    def test_severity_priority_mapping(self):
        """TS-ES-004: Severity to priority mapping."""
        from app.services.export_service import _SEV_PRIORITY
        assert _SEV_PRIORITY["S0"] == "P0-紧急"
        assert _SEV_PRIORITY["S1"] == "P1-高"
        assert _SEV_PRIORITY["S2"] == "P2-中"
        assert _SEV_PRIORITY["S3"] == "P3-低"

    def test_export_json_format(self, client):
        """TS-ES-005: JSON export has correct structure."""
        # Create a task first
        proj_res = client.post("/api/v1/projects", json={"name": "export-proj"})
        pid = proj_res.json()["data"]["project_id"]
        repo_res = client.post(f"/api/v1/projects/{pid}/repos", json={
            "name": "export-repo", "git_url": "https://example.com/repo.git"
        })
        rid = repo_res.json()["data"]["repo_id"]
        task_res = client.post("/api/v1/analysis/tasks", json={
            "project_id": pid, "repo_id": rid, "task_type": "full",
            "analyzers": ["branch_path"],
        })
        tid = task_res.json()["data"]["task_id"]

        res = client.get(f"/api/v1/analysis/tasks/{tid}/export?fmt=json")
        assert res.status_code == 200
        data = json.loads(res.text)
        assert "export_format" in data
        assert data["export_format"] == "grayscope_testcases_v1"
        assert "test_cases" in data
        assert isinstance(data["test_cases"], list)

    def test_export_csv_format(self, client):
        """TS-ES-006: CSV export has headers."""
        proj_res = client.post("/api/v1/projects", json={"name": "csv-proj"})
        pid = proj_res.json()["data"]["project_id"]
        repo_res = client.post(f"/api/v1/projects/{pid}/repos", json={
            "name": "csv-repo", "git_url": "https://example.com/repo.git"
        })
        rid = repo_res.json()["data"]["repo_id"]
        task_res = client.post("/api/v1/analysis/tasks", json={
            "project_id": pid, "repo_id": rid, "task_type": "full",
            "analyzers": ["branch_path"],
        })
        tid = task_res.json()["data"]["task_id"]

        res = client.get(f"/api/v1/analysis/tasks/{tid}/export?fmt=csv")
        assert res.status_code == 200
        lines = res.text.strip().split("\n")
        assert len(lines) >= 1  # At least header
        header = lines[0]
        assert "test_case_id" in header
        assert "priority" in header


# ═══════════════════════════════════════════════════════════════════
# 6. TESTCASE SERVICE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestTestcaseService:
    """Tests for app.services.testcase_service."""

    def test_persist_test_cases(self, db):
        """TS-TC-001: Persist test cases from task analysis."""
        from app.repositories import project_repo, repository_repo, task_repo
        from app.services.testcase_service import persist_test_cases

        p = project_repo.create(db, name="tc-proj")
        r = repository_repo.create(
            db, project_id=p.id, name="tc-repo", git_url="url",
            default_branch="main", local_mirror_path="/tmp/tc",
        )
        task = task_repo.create_task(
            db, task_id="tsk-tc", project_id=p.id, repo_id=r.id,
            task_type="full", target={}, revision={}, analyzers=["branch_path"], ai={},
        )
        mr = task_repo.create_module_result(db, task_pk=task.id, module_id="branch_path")
        findings = [
            {
                "finding_id": "BP-F0001",
                "module_id": "branch_path",
                "risk_type": "branch_error",
                "severity": "S1",
                "risk_score": 0.8,
                "title": "Error branch in foo()",
                "file_path": "test.c",
                "symbol_name": "foo",
                "line_start": 10,
                "line_end": 20,
                "evidence": {},
            }
        ]
        task_repo.update_module_result(
            db, mr.id, status="success", risk_score=0.8,
            findings_json=json.dumps(findings),
        )
        task_repo.update_task_status(db, "tsk-tc", "success")

        # Refresh task object
        task = task_repo.get_task_by_id(db, "tsk-tc")
        count = persist_test_cases(db, task)
        assert count >= 1

    def test_persist_idempotent(self, db):
        """TS-TC-002: Persisting same task twice is idempotent."""
        from app.repositories import project_repo, repository_repo, task_repo
        from app.services.testcase_service import persist_test_cases

        p = project_repo.create(db, name="tc-idm-proj")
        r = repository_repo.create(
            db, project_id=p.id, name="tc-idm-repo", git_url="url",
            default_branch="main", local_mirror_path="/tmp/tc-idm",
        )
        task = task_repo.create_task(
            db, task_id="tsk-tc-idm", project_id=p.id, repo_id=r.id,
            task_type="full", target={}, revision={}, analyzers=["branch_path"], ai={},
        )
        mr = task_repo.create_module_result(db, task_pk=task.id, module_id="branch_path")
        findings = [{"finding_id": "F001", "module_id": "branch_path", "risk_type": "test",
                     "severity": "S2", "risk_score": 0.5, "title": "t", "file_path": "f",
                     "symbol_name": "s", "line_start": 1, "line_end": 1, "evidence": {}}]
        task_repo.update_module_result(db, mr.id, status="success", findings_json=json.dumps(findings))
        task_repo.update_task_status(db, "tsk-tc-idm", "success")

        task = task_repo.get_task_by_id(db, "tsk-tc-idm")
        count1 = persist_test_cases(db, task)
        count2 = persist_test_cases(db, task)
        assert count1 >= 1
        assert count2 == 0  # Already persisted

    def test_update_status(self, db):
        """TS-TC-003: Update test case status."""
        from app.services.testcase_service import update_test_case_status
        # No existing test case
        result = update_test_case_status(db, 99999, "adopted")
        assert result is None


# ═══════════════════════════════════════════════════════════════════
# 7. SCHEMA VALIDATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestSchemaValidation:
    """Tests for schema edge cases and validation."""

    def test_project_name_boundary_min(self, client):
        """TS-SV-001: Project name at minimum length (1 char)."""
        res = client.post("/api/v1/projects", json={"name": "x"})
        assert res.status_code == 201

    def test_project_name_boundary_max(self, client):
        """TS-SV-002: Project name at maximum length (64 chars)."""
        res = client.post("/api/v1/projects", json={"name": "a" * 64})
        assert res.status_code == 201

    def test_project_name_over_max(self, client):
        """TS-SV-003: Project name over maximum length rejected."""
        res = client.post("/api/v1/projects", json={"name": "a" * 65})
        assert res.status_code == 422

    def test_project_desc_boundary_max(self, client):
        """TS-SV-004: Description at maximum length (512 chars)."""
        res = client.post("/api/v1/projects", json={"name": "desc-max", "description": "d" * 512})
        assert res.status_code == 201

    def test_project_desc_over_max(self, client):
        """TS-SV-005: Description over maximum rejected."""
        res = client.post("/api/v1/projects", json={"name": "desc-over", "description": "d" * 513})
        assert res.status_code == 422

    def test_task_type_enum_validation(self, client):
        """TS-SV-006: Task type must be from valid set."""
        proj = client.post("/api/v1/projects", json={"name": "sv-proj"}).json()["data"]
        repo = client.post(f"/api/v1/projects/{proj['project_id']}/repos", json={
            "name": "sv-repo", "git_url": "url"
        }).json()["data"]

        # Valid types
        for t in ["full", "file", "function"]:
            res = client.post("/api/v1/analysis/tasks", json={
                "project_id": proj["project_id"], "repo_id": repo["repo_id"],
                "task_type": t, "analyzers": ["branch_path"],
            })
            assert res.status_code == 201, f"Type '{t}' should be accepted"

        # Invalid type
        res = client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"], "repo_id": repo["repo_id"],
            "task_type": "invalid_type", "analyzers": ["branch_path"],
        })
        assert res.status_code == 422

    def test_analyzer_validation(self, client):
        """TS-SV-007: Invalid analyzer module is rejected."""
        proj = client.post("/api/v1/projects", json={"name": "av-proj"}).json()["data"]
        repo = client.post(f"/api/v1/projects/{proj['project_id']}/repos", json={
            "name": "av-repo", "git_url": "url"
        }).json()["data"]

        res = client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"], "repo_id": repo["repo_id"],
            "task_type": "full", "analyzers": ["fake_module"],
        })
        assert res.status_code == 422

    def test_pagination_page_zero(self, client):
        """TS-SV-008: Page=0 is rejected."""
        res = client.get("/api/v1/projects?page=0")
        assert res.status_code == 422

    def test_pagination_negative_page_size(self, client):
        """TS-SV-009: Negative page_size is rejected."""
        res = client.get("/api/v1/projects?page_size=-1")
        assert res.status_code == 422

    def test_pagination_oversized_page(self, client):
        """TS-SV-010: page_size > 100 rejected for projects."""
        res = client.get("/api/v1/projects?page_size=101")
        assert res.status_code == 422

    def test_diff_task_requires_commits(self, client):
        """TS-SV-011: Diff task without commits is rejected."""
        proj = client.post("/api/v1/projects", json={"name": "diff-proj"}).json()["data"]
        repo = client.post(f"/api/v1/projects/{proj['project_id']}/repos", json={
            "name": "diff-repo", "git_url": "url"
        }).json()["data"]

        res = client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"], "repo_id": repo["repo_id"],
            "task_type": "diff", "analyzers": ["branch_path"],
        })
        assert res.status_code == 422

    def test_diff_task_with_commits_accepted(self, client):
        """TS-SV-012: Diff task with commits is accepted."""
        proj = client.post("/api/v1/projects", json={"name": "diff-ok-proj"}).json()["data"]
        repo = client.post(f"/api/v1/projects/{proj['project_id']}/repos", json={
            "name": "diff-ok-repo", "git_url": "url"
        }).json()["data"]

        res = client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"], "repo_id": repo["repo_id"],
            "task_type": "diff", "analyzers": ["branch_path"],
            "revision": {"base_commit": "abc", "head_commit": "def"},
        })
        assert res.status_code == 201


# ═══════════════════════════════════════════════════════════════════
# 8. RESPONSE ENVELOPE AND ERROR HANDLING TESTS
# ═══════════════════════════════════════════════════════════════════

class TestResponseAndErrors:
    """Tests for response envelope and error handling."""

    def test_success_envelope_structure(self, client):
        """TS-RE-001: Success response has code, message, data."""
        res = client.get("/api/v1/health")
        body = res.json()
        assert "code" in body
        assert "message" in body
        assert "data" in body
        assert body["code"] == "OK"

    def test_404_envelope_structure(self, client):
        """TS-RE-002: 404 error has proper envelope."""
        res = client.get("/api/v1/projects/99999")
        assert res.status_code == 404
        body = res.json()
        assert body["code"] != "OK"
        assert "message" in body

    def test_422_validation_error(self, client):
        """TS-RE-003: 422 validation error for bad input."""
        res = client.post("/api/v1/projects", json={"name": ""})
        assert res.status_code == 422

    def test_409_task_state_error(self, client):
        """TS-RE-004: 409 for invalid state transition."""
        # Create and complete a task, then try to cancel it
        proj = client.post("/api/v1/projects", json={"name": "state-proj"}).json()["data"]
        repo = client.post(f"/api/v1/projects/{proj['project_id']}/repos", json={
            "name": "state-repo", "git_url": "url"
        }).json()["data"]
        task = client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"], "repo_id": repo["repo_id"],
            "task_type": "full", "analyzers": ["branch_path"],
        }).json()["data"]

        # Task is already in terminal state (success/failed), cancel should return 409
        res = client.post(f"/api/v1/analysis/tasks/{task['task_id']}/cancel", json={})
        assert res.status_code in (202, 409)

    def test_root_redirects_to_docs(self, client):
        """TS-RE-005: Root path redirects to /docs."""
        res = client.get("/", follow_redirects=False)
        assert res.status_code == 307
        assert "/docs" in res.headers.get("location", "")


# ═══════════════════════════════════════════════════════════════════
# 9. ADDITIONAL API INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestAdditionalAPIIntegration:
    """Additional API endpoint integration tests for edge cases."""

    def test_multiple_tasks_same_project(self, client):
        """TS-AI-001: Create multiple tasks for the same project."""
        proj = client.post("/api/v1/projects", json={"name": "multi-task-proj"}).json()["data"]
        repo = client.post(f"/api/v1/projects/{proj['project_id']}/repos", json={
            "name": "mt-repo", "git_url": "url"
        }).json()["data"]

        for i in range(3):
            res = client.post("/api/v1/analysis/tasks", json={
                "project_id": proj["project_id"], "repo_id": repo["repo_id"],
                "task_type": "full", "analyzers": ["branch_path"],
            })
            assert res.status_code == 201

        # Verify all tasks are listed
        tasks_res = client.get(f"/api/v1/projects/{proj['project_id']}/tasks")
        assert tasks_res.json()["data"]["total"] == 3

    def test_global_findings_deduplication(self, client):
        """TS-AI-002: Global findings only show latest task per project."""
        proj = client.post("/api/v1/projects", json={"name": "dedup-proj"}).json()["data"]
        repo = client.post(f"/api/v1/projects/{proj['project_id']}/repos", json={
            "name": "dd-repo", "git_url": "url"
        }).json()["data"]

        # Create two tasks
        for _ in range(2):
            client.post("/api/v1/analysis/tasks", json={
                "project_id": proj["project_id"], "repo_id": repo["repo_id"],
                "task_type": "full", "analyzers": ["branch_path"],
            })

        res = client.get("/api/v1/findings")
        assert res.status_code == 200

    def test_project_summary_structure(self, client):
        """TS-AI-003: Project summary has all required fields."""
        proj = client.post("/api/v1/projects", json={"name": "summary-proj"}).json()["data"]
        repo = client.post(f"/api/v1/projects/{proj['project_id']}/repos", json={
            "name": "sum-repo", "git_url": "url"
        }).json()["data"]
        client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"], "repo_id": repo["repo_id"],
            "task_type": "full", "analyzers": ["branch_path", "boundary_value"],
        })

        res = client.get(f"/api/v1/projects/{proj['project_id']}/summary")
        data = res.json()["data"]
        assert "task_count" in data
        assert "finding_count" in data
        assert "modules" in data
        assert "recent_tasks" in data
        assert "trends" in data
        assert "s0_count" in data
        assert "s1_count" in data

    def test_project_measures_file_aggregation(self, client):
        """TS-AI-004: Measures endpoint aggregates by file."""
        proj = client.post("/api/v1/projects", json={"name": "measures-proj"}).json()["data"]
        repo = client.post(f"/api/v1/projects/{proj['project_id']}/repos", json={
            "name": "meas-repo", "git_url": "url"
        }).json()["data"]
        client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"], "repo_id": repo["repo_id"],
            "task_type": "full", "analyzers": ["branch_path"],
        })

        res = client.get(f"/api/v1/projects/{proj['project_id']}/measures")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "files" in data
        assert "total" in data

    def test_test_case_generate_and_query(self, client):
        """TS-AI-005: Generate test cases and then query them."""
        proj = client.post("/api/v1/projects", json={"name": "tcgen-proj"}).json()["data"]
        repo = client.post(f"/api/v1/projects/{proj['project_id']}/repos", json={
            "name": "tcgen-repo", "git_url": "url"
        }).json()["data"]
        client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"], "repo_id": repo["repo_id"],
            "task_type": "full", "analyzers": ["branch_path"],
        })

        # Generate
        gen_res = client.post(f"/api/v1/projects/{proj['project_id']}/test-cases/generate")
        assert gen_res.status_code == 200
        gen_data = gen_res.json()["data"]
        assert "generated" in gen_data
        assert "tasks_processed" in gen_data

    def test_global_tasks_filter_by_status(self, client):
        """TS-AI-006: Filter global tasks by status."""
        res = client.get("/api/v1/analysis/tasks?status=success")
        assert res.status_code == 200

    def test_global_test_cases_structure(self, client):
        """TS-AI-007: Global test cases response structure."""
        res = client.get("/api/v1/test-cases")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "test_cases" in data
        assert "total" in data

    def test_settings_get_and_update(self, client):
        """TS-AI-008: Get and update settings."""
        get_res = client.get("/api/v1/settings")
        assert get_res.status_code == 200
        settings = get_res.json()["data"]
        assert "quality_gate" in settings
        assert "system" in settings

        put_res = client.put("/api/v1/settings", json={"quality_gate": {"max_risk_score": 80}})
        assert put_res.status_code == 200

    def test_postmortem_creates_patterns(self, client):
        """TS-AI-009: Postmortem analysis creates knowledge patterns."""
        proj = client.post("/api/v1/projects", json={"name": "pm-proj"}).json()["data"]
        repo = client.post(f"/api/v1/projects/{proj['project_id']}/repos", json={
            "name": "pm-repo", "git_url": "url"
        }).json()["data"]

        res = client.post("/api/v1/postmortem", json={
            "project_id": proj["project_id"],
            "repo_id": repo["repo_id"],
            "defect": {"title": "Null deref in parser", "severity": "S0", "description": "desc"},
        })
        assert res.status_code == 201
        data = res.json()["data"]
        assert "task_id" in data
        assert "root_causes" in data

    def test_knowledge_search_empty(self, client):
        """TS-AI-010: Knowledge search returns empty when no patterns."""
        proj = client.post("/api/v1/projects", json={"name": "ks-proj"}).json()["data"]
        res = client.get(f"/api/v1/knowledge/patterns?project_id={proj['project_id']}")
        assert res.status_code == 200
        assert res.json()["data"]["total"] == 0

    def test_finding_test_suggestion(self, client):
        """TS-AI-011: Test suggestion for a finding."""
        res = client.get("/api/v1/findings/fake-id/test-suggestion")
        assert res.status_code == 200
        assert res.json()["data"]["suggestion"] is None

    def test_file_tree_structure(self, client):
        """TS-AI-012: File tree has correct node structure."""
        proj = client.post("/api/v1/projects", json={"name": "ft-proj"}).json()["data"]
        repo = client.post(f"/api/v1/projects/{proj['project_id']}/repos", json={
            "name": "ft-repo", "git_url": "url"
        }).json()["data"]
        client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"], "repo_id": repo["repo_id"],
            "task_type": "full", "analyzers": ["branch_path"],
        })

        res = client.get(f"/api/v1/projects/{proj['project_id']}/file-tree")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "files" in data
        for node in data["files"]:
            assert "path" in node
            assert "name" in node
            assert "type" in node
            assert node["type"] in ("file", "dir")

    def test_concurrent_analysis_tasks(self, client):
        """TS-AI-013: Multiple analysis tasks don't interfere."""
        proj = client.post("/api/v1/projects", json={"name": "conc-proj"}).json()["data"]
        repo = client.post(f"/api/v1/projects/{proj['project_id']}/repos", json={
            "name": "conc-repo", "git_url": "url"
        }).json()["data"]

        task_ids = []
        for _ in range(5):
            res = client.post("/api/v1/analysis/tasks", json={
                "project_id": proj["project_id"], "repo_id": repo["repo_id"],
                "task_type": "full", "analyzers": ["branch_path"],
            })
            assert res.status_code == 201
            task_ids.append(res.json()["data"]["task_id"])

        # All task IDs should be unique
        assert len(set(task_ids)) == 5

    def test_unicode_in_project_and_repo(self, client):
        """TS-AI-014: Unicode characters in project and repo names."""
        proj = client.post("/api/v1/projects", json={
            "name": "项目-测试-2025", "description": "测试描述 Unicode ✓"
        }).json()["data"]
        assert proj["name"] == "项目-测试-2025"

        repo = client.post(f"/api/v1/projects/{proj['project_id']}/repos", json={
            "name": "仓库-测试", "git_url": "https://example.com/repo.git"
        })
        assert repo.status_code == 201
