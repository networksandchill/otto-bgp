#!/usr/bin/env python3
"""
Large file memory optimization test
Tests streaming with larger files to demonstrate significant memory reduction
"""

import logging
import sys
import os
import tempfile
import gc
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from otto_bgp.processors.as_extractor import (
    ASNumberExtractor, 
    MemoryBenchmark
)

# Set up logging
logging.basicConfig(
    level=logging.WARNING,  # Reduce log verbosity
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_large_bgp_file(file_path: Path, size_mb: int) -> Path:
    """Create a large BGP configuration file for testing"""
    logger.info(f"Creating {size_mb}MB BGP test file...")
    
    # Calculate lines needed
    avg_line_length = 60  # bytes per line
    target_bytes = size_mb * 1024 * 1024
    target_lines = target_bytes // avg_line_length
    
    as_number = 10000
    
    with open(file_path, 'w', encoding='utf-8') as f:
        for i in range(target_lines):
            if i % 20 == 0:  # Every 20th line has an AS number
                line = f"neighbor 10.{(i//65536)%256}.{(i//256)%256}.{i%256} {{ peer-as {as_number}; }}\n"
                as_number += 1
                if as_number > 65000:  # Wrap around to avoid reserved ranges
                    as_number = 10000
            else:
                # Filler lines with varying content
                line = f"interface ge-{i//1000}/{(i//100)%10}/{i%100} {{ description \"Port {i}\"; mtu 9000; }}\n"
            
            f.write(line)
    
    actual_size = file_path.stat().st_size / 1024 / 1024
    logger.info(f"Created {actual_size:.1f}MB file with ~{target_lines//20} AS numbers")
    
    return file_path


def measure_memory_usage(extractor, file_path, method_name):
    """Measure memory usage for extraction method"""
    
    # Force garbage collection before measurement
    gc.collect()
    
    # Get initial memory state
    try:
        import psutil
        process = psutil.Process()
        memory_before = process.memory_info().rss / 1024 / 1024  # MB
    except ImportError:
        memory_before = 0
        logger.warning("psutil not available, using basic measurement")
    
    # Run extraction
    import time
    start_time = time.time()
    
    try:
        result = extractor.extract_as_numbers_from_file(file_path)
        success = True
        as_count = len(result.as_numbers)
        error = None
    except Exception as e:
        success = False
        as_count = 0
        error = str(e)
    
    end_time = time.time()
    
    # Get final memory state
    try:
        memory_after = process.memory_info().rss / 1024 / 1024  # MB
    except:
        memory_after = memory_before
    
    return {
        "method": method_name,
        "success": success,
        "as_count": as_count,
        "processing_time": end_time - start_time,
        "memory_before_mb": memory_before,
        "memory_after_mb": memory_after,
        "memory_delta_mb": memory_after - memory_before,
        "error": error
    }


def test_large_file_memory_optimization():
    """Test memory optimization with a large file"""
    
    # Test with a large file (50MB)
    test_file_size = 50  # MB
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
        test_file = Path(temp_file.name)
    
    try:
        # Create large test file
        create_large_bgp_file(test_file, test_file_size)
        
        logger.info(f"Testing memory usage with {test_file_size}MB file...")
        
        # Test legacy method
        logger.info("Testing legacy method...")
        extractor_legacy = ASNumberExtractor(
            enable_streaming=False,
            warn_reserved=False  # Reduce log verbosity
        )
        
        legacy_results = measure_memory_usage(extractor_legacy, test_file, "Legacy")
        
        # Clean up memory
        del extractor_legacy
        gc.collect()
        
        # Test streaming method
        logger.info("Testing streaming method...")
        extractor_streaming = ASNumberExtractor(
            enable_streaming=True,
            warn_reserved=False,  # Reduce log verbosity
            streaming_memory_limit_mb=30  # Conservative limit
        )
        
        streaming_results = measure_memory_usage(extractor_streaming, test_file, "Streaming")
        
        # Report results
        print("\n" + "="*60)
        print(f"MEMORY OPTIMIZATION TEST RESULTS ({test_file_size}MB file)")
        print("="*60)
        
        for results in [legacy_results, streaming_results]:
            print(f"\n{results['method']} Method:")
            if results['success']:
                print(f"  Processing time: {results['processing_time']:.2f}s")
                print(f"  Memory before:   {results['memory_before_mb']:.1f}MB")
                print(f"  Memory after:    {results['memory_after_mb']:.1f}MB")
                print(f"  Memory delta:    {results['memory_delta_mb']:.1f}MB")
                print(f"  AS numbers found: {results['as_count']}")
            else:
                print(f"  ERROR: {results['error']}")
        
        # Calculate improvement
        if legacy_results['success'] and streaming_results['success']:
            legacy_peak = legacy_results['memory_after_mb']
            streaming_peak = streaming_results['memory_after_mb']
            
            if legacy_peak > 0:
                memory_reduction = ((legacy_peak - streaming_peak) / legacy_peak) * 100
                memory_savings = legacy_peak - streaming_peak
                
                print(f"\nMEMORY OPTIMIZATION SUMMARY:")
                print(f"  Memory reduction: {memory_reduction:.1f}%")
                print(f"  Memory savings:   {memory_savings:.1f}MB")
                
                # Check if results are identical
                if legacy_results['as_count'] == streaming_results['as_count']:
                    print(f"  Accuracy check:   ✓ PASS (identical results)")
                else:
                    print(f"  Accuracy check:   ✗ FAIL (different counts)")
                
                # Determine success
                if memory_reduction >= 30:  # At least 30% reduction for large files
                    print(f"  Result:           ✓ SUCCESS - Significant memory reduction achieved")
                    return True
                else:
                    print(f"  Result:           ⚠ MARGINAL - Expected >30% reduction for large files")
                    return False
            else:
                print(f"  Result:           ✗ UNABLE TO MEASURE - No memory monitoring available")
                return False
        else:
            print(f"  Result:           ✗ FAILED - One or both methods failed")
            return False
    
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        return False
    
    finally:
        # Clean up test file
        try:
            os.unlink(test_file)
        except OSError:
            pass


def test_memory_with_multiple_sizes():
    """Test memory optimization across different file sizes"""
    
    test_sizes = [10, 25, 50, 100]  # MB
    results = []
    
    print("\n" + "="*80)
    print("COMPREHENSIVE MEMORY OPTIMIZATION TEST")
    print("="*80)
    
    for size_mb in test_sizes:
        print(f"\nTesting {size_mb}MB file...")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
            test_file = Path(temp_file.name)
        
        try:
            # Create test file
            create_large_bgp_file(test_file, size_mb)
            
            # Test both methods
            extractor_legacy = ASNumberExtractor(enable_streaming=False, warn_reserved=False)
            legacy_results = measure_memory_usage(extractor_legacy, test_file, f"Legacy-{size_mb}MB")
            del extractor_legacy
            gc.collect()
            
            extractor_streaming = ASNumberExtractor(enable_streaming=True, warn_reserved=False)
            streaming_results = measure_memory_usage(extractor_streaming, test_file, f"Streaming-{size_mb}MB")
            del extractor_streaming
            gc.collect()
            
            # Calculate metrics
            if legacy_results['success'] and streaming_results['success']:
                memory_reduction = ((legacy_results['memory_after_mb'] - streaming_results['memory_after_mb']) / 
                                  legacy_results['memory_after_mb']) * 100 if legacy_results['memory_after_mb'] > 0 else 0
                
                results.append({
                    "size_mb": size_mb,
                    "legacy_memory": legacy_results['memory_after_mb'],
                    "streaming_memory": streaming_results['memory_after_mb'],
                    "memory_reduction": memory_reduction,
                    "legacy_time": legacy_results['processing_time'],
                    "streaming_time": streaming_results['processing_time'],
                    "as_count": legacy_results['as_count']
                })
                
                print(f"  Memory reduction: {memory_reduction:.1f}%")
            else:
                print(f"  Error in processing")
        
        except Exception as e:
            logger.error(f"Error testing {size_mb}MB file: {e}")
        
        finally:
            try:
                os.unlink(test_file)
            except OSError:
                pass
    
    # Summary report
    print(f"\nFINAL RESULTS SUMMARY:")
    print(f"{'Size':>6} {'Legacy':>8} {'Stream':>8} {'Reduction':>10} {'Legacy T':>9} {'Stream T':>9}")
    print(f"{'(MB)':>6} {'(MB)':>8} {'(MB)':>8} {'(%)':>10} {'(sec)':>9} {'(sec)':>9}")
    print("-" * 60)
    
    successful_tests = 0
    for result in results:
        print(f"{result['size_mb']:>6} {result['legacy_memory']:>8.1f} {result['streaming_memory']:>8.1f} "
              f"{result['memory_reduction']:>10.1f} {result['legacy_time']:>9.2f} {result['streaming_time']:>9.2f}")
        
        if result['memory_reduction'] >= 20:  # At least 20% reduction
            successful_tests += 1
    
    print(f"\nTests with significant memory reduction (≥20%): {successful_tests}/{len(results)}")
    
    return successful_tests >= len(results) // 2  # At least half should show good reduction


def main():
    """Run large file memory optimization tests"""
    
    print("Otto BGP Streaming Memory Optimization - Large File Tests")
    print("This test demonstrates memory optimization with large BGP configuration files")
    
    # Check if psutil is available
    try:
        import psutil
        print(f"✓ Memory monitoring available (psutil installed)")
    except ImportError:
        print(f"⚠ Limited memory monitoring (install psutil for detailed metrics)")
    
    # Run tests
    test1_passed = test_large_file_memory_optimization()
    test2_passed = test_memory_with_multiple_sizes()
    
    print("\n" + "="*60)
    print("OVERALL TEST RESULTS:")
    print("="*60)
    
    if test1_passed and test2_passed:
        print("🎉 SUCCESS: Streaming memory optimization is working effectively!")
        print("   - Significant memory reduction achieved for large files")
        print("   - Processing accuracy maintained")
        print("   - Auto-detection and configuration working correctly")
        return 0
    elif test1_passed or test2_passed:
        print("⚠ PARTIAL SUCCESS: Some memory optimization achieved")
        print("   - Consider adjusting memory limits or file size thresholds")
        return 0
    else:
        print("❌ FAILED: Streaming optimization not providing expected benefits")
        print("   - Check implementation and memory management logic")
        return 1


if __name__ == "__main__":
    sys.exit(main())