"""CMakeLists.txt 生成器：为 CppUnit 测试代码生成可编译的 CMake 配置。"""

from __future__ import annotations

from typing import Any


def generate_cmake(
    test_sources: list[str],
    include_dirs: list[str] | None = None,
    link_libraries: list[str] | None = None,
    project_name: str = "grayscope_dt_tests",
    test_framework: str = "cppunit",
) -> str:
    """
    生成 CMakeLists.txt 内容，用于构建 CppUnit 测试可执行文件。

    :param test_sources: 测试源文件列表（如 ["test_storage.cpp", "test_volume.cpp"]）
    :param include_dirs: 头文件搜索路径（相对或绝对）
    :param link_libraries: 链接库（如 gcov）
    :param project_name: 项目名
    :param test_framework: 测试框架，支持 "cppunit" (默认) 或 "gtest"
    :return: CMakeLists.txt 内容
    """
    include_dirs = include_dirs or ["${CMAKE_CURRENT_SOURCE_DIR}", "${CMAKE_CURRENT_SOURCE_DIR}/.."]
    link_libraries = link_libraries or []
    has_c_sources = any(s.endswith(".c") for s in test_sources)
    languages = "C CXX" if has_c_sources else "CXX"
    lines = [
        f"cmake_minimum_required(VERSION 3.14)",
        f"project({project_name} LANGUAGES {languages})",
        "",
        "set(CMAKE_CXX_STANDARD 14)",
        "set(CMAKE_CXX_FLAGS \"${CMAKE_CXX_FLAGS} --coverage -O0 -g\")",
        "",
    ]
    
    if test_framework.lower() == "gtest":
        lines.extend([
            "find_package(GTest QUIET)",
            "if(NOT GTest_FOUND)",
            "  find_library(GTEST_LIB gtest)",
            "  find_library(GTEST_MAIN_LIB gtest_main)",
            "  find_path(GTEST_INCLUDE gtest/gtest.h)",
            "  if(GTEST_LIB AND GTEST_INCLUDE)",
            "    add_library(GTest::gtest UNKNOWN IMPORTED)",
            "    set_target_properties(GTest::gtest PROPERTIES IMPORTED_LOCATION ${GTEST_LIB})",
            "    set_target_properties(GTest::gtest PROPERTIES INTERFACE_INCLUDE_DIRECTORIES ${GTEST_INCLUDE})",
            "  endif()",
            "endif()",
        ])
    else:
        # CppUnit (default)
        lines.extend([
            "# CppUnit 查找",
            "find_library(CPPUNIT_LIB cppunit)",
            "find_path(CPPUNIT_INCLUDE cppunit/TestFixture.h)",
            "if(NOT CPPUNIT_LIB)",
            "  # 尝试 pkg-config",
            "  find_package(PkgConfig QUIET)",
            "  if(PkgConfig_FOUND)",
            "    pkg_check_modules(CPPUNIT cppunit)",
            "  endif()",
            "endif()",
        ])
    
    lines.append("")
    lines.append("include_directories(")
    for d in include_dirs:
        lines.append(f"  {d}")
    lines.append(")")
    lines.append("")

    if test_sources:
        lines.append("# 测试可执行文件")
        lines.append("add_executable(${PROJECT_NAME}")
        # 添加 main 入口文件（CppUnit 需要 TestRunner）
        if test_framework.lower() != "gtest":
            lines.append("  test_main.cpp  # CppUnit TestRunner 入口")
        for src in test_sources:
            lines.append(f"  {src}")
        lines.append(")")
        lines.append("")
        
        if test_framework.lower() == "gtest":
            lines.append("if(TARGET GTest::gtest)")
            lines.append("  target_link_libraries(${PROJECT_NAME} GTest::gtest GTest::gtest_main)")
            lines.append("elseif(GTEST_LIB)")
            lines.append("  target_include_directories(${PROJECT_NAME} PRIVATE ${GTEST_INCLUDE})")
            lines.append("  target_link_libraries(${PROJECT_NAME} ${GTEST_LIB} ${GTEST_MAIN_LIB})")
            lines.append("else()")
            lines.append("  target_link_libraries(${PROJECT_NAME} gtest gtest_main)")
            lines.append("endif()")
        else:
            # CppUnit linking
            lines.append("if(CPPUNIT_LIB)")
            lines.append("  target_include_directories(${PROJECT_NAME} PRIVATE ${CPPUNIT_INCLUDE})")
            lines.append("  target_link_libraries(${PROJECT_NAME} ${CPPUNIT_LIB})")
            lines.append("elseif(CPPUNIT_LIBRARIES)")
            lines.append("  target_include_directories(${PROJECT_NAME} PRIVATE ${CPPUNIT_INCLUDE_DIRS})")
            lines.append("  target_link_libraries(${PROJECT_NAME} ${CPPUNIT_LIBRARIES})")
            lines.append("else()")
            lines.append("  target_link_libraries(${PROJECT_NAME} cppunit)")
            lines.append("endif()")
        
        for lib in link_libraries:
            lines.append(f"target_link_libraries(${{PROJECT_NAME}} {lib})")
        lines.append("")
        lines.append("enable_testing()")
        
        if test_framework.lower() == "gtest":
            lines.append("add_test(NAME ${PROJECT_NAME} COMMAND ${PROJECT_NAME} --gtest_output=xml:${PROJECT_NAME}_results.xml)")
        else:
            lines.append("add_test(NAME ${PROJECT_NAME} COMMAND ${PROJECT_NAME})")
    else:
        lines.append("# 无测试源文件，占位")
        lines.append("add_custom_target(${PROJECT_NAME} ALL echo \"No test sources\")")
    lines.append("")
    return "\n".join(lines)


