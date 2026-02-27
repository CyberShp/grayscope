"""
Tests for AI Narrative Service and Prompt Templates.

Covers:
  - Prompt template loading from YAML files
  - Template rendering with variables
  - AINarrativeService functions
  - Batch processing with semaphore
  - Error handling for AI calls
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.prompt_templates import (
    _load_template,
    get_system_prompt,
    get_user_prompt,
    render_prompt,
    list_templates,
    _template_cache,
)


# ═══════════════════════════════════════════════════════════════════
# 1. PROMPT TEMPLATE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestPromptTemplateLoading:
    """Tests for prompt template loading."""

    def setup_method(self):
        """Clear template cache before each test."""
        _template_cache.clear()

    def test_load_all_templates(self):
        """All 5 narrative templates can be loaded."""
        template_ids = [
            "flow_narrative",
            "function_dictionary",
            "what_if_scenarios",
            "risk_scenario_cards",
            "test_design_matrix",
        ]
        
        for tid in template_ids:
            template = _load_template(tid)
            assert template is not None
            assert "system" in template or "user" in template

    def test_load_template_caches(self):
        """Templates are cached after first load."""
        _template_cache.clear()
        
        # First load
        template1 = _load_template("flow_narrative")
        assert "flow_narrative" in _template_cache
        
        # Second load should use cache
        template2 = _load_template("flow_narrative")
        assert template1 is template2

    def test_missing_template_raises(self):
        """Non-existent template raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Template not found"):
            _load_template("nonexistent_template_xyz")

    def test_list_templates(self):
        """list_templates returns all available templates."""
        templates = list_templates()
        
        assert isinstance(templates, list)
        assert len(templates) >= 5  # At least 5 narrative templates
        
        # Each template has id, name, description
        for tpl in templates:
            assert "id" in tpl


class TestPromptTemplateRendering:
    """Tests for prompt template rendering."""

    def setup_method(self):
        """Clear template cache before each test."""
        _template_cache.clear()

    def test_render_flow_narrative(self):
        """Flow narrative template renders correctly."""
        system, user = render_prompt(
            "flow_narrative",
            call_chain="main -> process -> send_data",
            entry_point="main",
            entry_type="main",
            branch_path="if (status == 0)",
            locks_held="g_lock",
            protocol_sequence="connect -> send",
            function_summaries="- main: 程序入口\n- process: 处理数据",
        )
        
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert len(system) > 0
        # User prompt should contain rendered variables
        assert "main" in user or len(user) > 0

    def test_render_function_dictionary(self):
        """Function dictionary template renders."""
        system, user = render_prompt(
            "function_dictionary",
            function_name="process_data",
            params="buffer, size",
            comments="处理输入数据",
            source_snippet="void process_data(char *buf, int size) { ... }",
            callers="main, init",
            callees="validate, send",
        )
        
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_render_what_if(self):
        """What-If scenarios template renders."""
        system, user = render_prompt(
            "what_if_scenarios",
            call_chain="main -> handler -> cleanup",
            branch_paths='[{"condition": "ret < 0"}]',
            lock_operations='[{"op": "acquire", "lock": "mutex"}]',
            protocol_states="INIT, CONNECTED",
            identified_risks='[{"type": "resource_leak"}]',
        )
        
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_render_risk_cards(self):
        """Risk scenario cards template renders."""
        system, user = render_prompt(
            "risk_scenario_cards",
            risk_type="error_path_resource_leak",
            risk_description="锁未在错误路径释放",
            call_chain="main -> process",
            file_path="test.c",
            line_range="10-25",
            code_evidence="pthread_mutex_lock(&lock); if (err) return -1;",
            branch_context="if (ret < 0)",
            risk_id="FR-0001",
        )
        
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_render_test_matrix(self):
        """Test design matrix template renders."""
        system, user = render_prompt(
            "test_design_matrix",
            call_chain_summary="- main -> process\n- init -> setup",
            branch_paths='[{"function": "process", "branches": 3}]',
            risks='[{"id": "FR-0001", "type": "leak"}]',
            what_if_scenarios='[{"scenario": "测试场景1"}]',
            entry_type="handler",
        )
        
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_render_with_missing_variable(self):
        """Missing variable logs warning but doesn't crash."""
        # Create a mock template with a variable
        _template_cache["test_template"] = {
            "system": "Test system",
            "user": "Variable: {required_var}",
        }
        
        # Render without the variable
        system, user = render_prompt("test_template")
        
        # Should return template string without substitution
        assert "{required_var}" in user

    def test_get_system_prompt(self):
        """get_system_prompt returns system prompt."""
        system = get_system_prompt("flow_narrative")
        
        assert isinstance(system, str)
        assert len(system) > 0

    def test_get_user_prompt(self):
        """get_user_prompt returns user prompt template."""
        user = get_user_prompt("flow_narrative")
        
        assert isinstance(user, str)
        assert "{" in user  # Should contain template variables


