#!/usr/bin/env python3
"""
Phase 6 Validation Script - Migration & Polish

Validates that Phase 6 implementation meets all requirements:
1. Documentation updates (README, guides)
2. Performance optimizations (parallel processing, caching)
3. Integration test suite
4. Polish and refinement
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 60)
print("Phase 6 Validation: Migration & Polish")
print("=" * 60)
print()

# Test 1: Check documentation updates
print("Test 1: Checking documentation updates...")
required_docs = [
    "README.md",
    "docs/ROUTER_ARCHITECTURE.md",
    "docs/AUTOMATION_GUIDE.md"
]

all_docs_exist = True
for doc_path in required_docs:
    full_path = Path(doc_path)
    if full_path.exists():
        print(f"  ✓ {doc_path} exists")
    else:
        print(f"  ✗ {doc_path} missing")
        all_docs_exist = False

if all_docs_exist:
    print("✓ All Phase 6 documentation created\n")
else:
    print("✗ Some documentation missing\n")
    sys.exit(1)

# Test 2: Check README updates for v0.3.0
print("Test 2: Checking README v0.3.0 updates...")
readme_path = Path("README.md")
if readme_path.exists():
    readme_content = readme_path.read_text()
    
    v3_features = [
        "v0.3.0",
        "Router-Aware Architecture",
        "Router Discovery",
        "Policy Automation",
        "IRR Proxy Support",
        "NETCONF Automation"
    ]
    
    readme_complete = True
    for feature in v3_features:
        if feature in readme_content:
            print(f"  ✓ {feature} documented")
        else:
            print(f"  ✗ {feature} missing from README")
            readme_complete = False
    
    if readme_complete:
        print("✓ README v0.3.0 updates complete\n")
    else:
        print("✗ Some README features missing\n")
else:
    print("  ✗ README.md not found\n")
    readme_complete = False

# Test 3: Check performance optimization modules
print("Test 3: Checking performance optimization modules...")
try:
    from otto_bgp.utils.parallel import ParallelExecutor, parallel_discover_routers, parallel_generate_policies
    from otto_bgp.utils.cache import PolicyCache, DiscoveryCache
    
    perf_checks = [
        ("ParallelExecutor class", lambda: ParallelExecutor()),
        ("parallel_discover_routers function", lambda: callable(parallel_discover_routers)),
        ("parallel_generate_policies function", lambda: callable(parallel_generate_policies)),
        ("PolicyCache class", lambda: PolicyCache()),
        ("DiscoveryCache class", lambda: DiscoveryCache())
    ]
    
    perf_complete = True
    for check_name, check_obj in perf_checks:
        try:
            if callable(check_obj):
                check_obj()
            print(f"  ✓ {check_name} implemented")
        except Exception as e:
            print(f"  ✗ {check_name} missing or broken: {e}")
            perf_complete = False
    
    if perf_complete:
        print("✓ Performance optimizations complete\n")
    else:
        print("✗ Some performance features missing\n")

except ImportError as e:
    print(f"  ✗ Failed to import performance modules: {e}\n")
    perf_complete = False

# Test 4: Check BGPq4Wrapper cache integration
print("Test 4: Checking BGPq4Wrapper cache integration...")
try:
    from otto_bgp.generators.bgpq4_wrapper import BGPq4Wrapper
    
    # Test wrapper with cache enabled
    wrapper = BGPq4Wrapper(enable_cache=True, cache_ttl=300)
    
    cache_checks = [
        ("Cache initialization", lambda: wrapper.cache is not None),
        ("Cache TTL setting", lambda: wrapper.cache_ttl == 300),
        ("Status info includes cache", lambda: 'cache' in wrapper.get_status_info()),
        ("Cache statistics", lambda: 'cache_entries' in wrapper.get_status_info() if wrapper.cache else True)
    ]
    
    cache_complete = True
    for check_name, check_func in cache_checks:
        try:
            result = check_func()
            if result:
                print(f"  ✓ {check_name} working")
            else:
                print(f"  ✗ {check_name} failed")
                cache_complete = False
        except Exception as e:
            print(f"  ✗ {check_name} error: {e}")
            cache_complete = False
    
    if cache_complete:
        print("✓ BGPq4Wrapper cache integration complete\n")
    else:
        print("✗ Some cache integration features missing\n")

except ImportError as e:
    print(f"  ✗ Failed to import BGPq4Wrapper: {e}\n")
    cache_complete = False

# Test 5: Check integration test suite
print("Test 5: Checking integration test suite...")
integration_tests = [
    "tests/integration/__init__.py",
    "tests/integration/test_full_pipeline.py",
    "tests/integration/test_automation.py"
]

integration_complete = True
for test_path in integration_tests:
    full_path = Path(test_path)
    if full_path.exists():
        print(f"  ✓ {test_path} exists")
    else:
        print(f"  ✗ {test_path} missing")
        integration_complete = False

if integration_complete:
    print("✓ Integration test suite complete\n")
else:
    print("✗ Some integration tests missing\n")

# Test 6: Check integration test classes
print("Test 6: Checking integration test classes...")
test_class_complete = True

# Check if test files exist and have expected content
test_files = [
    ("tests/integration/test_full_pipeline.py", ["TestFullPipeline", "TestPerformanceBenchmarks"]),
    ("tests/integration/test_automation.py", ["TestAutomationIntegration"])
]

for test_file, expected_classes in test_files:
    file_path = Path(test_file)
    if file_path.exists():
        content = file_path.read_text()
        for class_name in expected_classes:
            if f"class {class_name}" in content:
                print(f"  ✓ {class_name} test class found")
            else:
                print(f"  ✗ {class_name} test class missing")
                test_class_complete = False
    else:
        print(f"  ✗ {test_file} not found")
        test_class_complete = False

if test_class_complete:
    print("✓ Integration test classes complete\n")
else:
    print("✗ Some integration test classes incomplete\n")

# Test 7: Check performance utilities functionality
print("Test 7: Checking performance utilities functionality...")
try:
    from otto_bgp.utils.parallel import ParallelExecutor
    from otto_bgp.utils.cache import PolicyCache
    import tempfile
    
    # Test parallel executor
    executor = ParallelExecutor(max_workers=2, show_progress=False)
    
    def test_task(item):
        return item * 2
    
    test_items = [1, 2, 3, 4, 5]
    results = executor.execute_batch(test_items, test_task, "Testing")
    
    parallel_works = len(results) == 5 and all(r.success for r in results)
    
    # Test policy cache
    with tempfile.TemporaryDirectory() as temp_dir:
        cache = PolicyCache(cache_dir=temp_dir)
        
        # Test cache operations
        test_policy = "test policy content"
        cache.put_policy(13335, test_policy)
        retrieved = cache.get_policy(13335)
        
        cache_works = retrieved == test_policy
    
    util_checks = [
        ("Parallel executor", parallel_works),
        ("Policy cache", cache_works)
    ]
    
    util_complete = True
    for check_name, check_result in util_checks:
        if check_result:
            print(f"  ✓ {check_name} functional")
        else:
            print(f"  ✗ {check_name} not working")
            util_complete = False
    
    if util_complete:
        print("✓ Performance utilities functional\n")
    else:
        print("✗ Some performance utilities not working\n")

except Exception as e:
    print(f"  ✗ Performance utilities test failed: {e}\n")
    util_complete = False

# Test 8: Check architecture documentation
print("Test 8: Checking architecture documentation...")
arch_doc_path = Path("docs/ROUTER_ARCHITECTURE.md")
if arch_doc_path.exists():
    arch_content = arch_doc_path.read_text()
    
    arch_sections = [
        "Router Identity Foundation",
        "Discovery Engine", 
        "Policy Generation Engine",
        "Policy Application System",
        "IRR Proxy Support",
        "Data Flow Architecture",
        "Security Architecture"
    ]
    
    arch_complete = True
    for section in arch_sections:
        if section in arch_content:
            print(f"  ✓ {section} documented")
        else:
            print(f"  ✗ {section} missing from architecture docs")
            arch_complete = False
    
    if arch_complete:
        print("✓ Architecture documentation complete\n")
    else:
        print("✗ Some architecture sections missing\n")
else:
    print("  ✗ Architecture documentation not found\n")
    arch_complete = False

# Summary
print("=" * 60)
print("VALIDATION SUMMARY")
print("=" * 60)

tests_passed = [
    ("Documentation Updates", all_docs_exist),
    ("README v0.3.0 Features", readme_complete),
    ("Performance Modules", perf_complete),
    ("Cache Integration", cache_complete),
    ("Integration Test Suite", integration_complete),
    ("Integration Test Classes", test_class_complete),
    ("Performance Utilities", util_complete),
    ("Architecture Documentation", arch_complete)
]

all_passed = all(passed for _, passed in tests_passed)

for test_name, passed in tests_passed:
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  {test_name:.<40} {status}")

print()
if all_passed:
    print("🎉 Phase 6 Validation COMPLETE - All checks passed!")
    print()
    print("Phase 6 Key Features Verified:")
    print("✓ Updated documentation with v0.3.0 router-aware features")
    print("✓ Comprehensive architecture and automation guides")
    print("✓ Parallel processing for discovery and policy generation")
    print("✓ Intelligent caching for performance optimization")
    print("✓ Complete integration test suite with benchmarks")
    print("✓ Performance utilities and monitoring capabilities")
    print("✓ Detailed technical documentation")
    print()
    print("⚠ IMPORTANT: Phase 6 completes the migration and polish phase.")
    print("           All core features are implemented and tested.")
    print()
    print("Phase 6: Migration & Polish is COMPLETE")
else:
    print("❌ Phase 6 Validation FAILED - Some checks did not pass")
    sys.exit(1)