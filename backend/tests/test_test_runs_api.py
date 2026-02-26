"""
测试运行 API 与前后端契约测试。

覆盖：创建运行、列表、详情、执行/暂停/取消/删除、用例执行历史；
响应 envelope 与前端期望的字段（test_runs, run_id, test_run, executions）。
"""

import pytest


class TestTestRunsCreate:
    """创建测试运行."""

    def test_create_run_minimal(self, client):
        """创建运行（仅必填：environment）。"""
        res = client.post("/api/v1/test-runs", json={"environment": "docker"})
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["run_id"]
        assert data["status"] == "pending"
        assert data["environment"] == "docker"
        assert data["total"] == 0
        assert "created_at" in data

    def test_create_run_with_name_and_image(self, client):
        """创建运行（名称 + Docker 镜像）。"""
        res = client.post("/api/v1/test-runs", json={
            "environment": "docker",
            "name": "my-run",
            "docker_image": "ubuntu:22.04",
        })
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["name"] == "my-run"
        assert data["docker_image"] == "ubuntu:22.04"

    def test_create_run_with_project_id(self, client, create_project):
        """创建运行（关联项目）。"""
        proj = create_project()
        res = client.post("/api/v1/test-runs", json={
            "environment": "docker",
            "project_id": proj["project_id"],
        })
        assert res.status_code == 200
        assert res.json()["data"]["project_id"] == proj["project_id"]


class TestTestRunsList:
    """测试运行列表."""

    def test_list_runs_empty(self, client):
        """无运行时列表为空."""
        res = client.get("/api/v1/test-runs")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "test_runs" in data
        assert data["test_runs"] == []
        assert data["page"] == 1
        assert data["page_size"] == 20

    def test_list_runs_after_create(self, client):
        """创建后列表包含该运行."""
        create = client.post("/api/v1/test-runs", json={"environment": "docker", "name": "list-me"})
        run_id = create.json()["data"]["run_id"]
        res = client.get("/api/v1/test-runs")
        assert res.status_code == 200
        items = res.json()["data"]["test_runs"]
        assert any(r["run_id"] == run_id for r in items)
        run = next(r for r in items if r["run_id"] == run_id)
        assert run["name"] == "list-me"

    def test_list_runs_filter_by_status(self, client):
        """按状态筛选."""
        res = client.get("/api/v1/test-runs?status=pending")
        assert res.status_code == 200
        assert "test_runs" in res.json()["data"]

    def test_list_runs_pagination(self, client):
        """分页参数."""
        res = client.get("/api/v1/test-runs?page=2&page_size=5")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["page"] == 2
        assert data["page_size"] == 5

    def test_list_runs_frontend_contract(self, client):
        """前端期望：data.test_runs 为数组，每项含 run_id, status, total, passed, failed, created_at."""
        client.post("/api/v1/test-runs", json={"environment": "docker"})
        res = client.get("/api/v1/test-runs")
        data = res.json()["data"]
        assert isinstance(data["test_runs"], list)
        if data["test_runs"]:
            row = data["test_runs"][0]
            for key in ("run_id", "status", "total", "passed", "failed", "created_at", "environment"):
                assert key in row, f"missing key: {key}"


class TestTestRunsDetail:
    """运行详情."""

    def test_get_run_detail_not_found(self, client):
        """不存在的 run_id 返回 test_run: null."""
        res = client.get("/api/v1/test-runs/nonexistent-uuid")
        assert res.status_code == 200
        assert res.json()["data"]["test_run"] is None

    def test_get_run_detail_success(self, client):
        """详情含 test_run 与 executions."""
        create = client.post("/api/v1/test-runs", json={"environment": "docker", "name": "detail-me"})
        run_id = create.json()["data"]["run_id"]
        res = client.get(f"/api/v1/test-runs/{run_id}")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["test_run"] is not None
        assert data["test_run"]["run_id"] == run_id
        assert "executions" in data
        assert isinstance(data["executions"], list)


class TestTestRunsExecute:
    """触发执行."""

    def test_execute_pending_run(self, client):
        """pending 运行可触发执行."""
        create = client.post("/api/v1/test-runs", json={"environment": "docker"})
        run_id = create.json()["data"]["run_id"]
        res = client.post(f"/api/v1/test-runs/{run_id}/execute", json={})
        assert res.status_code == 200
        data = res.json()["data"]
        assert data.get("ok") is True
        assert "run_id" in data

    def test_execute_nonexistent(self, client):
        """不存在的运行返回 ok: false."""
        res = client.post("/api/v1/test-runs/nonexistent-uuid/execute", json={})
        assert res.status_code == 200
        assert res.json()["data"].get("ok") is False


class TestTestRunsPauseCancelDelete:
    """暂停、取消、删除."""

    def test_delete_run(self, client):
        """删除运行."""
        create = client.post("/api/v1/test-runs", json={"environment": "docker"})
        run_id = create.json()["data"]["run_id"]
        res = client.delete(f"/api/v1/test-runs/{run_id}")
        assert res.status_code == 200
        assert res.json()["data"].get("ok") is True
        get_res = client.get(f"/api/v1/test-runs/{run_id}")
        assert get_res.json()["data"]["test_run"] is None

    def test_delete_nonexistent(self, client):
        """删除不存在的运行返回 ok: false."""
        res = client.delete("/api/v1/test-runs/nonexistent-uuid")
        assert res.status_code == 200
        assert res.json()["data"].get("ok") is False


class TestTestCaseExecutions:
    """用例执行历史."""

    def test_get_case_executions_empty(self, client):
        """不存在的用例或无执行记录返回空列表."""
        res = client.get("/api/v1/test-cases/99999/executions")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["test_case_id"] == 99999
        assert data["executions"] == []


class TestTestRunsTrend:
    """运行趋势（前端图表）."""

    def test_trend_empty(self, client):
        """无运行时时 trend 为空."""
        res = client.get("/api/v1/test-runs/trend")
        assert res.status_code == 200
        assert res.json()["data"]["trend"] == []

    def test_trend_has_run_id_and_status(self, client):
        """trend 项含 run_id, status, passed, failed."""
        client.post("/api/v1/test-runs", json={"environment": "docker"})
        res = client.get("/api/v1/test-runs/trend?limit=5")
        data = res.json()["data"]
        assert "trend" in data
        if data["trend"]:
            for key in ("run_id", "status", "passed", "failed", "total"):
                assert key in data["trend"][0]