# ═══════════════════════════════════════════════════════════════════
# 2. AI NARRATIVE SERVICE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestCallAI:
    """Tests for _call_ai helper function."""

    @pytest.mark.asyncio
    async def test_call_ai_json_parse(self):
        """Correctly parse JSON response."""
        from app.services.ai_narrative_service import _call_ai
        
        mock_response = '{"test": "data", "number": 42}'
        
        with patch("app.services.ai_narrative_service.get_provider") as mock_get:
            mock_provider = MagicMock()
            mock_provider.chat = AsyncMock(return_value={"content": mock_response})
            mock_get.return_value = mock_provider
            
            result = await _call_ai(
                "deepseek",
                "test-model",
                "system prompt",
                "user prompt",
            )
            
            assert result["test"] == "data"
            assert result["number"] == 42

    @pytest.mark.asyncio
    async def test_call_ai_code_block_json(self):
        """Handle JSON wrapped in code block."""
        from app.services.ai_narrative_service import _call_ai
        
        mock_response = '```json\n{"test": "value"}\n```'
        
        with patch("app.services.ai_narrative_service.get_provider") as mock_get:
            mock_provider = MagicMock()
            mock_provider.chat = AsyncMock(return_value={"content": mock_response})
            mock_get.return_value = mock_provider
            
            result = await _call_ai(
                "deepseek",
                "test-model",
                "system",
                "user",
            )
            
            assert result["test"] == "value"

    @pytest.mark.asyncio
    async def test_call_ai_parse_error_fallback(self):
        """JSON parse failure returns raw_content."""
        from app.services.ai_narrative_service import _call_ai
        
        mock_response = "This is not JSON at all"
        
        with patch("app.services.ai_narrative_service.get_provider") as mock_get:
            mock_provider = MagicMock()
            mock_provider.chat = AsyncMock(return_value={"content": mock_response})
            mock_get.return_value = mock_provider
            
            result = await _call_ai(
                "deepseek",
                "test-model",
                "system",
                "user",
            )
            
            assert "raw_content" in result
            assert "parse_error" in result

    @pytest.mark.asyncio
    async def test_call_ai_exception_handling(self):
        """AI call exception returns error field."""
        from app.services.ai_narrative_service import _call_ai
        
        with patch("app.services.ai_narrative_service.get_provider") as mock_get:
            mock_provider = MagicMock()
            mock_provider.chat = AsyncMock(side_effect=Exception("Connection failed"))
            mock_get.return_value = mock_provider
            
            result = await _call_ai(
                "deepseek",
                "test-model",
                "system",
                "user",
            )
            
            assert "error" in result
            assert "Connection failed" in result["error"]


