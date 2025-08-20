#!/usr/bin/env python3
"""
Memory usage analysis script
Analyzes where memory is actually being consumed in AS extraction
"""

import logging
import sys
import os
import tempfile
import gc
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from otto_bgp.processors.as_extractor import ASNumberExtractor

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def create_test_file(file_path: Path, size_mb: int) -> Path:
    """Create a test BGP file"""
    print(f"Creating {size_mb}MB test file...")
    
    avg_line_length = 60
    target_bytes = size_mb * 1024 * 1024
    target_lines = target_bytes // avg_line_length
    
    as_number = 10000
    
    with open(file_path, 'w', encoding='utf-8') as f:
        for i in range(target_lines):
            if i % 20 == 0:
                line = f"neighbor 10.{(i//65536)%256}.{(i//256)%256}.{i%256} {{ peer-as {as_number}; }}\n"
                as_number += 1
                if as_number > 65000:
                    as_number = 10000
            else:
                line = f"interface ge-{i//1000}/{(i//100)%10}/{i%100} {{ description \"Port {i}\"; mtu 9000; }}\n"
            f.write(line)
    
    actual_size = file_path.stat().st_size / 1024 / 1024
    print(f"Created {actual_size:.1f}MB file")
    return file_path


def get_memory_usage():
    """Get current memory usage"""
    try:
        import psutil
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024  # MB
    except ImportError:
        return 0


def analyze_memory_step_by_step():
    """Analyze memory usage step by step during AS extraction"""
    
    # Create test file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
        test_file = Path(temp_file.name)
    
    try:
        create_test_file(test_file, 50)  # 50MB file
        
        print("\nMemory usage analysis for 50MB BGP file:")
        print("=" * 60)
        
        # Baseline memory
        gc.collect()
        baseline_memory = get_memory_usage()
        print(f"Baseline memory: {baseline_memory:.1f}MB")
        
        # Test 1: Just reading the entire file into memory
        print("\n1. Reading entire file into memory:")
        mem_before = get_memory_usage()
        with open(test_file, 'r') as f:
            file_content = f.read()
        mem_after = get_memory_usage()
        print(f"  Memory before: {mem_before:.1f}MB")
        print(f"  Memory after: {mem_after:.1f}MB")
        print(f"  Memory delta: {mem_after - mem_before:.1f}MB")
        print(f"  File size: {len(file_content) / 1024 / 1024:.1f}MB")
        
        # Estimate AS numbers in file
        estimated_as_count = file_content.count('peer-as')
        print(f"  Estimated AS numbers: {estimated_as_count:,}")
        
        del file_content  # Free memory
        gc.collect()
        
        # Test 2: Legacy extraction
        print("\n2. Legacy extraction (load entire file):")
        mem_before = get_memory_usage()
        extractor_legacy = ASNumberExtractor(enable_streaming=False, warn_reserved=False)
        result_legacy = extractor_legacy.extract_as_numbers_from_file(test_file)
        mem_after = get_memory_usage()
        print(f"  Memory before: {mem_before:.1f}MB")
        print(f"  Memory after: {mem_after:.1f}MB")
        print(f"  Memory delta: {mem_after - mem_before:.1f}MB")
        print(f"  AS numbers found: {len(result_legacy.as_numbers):,}")
        
        # Calculate memory per AS number
        as_memory_overhead = (mem_after - mem_before) / len(result_legacy.as_numbers) * 1024  # KB per AS
        print(f"  Memory per AS number: {as_memory_overhead:.2f}KB")
        
        del extractor_legacy, result_legacy
        gc.collect()
        
        # Test 3: Ultra-efficient extraction
        print("\n3. Ultra-efficient extraction:")
        mem_before = get_memory_usage()
        extractor_ultra = ASNumberExtractor(
            enable_streaming=True, 
            ultra_efficient_mode=True, 
            warn_reserved=False,
            streaming_memory_limit_mb=5
        )
        result_ultra = extractor_ultra.extract_as_numbers_from_file(test_file)
        mem_after = get_memory_usage()
        print(f"  Memory before: {mem_before:.1f}MB")
        print(f"  Memory after: {mem_after:.1f}MB")
        print(f"  Memory delta: {mem_after - mem_before:.1f}MB")
        print(f"  AS numbers found: {len(result_ultra.as_numbers):,}")
        
        del extractor_ultra, result_ultra
        gc.collect()
        
        # Test 4: Line-by-line analysis
        print("\n4. Line-by-line processing analysis:")
        mem_before = get_memory_usage()
        
        # Simulate line-by-line processing
        as_count = 0
        line_count = 0
        
        with open(test_file, 'r') as f:
            for line in f:
                line_count += 1
                if 'peer-as' in line:
                    as_count += 1
                
                # Check memory every 10,000 lines
                if line_count % 10000 == 0:
                    current_mem = get_memory_usage()
                    if line_count == 10000:  # First measurement
                        print(f"  After {line_count:,} lines: {current_mem:.1f}MB (+{current_mem - mem_before:.1f}MB)")
        
        mem_after = get_memory_usage()
        print(f"  Final memory: {mem_after:.1f}MB")
        print(f"  Total delta: {mem_after - mem_before:.1f}MB")
        print(f"  Lines processed: {line_count:,}")
        print(f"  AS lines found: {as_count:,}")
        
        # Final analysis
        print("\n" + "=" * 60)
        print("MEMORY ANALYSIS SUMMARY:")
        print("=" * 60)
        print("Key findings:")
        print("1. File reading creates significant memory overhead")
        print("2. AS number set storage has high per-object overhead in Python")
        print("3. Memory reduction requires avoiding large intermediate objects")
        print("\nRecommendations:")
        print("- Focus on reducing memory delta, not peak memory")
        print("- Use external tools (sort) for deduplication")
        print("- Process in smaller chunks with frequent cleanup")
        
    finally:
        try:
            os.unlink(test_file)
        except OSError:
            pass


