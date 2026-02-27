"""测试脚本生成器：从测试用例生成可执行脚本（Python 灰盒占位 或 GTest/Unity C++ DT 代码）。

借鉴成熟 DT 实践：
- 边界值：BVA 法 min / min+1 / nominal / max-1 / max，每点显式断言（EXPECT_* / TEST_ASSERT_*）。
- 错误路径：malloc 失败等通过 wrapper 或 LD_PRELOAD 注入，断言返回值与无泄漏。
- 并发：双线程调用 + join + 对共享状态的断言。
"""

from __future__ import annotations

import json
import re
from typing import Any


# ---- 成熟 DT 模式说明（写入生成脚本头部）----
_DT_HEADER_COMMENT = """// Directed Testing (DT): 目标导向测试，针对边界/错误路径/并发等风险。
// 参考: BVA 边界 min/min+1/nominal/max-1/max；错误路径 malloc 注入 + 返回值/泄漏断言；并发双线程 + 状态断言。
"""


def generate_python_script(test_case: dict[str, Any]) -> str:
    """根据用例生成 Python 测试脚本内容（兼容自研框架风格）。"""
    title = test_case.get("title") or "未命名用例"
    steps = test_case.get("test_steps")
    if isinstance(test_case.get("steps_json"), str):
        try:
            steps = json.loads(test_case["steps_json"])
        except (TypeError, json.JSONDecodeError):
            steps = []
    if not steps and isinstance(test_case.get("preconditions"), list):
        steps = []
    if not steps:
        steps = [f"执行与 {title} 相关的测试步骤"]
    expected = test_case.get("expected_result") or test_case.get("expected") or "通过"
    if isinstance(expected, list):
        expected = "\n".join(str(x) for x in expected)
    priority = (test_case.get("priority") or "P3").split("-")[0]
    lines = [
        '"""',
        f"用例: {title}",
        f"优先级: {priority}",
        '"""',
        "",
        "def test_case():",
        "    # 前置条件与步骤",
    ]
    for i, step in enumerate(steps or [], 1):
        lines.append(f'    # {i}. {step}')
    lines.extend([
        "    # 预期结果",
        f'    # {expected}',
        "    pass  # 请在此实现断言与调用",
        "",
    ])
    return "\n".join(lines)


def _header_path_from_file(target_file: str) -> str:
    """从源文件路径推导被测头文件路径（简单规则：同目录同名 .h）。"""
    if not target_file:
        return "target_module.h"
    base = target_file.replace("\\", "/").rstrip("/")
    if "/" in base:
        base = base.split("/")[-1]
    name = re.sub(r"\.(c|cpp|cc|cxx)$", "", base, flags=re.IGNORECASE)
    return f"{name}.h"


def _safe_cpp_id(s: str) -> str:
    """生成合法 C++ 标识符（测试套件/用例名用）。"""
    if not s:
        return "Unknown"
    out = re.sub(r"[^a-zA-Z0-9_]", "_", s)
    if out and out[0].isdigit():
        out = "_" + out
    return out[:64] if len(out) > 64 else out


def _boundary_candidates(evidence: dict) -> list[Any]:
    """从 evidence 取边界候选值（candidates）。"""
    c = evidence.get("candidates") or []
    if isinstance(c, list):
        return c[:20]
    return []


def _constraint_expr(evidence: dict) -> str:
    """从 evidence 取约束表达式描述。"""
    return (evidence.get("constraint_expr") or "").strip()