def generate_cppunit_main() -> str:
    """生成 CppUnit 的 main 入口文件 (test_main.cpp)。"""
    return '''// CppUnit TestRunner 入口
#include <cppunit/TestRunner.h>
#include <cppunit/TestResult.h>
#include <cppunit/TestResultCollector.h>
#include <cppunit/TextOutputter.h>
#include <cppunit/XmlOutputter.h>
#include <cppunit/extensions/TestFactoryRegistry.h>
#include <fstream>

int main(int argc, char* argv[]) {
    CppUnit::TestRunner runner;
    runner.addTest(CppUnit::TestFactoryRegistry::getRegistry().makeTest());

    CppUnit::TestResult controller;
    CppUnit::TestResultCollector result;
    controller.addListener(&result);

    runner.run(controller);

    // 控制台输出
    CppUnit::TextOutputter consoleOutputter(&result, std::cout);
    consoleOutputter.write();

    // XML 输出用于 CI 集成
    std::ofstream xmlFile("test_results.xml");
    CppUnit::XmlOutputter xmlOutputter(&result, xmlFile);
    xmlOutputter.write();

    return result.wasSuccessful() ? 0 : 1;
}
'''


def generate_cmake_for_run(
    test_file_names: list[str],
    workspace_include_dirs: list[str] | None = None,
    workspace_source_files: list[str] | None = None,
    coverage: bool = True,
    test_framework: str = "cppunit",
) -> str:
    """
    为一次测试运行生成 CMakeLists.txt（tests 子目录下使用）。
    
    :param test_file_names: 测试源文件名列表
    :param workspace_include_dirs: 头文件搜索路径
    :param workspace_source_files: 工作区源文件（.c/.cpp 相对路径）
    :param coverage: 是否启用覆盖率
    :param test_framework: 测试框架，默认 "cppunit"
    """
    include_dirs = list(workspace_include_dirs or [".."])
    link_libs = ["gcov"] if coverage else []
    # 测试源在 tests/ 下，工作区源：根下文件用 ../ 前缀；tests/ 下文件相对 tests/ 不加 ..
    all_sources = list(test_file_names)
    if workspace_source_files:
        for s in workspace_source_files:
            if s.startswith("tests/"):
                all_sources.append(s[6:])  # 相对 tests/，如 unity/src/unity.c
            else:
                all_sources.append(f"../{s}")
    return generate_cmake(
        test_sources=all_sources,
        include_dirs=include_dirs,
        link_libraries=link_libs,
        project_name="dt_run",
        test_framework=test_framework,
    )
