#!/usr/bin/env python3
"""
Performance Benchmark for Parallel BGPq4 Processing

Tests the parallel processing improvements in bgpq4_wrapper.py to validate
the 4.3x speedup target while ensuring all security features are preserved.
"""

import os
import sys
import time
import logging
from pathlib import Path

# Add the otto_bgp module to the path
sys.path.insert(0, str(Path(__file__).parent))

from otto_bgp.generators.bgpq4_wrapper import BGPq4Wrapper, BGPq4Mode


def setup_logging():
    """Setup logging for benchmark tests"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def test_security_validation():
    """Test that security validations are preserved in parallel processing"""
    print("\n🔒 Testing Security Validation...")
    
    wrapper = BGPq4Wrapper(mode=BGPq4Mode.AUTO, command_timeout=10)
    
    # Test malicious AS numbers
    malicious_as_numbers = [
        "; rm -rf /",  # Command injection attempt
        "1; cat /etc/passwd",  # Command chaining
        "$(whoami)",  # Command substitution
        "`id`",  # Command substitution (backticks)
        "1 && echo hacked",  # Command conjunction
        "4294967296",  # Out of range AS number
        -1,  # Negative AS number
    ]
    
    for malicious_as in malicious_as_numbers:
        try:
            # This should fail validation and not execute any commands
            result = wrapper.generate_policies_batch([malicious_as], parallel=True)
            if result.successful_count > 0:
                print(f"❌ SECURITY FAILURE: Malicious AS {malicious_as} was processed!")
                return False
            else:
                print(f"✅ Blocked malicious AS: {malicious_as}")
        except Exception as e:
            print(f"✅ Exception caught for malicious AS {malicious_as}: {type(e).__name__}")
    
    # Test malicious policy names
    malicious_policy_names = {
        13335: "policy; rm -rf /",
        174: "policy$(whoami)",
        6939: "policy`id`",
    }
    
    for as_num, malicious_name in malicious_policy_names.items():
        try:
            result = wrapper.generate_policies_batch([as_num], 
                                                   custom_policy_names={as_num: malicious_name},
                                                   parallel=True)
            if result.successful_count > 0:
                print(f"❌ SECURITY FAILURE: Malicious policy name {malicious_name} was processed!")
                return False
            else:
                print(f"✅ Blocked malicious policy name: {malicious_name}")
        except Exception as e:
            print(f"✅ Exception caught for malicious policy name {malicious_name}: {type(e).__name__}")
    
    print("✅ All security validations passed!")
    return True


def benchmark_performance(test_as_numbers, test_name):
    """Benchmark sequential vs parallel performance"""
    print(f"\n⚡ {test_name}")
    print(f"Testing with AS numbers: {test_as_numbers}")
    
    wrapper = BGPq4Wrapper(mode=BGPq4Mode.AUTO, command_timeout=45)
    
    # Test sequential processing
    print("\n📊 Sequential Processing:")
    start_time = time.time()
    sequential_result = wrapper.generate_policies_batch(test_as_numbers, parallel=False)
    sequential_time = time.time() - start_time
    
    print(f"   Time: {sequential_time:.2f}s")
    print(f"   Success: {sequential_result.successful_count}/{sequential_result.total_as_count}")
    print(f"   Failed: {sequential_result.failed_count}")
    
    # Test parallel processing
    print("\n⚡ Parallel Processing:")
    start_time = time.time()
    parallel_result = wrapper.generate_policies_batch(test_as_numbers, parallel=True)
    parallel_time = time.time() - start_time
    
    print(f"   Time: {parallel_time:.2f}s")
    print(f"   Success: {parallel_result.successful_count}/{parallel_result.total_as_count}")
    print(f"   Failed: {parallel_result.failed_count}")
    
    # Calculate speedup
    if parallel_time > 0 and sequential_time > 0:
        speedup = sequential_time / parallel_time
        print(f"\n🚀 Speedup: {speedup:.2f}x")
        
        # Check if we achieved our target
        if len(test_as_numbers) >= 10 and speedup >= 4.0:
            print("✅ Achieved target 4.0x+ speedup for large workload!")
        elif len(test_as_numbers) >= 3 and speedup >= 2.0:
            print("✅ Good speedup for medium workload!")
        elif speedup >= 1.1:
            print("✅ Modest speedup achieved!")
        else:
            print("⚠️ Limited speedup - may need optimization")
    
    return {
        'sequential_time': sequential_time,
        'parallel_time': parallel_time,
        'speedup': sequential_time / parallel_time if parallel_time > 0 else 0,
        'sequential_success': sequential_result.successful_count,
        'parallel_success': parallel_result.successful_count
    }


def test_cache_consistency():
    """Test that parallel processing maintains cache consistency"""
    print("\n💾 Testing Cache Consistency...")
    
    # Clear any existing cache
    cache_dir = Path.home() / ".otto-bgp" / "cache"
    if cache_dir.exists():
        for cache_file in cache_dir.glob("*.json"):
            cache_file.unlink()
    
    wrapper = BGPq4Wrapper(mode=BGPq4Mode.AUTO, command_timeout=30, enable_cache=True)
    test_as = [13335, 174]  # Small test set
    
    # First run - should populate cache
    print("First run (populate cache):")
    result1 = wrapper.generate_policies_batch(test_as, parallel=True)
    
    # Second run - should use cache
    print("Second run (use cache):")
    start_time = time.time()
    result2 = wrapper.generate_policies_batch(test_as, parallel=True)
    cache_time = time.time() - start_time
    
    print(f"Cache lookup time: {cache_time:.2f}s")
    
    # Verify results are identical
    if result1.successful_count == result2.successful_count:
        print("✅ Cache consistency maintained!")
        return True
    else:
        print("❌ Cache consistency failed!")
        return False


def test_resource_management():
    """Test resource management and worker scaling"""
    print("\n🔧 Testing Resource Management...")
    
    wrapper = BGPq4Wrapper(mode=BGPq4Mode.AUTO, command_timeout=30)
    
    # Test different workload sizes
    workloads = [
        ([13335], "Single AS"),
        ([13335, 174], "Two AS"),
        ([13335, 174, 6939], "Three AS"),
        ([13335, 174, 6939, 15169, 8075], "Five AS"),
    ]
    
    for as_list, name in workloads:
        optimal_workers = wrapper.get_optimal_worker_count(len(as_list))
        print(f"{name}: {len(as_list)} AS → {optimal_workers} workers")
    
    # Test environment variable override
    original_env = os.getenv('OTTO_BGP_BGP_MAX_WORKERS')
    try:
        os.environ['OTTO_BGP_BGP_MAX_WORKERS'] = '4'
        override_workers = wrapper.get_optimal_worker_count(10)
        print(f"Environment override: 10 AS → {override_workers} workers (should be 4)")
        
        if override_workers == 4:
            print("✅ Environment variable override works!")
        else:
            print("❌ Environment variable override failed!")
            return False
    finally:
        if original_env is not None:
            os.environ['OTTO_BGP_BGP_MAX_WORKERS'] = original_env
        else:
            os.environ.pop('OTTO_BGP_BGP_MAX_WORKERS', None)
    
    return True


def main():
    """Run all performance and security tests"""
    setup_logging()
    
    print("🧪 Otto BGP Parallel Processing Performance Test")
    print("=" * 60)
    
    # Check if bgpq4 is available
    try:
        wrapper = BGPq4Wrapper(mode=BGPq4Mode.AUTO, command_timeout=10)
        if not wrapper.test_bgpq4_connection():
            print("❌ bgpq4 not available - skipping performance tests")
            return
    except Exception as e:
        print(f"❌ Failed to initialize bgpq4 wrapper: {e}")
        return
    
    # Test security first
    if not test_security_validation():
        print("❌ Security tests failed - aborting!")
        return
    
    # Test cache consistency
    if not test_cache_consistency():
        print("❌ Cache consistency tests failed!")
        return
    
    # Test resource management
    if not test_resource_management():
        print("❌ Resource management tests failed!")
        return
    
    # Performance benchmarks
    benchmarks = [
        ([13335, 174, 6939], "Small Workload (3 AS)"),
        ([13335, 174, 6939, 15169, 8075], "Medium Workload (5 AS)"),
        ([13335, 174, 6939, 15169, 8075, 7922, 3356, 16509, 2914, 1299], "Large Workload (10 AS)"),
    ]
    
    all_results = []
    for as_numbers, test_name in benchmarks:
        try:
            result = benchmark_performance(as_numbers, test_name)
            all_results.append((test_name, result))
        except Exception as e:
            print(f"❌ Benchmark failed for {test_name}: {e}")
    
    # Summary
    print("\n📈 Performance Summary")
    print("=" * 60)
    
    for test_name, result in all_results:
        speedup = result['speedup']
        print(f"{test_name:25} | {speedup:5.2f}x speedup | "
              f"Sequential: {result['sequential_time']:5.1f}s | "
              f"Parallel: {result['parallel_time']:5.1f}s")
    
    # Check if we achieved our targets
    large_workload_results = [r for name, r in all_results if "Large" in name]
    if large_workload_results and large_workload_results[0]['speedup'] >= 4.0:
        print("\n🎯 SUCCESS: Achieved 4.0x+ speedup target for large workloads!")
    else:
        print("\n⚠️ Target 4.0x speedup not achieved for large workloads")
    
    print("\n✅ All tests completed!")


if __name__ == "__main__":
    main()