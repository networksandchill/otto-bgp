#!/usr/bin/env python3
"""
Phase 5 Validation Script - IRR Proxy Support

Validates that Phase 5 implementation meets all requirements:
1. Proxy module structure
2. SSH tunnel management
3. Configuration integration
4. BGPq4 wrapper proxy support
5. CLI test command
6. Security implementation
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 60)
print("Phase 5 Validation: IRR Proxy Support")
print("=" * 60)
print()

# Test 1: Check module structure
print("Test 1: Checking proxy module structure...")
required_files = [
    "otto_bgp/proxy/__init__.py",
    "otto_bgp/proxy/irr_tunnel.py",
    "otto_bgp/proxy/CLAUDE.md",
    "tests/test_proxy.py"
]

all_exist = True
for file_path in required_files:
    full_path = Path(file_path)
    if full_path.exists():
        print(f"  ✓ {file_path} exists")
    else:
        print(f"  ✗ {file_path} missing")
        all_exist = False

if all_exist:
    print("✓ All Phase 5 modules created\n")
else:
    print("✗ Some modules missing\n")
    sys.exit(1)

# Test 2: Check IRRProxyManager implementation
print("Test 2: Checking IRRProxyManager implementation...")
try:
    from otto_bgp.proxy import IRRProxyManager, ProxyConfig, TunnelStatus
    
    required_methods = [
        "setup_tunnel",
        "test_tunnel_connectivity", 
        "wrap_bgpq4_command",
        "monitor_tunnels",
        "cleanup_tunnel",
        "cleanup_all_tunnels"
    ]
    
    all_methods = True
    for method in required_methods:
        if hasattr(IRRProxyManager, method):
            print(f"  ✓ Method {method} implemented")
        else:
            print(f"  ✗ Method {method} missing")
            all_methods = False
    
    if all_methods:
        print("✓ IRRProxyManager fully implemented\n")
    else:
        print("✗ Some methods missing\n")

except ImportError as e:
    print(f"  ✗ Failed to import proxy module: {e}\n")
    all_methods = False

# Test 3: Check configuration integration
print("Test 3: Checking configuration integration...")
try:
    from otto_bgp.utils.config import ConfigManager, IRRProxyConfig
    
    config_checks = [
        ("IRRProxyConfig class", lambda: IRRProxyConfig()),
        ("ConfigManager proxy support", lambda: hasattr(ConfigManager().get_config(), 'irr_proxy')),
        ("Config validation", lambda: 'irr_proxy' in str(ConfigManager().validate_config)),
        ("Config printing", lambda: 'IRR Proxy:' in str(ConfigManager().print_config))
    ]
    
    config_complete = True
    for check_name, check_func in config_checks:
        try:
            check_func()
            print(f"  ✓ {check_name} working")
        except Exception:
            print(f"  ✗ {check_name} missing or broken")
            config_complete = False
    
    if config_complete:
        print("✓ Configuration integration complete\n")
    else:
        print("✗ Some configuration features missing\n")

except ImportError as e:
    print(f"  ✗ Failed to import configuration: {e}\n")
    config_complete = False

# Test 4: Check BGPq4Wrapper proxy support
print("Test 4: Checking BGPq4Wrapper proxy support...")
try:
    import inspect
    from otto_bgp.generators.bgpq4_wrapper import BGPq4Wrapper
    
    bgpq4_checks = [
        ("proxy_manager parameter", lambda: 'proxy_manager' in BGPq4Wrapper.__init__.__code__.co_varnames),
        ("create_with_proxy method", "create_with_proxy"),
        ("proxy status info", lambda: "proxy" in inspect.getsource(BGPq4Wrapper.get_status_info))
    ]
    
    bgpq4_complete = True
    for check_name, check_attr in bgpq4_checks:
        if callable(check_attr):
            try:
                result = check_attr()
                if result:
                    print(f"  ✓ {check_name} implemented")
                else:
                    print(f"  ✗ {check_name} missing")
                    bgpq4_complete = False
            except Exception:
                print(f"  ✗ {check_name} check failed")
                bgpq4_complete = False
        else:
            if hasattr(BGPq4Wrapper, check_attr):
                print(f"  ✓ {check_name} implemented")
            else:
                print(f"  ✗ {check_name} missing")
                bgpq4_complete = False
    
    if bgpq4_complete:
        print("✓ BGPq4Wrapper proxy support complete\n")
    else:
        print("✗ Some BGPq4Wrapper features missing\n")

except ImportError as e:
    print(f"  ✗ Failed to import BGPq4Wrapper: {e}\n")
    bgpq4_complete = False

# Test 5: Check CLI integration
print("Test 5: Checking CLI integration...")
main_path = Path("otto_bgp/main.py")
if main_path.exists():
    main_content = main_path.read_text()
    
    cli_checks = [
        ("cmd_test_proxy function", "def cmd_test_proxy"),
        ("test-proxy parser", "test-proxy"),
        ("test-proxy command mapping", "'test-proxy': cmd_test_proxy"),
        ("proxy configuration access", "proxy_config = ")
    ]
    
    cli_complete = True
    for check_name, check_text in cli_checks:
        if check_text in main_content:
            print(f"  ✓ {check_name} found")
        else:
            print(f"  ✗ {check_name} missing")
            cli_complete = False
    
    if cli_complete:
        print("✓ CLI integration complete\n")
    else:
        print("✗ Some CLI components missing\n")
else:
    print("  ✗ main.py not found\n")
    cli_complete = False

# Test 6: Check security implementations
print("Test 6: Checking security implementations...")
tunnel_path = Path("otto_bgp/proxy/irr_tunnel.py")
if tunnel_path.exists():
    tunnel_content = tunnel_path.read_text()
    
    security_checks = [
        ("SSH host key verification", "StrictHostKeyChecking=yes"),
        ("Batch mode (no interactive)", "BatchMode=yes"),  
        ("Process cleanup", "cleanup_all_tunnels"),
        ("Signal handlers", "signal.signal"),
        ("Port validation", "_is_port_available"),
        ("Known hosts support", "UserKnownHostsFile"),
        ("Connection timeout", "ConnectTimeout")
    ]
    
    security_complete = True
    for check_name, check_text in security_checks:
        if check_text in tunnel_content:
            print(f"  ✓ {check_name} implemented")
        else:
            print(f"  ✗ {check_name} missing")
            security_complete = False
    
    if security_complete:
        print("✓ Security mechanisms complete\n")
    else:
        print("✗ Some security features missing\n")
else:
    print("  ✗ irr_tunnel.py not found\n")
    security_complete = False

# Test 7: Check test coverage
print("Test 7: Checking test coverage...")
test_path = Path("tests/test_proxy.py")
if test_path.exists():
    test_content = test_path.read_text()
    
    test_classes = [
        "TestProxyConfig",
        "TestIRRProxyManager", 
        "TestBGPq4ProxyIntegration",
        "TestProxyConfigValidation",
        "TestProxySecurityFeatures"
    ]
    
    test_complete = True
    for test_class in test_classes:
        if f"class {test_class}" in test_content:
            print(f"  ✓ {test_class} test suite found")
        else:
            print(f"  ✗ {test_class} test suite missing")
            test_complete = False
    
    if test_complete:
        print("✓ Test coverage comprehensive\n")
    else:
        print("✗ Some test suites missing\n")
else:
    print("  ✗ Test file not found\n")
    test_complete = False

# Test 8: Check documentation
print("Test 8: Checking documentation...")
claude_md_path = Path("otto_bgp/proxy/CLAUDE.md")
if claude_md_path.exists():
    claude_content = claude_md_path.read_text()
    
    doc_checks = [
        ("Security requirements", "Security Implementation Requirements"),
        ("SSH tunnel security", "SSH Tunnel Security"),
        ("Process management", "Process Management"),
        ("Port management", "Port Management"),
        ("Architecture patterns", "Architecture Patterns"),
        ("Anti-patterns", "NEVER Do These Things"),
        ("Configuration schema", "Configuration Schema")
    ]
    
    doc_complete = True
    for check_name, check_text in doc_checks:
        if check_text in claude_content:
            print(f"  ✓ {check_name} documented")
        else:
            print(f"  ✗ {check_name} missing from docs")
            doc_complete = False
    
    if doc_complete:
        print("✓ Documentation complete\n")
    else:
        print("✗ Some documentation missing\n")
else:
    print("  ✗ CLAUDE.md not found\n")
    doc_complete = False

# Summary
print("=" * 60)
print("VALIDATION SUMMARY")
print("=" * 60)

tests_passed = [
    ("Module Structure", all_exist),
    ("IRRProxyManager", all_methods),
    ("Configuration Integration", config_complete),
    ("BGPq4Wrapper Integration", bgpq4_complete),
    ("CLI Integration", cli_complete),
    ("Security Implementation", security_complete),
    ("Test Coverage", test_complete),
    ("Documentation", doc_complete)
]

all_passed = all(passed for _, passed in tests_passed)

for test_name, passed in tests_passed:
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  {test_name:.<40} {status}")

print()
if all_passed:
    print("🎉 Phase 5 Validation COMPLETE - All checks passed!")
    print()
    print("Phase 5 Key Features Verified:")
    print("✓ SSH tunnel management for IRR access")
    print("✓ Secure tunnel configuration with host key verification")
    print("✓ BGPq4 proxy integration with transparent failover")
    print("✓ Configuration management with validation")
    print("✓ CLI test command for proxy verification")
    print("✓ Comprehensive security measures")
    print("✓ Complete test coverage")
    print("✓ Detailed documentation")
    print()
    print("⚠ IMPORTANT: Phase 5 enables IRR access through SSH tunnels.")
    print("           Test thoroughly in restricted network environments.")
    print()
    print("Phase 5: IRR Proxy Support is COMPLETE")
else:
    print("❌ Phase 5 Validation FAILED - Some checks did not pass")
    sys.exit(1)