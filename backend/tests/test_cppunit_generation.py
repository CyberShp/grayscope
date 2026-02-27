"""
Tests for CppUnit test script generation and CMake configuration.

Covers:
  - CppUnit script generation for different risk types
  - CPPUNIT_TEST_SUITE macros
  - CPPUNIT_ASSERT variants
  - CPPUNIT_TEST_SUITE_REGISTRATION
  - CMake generation for CppUnit
  - CppUnit main runner generation
  - GTest fallback still works
"""

import pytest

from app.services.script_generator import (
    generate_script,
    generate_cppunit_script,
    generate_gtest_script,
    generate_python_script,
    _safe_cpp_id,
    _header_path_from_file,
)
from app.services.cmake_generator import (
    generate_cmake,
    generate_cppunit_main,
    generate_cmake_for_run,
)


# ═══════════════════════════════════════════════════════════════════
# 1. CPPUNIT SCRIPT GENERATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestCppUnitGeneration:
    """Tests for CppUnit script generation."""

    def test_generate_cppunit_boundary(self):
        """boundary_miss risk type generates BVA tests."""
        test_case = {
            "risk_type": "boundary_miss",
            "target_function": "check_range",
            "target_file": "validator.c",
            "evidence": {
                "candidates": [0, 1, 99, 100, 101],
                "constraint_expr": "0 <= x <= 100",
            },
            "finding_id": "FR-0001",
        }
        
        script = generate_cppunit_script(test_case)
        
        # Verify CppUnit structure
        assert "CPPUNIT_TEST_SUITE(check_rangeTest)" in script
        assert "CPPUNIT_TEST_SUITE_END();" in script
        assert "CPPUNIT_TEST_SUITE_REGISTRATION(check_rangeTest)" in script
        
        # Verify BVA test methods
        assert "testBVA_min" in script or "Boundary" in script
        assert "CPPUNIT_ASSERT(" in script

    def test_generate_cppunit_cleanup(self):
        """missing_cleanup risk type generates cleanup tests."""
        test_case = {
            "risk_type": "missing_cleanup",
            "target_function": "allocate_buffer",
            "target_file": "memory.c",
            "finding_id": "FR-0002",
        }
        
        script = generate_cppunit_script(test_case)
        
        # Verify cleanup test structure
        assert "CPPUNIT_TEST_SUITE(" in script
        assert "testCleanupOnAllocFailure" in script
        assert "testResourceReleaseOnError" in script
        assert "CPPUNIT_ASSERT_EQUAL(-ENOMEM" in script
        assert "CPPUNIT_TEST_SUITE_REGISTRATION(" in script

    def test_generate_cppunit_race(self):
        """race/lock risk type generates concurrency tests."""
        test_case = {
            "risk_type": "race_condition",
            "target_function": "shared_increment",
            "target_file": "shared.c",
            "finding_id": "FR-0003",
        }
        
        script = generate_cppunit_script(test_case)
        
        # Verify concurrency test structure
        assert "#include <thread>" in script
        assert "#include <atomic>" in script
        assert "testConcurrencyStress" in script
        assert "testNoDeadlock" in script
        assert "testSharedStateConsistency" in script
        assert "CPPUNIT_TEST_SUITE_REGISTRATION(" in script

    def test_generate_cppunit_protocol(self):
        """protocol risk type generates message tests."""
        test_case = {
            "risk_type": "protocol_error",
            "target_function": "parse_message",
            "target_file": "protocol.c",
            "finding_id": "FR-0004",
        }
        
        script = generate_cppunit_script(test_case)
        
        # Verify protocol test structure
        assert "testValidMessage" in script
        assert "testMalformedMessage" in script
        assert "testBoundaryLengthMessage" in script
        assert "testInvalidFieldValue" in script
        assert "CPPUNIT_TEST_SUITE_REGISTRATION(" in script

    def test_cppunit_has_suite_macro(self):
        """Generated script contains CPPUNIT_TEST_SUITE."""
        test_case = {
            "risk_type": "general",
            "target_function": "my_func",
        }
        
        script = generate_cppunit_script(test_case)
        
        assert "CPPUNIT_TEST_SUITE(" in script
        assert "CPPUNIT_TEST(" in script
        assert "CPPUNIT_TEST_SUITE_END();" in script

    def test_cppunit_has_assert(self):
        """Generated script contains CPPUNIT_ASSERT."""
        test_case = {
            "risk_type": "boundary_miss",
            "target_function": "check",
            "evidence": {"candidates": [0, 100]},
        }
        
        script = generate_cppunit_script(test_case)
        
        assert "CPPUNIT_ASSERT" in script

    def test_cppunit_has_registration(self):
        """Generated script contains CPPUNIT_TEST_SUITE_REGISTRATION."""
        test_case = {
            "target_function": "test_func",
        }
        
        script = generate_cppunit_script(test_case)
        
        assert "CPPUNIT_TEST_SUITE_REGISTRATION(" in script

    def test_default_format_is_cppunit(self):
        """Default format is cppunit."""
        test_case = {
            "target_function": "my_func",
        }
        
        # Without format parameter, should default to cppunit
        script = generate_script(test_case)
        
        assert "CPPUNIT_TEST_SUITE" in script
        assert "cppunit/TestFixture.h" in script

    def test_gtest_still_works(self):
        """gtest format still generates GTest code."""
        test_case = {
            "risk_type": "boundary_miss",
            "target_function": "check",
            "evidence": {"candidates": [0, 100]},
        }
        
        script = generate_script(test_case, format="gtest")
        
        assert "gtest/gtest.h" in script
        assert "TEST(" in script
        assert "EXPECT_" in script

    def test_cppunit_inherits_test_fixture(self):
        """Generated class inherits from CppUnit::TestFixture."""
        test_case = {
            "target_function": "my_func",
        }
        
        script = generate_cppunit_script(test_case)
        
        assert ": public CppUnit::TestFixture" in script

    def test_cppunit_has_setup_teardown(self):
        """Generated script has setUp and tearDown methods."""
        test_case = {
            "target_function": "my_func",
        }
        
        script = generate_cppunit_script(test_case)
        
        assert "void setUp() override" in script
        assert "void tearDown() override" in script