def _generate_unity_fixture_script(
    test_case: dict[str, Any],
    suite: str,
    symbol: str,
    header: str,
    finding_id: str,
) -> str:
    """生成纯 Unity Fixture 脚本（不含 GTest）。成熟 DT：错误路径上断言返回值与无泄漏。"""
    lines = [
        "// Unity Fixture DT — 错误路径（malloc 失败等）",
        _DT_HEADER_COMMENT.strip(),
        f"// 来源: finding {finding_id} @ {symbol}",
        "// 成熟做法: malloc wrapper 第 N 次返回 NULL，或 LD_PRELOAD 注入；断言: 返回值==-ENOMEM 且无泄漏。",
        "",
        "extern \"C\" {",
        "#include \"unity_fixture.h\"",
        "}",
        "#include <errno.h>",
        "extern \"C\" {",
        f"#include \"{header}\"",
        "}",
        "",
        f"TEST_GROUP({suite});",
        f"TEST_SETUP({suite}) {{ }}",
        f"TEST_TEAR_DOWN({suite}) {{ }}",
        "",
        f"TEST({suite}, CleanupOnAllocFailure) {{",
        f"    // 1. (可选) 设置 malloc 失败注入，使第二次分配失败",
        f"    // 2. 调用 {symbol}(...) 触发错误路径",
        f"    // 3. 断言: 返回值为 -ENOMEM（或贵项目错误码）",
        f"    // 4. 断言: 已分配资源已释放（无泄漏）",
        f"    int result = 0; /* 替换为实际调用，如 {symbol}(&ctx) */",
        f"    TEST_ASSERT_EQUAL_INT(-ENOMEM, result);  // 或 TEST_ASSERT(result == 预期错误码);",
        "}",
        "",
        f"TEST_GROUP_RUNNER({suite}) {{",
        f"    RUN_TEST_CASE({suite}, CleanupOnAllocFailure);",
        "}",
        "",
        "static void run_all_groups(void) {",
        f"    RUN_TEST_GROUP({suite});",
        "}",
        "",
        "int main(void) {",
        "    return UnityMain(0, (const char**)0, run_all_groups);",
        "}",
    ]
    return "\n".join(lines)


def generate_gtest_script(test_case: dict[str, Any]) -> str:
    """根据用例生成可编译的 GTest C++ 代码（按 risk_type 使用成熟 DT 模板）。"""
    risk_type = test_case.get("category") or test_case.get("risk_type") or ""
    symbol = test_case.get("target_function") or test_case.get("symbol_name") or "target_func"
    target_file = test_case.get("target_file") or test_case.get("file_path") or ""
    evidence = test_case.get("evidence") or {}
    finding_id = test_case.get("source_finding_id") or test_case.get("finding_id") or ""
    title = test_case.get("title") or ""
    steps = test_case.get("test_steps") or []
    if isinstance(test_case.get("steps_json"), str):
        try:
            steps = json.loads(test_case["steps_json"]) or []
        except (TypeError, json.JSONDecodeError):
            pass
    expected = test_case.get("expected_result") or test_case.get("expected") or "通过"
    if isinstance(expected, list):
        expected = " ".join(str(x) for x in expected)

    header = _header_path_from_file(target_file)
    suite = _safe_cpp_id(symbol)
    lines = [
        "// GTest DT — GrayScope 灰盒生成",
        _DT_HEADER_COMMENT.strip(),
        f"// risk_type: {risk_type}",
        f"// 目标: {symbol}",
        "",
        "#include <gtest/gtest.h>",
        "#include <cerrno>",
        "#include <cstdint>",
        "extern \"C\" {",
        f"#include \"{header}\"",
        "}",
        "",
    ]

    if risk_type == "missing_cleanup":
        return _generate_unity_fixture_script(test_case, suite, symbol, header, finding_id)
    if risk_type == "boundary_miss":
        candidates = _boundary_candidates(evidence)
        constraint = _constraint_expr(evidence)
        lines.append(f"// 边界约束: {constraint or '(见 evidence)'}")
        if not candidates:
            candidates = [0, -1, 1]
        # BVA: min, min+1, nominal, max-1, max（成熟 DT 边界五点）
        n = len(candidates)
        for i, val in enumerate(candidates[:10]):
            safe_val = val if isinstance(val, (int, float)) else 0
            if n >= 3 and i == 0:
                bva_label = "BVA_min"
            elif n >= 3 and i == 1:
                bva_label = "BVA_minPlus1"
            elif n >= 3 and i == n - 2:
                bva_label = "BVA_maxMinus1"
            elif n >= 3 and i == n - 1:
                bva_label = "BVA_max"
            elif n >= 3:
                bva_label = "BVA_nominal"
            else:
                bva_label = f"Boundary_{i}"
            name = _safe_cpp_id(f"{bva_label}_{safe_val}")
            lines.append(f"TEST({suite}, {name}) {{")
            lines.append(f"    // 边界值: {safe_val} (约束: {constraint!r})")
            lines.append(f"    int result = 0;  // 替换为: {symbol}({safe_val}) 或实际签名")
            lines.append(f"    EXPECT_GE(result, 0);  // 或 EXPECT_EQ(预期返回值, result);")
            lines.append("}")
            lines.append("")
        if not candidates:
            lines.append(f"TEST({suite}, BoundaryPlaceholder) {{")
            lines.append(f"    // 根据约束 {constraint!r} 填写边界输入与 EXPECT_* 断言")
            lines.append("}")
            lines.append("")
    elif "race" in risk_type or "lock" in risk_type:
        lines.append("#include <thread>")
        lines.append("#include <atomic>")
        lines.append("// 成熟 DT 并发: 双线程调用 + join + 对共享状态断言")
        lines.append(f"TEST({suite}, ConcurrencyStress) {{")
        lines.append(f"    std::atomic<int> done{{0}};")
        lines.append(f"    auto worker = [&]() {{ /* 调用 {symbol} 或相关接口 */ done++; }};")
        lines.append("    std::thread t1(worker), t2(worker);")
        lines.append("    t1.join(); t2.join();")
        lines.append("    EXPECT_EQ(2, done.load());  // 无异常终止则两次均完成");
        lines.append("}")
        lines.append("")
    else:
        lines.append(f"// 用例: {title}")
        for i, step in enumerate(steps[:5], 1):
            lines.append(f"// 步骤{i}: {step}")
        lines.append(f"// 预期: {expected}")
        lines.append(f"TEST({suite}, DefaultCase) {{")
        lines.append(f"    int result = 0;  // 替换为: 调用 {symbol}(...) 并按步骤执行")
        lines.append(f"    EXPECT_TRUE(result >= 0);  // 或 EXPECT_EQ(预期, result);")
        lines.append("}")
        lines.append("")

    if risk_type == "missing_cleanup":
        return _generate_unity_fixture_script(test_case, suite, symbol, header, finding_id)
    return "\n".join(lines).strip()


