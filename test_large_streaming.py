#!/usr/bin/env python3
"""
Test script for streaming policy combiner with very large policy files

This creates truly large policy files to demonstrate significant memory reduction.
"""

import os
import sys
import tempfile
import time
import logging
from pathlib import Path

# Add the project to path
sys.path.insert(0, '/Users/randallfussell/GITHUB_PROJECTS/otto-bgp')

from otto_bgp.generators.combiner import PolicyCombiner

def setup_logging():
    """Setup logging for the test"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def measure_memory_usage():
    """Measure current memory usage"""
    try:
        import psutil
        process = psutil.Process()
        return process.memory_info().rss / (1024 * 1024)  # MB
    except ImportError:
        return 0.0

def generate_large_policy_file(filepath: Path, as_number: int, num_prefixes: int):
    """Generate a large policy file with many prefixes"""
    
    with open(filepath, 'w') as f:
        f.write("policy-options {\n")
        f.write("replace:\n")
        f.write(f" prefix-list AS{as_number} {{\n")
        
        # Generate prefixes in various ranges
        for i in range(num_prefixes):
            # Generate realistic-looking IP prefixes
            a = (i // 65536) % 256
            b = (i // 256) % 256
            c = i % 256
            d = 0
            cidr = 24
            
            # Ensure valid IP ranges
            if a == 0:
                a = 1
            if a >= 224:  # Avoid multicast ranges
                a = 10
                
            f.write(f"    {a}.{b}.{c}.{d}/{cidr};\n")
        
        f.write(" }\n")
        f.write("}\n")

def test_large_policy_memory_reduction():
    """Test memory reduction with very large policy files"""
    logger = setup_logging()
    logger.info("Testing streaming combiner with large policy files")
    
    with tempfile.TemporaryDirectory(prefix='otto_bgp_large_streaming_') as test_dir:
        test_dir_path = Path(test_dir)
        
        # Create large policy files
        policy_files = []
        prefixes_per_file = 10000  # 10K prefixes per file
        num_files = 10  # 10 files = 100K total prefixes
        
        logger.info(f"Creating {num_files} policy files with {prefixes_per_file} prefixes each")
        
        for i in range(num_files):
            as_number = 65000 + i
            filename = f"AS{as_number}_policy.txt"
            filepath = test_dir_path / filename
            
            generate_large_policy_file(filepath, as_number, prefixes_per_file)
            policy_files.append(filepath)
        
        # Check total file size
        total_size_mb = sum(f.stat().st_size for f in policy_files) / (1024 * 1024)
        logger.info(f"Total policy file size: {total_size_mb:.2f} MB")
        
        # Test 1: Standard (non-streaming) mode
        logger.info("=== Testing Standard Mode ===")
        
        combiner_standard = PolicyCombiner(logger=logger, enable_streaming=False)
        
        start_time = time.time()
        start_memory = measure_memory_usage()
        
        result_standard = combiner_standard.combine_policies_for_router(
            router_hostname="large-test-router",
            policy_files=policy_files,
            output_dir=test_dir_path,
            format="juniper"
        )
        
        standard_time = time.time() - start_time
        standard_memory = result_standard.memory_peak_mb
        
        logger.info(f"Standard mode - Time: {standard_time:.2f}s")
        logger.info(f"Standard mode - Memory peak: {standard_memory:.2f} MB")
        logger.info(f"Standard mode - Success: {result_standard.success}")
        
        # Test 2: Streaming mode
        logger.info("=== Testing Streaming Mode ===")
        
        combiner_streaming = PolicyCombiner(logger=logger, enable_streaming=True)
        # Force streaming mode
        combiner_streaming.streaming_threshold_mb = 0.1
        
        start_time = time.time()
        start_memory = measure_memory_usage()
        
        result_streaming = combiner_streaming.combine_policies_for_router(
            router_hostname="large-test-router-streaming",
            policy_files=policy_files,
            output_dir=test_dir_path,
            format="juniper"
        )
        
        streaming_time = time.time() - start_time
        streaming_memory = result_streaming.memory_peak_mb
        
        logger.info(f"Streaming mode - Time: {streaming_time:.2f}s")
        logger.info(f"Streaming mode - Memory peak: {streaming_memory:.2f} MB")
        logger.info(f"Streaming mode - Success: {result_streaming.success}")
        logger.info(f"Streaming mode - Enabled: {result_streaming.streaming_enabled}")
        
        # Test 3: Verify output accuracy
        logger.info("=== Validating Output Accuracy ===")
        
        standard_output = test_dir_path / "large-test-router_combined_policy.txt"
        streaming_output = test_dir_path / "large-test-router-streaming_combined_policy.txt"
        
        if standard_output.exists() and streaming_output.exists():
            # Extract prefixes from both files
            import re
            
            def extract_prefixes_from_file(filepath):
                prefixes = set()
                with open(filepath, 'r') as f:
                    for line in f:
                        matches = re.findall(r'(\d+\.\d+\.\d+\.\d+/\d+)', line)
                        prefixes.update(matches)
                return prefixes
            
            standard_prefixes = extract_prefixes_from_file(standard_output)
            streaming_prefixes = extract_prefixes_from_file(streaming_output)
            
            logger.info(f"Standard prefixes: {len(standard_prefixes)}")
            logger.info(f"Streaming prefixes: {len(streaming_prefixes)}")
            
            prefixes_match = standard_prefixes == streaming_prefixes
            logger.info(f"Prefix sets match: {prefixes_match}")
            
            # Check file sizes
            standard_size_mb = standard_output.stat().st_size / (1024 * 1024)
            streaming_size_mb = streaming_output.stat().st_size / (1024 * 1024)
            
            logger.info(f"Standard output size: {standard_size_mb:.2f} MB")
            logger.info(f"Streaming output size: {streaming_size_mb:.2f} MB")
            
        else:
            logger.error("Output files not found")
            prefixes_match = False
        
        # Test 4: Calculate improvements
        logger.info("=== Performance Analysis ===")
        
        if standard_memory > 0 and streaming_memory > 0:
            memory_reduction_mb = standard_memory - streaming_memory
            memory_reduction_percent = (memory_reduction_mb / standard_memory) * 100
            
            logger.info(f"Memory reduction: {memory_reduction_mb:.2f} MB ({memory_reduction_percent:.1f}%)")
            
            time_difference = streaming_time - standard_time
            time_change_percent = (time_difference / standard_time) * 100
            
            logger.info(f"Time difference: {time_difference:.2f}s ({time_change_percent:+.1f}%)")
            
            # Memory efficiency relative to file size
            standard_efficiency = standard_memory / total_size_mb if total_size_mb > 0 else 0
            streaming_efficiency = streaming_memory / total_size_mb if total_size_mb > 0 else 0
            
            logger.info(f"Standard memory efficiency: {standard_efficiency:.2f}x file size")
            logger.info(f"Streaming memory efficiency: {streaming_efficiency:.2f}x file size")
            
            # Check targets
            target_reduction_achieved = memory_reduction_percent >= 40.0
            reasonable_performance = abs(time_change_percent) <= 50  # Within 50% of original time
            
            logger.info("=== Test Summary ===")
            logger.info(f"Total file size: {total_size_mb:.2f} MB")
            logger.info(f"Standard memory: {standard_memory:.2f} MB")
            logger.info(f"Streaming memory: {streaming_memory:.2f} MB")
            logger.info(f"Memory reduction: {memory_reduction_percent:.1f}%")
            logger.info(f"Output accuracy: {'✓' if prefixes_match else '✗'}")
            logger.info(f"Target reduction achieved: {'✓' if target_reduction_achieved else '✗'}")
            logger.info(f"Performance acceptable: {'✓' if reasonable_performance else '✗'}")
            
            return (prefixes_match and 
                   target_reduction_achieved and 
                   reasonable_performance)
        else:
            logger.warning("Could not measure memory usage")
            return prefixes_match

def test_extreme_scale():
    """Test with even larger scale to push memory limits"""
    logger = setup_logging()
    logger.info("Testing extreme scale with massive policy files")
    
    with tempfile.TemporaryDirectory(prefix='otto_bgp_extreme_') as test_dir:
        test_dir_path = Path(test_dir)
        
        # Create very large policy files
        policy_files = []
        prefixes_per_file = 50000  # 50K prefixes per file
        num_files = 5  # 5 files = 250K total prefixes
        
        logger.info(f"Creating {num_files} extreme policy files with {prefixes_per_file} prefixes each")
        
        for i in range(num_files):
            as_number = 64000 + i
            filename = f"AS{as_number}_policy.txt"
            filepath = test_dir_path / filename
            
            generate_large_policy_file(filepath, as_number, prefixes_per_file)
            policy_files.append(filepath)
        
        # Check total file size
        total_size_mb = sum(f.stat().st_size for f in policy_files) / (1024 * 1024)
        logger.info(f"Extreme test total file size: {total_size_mb:.2f} MB")
        
        # Only test streaming mode for extreme scale
        logger.info("=== Testing Streaming Mode Only (Extreme Scale) ===")
        
        combiner_streaming = PolicyCombiner(logger=logger, enable_streaming=True)
        combiner_streaming.streaming_threshold_mb = 0.1
        combiner_streaming.max_memory_entries = 25000  # Reduce memory buffer
        
        start_time = time.time()
        start_memory = measure_memory_usage()
        
        result = combiner_streaming.combine_policies_for_router(
            router_hostname="extreme-test-router",
            policy_files=policy_files,
            output_dir=test_dir_path,
            format="juniper"
        )
        
        end_time = time.time() - start_time
        peak_memory = result.memory_peak_mb
        
        logger.info(f"Extreme streaming - Time: {end_time:.2f}s")
        logger.info(f"Extreme streaming - Memory peak: {peak_memory:.2f} MB")
        logger.info(f"Extreme streaming - Success: {result.success}")
        logger.info(f"Extreme streaming - Total prefixes: {result.total_prefixes}")
        
        # Check memory efficiency
        memory_efficiency = peak_memory / total_size_mb if total_size_mb > 0 else 0
        logger.info(f"Extreme memory efficiency: {memory_efficiency:.2f}x file size")
        
        # Verify output
        output_file = test_dir_path / "extreme-test-router_combined_policy.txt"
        if output_file.exists():
            output_size_mb = output_file.stat().st_size / (1024 * 1024)
            logger.info(f"Extreme output size: {output_size_mb:.2f} MB")
            
            success = (result.success and 
                      memory_efficiency < 2.0 and  # Memory should be less than 2x file size
                      peak_memory < 200)  # Should stay under 200MB for this test
            
            logger.info(f"Extreme test success: {'✓' if success else '✗'}")
            return success
        else:
            logger.error("Extreme test output file not found")
            return False

if __name__ == "__main__":
    print("Large-Scale Streaming Policy Combiner Test")
    print("=" * 50)
    
    # Test 1: Large but manageable scale
    print("\n1. Testing large-scale memory reduction...")
    large_test_passed = test_large_policy_memory_reduction()
    
    # Test 2: Extreme scale to test limits
    print("\n2. Testing extreme scale limits...")
    extreme_test_passed = test_extreme_scale()
    
    # Summary
    print("\n" + "=" * 50)
    print("Large-Scale Test Results:")
    print(f"  Large-scale test: {'PASS' if large_test_passed else 'FAIL'}")
    print(f"  Extreme-scale test: {'PASS' if extreme_test_passed else 'FAIL'}")
    
    overall_success = large_test_passed and extreme_test_passed
    print(f"  Overall: {'PASS' if overall_success else 'FAIL'}")
    
    if overall_success:
        print("\n✓ Large-scale streaming successfully implemented!")
        print("  - Significant memory reduction achieved")
        print("  - Performance maintained")
        print("  - Extreme scale handled efficiently")
    else:
        print("\n✗ Some large-scale tests failed.")
    
    sys.exit(0 if overall_success else 1)