# ═══════════════════════════════════════════════════════════════════
# 2. CMAKE GENERATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestCppUnitCMake:
    """Tests for CMake generation for CppUnit."""

    def test_cmake_finds_cppunit(self):
        """CMake includes find_library(CPPUNIT_LIB)."""
        cmake = generate_cmake(
            test_sources=["test_main.cpp"],
            test_framework="cppunit",
        )
        
        assert "find_library(CPPUNIT_LIB cppunit)" in cmake
        assert "find_path(CPPUNIT_INCLUDE cppunit/TestFixture.h)" in cmake

    def test_cmake_links_cppunit(self):
        """target_link_libraries includes cppunit."""
        cmake = generate_cmake(
            test_sources=["test_foo.cpp"],
            test_framework="cppunit",
        )
        
        # Should link cppunit library
        assert "cppunit" in cmake.lower()
        assert "target_link_libraries(" in cmake

    def test_generate_cppunit_main(self):
        """CppUnit main runner has TestRunner."""
        main = generate_cppunit_main()
        
        assert "CppUnit::TestRunner" in main
        assert "TestFactoryRegistry::getRegistry()" in main
        assert "TestResultCollector" in main
        assert "TextOutputter" in main
        assert "XmlOutputter" in main
        assert "test_results.xml" in main

    def test_cmake_for_run_cppunit(self):
        """End-to-end cmake generation for cppunit."""
        cmake = generate_cmake_for_run(
            test_file_names=["test_storage.cpp"],
            workspace_include_dirs=["include"],
            test_framework="cppunit",
        )
        
        # Should have project setup
        assert "cmake_minimum_required" in cmake
        assert "project(" in cmake
        
        # Should include CppUnit find
        assert "CPPUNIT" in cmake
        
        # Should add test executable
        assert "add_executable(" in cmake
        assert "enable_testing()" in cmake
        assert "add_test(" in cmake

    def test_cmake_gtest_alternative(self):
        """CMake generates GTest config when requested."""
        cmake = generate_cmake(
            test_sources=["test_foo.cpp"],
            test_framework="gtest",
        )
        
        assert "find_package(GTest" in cmake
        assert "gtest" in cmake.lower()

    def test_cmake_includes_coverage(self):
        """CMake includes coverage flags."""
        cmake = generate_cmake(
            test_sources=["test.cpp"],
        )
        
        assert "--coverage" in cmake

    def test_cmake_main_entry_for_cppunit(self):
        """CMake adds test_main.cpp for CppUnit."""
        cmake = generate_cmake(
            test_sources=["test_foo.cpp"],
            test_framework="cppunit",
        )
        
        assert "test_main.cpp" in cmake