def generate_cppunit_script(test_case: dict[str, Any]) -> str:
    """根据用例生成 CppUnit C++ 测试代码（按 risk_type 使用成熟 DT 模板）。
    
    生成标准 CppUnit 格式:
    - CPPUNIT_TEST_SUITE / CPPUNIT_TEST / CPPUNIT_TEST_SUITE_END
    - CPPUNIT_ASSERT_EQUAL, CPPUNIT_ASSERT, CPPUNIT_ASSERT_THROW
    - TestFixture 子类 with setUp() / tearDown()
    - CPPUNIT_TEST_SUITE_REGISTRATION
    """
    risk_type = test_case.get("category") or test_case.get("risk_type") or ""
    symbol = test_case.get("target_function") or test_case.get("symbol_name") or "target_func"
    target_file = test_case.get("target_file") or test_case.get("file_path") or ""
    evidence = test_case.get("evidence") or {}
    finding_id = test_case.get("source_finding_id") or test_case.get("finding_id") or ""
    title = test_case.get("title") or ""
    steps = test_case.get("test_steps") or []
    if isinstance(test_case.get("steps_json"), str):
        try:
            steps = json.loads(test_case["steps_json"]) or []
        except (TypeError, json.JSONDecodeError):
            pass
    expected = test_case.get("expected_result") or test_case.get("expected") or "通过"
    if isinstance(expected, list):
        expected = " ".join(str(x) for x in expected)

    header = _header_path_from_file(target_file)
    suite = _safe_cpp_id(symbol) + "Test"
    
    lines = [
        "// CppUnit DT — GrayScope 灰盒生成",
        _DT_HEADER_COMMENT.strip(),
        f"// risk_type: {risk_type}",
        f"// 目标: {symbol}",
        f"// finding_id: {finding_id}",
        "",
        "#include <cppunit/TestFixture.h>",
        "#include <cppunit/extensions/HelperMacros.h>",
        "#include <cerrno>",
        "#include <cstdint>",
        "extern \"C\" {",
        f"#include \"{header}\"",
        "}",
        "",
    ]

    if risk_type == "boundary_miss":
        candidates = _boundary_candidates(evidence)
        constraint = _constraint_expr(evidence)
        if not candidates:
            candidates = [0, -1, 1]
        
        lines.append(f"// 边界约束: {constraint or '(见 evidence)'}")
        lines.append(f"class {suite} : public CppUnit::TestFixture {{")
        lines.append(f"    CPPUNIT_TEST_SUITE({suite});")
        
        test_methods = []
        n = len(candidates)
        for i, val in enumerate(candidates[:10]):
            safe_val = val if isinstance(val, (int, float)) else 0
            if n >= 3 and i == 0:
                bva_label = "BVA_min"
            elif n >= 3 and i == 1:
                bva_label = "BVA_minPlus1"
            elif n >= 3 and i == n - 2:
                bva_label = "BVA_maxMinus1"
            elif n >= 3 and i == n - 1:
                bva_label = "BVA_max"
            elif n >= 3:
                bva_label = "BVA_nominal"
            else:
                bva_label = f"Boundary_{i}"
            method_name = f"test{_safe_cpp_id(bva_label)}_{abs(int(safe_val)) if isinstance(safe_val, (int, float)) else 0}"
            test_methods.append((method_name, safe_val, constraint))
            lines.append(f"    CPPUNIT_TEST({method_name});")
        
        lines.append(f"    CPPUNIT_TEST_SUITE_END();")
        lines.append("")
        lines.append("public:")
        lines.append("    void setUp() override {}")
        lines.append("    void tearDown() override {}")
        lines.append("")
        
        for method_name, val, constraint in test_methods:
            lines.append(f"    void {method_name}() {{")
            lines.append(f"        // 边界值: {val} (约束: {constraint!r})")
            lines.append(f"        int result = 0;  // 替换为: {symbol}({val}) 或实际签名")
            lines.append(f"        CPPUNIT_ASSERT(result >= 0);  // 或 CPPUNIT_ASSERT_EQUAL(预期, result);")
            lines.append("    }")
            lines.append("")
        
        lines.append("};")
        lines.append(f"CPPUNIT_TEST_SUITE_REGISTRATION({suite});")
        
    elif risk_type == "missing_cleanup":
        lines.append("// 成熟 DT: 错误路径上断言返回值与无泄漏")
        lines.append("// 做法: malloc wrapper 第 N 次返回 NULL，或 LD_PRELOAD 注入")
        lines.append("")
        lines.append(f"class {suite} : public CppUnit::TestFixture {{")
        lines.append(f"    CPPUNIT_TEST_SUITE({suite});")
        lines.append(f"    CPPUNIT_TEST(testCleanupOnAllocFailure);")
        lines.append(f"    CPPUNIT_TEST(testResourceReleaseOnError);")
        lines.append(f"    CPPUNIT_TEST_SUITE_END();")
        lines.append("")
        lines.append("public:")
        lines.append("    void setUp() override {}")
        lines.append("    void tearDown() override {}")
        lines.append("")
        lines.append("    void testCleanupOnAllocFailure() {")
        lines.append(f"        // 1. 设置 malloc 失败注入，使第 N 次分配失败")
        lines.append(f"        // 2. 调用 {symbol}(...) 触发错误路径")
        lines.append(f"        // 3. 断言: 返回值为 -ENOMEM（或项目错误码）")
        lines.append(f"        int result = 0;  // 替换为: {symbol}(&ctx)")
        lines.append(f"        CPPUNIT_ASSERT_EQUAL(-ENOMEM, result);")
        lines.append("    }")
        lines.append("")
        lines.append("    void testResourceReleaseOnError() {")
        lines.append(f"        // 断言: 所有已分配资源已释放（无泄漏）")
        lines.append(f"        // 可使用 valgrind 或自定义 alloc tracker 验证")
        lines.append(f"        CPPUNIT_ASSERT_MESSAGE(\"资源已正确释放\", true);")
        lines.append("    }")
        lines.append("};")
        lines.append(f"CPPUNIT_TEST_SUITE_REGISTRATION({suite});")
        
    elif "race" in risk_type or "lock" in risk_type:
        lines.append("#include <thread>")
        lines.append("#include <atomic>")
        lines.append("#include <mutex>")
        lines.append("// 成熟 DT 并发: 双线程调用 + join + 对共享状态断言")
        lines.append("")
        lines.append(f"class {suite} : public CppUnit::TestFixture {{")
        lines.append(f"    CPPUNIT_TEST_SUITE({suite});")
        lines.append(f"    CPPUNIT_TEST(testConcurrencyStress);")
        lines.append(f"    CPPUNIT_TEST(testNoDeadlock);")
        lines.append(f"    CPPUNIT_TEST(testSharedStateConsistency);")
        lines.append(f"    CPPUNIT_TEST_SUITE_END();")
        lines.append("")
        lines.append("public:")
        lines.append("    void setUp() override {}")
        lines.append("    void tearDown() override {}")
        lines.append("")
        lines.append("    void testConcurrencyStress() {")
        lines.append("        std::atomic<int> done{0};")
        lines.append(f"        auto worker = [&]() {{ /* 调用 {symbol} 或相关接口 */ done++; }};")
        lines.append("        std::thread t1(worker), t2(worker);")
        lines.append("        t1.join(); t2.join();")
        lines.append("        CPPUNIT_ASSERT_EQUAL(2, done.load());  // 无异常终止则两次均完成")
        lines.append("    }")
        lines.append("")
        lines.append("    void testNoDeadlock() {")
        lines.append("        // 设置超时，验证不发生死锁")
        lines.append("        std::atomic<bool> finished{false};")
        lines.append(f"        std::thread t([&]() {{ /* 调用 {symbol} */ finished = true; }});")
        lines.append("        t.join();")
        lines.append("        CPPUNIT_ASSERT_MESSAGE(\"操作应在合理时间内完成\", finished.load());")
        lines.append("    }")
        lines.append("")
        lines.append("    void testSharedStateConsistency() {")
        lines.append("        // 验证共享状态在并发访问后保持一致")
        lines.append(f"        // 替换为: 检查 {symbol} 相关的共享变量")
        lines.append("        CPPUNIT_ASSERT(true);  // 替换为实际断言")
        lines.append("    }")
        lines.append("};")
        lines.append(f"CPPUNIT_TEST_SUITE_REGISTRATION({suite});")
        
    elif "protocol" in risk_type or "message" in risk_type or "packet" in risk_type:
        lines.append("// 协议/报文测试: 构造各种报文场景验证处理逻辑")
        lines.append("")
        lines.append(f"class {suite} : public CppUnit::TestFixture {{")
        lines.append(f"    CPPUNIT_TEST_SUITE({suite});")
        lines.append(f"    CPPUNIT_TEST(testValidMessage);")
        lines.append(f"    CPPUNIT_TEST(testMalformedMessage);")
        lines.append(f"    CPPUNIT_TEST(testBoundaryLengthMessage);")
        lines.append(f"    CPPUNIT_TEST(testInvalidFieldValue);")
        lines.append(f"    CPPUNIT_TEST_SUITE_END();")
        lines.append("")
        lines.append("public:")
        lines.append("    void setUp() override {}")
        lines.append("    void tearDown() override {}")
        lines.append("")
        lines.append("    void testValidMessage() {")
        lines.append(f"        // 构造有效报文，验证 {symbol} 正常处理")
        lines.append("        // uint8_t msg[] = {{...}};")
        lines.append(f"        // int result = {symbol}(msg, sizeof(msg));")
        lines.append("        CPPUNIT_ASSERT_MESSAGE(\"有效报文应处理成功\", true);")
        lines.append("    }")
        lines.append("")
        lines.append("    void testMalformedMessage() {")
        lines.append("        // 构造畸形报文（截断/字段缺失）")
        lines.append(f"        // 预期: {symbol} 返回错误码，不崩溃")
        lines.append("        CPPUNIT_ASSERT_MESSAGE(\"畸形报文应返回错误\", true);")
        lines.append("    }")
        lines.append("")
        lines.append("    void testBoundaryLengthMessage() {")
        lines.append("        // 报文长度为边界值（0, 1, max-1, max, max+1）")
        lines.append("        CPPUNIT_ASSERT_MESSAGE(\"边界长度报文处理正确\", true);")
        lines.append("    }")
        lines.append("")
        lines.append("    void testInvalidFieldValue() {")
        lines.append("        // 字段值超出有效范围")
        lines.append("        CPPUNIT_ASSERT_MESSAGE(\"无效字段值应被拒绝\", true);")
        lines.append("    }")
        lines.append("};")
        lines.append(f"CPPUNIT_TEST_SUITE_REGISTRATION({suite});")
        
    else:
        # 默认通用模板
        lines.append(f"// 用例: {title}")
        for i, step in enumerate(steps[:5], 1):
            lines.append(f"// 步骤{i}: {step}")
        lines.append(f"// 预期: {expected}")
        lines.append("")
        lines.append(f"class {suite} : public CppUnit::TestFixture {{")
        lines.append(f"    CPPUNIT_TEST_SUITE({suite});")
        lines.append(f"    CPPUNIT_TEST(testDefaultCase);")
        lines.append(f"    CPPUNIT_TEST_SUITE_END();")
        lines.append("")
        lines.append("public:")
        lines.append("    void setUp() override {}")
        lines.append("    void tearDown() override {}")
        lines.append("")
        lines.append("    void testDefaultCase() {")
        lines.append(f"        // 调用 {symbol}(...) 并按步骤执行")
        lines.append("        int result = 0;  // 替换为实际调用")
        lines.append("        CPPUNIT_ASSERT(result >= 0);  // 或 CPPUNIT_ASSERT_EQUAL(预期, result);")
        lines.append("    }")
        lines.append("};")
        lines.append(f"CPPUNIT_TEST_SUITE_REGISTRATION({suite});")

    return "\n".join(lines).strip()