class TestNarrativeGenerators:
    """Tests for individual narrative generator functions."""

    @pytest.mark.asyncio
    async def test_generate_flow_narrative_format(self):
        """generate_flow_narrative output format."""
        from app.services.ai_narrative_service import generate_flow_narrative
        
        mock_result = {
            "title": "数据处理流程",
            "story": "该流程从主入口开始...",
            "steps": ["步骤1", "步骤2"],
        }
        
        with patch("app.services.ai_narrative_service._call_ai", new=AsyncMock(return_value=mock_result)):
            result = await generate_flow_narrative(
                call_chain=["main", "process", "send"],
                entry_point="main",
                entry_type="main",
                branch_path="if (status == 0)",
                locks_held=["g_lock"],
                protocol_sequence=["connect", "send"],
                function_summaries={"main": "入口函数"},
                ai_config={"provider": "deepseek", "model": "test"},
            )
            
            assert result["title"] == "数据处理流程"
            assert "story" in result

    @pytest.mark.asyncio
    async def test_generate_function_dictionary_format(self):
        """generate_function_dictionary output format."""
        from app.services.ai_narrative_service import generate_function_dictionary
        
        mock_result = {
            "business_name": "数据处理器",
            "purpose": "处理输入数据并验证格式",
            "inputs": "缓冲区, 大小",
            "outputs": "状态码",
        }
        
        with patch("app.services.ai_narrative_service._call_ai", new=AsyncMock(return_value=mock_result)):
            result = await generate_function_dictionary(
                function_name="process_data",
                params=["buffer", "size"],
                comments="处理数据",
                source_snippet="void process_data(...)",
                callers=["main"],
                callees=["validate"],
                ai_config={"provider": "deepseek", "model": "test"},
            )
            
            assert "business_name" in result

    @pytest.mark.asyncio
    async def test_generate_what_if_scenarios_format(self):
        """generate_what_if_scenarios output format."""
        from app.services.ai_narrative_service import generate_what_if_scenarios
        
        mock_result = {
            "scenarios": [
                {"scenario": "如果锁获取超时", "expected": "返回错误"},
                {"scenario": "如果数据为空", "expected": "跳过处理"},
            ]
        }
        
        with patch("app.services.ai_narrative_service._call_ai", new=AsyncMock(return_value=mock_result)):
            result = await generate_what_if_scenarios(
                call_chain=["main", "process"],
                branch_paths=[{"condition": "ret < 0"}],
                lock_operations=[{"op": "acquire", "lock": "mutex"}],
                protocol_states=["INIT"],
                identified_risks=[{"type": "leak"}],
                ai_config={"provider": "deepseek", "model": "test"},
            )
            
            assert "scenarios" in result
            assert len(result["scenarios"]) == 2


class TestBatchProcessing:
    """Tests for batch processing with semaphore."""

    @pytest.mark.asyncio
    async def test_generate_batch_with_semaphore(self):
        """Batch function dictionary respects semaphore."""
        from app.services.ai_narrative_service import generate_batch_function_dictionary
        
        mock_result = {"business_name": "Test"}
        
        with patch("app.services.ai_narrative_service.generate_function_dictionary", 
                   new=AsyncMock(return_value=mock_result)):
            functions = [
                {"name": f"func_{i}", "params": [], "comments": "", "source": ""}
                for i in range(5)
            ]
            
            result = await generate_batch_function_dictionary(
                functions,
                ai_config={"provider": "deepseek", "model": "test"},
                max_concurrent=2,
            )
            
            assert len(result) == 5
            assert "func_0" in result
            assert "func_4" in result

    @pytest.mark.asyncio
    async def test_generate_batch_handles_exceptions(self):
        """Batch processing handles individual failures."""
        from app.services.ai_narrative_service import generate_batch_function_dictionary
        
        call_count = 0
        
        async def mock_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("API error")
            return {"business_name": f"Func {call_count}"}
        
        with patch("app.services.ai_narrative_service.generate_function_dictionary", 
                   new=mock_generate):
            functions = [
                {"name": f"func_{i}", "params": [], "comments": "", "source": ""}
                for i in range(3)
            ]
            
            result = await generate_batch_function_dictionary(
                functions,
                ai_config={"provider": "deepseek", "model": "test"},
            )
            
            # Should have 2 successful results (skipping the failed one)
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_generate_batch_risk_cards(self):
        """Batch risk card generation works."""
        from app.services.ai_narrative_service import generate_batch_risk_cards
        
        mock_card = {
            "scenario": "测试场景",
            "risk": "风险描述",
            "evidence": "代码证据",
        }
        
        with patch("app.services.ai_narrative_service.generate_risk_scenario_card",
                   new=AsyncMock(return_value=mock_card)):
            risks = [
                {"risk_type": "leak", "description": "Resource leak", "call_chain": ["main"]},
                {"risk_type": "deadlock", "description": "Deadlock", "call_chain": ["init"]},
            ]
            
            result = await generate_batch_risk_cards(
                risks,
                ai_config={"provider": "deepseek", "model": "test"},
            )
            
            assert len(result) == 2
            assert result[0]["scenario"] == "测试场景"