def test_chunk_based_processing():
    """Test chunk-based processing to demonstrate memory efficiency"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
        test_file = Path(temp_file.name)
    
    try:
        create_test_file(test_file, 50)
        
        print("\nChunk-based processing test:")
        print("=" * 60)
        
        # Process in small chunks
        chunk_size = 1000  # lines per chunk
        total_as_numbers = set()
        
        gc.collect()
        mem_start = get_memory_usage()
        print(f"Starting memory: {mem_start:.1f}MB")
        
        import re
        pattern = re.compile(r'peer-as\s+(\d+)', re.IGNORECASE)
        
        with open(test_file, 'r') as f:
            chunk_lines = []
            line_count = 0
            
            for line in f:
                chunk_lines.append(line)
                line_count += 1
                
                if len(chunk_lines) >= chunk_size:
                    # Process chunk
                    chunk_as_numbers = set()
                    for chunk_line in chunk_lines:
                        matches = pattern.findall(chunk_line)
                        for match in matches:
                            try:
                                as_num = int(match)
                                if 256 <= as_num <= 4294967295:  # Basic validation
                                    chunk_as_numbers.add(as_num)
                            except ValueError:
                                continue
                    
                    # Add to total and clear chunk
                    total_as_numbers.update(chunk_as_numbers)
                    chunk_lines.clear()
                    
                    # Report memory usage
                    if line_count % 50000 == 0:
                        current_mem = get_memory_usage()
                        print(f"  After {line_count:,} lines: {current_mem:.1f}MB (+{current_mem - mem_start:.1f}MB)")
                        print(f"    AS numbers so far: {len(total_as_numbers):,}")
                        
                        # Force garbage collection
                        gc.collect()
            
            # Process final chunk
            if chunk_lines:
                chunk_as_numbers = set()
                for chunk_line in chunk_lines:
                    matches = pattern.findall(chunk_line)
                    for match in matches:
                        try:
                            as_num = int(match)
                            if 256 <= as_num <= 4294967295:
                                chunk_as_numbers.add(as_num)
                        except ValueError:
                            continue
                total_as_numbers.update(chunk_as_numbers)
        
        mem_end = get_memory_usage()
        print(f"\nFinal results:")
        print(f"  Memory delta: {mem_end - mem_start:.1f}MB")
        print(f"  Lines processed: {line_count:,}")
        print(f"  Unique AS numbers: {len(total_as_numbers):,}")
        print(f"  Memory per AS: {(mem_end - mem_start) / len(total_as_numbers) * 1024:.2f}KB")
        
    finally:
        try:
            os.unlink(test_file)
        except OSError:
            pass


def main():
    """Run memory analysis"""
    
    print("Otto BGP Memory Usage Analysis")
    print("This script analyzes where memory is consumed during AS extraction")
    
    try:
        import psutil
        print(f"✓ Memory monitoring available")
    except ImportError:
        print(f"✗ psutil not available - install with: pip install psutil")
        return 1
    
    analyze_memory_step_by_step()
    test_chunk_based_processing()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())