def generate_script(test_case: dict[str, Any], format: str = "cppunit") -> str:
    """统一入口：按 format 生成 Python 或 CppUnit C++ 脚本。默认使用 CppUnit。"""
    if format and format.lower() in ("python", "py"):
        return generate_python_script(test_case)
    if format and format.lower() in ("gtest", "googletest"):
        out = generate_gtest_script(test_case)
        return ensure_unity_test_groups(out)
    # 默认使用 CppUnit
    return generate_cppunit_script(test_case)


def ensure_unity_test_groups(script: str) -> str:
    """
    若脚本使用 Unity/Unity Fixture 的 TEST(Group, Name) 宏但未定义 TEST_GROUP(Group)，
    则自动在首个 TEST 前注入 TEST_GROUP，避免编译报错「was not declared in this scope」。
    适用于任意项目中使用 Unity 的用例。
    """
    if not script or "TEST(" not in script:
        return script
    # 判断是否为 Unity 系（unity.h / unity_fixture.h）
    is_unity = "unity_fixture.h" in script or "unity.h" in script
    if not is_unity:
        return script
    # 已有 TEST_GROUP 则不再注入
    if "TEST_GROUP(" in script:
        return script
    # 收集所有 TEST(Group, Name) 中的 Group（按出现顺序去重）
    groups = []
    seen = set()
    for m in re.finditer(r"TEST\s*\(\s*([^,)+]+)\s*,\s*", script):
        g = m.group(1).strip()
        if g and g not in seen:
            seen.add(g)
            groups.append(g)
    if not groups:
        return script
    # Unity Fixture 需要 TEST_GROUP 声明 + 每个 Group 的 SETUP/TEAR_DOWN 定义（否则未声明报错）
    inject_lines = "\n".join(f"TEST_GROUP({g});" for g in groups) + "\n\n"
    inject_lines += "\n".join(
        f"TEST_SETUP({g}) {{ }}\nTEST_TEAR_DOWN({g}) {{ }}"
        for g in groups
    ) + "\n\n"
    # 找最后一个 #include 行之后的位置
    last_include = 0
    for m in re.finditer(r"^\s*#\s*include\s+[^\n]+", script, re.MULTILINE):
        last_include = m.end()
    if last_include == 0:
        # 没有 #include 则放在文件开头
        return inject_lines + script
    return script[:last_include] + "\n" + inject_lines + script[last_include:]