# ═══════════════════════════════════════════════════════════════════
# 3. HELPER FUNCTION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestHelperFunctions:
    """Tests for helper functions."""

    def test_safe_cpp_id_normal(self):
        """Normal string generates valid C++ identifier."""
        result = _safe_cpp_id("my_function")
        assert result == "my_function"

    def test_safe_cpp_id_special_chars(self):
        """Special characters are replaced with underscore."""
        result = _safe_cpp_id("my-function.v2")
        assert result == "my_function_v2"

    def test_safe_cpp_id_starts_with_digit(self):
        """Leading digit gets underscore prefix."""
        result = _safe_cpp_id("123func")
        assert result == "_123func"

    def test_safe_cpp_id_truncates_long(self):
        """Long names are truncated to 64 chars."""
        long_name = "a" * 100
        result = _safe_cpp_id(long_name)
        assert len(result) == 64

    def test_header_path_from_c_file(self):
        """C file generates matching .h header path."""
        result = _header_path_from_file("src/module.c")
        assert result == "module.h"

    def test_header_path_from_cpp_file(self):
        """CPP file generates matching .h header path."""
        result = _header_path_from_file("src/module.cpp")
        assert result == "module.h"

    def test_header_path_default(self):
        """Empty file generates default header."""
        result = _header_path_from_file("")
        assert result == "target_module.h"


# ═══════════════════════════════════════════════════════════════════
# 4. PYTHON SCRIPT TESTS
# ═══════════════════════════════════════════════════════════════════

class TestPythonScriptGeneration:
    """Tests for Python script generation."""

    def test_python_script_basic(self):
        """Basic Python script generation."""
        test_case = {
            "title": "测试边界值",
            "priority": "P1",
            "test_steps": ["准备测试数据", "调用被测函数", "验证结果"],
            "expected_result": "返回值为0",
        }
        
        script = generate_python_script(test_case)
        
        assert "def test_case():" in script
        assert "测试边界值" in script
        assert "准备测试数据" in script
        assert "返回值为0" in script

    def test_python_format_selection(self):
        """Python format is selected correctly."""
        test_case = {"title": "Test"}
        
        script = generate_script(test_case, format="python")
        
        assert "def test_case():" in script


# ═══════════════════════════════════════════════════════════════════
# 5. EDGE CASES
# ═══════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Edge case tests."""

    def test_empty_test_case(self):
        """Empty test case still generates valid script."""
        test_case = {}
        
        script = generate_cppunit_script(test_case)
        
        # Should still generate valid structure
        assert "CPPUNIT_TEST_SUITE(" in script
        assert "CPPUNIT_TEST_SUITE_REGISTRATION(" in script

    def test_missing_evidence_boundary(self):
        """Boundary test without evidence uses defaults."""
        test_case = {
            "risk_type": "boundary_miss",
            "target_function": "check",
        }
        
        script = generate_cppunit_script(test_case)
        
        # Should still generate boundary tests with default values
        assert "CPPUNIT_TEST(" in script

    def test_special_characters_in_function_name(self):
        """Function name with special chars is sanitized."""
        test_case = {
            "target_function": "my::class::method",
        }
        
        script = generate_cppunit_script(test_case)
        
        # Should have sanitized class name
        assert "my__class__method" in script or "class" not in script

    def test_long_code_evidence_truncated(self):
        """Long code evidence is truncated in comments."""
        test_case = {
            "risk_type": "missing_cleanup",
            "target_function": "test",
            "evidence": {"code": "x" * 5000},
        }
        
        script = generate_cppunit_script(test_case)
        
        # Should generate without error
        assert "CPPUNIT_TEST_SUITE(" in script

    def test_cmake_empty_sources(self):
        """CMake handles empty source list."""
        cmake = generate_cmake(test_sources=[])
        
        assert "cmake_minimum_required" in cmake
        # Should have placeholder
        assert "No test sources" in cmake or "add_custom_target" in cmake