# ═══════════════════════════════════════════════════════════════════
# 3. AI NARRATIVE SERVICE CLASS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestAINarrativeService:
    """Tests for AINarrativeService class."""

    def test_service_initialization(self):
        """Service initializes with config."""
        from app.services.ai_narrative_service import AINarrativeService
        
        config = {"provider": "deepseek", "model": "test-model"}
        service = AINarrativeService(config)
        
        assert service.ai_config == config

    @pytest.mark.asyncio
    async def test_generate_full_narrative_structure(self):
        """generate_full_narrative returns complete structure."""
        from app.services.ai_narrative_service import AINarrativeService
        
        # Create mock graph and findings
        class MockCallChain:
            functions = ["main", "process"]
            entry_point = "main"
            entry_type = "main"
            branch_coverage = "normal"
            lock_sequence = []
            protocol_sequence = []
        
        class MockNode:
            name = "main"
            params = []
            comments = []
            source = "void main() {}"
        
        class MockEdge:
            caller = "main"
            callee = "process"
        
        class MockGraph:
            call_chains = [MockCallChain()]
            nodes = {"main": MockNode()}
            edges = [MockEdge()]
        
        mock_graph = MockGraph()
        mock_findings = [{"finding_id": "FR-0001", "severity": "high", "risk_type": "leak"}]
        
        # Mock all the generator functions
        with patch("app.services.ai_narrative_service.generate_flow_narrative",
                   new=AsyncMock(return_value={"title": "Test"})):
            with patch("app.services.ai_narrative_service.generate_batch_function_dictionary",
                       new=AsyncMock(return_value={"main": {"business_name": "Entry"}})):
                with patch("app.services.ai_narrative_service.generate_batch_risk_cards",
                           new=AsyncMock(return_value=[{"card": "test"}])):
                    with patch("app.services.ai_narrative_service.generate_what_if_scenarios",
                               new=AsyncMock(return_value={"scenarios": []})):
                        with patch("app.services.ai_narrative_service.generate_test_design_matrix",
                                   new=AsyncMock(return_value={"test_cases": []})):
                            
                            service = AINarrativeService({"provider": "deepseek", "model": "test"})
                            result = await service.generate_full_narrative(mock_graph, mock_findings)
                            
                            # Verify structure
                            assert "flow_narratives" in result
                            assert "function_dictionary" in result
                            assert "risk_cards" in result
                            assert "what_if_scenarios" in result
                            assert "test_matrix" in result


# ═══════════════════════════════════════════════════════════════════
# 4. EDGE CASES
# ═══════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Edge case tests."""

    def test_template_with_special_characters(self):
        """Template handles special characters in variables."""
        _template_cache["special_test"] = {
            "system": "System",
            "user": "Code: {code}",
        }
        
        code_with_special = 'if (x < 0 && y > 10) { printf("%s\\n", buf); }'
        system, user = render_prompt("special_test", code=code_with_special)
        
        assert code_with_special in user

    @pytest.mark.asyncio
    async def test_call_ai_with_custom_credentials(self):
        """_call_ai passes custom api_key and base_url."""
        from app.services.ai_narrative_service import _call_ai
        
        with patch("app.services.ai_narrative_service.get_provider") as mock_get:
            mock_provider = MagicMock()
            mock_provider.chat = AsyncMock(return_value={"content": '{"test": 1}'})
            mock_get.return_value = mock_provider
            
            await _call_ai(
                "custom",
                "my-model",
                "sys",
                "usr",
                api_key="custom-key",
                base_url="http://custom:8000",
            )
            
            # Verify provider was created with custom credentials
            call_kwargs = mock_get.call_args[1]
            assert call_kwargs.get("api_key") == "custom-key"
            assert call_kwargs.get("base_url") == "http://custom:8000"

    @pytest.mark.asyncio
    async def test_empty_call_chain_handling(self):
        """Handle empty call chain gracefully."""
        from app.services.ai_narrative_service import generate_flow_narrative
        
        with patch("app.services.ai_narrative_service._call_ai",
                   new=AsyncMock(return_value={"story": "Empty flow"})):
            result = await generate_flow_narrative(
                call_chain=[],
                entry_point="",
                entry_type="unknown",
                branch_path="",
                locks_held=[],
                protocol_sequence=[],
                function_summaries={},
                ai_config={"provider": "deepseek", "model": "test"},
            )
            
            assert "story" in result
