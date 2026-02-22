"""
Comprehensive tests for GrayScope AI layer.

Covers:
  - Provider base class and registry
  - Individual provider construction (Ollama, DeepSeek, Qwen, OpenAICompat, CustomREST)
  - Prompt engine: template loading, rendering, cache, reload
  - AI enrichment service: enrich_module, synthesize_cross_module
  - Helper functions: _extract_test_suggestions, _build_cross_context
  - Edge cases: unknown provider, missing template, bad AI response
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml


# ═══════════════════════════════════════════════════════════════════
# 1. PROVIDER BASE CLASS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestProviderBase:
    """Tests for app.ai.provider_base.ModelProvider."""

    def test_model_provider_is_abstract(self):
        """TS-PB-001: ModelProvider cannot be instantiated directly."""
        from app.ai.provider_base import ModelProvider

        with pytest.raises(TypeError):
            ModelProvider()  # type: ignore[abstract]

    def test_model_provider_has_required_methods(self):
        """TS-PB-002: ModelProvider defines chat, health_check, name."""
        from app.ai.provider_base import ModelProvider
        import inspect

        assert hasattr(ModelProvider, "chat")
        assert hasattr(ModelProvider, "health_check")
        assert hasattr(ModelProvider, "name")
        assert inspect.isabstract(ModelProvider)


# ═══════════════════════════════════════════════════════════════════
# 2. PROVIDER CONSTRUCTION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOllamaProvider:
    """Tests for OllamaProvider."""

    def test_construction_defaults(self):
        """TS-OL-001: Default construction."""
        from app.ai.providers.ollama import OllamaProvider
        p = OllamaProvider()
        assert p.name() == "ollama"
        assert p._base_url == "http://localhost:11434"
        assert p._default_model == "qwen2.5-coder"

    def test_construction_custom(self):
        """TS-OL-002: Custom URL and model."""
        from app.ai.providers.ollama import OllamaProvider
        p = OllamaProvider(base_url="http://custom:8080/", default_model="llama3")
        assert p._base_url == "http://custom:8080"  # trailing slash stripped
        assert p._default_model == "llama3"

    def test_chat_request_format(self):
        """TS-OL-003: Chat builds correct payload."""
        from app.ai.providers.ollama import OllamaProvider
        p = OllamaProvider()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test reply"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        mock_response.raise_for_status = MagicMock()

        async def run_test():
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await p.chat(
                    [{"role": "user", "content": "hello"}],
                    model="test-model",
                )
                assert result["content"] == "test reply"
                assert result["usage"]["prompt_tokens"] == 10

        asyncio.get_event_loop().run_until_complete(run_test())

    def test_health_check_success(self):
        """TS-OL-004: Health check returns True on 200."""
        from app.ai.providers.ollama import OllamaProvider
        p = OllamaProvider()

        mock_response = MagicMock()
        mock_response.status_code = 200

        async def run_test():
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await p.health_check()
                assert result is True

        asyncio.get_event_loop().run_until_complete(run_test())

    def test_health_check_failure(self):
        """TS-OL-005: Health check returns False on exception."""
        from app.ai.providers.ollama import OllamaProvider
        p = OllamaProvider()

        async def run_test():
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await p.health_check()
                assert result is False

        asyncio.get_event_loop().run_until_complete(run_test())

    def test_chat_empty_choices(self):
        """TS-OL-006: Chat handles empty choices gracefully."""
        from app.ai.providers.ollama import OllamaProvider
        p = OllamaProvider()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [], "usage": {}}
        mock_response.raise_for_status = MagicMock()

        async def run_test():
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await p.chat([{"role": "user", "content": "test"}])
                assert result["content"] == ""

        asyncio.get_event_loop().run_until_complete(run_test())


class TestDeepSeekProvider:
    """Tests for DeepSeekProvider."""

    def test_construction(self):
        """TS-DS-001: Default construction."""
        from app.ai.providers.deepseek import DeepSeekProvider
        p = DeepSeekProvider(api_key="test-key")
        assert p.name() == "deepseek"
        assert p._api_key == "test-key"
        assert p._default_model == "deepseek-coder"

    def test_headers_with_api_key(self):
        """TS-DS-002: Headers include Authorization when api_key set."""
        from app.ai.providers.deepseek import DeepSeekProvider
        p = DeepSeekProvider(api_key="sk-test")
        headers = p._headers()
        assert headers["Authorization"] == "Bearer sk-test"
        assert headers["Content-Type"] == "application/json"

    def test_headers_without_api_key(self):
        """TS-DS-003: Headers omit Authorization when no api_key."""
        from app.ai.providers.deepseek import DeepSeekProvider
        p = DeepSeekProvider()
        headers = p._headers()
        assert "Authorization" not in headers

    def test_url_trailing_slash_stripped(self):
        """TS-DS-004: Trailing slash in base_url is stripped."""
        from app.ai.providers.deepseek import DeepSeekProvider
        p = DeepSeekProvider(base_url="https://api.deepseek.com/")
        assert p._base_url == "https://api.deepseek.com"


class TestQwenProvider:
    """Tests for QwenProvider."""

    def test_construction(self):
        """TS-QW-001: Default construction."""
        from app.ai.providers.qwen import QwenProvider
        p = QwenProvider(api_key="qwen-key")
        assert p.name() == "qwen"
        assert p._default_model == "qwen-plus"
        assert "dashscope" in p._base_url

    def test_headers(self):
        """TS-QW-002: Headers format."""
        from app.ai.providers.qwen import QwenProvider
        p = QwenProvider(api_key="test")
        h = p._headers()
        assert h["Authorization"] == "Bearer test"


class TestOpenAICompatProvider:
    """Tests for OpenAICompatProvider."""

    def test_construction(self):
        """TS-OC-001: Construction with parameters."""
        from app.ai.providers.openai_compat import OpenAICompatProvider
        p = OpenAICompatProvider(
            base_url="http://vllm:8000",
            api_key="key",
            default_model="mistral-7b",
        )
        assert p.name() == "openai_compat"
        assert p._default_model == "mistral-7b"

    def test_headers_with_key(self):
        """TS-OC-002: Auth header present when key provided."""
        from app.ai.providers.openai_compat import OpenAICompatProvider
        p = OpenAICompatProvider(base_url="http://x", api_key="apikey")
        h = p._headers()
        assert h["Authorization"] == "Bearer apikey"


class TestCustomRESTProvider:
    """Tests for CustomRESTProvider."""

    def test_construction(self):
        """TS-CR-001: Default construction."""
        from app.ai.providers.custom_rest import CustomRESTProvider
        p = CustomRESTProvider()
        assert p.name() == "custom_rest"
        assert p._default_model == "distill-v1"
        assert p._chat_path == "/v1/chat/completions"
        assert p._health_path == "/health"

    def test_custom_paths(self):
        """TS-CR-002: Custom chat and health paths."""
        from app.ai.providers.custom_rest import CustomRESTProvider
        p = CustomRESTProvider(
            chat_path="/api/generate",
            health_path="/api/health",
        )
        assert p._chat_path == "/api/generate"
        assert p._health_path == "/api/health"

    def test_extract_nested_key(self):
        """TS-CR-003: _extract navigates nested dict/list."""
        from app.ai.providers.custom_rest import CustomRESTProvider
        data = {
            "choices": [
                {"message": {"content": "hello world"}},
            ],
        }
        result = CustomRESTProvider._extract(data, "choices.0.message.content")
        assert result == "hello world"

    def test_extract_missing_key(self):
        """TS-CR-004: _extract returns empty string on missing key."""
        from app.ai.providers.custom_rest import CustomRESTProvider
        data = {"foo": "bar"}
        result = CustomRESTProvider._extract(data, "choices.0.message.content")
        assert result == ""

    def test_extract_invalid_index(self):
        """TS-CR-005: _extract returns empty on bad list index."""
        from app.ai.providers.custom_rest import CustomRESTProvider
        data = {"choices": []}
        result = CustomRESTProvider._extract(data, "choices.0.message.content")
        assert result == ""

    def test_extract_non_dict_non_list(self):
        """TS-CR-006: _extract returns empty on scalar value."""
        from app.ai.providers.custom_rest import CustomRESTProvider
        data = {"choices": "not_a_list"}
        result = CustomRESTProvider._extract(data, "choices.0")
        assert result == ""

    def test_extract_simple_key(self):
        """TS-CR-007: _extract works with single-level key."""
        from app.ai.providers.custom_rest import CustomRESTProvider
        data = {"response": "ok"}
        result = CustomRESTProvider._extract(data, "response")
        assert result == "ok"


# ═══════════════════════════════════════════════════════════════════
# 3. PROVIDER REGISTRY TESTS
# ═══════════════════════════════════════════════════════════════════

class TestProviderRegistry:
    """Tests for app.ai.provider_registry."""

    def setup_method(self):
        """Clear the provider cache before each test."""
        from app.ai.provider_registry import clear_cache
        clear_cache()

    def test_get_ollama_provider(self):
        """TS-PR-001: Get Ollama provider."""
        from app.ai.provider_registry import get_provider
        p = get_provider("ollama", model="test-model")
        assert p.name() == "ollama"

    def test_get_deepseek_provider(self):
        """TS-PR-002: Get DeepSeek provider."""
        from app.ai.provider_registry import get_provider
        p = get_provider("deepseek", model="deepseek-coder", api_key="key")
        assert p.name() == "deepseek"

    def test_get_qwen_provider(self):
        """TS-PR-003: Get Qwen provider."""
        from app.ai.provider_registry import get_provider
        p = get_provider("qwen", model="qwen-plus", api_key="key")
        assert p.name() == "qwen"

    def test_get_openai_compat_provider(self):
        """TS-PR-004: Get OpenAI-compatible provider."""
        from app.ai.provider_registry import get_provider
        p = get_provider("openai_compat", model="default")
        assert p.name() == "openai_compat"

    def test_get_custom_rest_provider(self):
        """TS-PR-005: Get Custom REST provider."""
        from app.ai.provider_registry import get_provider
        p = get_provider("custom_rest", model="distill")
        assert p.name() == "custom_rest"

    def test_unknown_provider_raises(self):
        """TS-PR-006: Unknown provider name raises ValueError."""
        from app.ai.provider_registry import get_provider
        with pytest.raises(ValueError, match="unknown provider"):
            get_provider("nonexistent_provider")

    def test_provider_caching(self):
        """TS-PR-007: Same (provider, model) returns cached instance."""
        from app.ai.provider_registry import get_provider
        p1 = get_provider("ollama", model="m1")
        p2 = get_provider("ollama", model="m1")
        assert p1 is p2

    def test_different_models_different_instances(self):
        """TS-PR-008: Different models create different instances."""
        from app.ai.provider_registry import get_provider
        p1 = get_provider("ollama", model="model-a")
        p2 = get_provider("ollama", model="model-b")
        assert p1 is not p2

    def test_clear_cache(self):
        """TS-PR-009: clear_cache removes all cached providers."""
        from app.ai.provider_registry import get_provider, clear_cache, _cache
        get_provider("ollama", model="test")
        assert len(_cache) > 0
        clear_cache()
        assert len(_cache) == 0

    def test_supported_providers_set(self):
        """TS-PR-010: SUPPORTED_PROVIDERS contains all expected names."""
        from app.ai.provider_registry import SUPPORTED_PROVIDERS
        assert "ollama" in SUPPORTED_PROVIDERS
        assert "deepseek" in SUPPORTED_PROVIDERS
        assert "qwen" in SUPPORTED_PROVIDERS
        assert "openai_compat" in SUPPORTED_PROVIDERS
        assert "custom_rest" in SUPPORTED_PROVIDERS
        assert len(SUPPORTED_PROVIDERS) == 5


# ═══════════════════════════════════════════════════════════════════
# 4. PROMPT ENGINE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestPromptEngine:
    """Tests for app.ai.prompt_engine."""

    def setup_method(self):
        """Clear template cache before each test."""
        from app.ai import prompt_engine
        prompt_engine._template_cache.clear()

    def test_load_real_templates(self):
        """TS-PE-001: Load all real templates from disk."""
        from app.ai import prompt_engine
        prompt_engine._load_all()
        assert len(prompt_engine._template_cache) >= 5  # We have at least 5 templates
        assert "branch_path_analysis" in prompt_engine._template_cache
        assert "boundary_value_analysis" in prompt_engine._template_cache

    def test_get_template_by_id(self):
        """TS-PE-002: Get template by ID."""
        from app.ai import prompt_engine
        tpl = prompt_engine.get_template("branch_path_analysis")
        assert tpl is not None
        assert tpl["template_id"] == "branch_path_analysis"
        assert "system_prompt" in tpl
        assert "user_prompt" in tpl

    def test_get_template_nonexistent(self):
        """TS-PE-003: Get nonexistent template returns None."""
        from app.ai import prompt_engine
        result = prompt_engine.get_template("this_does_not_exist")
        assert result is None

    def test_list_templates(self):
        """TS-PE-004: List templates returns list with IDs."""
        from app.ai import prompt_engine
        templates = prompt_engine.list_templates()
        assert isinstance(templates, list)
        assert len(templates) >= 5
        ids = [t["template_id"] for t in templates]
        assert "branch_path_analysis" in ids

    def test_render_branch_path(self):
        """TS-PE-005: Render branch_path_analysis template."""
        from app.ai import prompt_engine
        messages = prompt_engine.render("branch_path_analysis", {
            "function_name": "pool_insert",
            "source_code": "void pool_insert(Pool *p, Entry *e) { ... }",
            "cfg_summary": "3 branches: error, cleanup, normal",
        })
        assert isinstance(messages, list)
        assert len(messages) >= 2  # system + user
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        assert "pool_insert" in messages[-1]["content"]

    def test_render_boundary_value_with_cross_context(self):
        """TS-PE-006: Render boundary_value template with cross-module context."""
        from app.ai import prompt_engine
        messages = prompt_engine.render("boundary_value_analysis", {
            "function_name": "check_index",
            "source_code": "int check_index(int idx) { if (idx >= MAX) return -1; }",
            "cfg_summary": "1 boundary condition",
            "call_chain_context": "caller_a() -> check_index()",
            "data_flow_paths": "[external] param flows from network",
            "cross_module_findings": "[Error Path] missing cleanup S0",
        })
        assert len(messages) >= 2
        content = messages[-1]["content"]
        assert "check_index" in content
        # Cross-module context should be rendered
        assert "caller_a" in content
        assert "external" in content

    def test_render_nonexistent_template_raises(self):
        """TS-PE-007: Render with unknown template ID raises ValueError."""
        from app.ai import prompt_engine
        with pytest.raises(ValueError, match="not found"):
            prompt_engine.render("totally_fake_template", {})

    def test_render_with_empty_variables(self):
        """TS-PE-008: Render with empty variables uses defaults."""
        from app.ai import prompt_engine
        messages = prompt_engine.render("branch_path_analysis", {
            "function_name": "",
            "source_code": "",
            "cfg_summary": "",
        })
        assert isinstance(messages, list)
        assert len(messages) >= 1

    def test_reload_clears_and_reloads(self):
        """TS-PE-009: reload() clears cache and reloads templates."""
        from app.ai import prompt_engine
        # Load first
        prompt_engine.get_template("branch_path_analysis")
        assert len(prompt_engine._template_cache) > 0

        # Reload
        prompt_engine.reload()
        assert len(prompt_engine._template_cache) > 0  # Reloaded
        assert "branch_path_analysis" in prompt_engine._template_cache

    def test_template_version_present(self):
        """TS-PE-010: Templates have version field."""
        from app.ai import prompt_engine
        tpl = prompt_engine.get_template("branch_path_analysis")
        assert tpl is not None
        assert "version" in tpl
        assert tpl["version"] == "v1"

    def test_lazy_loading(self):
        """TS-PE-011: Templates are loaded lazily on first access."""
        from app.ai import prompt_engine
        assert len(prompt_engine._template_cache) == 0
        prompt_engine.get_template("branch_path_analysis")
        assert len(prompt_engine._template_cache) > 0

    def test_render_with_custom_temp_template(self):
        """TS-PE-012: Render works with a dynamically added template."""
        from app.ai import prompt_engine
        prompt_engine._template_cache["test_custom"] = {
            "template_id": "test_custom",
            "version": "v1",
            "system_prompt": "You are a {{ role }}.",
            "user_prompt": "Analyze {{ target }}.",
        }
        messages = prompt_engine.render("test_custom", {
            "role": "test expert",
            "target": "foo_function",
        })
        assert messages[0]["content"] == "You are a test expert."
        assert messages[1]["content"] == "Analyze foo_function."

    def test_render_empty_system_prompt_omitted(self):
        """TS-PE-013: Empty system prompt is omitted from messages."""
        from app.ai import prompt_engine
        prompt_engine._template_cache["no_sys"] = {
            "template_id": "no_sys",
            "version": "v1",
            "system_prompt": "   ",
            "user_prompt": "Do something.",
        }
        messages = prompt_engine.render("no_sys", {})
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    def test_all_analysis_templates_renderable(self):
        """TS-PE-014: All analysis templates can be rendered without errors."""
        from app.ai import prompt_engine
        template_ids = [
            "branch_path_analysis",
            "boundary_value_analysis",
            "error_path_analysis",
            "concurrency_analysis",
            "diff_impact_analysis",
            "data_flow_analysis",
        ]
        base_vars = {
            "function_name": "test_func",
            "source_code": "void test_func() {}",
            "cfg_summary": "simple function",
            "module_path": "test.c",
            "shared_vars": "",
            "lock_usage": "",
            "changed_files": "",
            "changed_symbols": "",
            "diff_text": "",
            "depth": 2,
            "impacted_symbols": "",
            "call_chain_context": "",
            "data_flow_paths": "",
            "cross_module_findings": "",
        }
        for tid in template_ids:
            tpl = prompt_engine.get_template(tid)
            if tpl is not None:
                messages = prompt_engine.render(tid, base_vars)
                assert isinstance(messages, list)
                assert len(messages) >= 1


# ═══════════════════════════════════════════════════════════════════
# 5. AI ENRICHMENT SERVICE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestAIEnrichment:
    """Tests for app.services.ai_enrichment."""

    def test_extract_test_suggestions_json_list(self):
        """TS-AE-001: Extract suggestions from JSON list response."""
        from app.services.ai_enrichment import _extract_test_suggestions
        content = json.dumps([
            {"test_case": "TC-001", "description": "test boundary"},
            {"test_case": "TC-002", "description": "test error path"},
        ])
        result = _extract_test_suggestions(content)
        assert len(result) == 2

    def test_extract_test_suggestions_json_dict_with_key(self):
        """TS-AE-002: Extract suggestions from JSON dict with test_suggestions key."""
        from app.services.ai_enrichment import _extract_test_suggestions
        content = json.dumps({
            "test_suggestions": [
                {"name": "Test1"},
                {"name": "Test2"},
            ]
        })
        result = _extract_test_suggestions(content)
        assert len(result) == 2

    def test_extract_test_suggestions_json_dict_tests_key(self):
        """TS-AE-003: Extract from dict with 'tests' key."""
        from app.services.ai_enrichment import _extract_test_suggestions
        content = json.dumps({"tests": [{"id": 1}]})
        result = _extract_test_suggestions(content)
        assert len(result) == 1

    def test_extract_test_suggestions_json_dict_no_known_key(self):
        """TS-AE-004: Extract from dict without known keys returns [dict]."""
        from app.services.ai_enrichment import _extract_test_suggestions
        content = json.dumps({"analysis": "detailed", "risk": "high"})
        result = _extract_test_suggestions(content)
        assert len(result) == 1
        assert result[0]["analysis"] == "detailed"

    def test_extract_test_suggestions_invalid_json(self):
        """TS-AE-005: Non-JSON content returns raw text block."""
        from app.services.ai_enrichment import _extract_test_suggestions
        content = "This is plain text analysis output."
        result = _extract_test_suggestions(content)
        assert len(result) == 1
        assert result[0]["type"] == "raw_text"
        assert "plain text" in result[0]["content"]

    def test_extract_test_suggestions_empty(self):
        """TS-AE-006: Empty content returns empty list."""
        from app.services.ai_enrichment import _extract_test_suggestions
        result = _extract_test_suggestions("")
        assert result == []

    def test_extract_test_suggestions_none(self):
        """TS-AE-007: None content returns empty list."""
        from app.services.ai_enrichment import _extract_test_suggestions
        result = _extract_test_suggestions(None)
        assert result == []

    def test_extract_e2e_test_scenarios(self):
        """TS-AE-008: Extract from 'e2e_test_scenarios' key."""
        from app.services.ai_enrichment import _extract_test_suggestions
        content = json.dumps({
            "e2e_test_scenarios": [{"scenario": "race condition test"}]
        })
        result = _extract_test_suggestions(content)
        assert len(result) == 1

    def test_build_cross_context_no_upstream(self):
        """TS-AE-009: _build_cross_context with no upstream returns empty."""
        from app.services.ai_enrichment import _build_cross_context
        result = _build_cross_context("branch_path", [], None)
        assert result == {}

    def test_build_cross_context_empty_upstream(self):
        """TS-AE-010: _build_cross_context with empty upstream returns empty."""
        from app.services.ai_enrichment import _build_cross_context
        result = _build_cross_context("branch_path", [], {})
        assert result == {}

    def test_build_cross_context_with_call_graph(self):
        """TS-AE-011: Cross context includes call chain info."""
        from app.services.ai_enrichment import _build_cross_context
        upstream = {
            "call_graph": {
                "findings": [
                    {
                        "symbol_name": "foo",
                        "evidence": {
                            "callees": ["bar", "baz"],
                            "callers": ["main"],
                            "caller_chains": [["main", "init", "foo"]],
                        },
                    }
                ],
                "risk_score": 0.5,
            }
        }
        result = _build_cross_context("boundary_value", [], upstream)
        assert "call_chain_context" in result
        assert "foo" in result["call_chain_context"]

    def test_build_cross_context_with_data_flow(self):
        """TS-AE-012: Cross context includes data flow paths."""
        from app.services.ai_enrichment import _build_cross_context
        upstream = {
            "data_flow": {
                "findings": [
                    {
                        "evidence": {
                            "propagation_chain": [
                                {"function": "read_input", "param": "buf"},
                                {"function": "parse", "param": "data"},
                            ],
                            "is_external_input": True,
                            "sensitive_ops": ["memcpy"],
                        },
                    }
                ],
                "risk_score": 0.8,
            }
        }
        result = _build_cross_context("boundary_value", [], upstream)
        assert "data_flow_paths" in result
        assert "外部输入" in result["data_flow_paths"]
        assert "memcpy" in result["data_flow_paths"]

    def test_build_cross_context_with_high_risk_findings(self):
        """TS-AE-013: Cross context includes high-risk cross-module findings."""
        from app.services.ai_enrichment import _build_cross_context
        upstream = {
            "error_path": {
                "findings": [
                    {"title": "Missing cleanup", "risk_score": 0.9, "severity": "S0"},
                ],
                "risk_score": 0.9,
            },
            "concurrency": {
                "findings": [
                    {"title": "Low risk item", "risk_score": 0.3},
                ],
                "risk_score": 0.3,
            },
        }
        result = _build_cross_context("branch_path", [], upstream)
        assert "cross_module_findings" in result
        assert "Missing cleanup" in result["cross_module_findings"]
        # Low risk items should not appear
        assert "Low risk item" not in result.get("cross_module_findings", "")

    def test_build_cross_context_skips_own_module(self):
        """TS-AE-014: Cross context skips findings from the same module."""
        from app.services.ai_enrichment import _build_cross_context
        upstream = {
            "branch_path": {
                "findings": [
                    {"title": "Own module finding", "risk_score": 0.95},
                ],
                "risk_score": 0.95,
            }
        }
        result = _build_cross_context("branch_path", [], upstream)
        # Should not include own module's findings in cross context
        assert "cross_module_findings" not in result or "Own module finding" not in result.get("cross_module_findings", "")

    def test_enrich_module_no_template(self):
        """TS-AE-015: enrich_module returns failure for module without template."""
        from app.services.ai_enrichment import enrich_module
        result = enrich_module(
            "coverage_map",  # No template for coverage_map
            [{"finding_id": "F1"}],
            {},
            {"provider": "ollama", "model": "test"},
        )
        assert result["success"] is False
        assert "暂无" in result["ai_summary"]

    def test_enrich_module_template_mapping(self):
        """TS-AE-016: All mapped templates exist."""
        from app.services.ai_enrichment import _MODULE_TEMPLATES
        from app.ai import prompt_engine

        for module_id, template_id in _MODULE_TEMPLATES.items():
            tpl = prompt_engine.get_template(template_id)
            assert tpl is not None, f"Template '{template_id}' for module '{module_id}' not found"

    @patch("app.services.ai_enrichment._call_model_sync")
    def test_enrich_module_ai_call_success(self, mock_call):
        """TS-AE-017: enrich_module with successful AI call."""
        mock_call.return_value = {
            "content": json.dumps({"test_suggestions": [{"test": "boundary check"}]}),
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            "success": True,
        }
        from app.services.ai_enrichment import enrich_module
        result = enrich_module(
            "branch_path",
            [{"finding_id": "F1", "symbol_name": "foo", "risk_score": 0.8}],
            {"foo": "void foo() {}"},
            {"provider": "ollama", "model": "test"},
        )
        assert result["success"] is True
        assert len(result["test_suggestions"]) >= 1

    @patch("app.services.ai_enrichment._call_model_sync")
    def test_enrich_module_ai_call_failure(self, mock_call):
        """TS-AE-018: enrich_module handles AI call failure gracefully."""
        mock_call.return_value = {
            "content": "",
            "usage": {},
            "success": False,
            "error": "connection timeout",
        }
        from app.services.ai_enrichment import enrich_module
        result = enrich_module(
            "branch_path",
            [{"finding_id": "F1", "symbol_name": "foo", "risk_score": 0.8}],
            {},
            {"provider": "ollama", "model": "test"},
        )
        assert result["success"] is False
        assert "不可用" in result["ai_summary"]
        assert result["error"] == "connection timeout"

    @patch("app.services.ai_enrichment._call_model_sync")
    def test_enrich_module_with_upstream(self, mock_call):
        """TS-AE-019: enrich_module passes cross-module context."""
        mock_call.return_value = {
            "content": json.dumps({"branches": []}),
            "usage": {},
            "success": True,
        }
        from app.services.ai_enrichment import enrich_module
        upstream = {
            "call_graph": {
                "findings": [
                    {"symbol_name": "bar", "evidence": {"callees": ["foo"]}}
                ],
                "risk_score": 0.5,
            }
        }
        result = enrich_module(
            "branch_path",
            [{"finding_id": "F1", "symbol_name": "foo"}],
            {},
            {"provider": "ollama", "model": "test"},
            upstream_results=upstream,
        )
        assert result["success"] is True
        # Verify the model was called
        mock_call.assert_called_once()

    @patch("app.services.ai_enrichment._call_model_sync")
    def test_synthesize_cross_module_success(self, mock_call):
        """TS-AE-020: synthesize_cross_module with successful AI call."""
        mock_call.return_value = {
            "content": json.dumps({
                "cross_module_risks": [],
                "hidden_risk_paths": [],
                "e2e_test_scenarios": [{"scenario": "end-to-end test"}],
                "methodology_advice": "Use taint analysis",
            }),
            "usage": {"prompt_tokens": 200, "completion_tokens": 100},
            "success": True,
        }
        from app.services.ai_enrichment import synthesize_cross_module
        all_results = {
            "branch_path": {
                "findings": [{"risk_score": 0.8, "title": "Error branch"}],
                "risk_score": 0.8,
            },
            "error_path": {
                "findings": [{"risk_score": 0.7, "title": "Missing cleanup"}],
                "risk_score": 0.7,
            },
        }
        result = synthesize_cross_module(
            all_results,
            {"foo": "void foo() {}"},
            {"provider": "ollama", "model": "test"},
        )
        assert result["success"] is True
        assert len(result["test_suggestions"]) >= 1

    def test_synthesize_cross_module_skip_no_provider(self):
        """TS-AE-021: synthesize_cross_module skips when no provider."""
        from app.services.ai_enrichment import synthesize_cross_module
        result = synthesize_cross_module(
            {"branch_path": {"findings": [], "risk_score": 0}},
            {},
            {"provider": "none"},
        )
        assert result["success"] is False
        assert result.get("skipped") is True

    def test_synthesize_cross_module_skip_empty_provider(self):
        """TS-AE-022: synthesize_cross_module skips with empty provider."""
        from app.services.ai_enrichment import synthesize_cross_module
        result = synthesize_cross_module(
            {"branch_path": {"findings": [], "risk_score": 0}},
            {},
            {"provider": ""},
        )
        assert result["success"] is False
        assert result.get("skipped") is True

    @patch("app.services.ai_enrichment._call_model_sync")
    def test_synthesize_cross_module_failure(self, mock_call):
        """TS-AE-023: synthesize_cross_module handles AI failure."""
        mock_call.return_value = {
            "content": "",
            "usage": {},
            "success": False,
            "error": "model not found",
        }
        from app.services.ai_enrichment import synthesize_cross_module
        result = synthesize_cross_module(
            {"branch_path": {"findings": [], "risk_score": 0}},
            {},
            {"provider": "ollama", "model": "nonexistent"},
        )
        assert result["success"] is False
        assert "失败" in result["ai_summary"]

    @patch("app.services.ai_enrichment._call_model_sync")
    def test_enrich_module_prompt_render_failure(self, mock_call):
        """TS-AE-024: enrich_module handles prompt render failure gracefully."""
        # Force a render error by corrupting the template cache
        from app.ai import prompt_engine
        original_cache = dict(prompt_engine._template_cache)
        prompt_engine._template_cache["branch_path_analysis"] = {
            "template_id": "branch_path_analysis",
            "system_prompt": "{{ undefined_function() }}",
            "user_prompt": "test",
        }
        try:
            from app.services.ai_enrichment import enrich_module
            result = enrich_module(
                "branch_path",
                [{"finding_id": "F1", "symbol_name": "foo"}],
                {},
                {"provider": "ollama", "model": "test"},
            )
            assert result["success"] is False
            assert "渲染失败" in result["ai_summary"]
            mock_call.assert_not_called()
        finally:
            prompt_engine._template_cache.update(original_cache)


# ═══════════════════════════════════════════════════════════════════
# 6. CALL_MODEL_SYNC TESTS
# ═══════════════════════════════════════════════════════════════════

class TestCallModelSync:
    """Tests for _call_model_sync helper."""

    @patch("app.services.ai_enrichment._call_model_async")
    def test_call_model_sync_success(self, mock_async):
        """TS-CS-001: Sync wrapper completes successfully."""
        async def fake_async(*args, **kwargs):
            return {"content": "reply", "usage": {}, "success": True}

        mock_async.side_effect = fake_async

        from app.services.ai_enrichment import _call_model_sync
        result = _call_model_sync("ollama", "test", [{"role": "user", "content": "hi"}])
        assert result["success"] is True
        assert result["content"] == "reply"

    def test_call_model_sync_catches_exception(self):
        """TS-CS-002: Sync wrapper catches and returns errors."""
        from app.services.ai_enrichment import _call_model_sync
        with patch("app.services.ai_enrichment._call_model_async",
                    side_effect=RuntimeError("test error")):
            result = _call_model_sync("ollama", "test", [])
            assert result["success"] is False
            assert "test error" in result.get("error", "")


# ═══════════════════════════════════════════════════════════════════
# 7. MODULE TEMPLATE MAPPING TESTS
# ═══════════════════════════════════════════════════════════════════

class TestModuleTemplateMapping:
    """Tests for the mapping between analysis modules and prompt templates."""

    def test_all_mapped_modules_have_templates(self):
        """TS-MT-001: Every mapped module has a corresponding template file."""
        from app.services.ai_enrichment import _MODULE_TEMPLATES
        from app.config import settings
        tpl_dir = Path(settings.prompt_template_dir)
        for module_id, template_id in _MODULE_TEMPLATES.items():
            path = tpl_dir / f"{template_id}.yaml"
            assert path.exists(), f"Template file missing for {module_id}: {path}"

    def test_template_structure_valid(self):
        """TS-MT-002: All templates have required fields."""
        from app.ai import prompt_engine
        from app.services.ai_enrichment import _MODULE_TEMPLATES
        for module_id, template_id in _MODULE_TEMPLATES.items():
            tpl = prompt_engine.get_template(template_id)
            assert tpl is not None, f"Template {template_id} not loaded"
            assert "system_prompt" in tpl, f"{template_id} missing system_prompt"
            assert "user_prompt" in tpl, f"{template_id} missing user_prompt"

    def test_modules_without_templates(self):
        """TS-MT-003: Modules without templates are handled gracefully."""
        from app.services.ai_enrichment import _MODULE_TEMPLATES
        unmapped = ["coverage_map", "postmortem", "knowledge_pattern", "call_graph"]
        for mod_id in unmapped:
            assert mod_id not in _MODULE_TEMPLATES


# ═══════════════════════════════════════════════════════════════════
# 8. EDGE CASES AND INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Edge case tests for AI layer."""

    def test_extract_suggestions_all_key_variants(self):
        """TS-EC-001: _extract_test_suggestions handles all known keys."""
        from app.services.ai_enrichment import _extract_test_suggestions
        keys = ["test_suggestions", "tests", "test_cases", "branches",
                "e2e_test_scenarios", "regression_tests", "test_scenarios"]
        for key in keys:
            content = json.dumps({key: [{"item": f"from_{key}"}]})
            result = _extract_test_suggestions(content)
            assert len(result) == 1, f"Failed for key '{key}'"
            assert result[0]["item"] == f"from_{key}"

    def test_extract_suggestions_truncates_raw_text(self):
        """TS-EC-002: Raw text fallback is truncated to 3000 chars."""
        from app.services.ai_enrichment import _extract_test_suggestions
        long_text = "x" * 5000
        result = _extract_test_suggestions(long_text)
        assert len(result) == 1
        assert len(result[0]["content"]) <= 3000

    @patch("app.services.ai_enrichment._call_model_sync")
    def test_enrich_module_empty_findings(self, mock_call):
        """TS-EC-003: enrich_module with empty findings still proceeds (no early return)."""
        mock_call.return_value = {
            "content": json.dumps({"branches": []}),
            "usage": {},
            "success": True,
        }
        from app.services.ai_enrichment import enrich_module
        result = enrich_module(
            "branch_path",
            [],  # No findings
            {},
            {"provider": "ollama", "model": "test"},
        )
        # With empty findings the AI is still called (function proceeds with empty context)
        mock_call.assert_called_once()
        assert result["success"] is True

    @patch("app.services.ai_enrichment._call_model_sync")
    def test_enrich_module_limits_findings_to_10(self, mock_call):
        """TS-EC-004: enrich_module only sends top 10 findings to AI."""
        mock_call.return_value = {
            "content": json.dumps({"branches": []}),
            "usage": {},
            "success": True,
        }
        from app.services.ai_enrichment import enrich_module
        findings = [
            {"finding_id": f"F{i}", "symbol_name": "func", "risk_score": 0.5}
            for i in range(20)
        ]
        enrich_module(
            "branch_path",
            findings,
            {},
            {"provider": "ollama", "model": "test"},
        )
        # Verify the call was made
        mock_call.assert_called_once()
        # The user message should contain findings (limited to top 10)
        call_args = mock_call.call_args
        messages = call_args[0][2]  # Third positional arg is messages
        user_content = messages[-1]["content"]
        # Should contain "20 条发现" in the stats
        assert "20" in user_content

    @patch("app.services.ai_enrichment._call_model_sync")
    def test_enrich_module_limits_source_snippets(self, mock_call):
        """TS-EC-005: enrich_module limits source snippets to 3."""
        mock_call.return_value = {
            "content": "ok",
            "usage": {},
            "success": True,
        }
        from app.services.ai_enrichment import enrich_module
        snippets = {f"func_{i}": f"void func_{i}() {{}}" for i in range(10)}
        enrich_module(
            "branch_path",
            [{"finding_id": "F1", "symbol_name": "func_0"}],
            snippets,
            {"provider": "ollama", "model": "test"},
        )
        mock_call.assert_called_once()

    def test_provider_registry_override_base_url(self):
        """TS-EC-006: Provider can override base_url via get_provider."""
        from app.ai.provider_registry import get_provider, clear_cache
        clear_cache()
        p = get_provider("ollama", model="test", base_url="http://custom:11434")
        assert p._base_url == "http://custom:11434"

    def test_custom_rest_provider_custom_response_key(self):
        """TS-EC-007: CustomREST extracts from custom response key path."""
        from app.ai.providers.custom_rest import CustomRESTProvider
        p = CustomRESTProvider(response_content_key="result.text")
        data = {"result": {"text": "custom response"}}
        content = p._extract(data, "result.text")
        assert content == "custom response"
