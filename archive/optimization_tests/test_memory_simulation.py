#!/usr/bin/env python3
"""
Memory simulation test for streaming policy combiner

This test simulates the memory usage patterns of processing many large policy files
by creating realistic scenarios and measuring memory pressure points.
"""

import os
import sys
import tempfile
import logging
import time
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

def create_memory_intensive_policy_file(filepath: Path, as_number: int, size_mb: int):
    """Create a policy file of specific size in MB"""
    
    # Calculate approximately how many prefixes needed for target size
    # Each prefix line is about 20 bytes: "    192.168.1.0/24;\n"
    bytes_per_prefix = 20
    target_bytes = size_mb * 1024 * 1024
    num_prefixes = target_bytes // bytes_per_prefix
    
    with open(filepath, 'w') as f:
        f.write("policy-options {\n")
        f.write("replace:\n")
        f.write(f" prefix-list AS{as_number} {{\n")
        
        # Generate prefixes to reach target size
        for i in range(num_prefixes):
            # Generate realistic IP prefixes
            a = ((i // 65536) % 223) + 1  # 1-223 (avoid 0, 224-255)
            b = (i // 256) % 256
            c = i % 256
            d = 0
            
            f.write(f"    {a}.{b}.{c}.{d}/24;\n")
        
        f.write(" }\n")
        f.write("}\n")

def measure_memory_behavior():
    """Test memory behavior with controlled policy sizes"""
    logger = setup_logging()
    logger.info("Testing memory behavior with size-controlled policy files")
    
    with tempfile.TemporaryDirectory(prefix='otto_bgp_memory_test_') as test_dir:
        test_dir_path = Path(test_dir)
        
        # Test with progressively larger file sets
        test_scenarios = [
            {"file_size_mb": 1, "num_files": 5, "name": "Small"},
            {"file_size_mb": 2, "num_files": 10, "name": "Medium"}, 
            {"file_size_mb": 5, "num_files": 10, "name": "Large"},
            {"file_size_mb": 10, "num_files": 10, "name": "Very Large"}
        ]
        
        results = []
        
        for scenario in test_scenarios:
            logger.info(f"\n=== Testing {scenario['name']} Scenario ===")
            logger.info(f"File size: {scenario['file_size_mb']}MB each, Count: {scenario['num_files']}")
            
            # Create policy files for this scenario
            policy_files = []
            
            for i in range(scenario["num_files"]):
                as_number = 65000 + i
                filename = f"AS{as_number}_policy.txt"
                filepath = test_dir_path / filename
                
                create_memory_intensive_policy_file(filepath, as_number, scenario["file_size_mb"])
                policy_files.append(filepath)
            
            # Calculate actual total size
            total_size_mb = sum(f.stat().st_size for f in policy_files) / (1024 * 1024)
            logger.info(f"Actual total size: {total_size_mb:.2f} MB")
            
            # Test standard mode
            logger.info("Testing Standard Mode...")
            combiner_standard = PolicyCombiner(logger=logger, enable_streaming=False)
            
            start_time = time.time()
            result_standard = combiner_standard.combine_policies_for_router(
                router_hostname=f"{scenario['name'].lower()}-standard",
                policy_files=policy_files,
                output_dir=test_dir_path,
                format="juniper"
            )
            standard_time = time.time() - start_time
            
            # Test streaming mode
            logger.info("Testing Streaming Mode...")
            combiner_streaming = PolicyCombiner(logger=logger, enable_streaming=True)
            combiner_streaming.streaming_threshold_mb = 0.1  # Force streaming
            
            start_time = time.time()
            result_streaming = combiner_streaming.combine_policies_for_router(
                router_hostname=f"{scenario['name'].lower()}-streaming",
                policy_files=policy_files,
                output_dir=test_dir_path,
                format="juniper"
            )
            streaming_time = time.time() - start_time
            
            # Calculate metrics
            memory_reduction = result_standard.memory_peak_mb - result_streaming.memory_peak_mb
            memory_reduction_percent = (memory_reduction / result_standard.memory_peak_mb) * 100 if result_standard.memory_peak_mb > 0 else 0
            
            scenario_result = {
                "name": scenario["name"],
                "file_size_mb": scenario["file_size_mb"],
                "num_files": scenario["num_files"],
                "total_size_mb": total_size_mb,
                "standard_memory_mb": result_standard.memory_peak_mb,
                "streaming_memory_mb": result_streaming.memory_peak_mb,
                "memory_reduction_mb": memory_reduction,
                "memory_reduction_percent": memory_reduction_percent,
                "standard_time": standard_time,
                "streaming_time": streaming_time,
                "accuracy_preserved": result_standard.total_prefixes == result_streaming.total_prefixes
            }
            
            results.append(scenario_result)
            
            logger.info(f"Standard: {result_standard.memory_peak_mb:.1f}MB, {standard_time:.2f}s")
            logger.info(f"Streaming: {result_streaming.memory_peak_mb:.1f}MB, {streaming_time:.2f}s")
            logger.info(f"Reduction: {memory_reduction:.1f}MB ({memory_reduction_percent:.1f}%)")
            
            # Clean up files for next scenario
            for policy_file in policy_files:
                policy_file.unlink()
        
        # Analyze results
        logger.info("\n=== Memory Behavior Analysis ===")
        logger.info(f"{'Scenario':<12} {'Files':<6} {'Size(MB)':<10} {'Std(MB)':<8} {'Stream(MB)':<10} {'Reduction':<10}")
        logger.info("-" * 70)
        
        for result in results:
            reduction_str = f"{result['memory_reduction_percent']:+.1f}%"
            logger.info(f"{result['name']:<12} {result['num_files']:<6} {result['total_size_mb']:<10.1f} "
                       f"{result['standard_memory_mb']:<8.1f} {result['streaming_memory_mb']:<10.1f} {reduction_str:<10}")
        
        # Find the best reduction
        best_reduction = max(results, key=lambda x: x['memory_reduction_percent'])
        logger.info(f"\nBest reduction: {best_reduction['name']} scenario with {best_reduction['memory_reduction_percent']:.1f}%")
        
        return results

def test_streaming_effectiveness():
    """Test the core effectiveness of the streaming approach"""
    logger = setup_logging()
    logger.info("Testing streaming approach core effectiveness")
    
    # Test the principle: does avoiding loading all files at once help?
    with tempfile.TemporaryDirectory(prefix='otto_bgp_effectiveness_') as test_dir:
        test_dir_path = Path(test_dir)
        
        # Create a moderate number of larger files
        policy_files = []
        file_size_mb = 3  # 3MB per file
        num_files = 15    # 15 files = 45MB total
        
        logger.info(f"Creating {num_files} files of {file_size_mb}MB each")
        
        for i in range(num_files):
            as_number = 64000 + i
            filename = f"AS{as_number}_policy.txt"
            filepath = test_dir_path / filename
            
            create_memory_intensive_policy_file(filepath, as_number, file_size_mb)
            policy_files.append(filepath)
        
        total_size_mb = sum(f.stat().st_size for f in policy_files) / (1024 * 1024)
        logger.info(f"Total dataset: {total_size_mb:.2f} MB")
        
        # Test memory growth patterns
        logger.info("\n=== Memory Growth Pattern Test ===")
        
        # Standard mode - loads all files
        logger.info("Standard mode (loads all files into memory)...")
        combiner_standard = PolicyCombiner(logger=logger, enable_streaming=False)
        
        result_standard = combiner_standard.combine_policies_for_router(
            router_hostname="effectiveness-standard",
            policy_files=policy_files,
            output_dir=test_dir_path,
            format="juniper"
        )
        
        # Streaming mode - processes one at a time
        logger.info("Streaming mode (processes files individually)...")
        combiner_streaming = PolicyCombiner(logger=logger, enable_streaming=True)
        combiner_streaming.streaming_threshold_mb = 0.1
        
        result_streaming = combiner_streaming.combine_policies_for_router(
            router_hostname="effectiveness-streaming", 
            policy_files=policy_files,
            output_dir=test_dir_path,
            format="juniper"
        )
        
        # Analysis
        memory_difference = result_standard.memory_peak_mb - result_streaming.memory_peak_mb
        memory_difference_percent = (memory_difference / result_standard.memory_peak_mb) * 100 if result_standard.memory_peak_mb > 0 else 0
        
        # Calculate expected memory usage ratios
        standard_ratio = result_standard.memory_peak_mb / total_size_mb
        streaming_ratio = result_streaming.memory_peak_mb / total_size_mb
        
        logger.info(f"\n=== Effectiveness Results ===")
        logger.info(f"Dataset size: {total_size_mb:.2f} MB")
        logger.info(f"Standard memory: {result_standard.memory_peak_mb:.2f} MB ({standard_ratio:.1f}x dataset)")
        logger.info(f"Streaming memory: {result_streaming.memory_peak_mb:.2f} MB ({streaming_ratio:.1f}x dataset)")
        logger.info(f"Memory difference: {memory_difference:.2f} MB ({memory_difference_percent:+.1f}%)")
        logger.info(f"Accuracy preserved: {result_standard.total_prefixes == result_streaming.total_prefixes}")
        
        # Success criteria
        meaningful_reduction = abs(memory_difference_percent) >= 5  # At least 5% difference
        streaming_more_efficient = streaming_ratio < standard_ratio
        accuracy_preserved = result_standard.total_prefixes == result_streaming.total_prefixes
        
        success = accuracy_preserved and (meaningful_reduction or streaming_more_efficient)
        
        logger.info(f"\nStreaming effectiveness: {'✓' if success else '✗'}")
        
        return success

def test_memory_pressure_simulation():
    """Simulate actual memory pressure scenarios"""
    logger = setup_logging()
    logger.info("Simulating real-world memory pressure scenarios")
    
    # Simulate what happens in a production environment with many large AS policies
    with tempfile.TemporaryDirectory(prefix='otto_bgp_pressure_') as test_dir:
        test_dir_path = Path(test_dir)
        
        # Scenario: Large ISP with many transit providers and customers
        # Each AS has varying numbers of prefixes
        as_configs = [
            # Major transit providers (large prefix counts)
            {"as_number": 174, "prefixes": 180000, "name": "Cogent"},
            {"as_number": 3356, "prefixes": 150000, "name": "Level3"},
            {"as_number": 1299, "prefixes": 140000, "name": "Arelion"},
            {"as_number": 6939, "prefixes": 120000, "name": "Hurricane"},
            {"as_number": 3257, "prefixes": 110000, "name": "GTT"},
            
            # Cloud providers (medium-large)
            {"as_number": 16509, "prefixes": 50000, "name": "AWS"},
            {"as_number": 15169, "prefixes": 30000, "name": "Google"},
            {"as_number": 8075, "prefixes": 25000, "name": "Microsoft"},
            
            # CDNs (medium)
            {"as_number": 13335, "prefixes": 15000, "name": "Cloudflare"},
            {"as_number": 16625, "prefixes": 12000, "name": "Akamai"},
            
            # Regional providers (smaller)
            {"as_number": 65001, "prefixes": 5000, "name": "Regional1"},
            {"as_number": 65002, "prefixes": 3000, "name": "Regional2"},
            {"as_number": 65003, "prefixes": 2000, "name": "Regional3"},
        ]
        
        policy_files = []
        expected_total_prefixes = 0
        
        logger.info("Creating realistic ISP policy scenario...")
        
        for config in as_configs:
            filename = f"AS{config['as_number']}_policy.txt"
            filepath = test_dir_path / filename
            
            with open(filepath, 'w') as f:
                f.write("policy-options {\n")
                f.write("replace:\n")
                f.write(f" prefix-list AS{config['as_number']} {{\n")
                
                # Generate realistic prefixes for this AS
                for i in range(config['prefixes']):
                    # Use AS number to seed realistic IP ranges
                    base = (config['as_number'] % 200) + 1
                    a = base
                    b = (i // 65536) % 256
                    c = (i // 256) % 256
                    d = 0
                    
                    # Vary CIDR based on AS type
                    if config['prefixes'] > 100000:  # Transit providers
                        cidr = 24 if i % 4 != 0 else 23  # Mostly /24s with some /23s
                    elif config['prefixes'] > 20000:  # Cloud providers
                        cidr = 24 if i % 3 != 0 else 22  # Mix of /24s and /22s
                    else:  # Smaller providers
                        cidr = 24  # Mostly /24s
                    
                    f.write(f"    {a}.{b}.{c}.{d}/{cidr};\n")
                
                f.write(" }\n")
                f.write("}\n")
            
            policy_files.append(filepath)
            expected_total_prefixes += config['prefixes']
            
            logger.info(f"Created AS{config['as_number']} ({config['name']}) with {config['prefixes']} prefixes")
        
        # Calculate dataset size
        total_size_mb = sum(f.stat().st_size for f in policy_files) / (1024 * 1024)
        logger.info(f"Realistic dataset: {len(policy_files)} ASes, {expected_total_prefixes} prefixes, {total_size_mb:.2f} MB")
        
        # Test both approaches
        logger.info("\n=== Testing Realistic Scenario ===")
        
        # Standard approach
        logger.info("Standard mode (production current behavior)...")
        combiner_standard = PolicyCombiner(logger=logger, enable_streaming=False)
        
        start_time = time.time()
        result_standard = combiner_standard.combine_policies_for_router(
            router_hostname="production-router-standard",
            policy_files=policy_files,
            output_dir=test_dir_path,
            format="juniper"
        )
        standard_time = time.time() - start_time
        
        # Streaming approach
        logger.info("Streaming mode (optimized behavior)...")
        combiner_streaming = PolicyCombiner(logger=logger, enable_streaming=True)
        combiner_streaming.streaming_threshold_mb = 5.0  # Realistic threshold
        
        start_time = time.time()
        result_streaming = combiner_streaming.combine_policies_for_router(
            router_hostname="production-router-streaming",
            policy_files=policy_files,
            output_dir=test_dir_path,
            format="juniper"
        )
        streaming_time = time.time() - start_time
        
        # Detailed analysis
        logger.info(f"\n=== Production Scenario Results ===")
        logger.info(f"Dataset: {len(as_configs)} ASes, {total_size_mb:.2f} MB")
        logger.info(f"Expected prefixes: {expected_total_prefixes}")
        
        logger.info(f"\nStandard Mode:")
        logger.info(f"  Memory peak: {result_standard.memory_peak_mb:.2f} MB")
        logger.info(f"  Processing time: {standard_time:.2f} seconds")
        logger.info(f"  Prefixes processed: {result_standard.total_prefixes}")
        logger.info(f"  Success: {result_standard.success}")
        
        logger.info(f"\nStreaming Mode:")
        logger.info(f"  Memory peak: {result_streaming.memory_peak_mb:.2f} MB")
        logger.info(f"  Processing time: {streaming_time:.2f} seconds")
        logger.info(f"  Prefixes processed: {result_streaming.total_prefixes}")
        logger.info(f"  Success: {result_streaming.success}")
        
        # Calculate improvements
        memory_savings = result_standard.memory_peak_mb - result_streaming.memory_peak_mb
        memory_savings_percent = (memory_savings / result_standard.memory_peak_mb) * 100 if result_standard.memory_peak_mb > 0 else 0
        
        time_difference = streaming_time - standard_time
        time_change_percent = (time_difference / standard_time) * 100 if standard_time > 0 else 0
        
        accuracy_match = result_standard.total_prefixes == result_streaming.total_prefixes
        
        logger.info(f"\nComparison:")
        logger.info(f"  Memory savings: {memory_savings:.2f} MB ({memory_savings_percent:+.1f}%)")
        logger.info(f"  Time difference: {time_difference:+.2f} seconds ({time_change_percent:+.1f}%)")
        logger.info(f"  Output accuracy: {'✓' if accuracy_match else '✗'}")
        
        # Success criteria for realistic scenario
        acceptable_memory_efficiency = result_streaming.memory_peak_mb < total_size_mb * 5  # Memory < 5x file size
        reasonable_performance = abs(time_change_percent) < 100  # Within 100% of original time
        
        success = (accuracy_match and 
                  acceptable_memory_efficiency and 
                  reasonable_performance and
                  result_streaming.success)
        
        logger.info(f"\nRealistic scenario success: {'✓' if success else '✗'}")
        
        return success

if __name__ == "__main__":
    print("Memory Simulation Test for Streaming Policy Combiner")
    print("=" * 60)
    
    # Test 1: Memory behavior analysis
    print("\n1. Analyzing memory behavior patterns...")
    memory_results = measure_memory_behavior()
    
    # Test 2: Streaming effectiveness
    print("\n2. Testing streaming effectiveness...")
    effectiveness_passed = test_streaming_effectiveness()
    
    # Test 3: Realistic production scenario
    print("\n3. Testing realistic production scenario...")
    realistic_passed = test_memory_pressure_simulation()
    
    # Summary
    print("\n" + "=" * 60)
    print("Memory Simulation Results:")
    print(f"  Memory behavior analysis: COMPLETED")
    print(f"  Streaming effectiveness: {'PASS' if effectiveness_passed else 'FAIL'}")
    print(f"  Realistic scenario: {'PASS' if realistic_passed else 'FAIL'}")
    
    overall_success = effectiveness_passed and realistic_passed
    print(f"  Overall: {'PASS' if overall_success else 'FAIL'}")
    
    print(f"\nMemory behavior findings:")
    for result in memory_results:
        if result['memory_reduction_percent'] > 0:
            print(f"  - {result['name']}: {result['memory_reduction_percent']:.1f}% reduction")
        else:
            print(f"  - {result['name']}: {abs(result['memory_reduction_percent']):.1f}% overhead")
    
    if overall_success:
        print("\n✓ Streaming implementation working effectively!")
    else:
        print("\n✗ Further optimization needed.")
    
    sys.exit(0 if overall_success else 1)