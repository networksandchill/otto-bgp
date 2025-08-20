"""
Policy Combiner - Merge multiple BGP policies for a single router

This module combines individual AS policies into a unified configuration
file that can be applied to a router. It handles proper formatting,
deduplication, and sectioning of Juniper policy configurations.
"""

import logging
import tempfile
import heapq
import os
import gc
import atexit
from pathlib import Path
from typing import List, Dict, Optional, Set, Iterator, TextIO, Union
from dataclasses import dataclass
from datetime import datetime
from contextlib import contextmanager


@dataclass
class CombinedPolicyResult:
    """Result of policy combination operation"""
    router_hostname: str
    policies_combined: int
    output_file: str
    success: bool
    total_prefixes: int = 0
    error_message: Optional[str] = None
    memory_peak_mb: float = 0.0
    streaming_enabled: bool = False


class StreamingPrefixListBuilder:
    """
    Memory-efficient prefix list builder with overflow to disk
    Enhanced with comprehensive resource management and leak prevention
    """
    
    def __init__(self, max_memory_entries: int = 50000):
        self.max_memory_entries = max_memory_entries
        self.prefix_sets = {}  # Memory-limited prefix storage
        self.overflow_files = {}  # Disk storage for large prefix lists
        self.temp_dir = None
        self._cleanup_registered = False
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        
    def __del__(self):
        """Destructor cleanup as last resort"""
        try:
            self.cleanup()
        except Exception:
            pass  # Silent cleanup in destructor
        
    def add_prefixes_streaming(self, as_number: int, prefix_stream: Iterator[str]) -> None:
        """Add prefixes with memory pressure management"""
        
        if as_number not in self.prefix_sets:
            self.prefix_sets[as_number] = set()
            
        for prefix in prefix_stream:
            # Check memory pressure across all AS numbers
            if self._estimate_total_prefixes() > self.max_memory_entries:
                self._flush_to_disk(as_number)
                
            self.prefix_sets[as_number].add(prefix.strip())
    
    def add_prefix_immediate(self, as_number: int, prefix: str) -> None:
        """Add a single prefix with memory management"""
        
        if as_number not in self.prefix_sets:
            self.prefix_sets[as_number] = set()
            
        # Check memory pressure
        if self._estimate_total_prefixes() > self.max_memory_entries:
            self._flush_to_disk(as_number)
            
        self.prefix_sets[as_number].add(prefix.strip())
    
    def get_prefix_iterator(self, as_number: int) -> Iterator[str]:
        """Get iterator for prefixes, combining memory and disk storage"""
        
        # First yield from memory
        if as_number in self.prefix_sets:
            for prefix in sorted(self.prefix_sets[as_number]):
                yield prefix
                
        # Then yield from disk if exists
        if as_number in self.overflow_files:
            self.overflow_files[as_number].seek(0)
            for line in self.overflow_files[as_number]:
                prefix = line.strip()
                if prefix:
                    yield prefix
    
    def get_all_prefixes_deduplicated(self, as_number: int) -> Iterator[str]:
        """Get deduplicated prefixes using external sort if needed"""
        
        all_prefixes = set()
        
        # Collect from memory
        if as_number in self.prefix_sets:
            all_prefixes.update(self.prefix_sets[as_number])
            
        # Collect from disk
        if as_number in self.overflow_files:
            self.overflow_files[as_number].seek(0)
            for line in self.overflow_files[as_number]:
                prefix = line.strip()
                if prefix:
                    all_prefixes.add(prefix)
                    
        # Yield sorted deduplicated prefixes
        for prefix in sorted(all_prefixes):
            yield prefix
    
    def _estimate_total_prefixes(self) -> int:
        """Estimate total prefixes in memory across all AS numbers"""
        return sum(len(prefixes) for prefixes in self.prefix_sets.values())
    
    def _flush_to_disk(self, as_number: int) -> None:
        """Flush prefix set to disk when memory pressure detected"""
        
        if not self.temp_dir:
            self.temp_dir = tempfile.mkdtemp(prefix='otto_bgp_prefixes_')
            # Register cleanup on exit
            atexit.register(self._emergency_cleanup)
            
        if as_number not in self.overflow_files:
            temp_file_path = os.path.join(self.temp_dir, f'prefixes_AS{as_number}.txt')
            try:
                # Use managed file handle
                file_handle = open(temp_file_path, 'w+')
                self.overflow_files[as_number] = file_handle
            except OSError as e:
                logging.getLogger(__name__).error(f"Failed to create overflow file for AS{as_number}: {e}")
                return
            
        # Write prefixes to disk and clear memory
        if as_number in self.prefix_sets and self.prefix_sets[as_number]:
            try:
                for prefix in sorted(self.prefix_sets[as_number]):
                    self.overflow_files[as_number].write(f"{prefix}\n")
                self.overflow_files[as_number].flush()
                
                # Clear memory
                self.prefix_sets[as_number].clear()
            except (OSError, IOError) as e:
                logging.getLogger(__name__).error(f"Failed to write overflow data for AS{as_number}: {e}")
                # Close and remove problematic file
                if as_number in self.overflow_files:
                    try:
                        self.overflow_files[as_number].close()
                        del self.overflow_files[as_number]
                    except Exception:
                        pass
    
    def cleanup(self) -> None:
        """Clean up temporary files with comprehensive resource management"""
        
        # Close overflow files with error handling
        for as_number, temp_file in list(self.overflow_files.items()):
            try:
                if hasattr(temp_file, 'close') and not temp_file.closed:
                    temp_file.close()
            except Exception as e:
                logging.getLogger(__name__).warning(f"Error closing overflow file for AS{as_number}: {e}")
            finally:
                # Always remove from tracking
                del self.overflow_files[as_number]
                
        # Remove temporary directory
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                import shutil
                shutil.rmtree(self.temp_dir)
                logging.getLogger(__name__).debug(f"Cleaned up temporary directory: {self.temp_dir}")
            except Exception as e:
                logging.getLogger(__name__).warning(f"Error cleaning up temp directory {self.temp_dir}: {e}")
            finally:
                self.temp_dir = None
                
        self.overflow_files.clear()
        self.prefix_sets.clear()
    
    def _emergency_cleanup(self):
        """Emergency cleanup for atexit handler"""
        try:
            self.cleanup()
        except Exception:
            pass  # Silent cleanup in emergency


class StreamingDeduplicator:
    """
    External sorting for memory-efficient prefix deduplication
    """
    
    def __init__(self, chunk_size: int = 10000):
        self.chunk_size = chunk_size
        
    def deduplicate_prefixes_streaming(self, 
                                     prefix_sources: List[Iterator[str]]) -> Iterator[str]:
        """Deduplicate prefixes from multiple sources using external sort with enhanced cleanup"""
        
        # Create temporary files for each source with managed cleanup
        temp_files = []
        
        try:
            for i, prefix_source in enumerate(prefix_sources):
                try:
                    # Use context manager for each temp file creation
                    with tempfile.NamedTemporaryFile(mode='w', delete=False, 
                                                    prefix=f'dedup_source_{i}_') as temp_file:
                        
                        # Write prefixes to temporary file
                        for prefix in prefix_source:
                            temp_file.write(f"{prefix.strip()}\n")
                        temp_file.flush()
                        temp_files.append(temp_file.name)
                        
                except (OSError, IOError) as e:
                    logging.getLogger(__name__).error(f"Failed to create temp file for source {i}: {e}")
                    continue
                
            if temp_files:
                # Use external sort for memory-efficient deduplication
                yield from self._external_sort_deduplicate(temp_files)
            
        finally:
            # Comprehensive cleanup of temporary files
            for temp_file_path in temp_files:
                try:
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
                        logging.getLogger(__name__).debug(f"Cleaned up temp file: {temp_file_path}")
                except OSError as e:
                    logging.getLogger(__name__).warning(f"Failed to cleanup temp file {temp_file_path}: {e}")
                    
    def _external_sort_deduplicate(self, temp_files: List[str]) -> Iterator[str]:
        """Use external sorting for memory-efficient deduplication with proper resource management"""
        
        if not temp_files:
            return
            
        # Use context manager for automatic file handle cleanup
        with self._managed_file_handles(temp_files) as file_handles:
            # Initialize heap with first line from each file
            heap = []
            for i, fh in enumerate(file_handles):
                try:
                    line = fh.readline().strip()
                    if line:
                        heapq.heappush(heap, (line, i))
                except (OSError, IOError) as e:
                    logging.getLogger(__name__).warning(f"Error reading from temp file {i}: {e}")
                    continue
                    
            last_prefix = None
            
            while heap:
                prefix, file_idx = heapq.heappop(heap)
                
                # Yield unique prefixes only
                if prefix != last_prefix:
                    yield prefix
                    last_prefix = prefix
                    
                # Read next line from same file
                try:
                    next_line = file_handles[file_idx].readline().strip()
                    if next_line:
                        heapq.heappush(heap, (next_line, file_idx))
                except (OSError, IOError) as e:
                    logging.getLogger(__name__).warning(f"Error reading next line from file {file_idx}: {e}")
                    continue
    
    @contextmanager
    def _managed_file_handles(self, temp_files: List[str]):
        """Context manager for managing multiple file handles with guaranteed cleanup"""
        file_handles = []
        try:
            for temp_file in temp_files:
                try:
                    fh = open(temp_file, 'r')
                    file_handles.append(fh)
                except (OSError, IOError) as e:
                    logging.getLogger(__name__).warning(f"Failed to open temp file {temp_file}: {e}")
                    # Add None placeholder to maintain index alignment
                    file_handles.append(None)
            
            # Filter out None handles
            valid_handles = [fh for fh in file_handles if fh is not None]
            yield valid_handles
            
        finally:
            # Ensure all file handles are closed
            for fh in file_handles:
                if fh is not None:
                    try:
                        fh.close()
                    except Exception as e:
                        logging.getLogger(__name__).warning(f"Error closing file handle: {e}")


class PolicyCombiner:
    """
    Combine multiple BGP policies into router-specific configuration files
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None, enable_streaming: bool = None):
        """
        Initialize policy combiner
        
        Args:
            logger: Optional logger instance
            enable_streaming: Enable streaming mode (auto-detect if None)
        """
        self.logger = logger or logging.getLogger(__name__)
        
        # Configure streaming based on environment or parameter
        if enable_streaming is None:
            # Auto-enable streaming based on environment variable
            enable_streaming = os.getenv('OTTO_BGP_COMBINER_STREAMING', 'auto').lower()
            if enable_streaming == 'auto':
                self.streaming_auto_detect = True
                self.streaming_enabled = False
            else:
                self.streaming_auto_detect = False
                self.streaming_enabled = enable_streaming in ('true', '1', 'yes', 'on')
        else:
            self.streaming_auto_detect = False
            self.streaming_enabled = enable_streaming
            
        # Memory management settings
        self.streaming_threshold_mb = float(os.getenv('OTTO_BGP_STREAMING_THRESHOLD_MB', '10'))
        self.max_memory_entries = int(os.getenv('OTTO_BGP_MAX_MEMORY_ENTRIES', '50000'))
        
        # Memory tracking
        self.memory_peak_mb = 0.0
        
    def _estimate_total_file_size_mb(self, policy_files: List[Path]) -> float:
        """Estimate total file size in MB"""
        total_size = 0
        for policy_file in policy_files:
            if policy_file.exists():
                total_size += policy_file.stat().st_size
        return total_size / (1024 * 1024)
    
    def _should_use_streaming(self, policy_files: List[Path]) -> bool:
        """Determine if streaming should be used based on file sizes and configuration"""
        
        if not self.streaming_auto_detect:
            return self.streaming_enabled
            
        # Auto-detect based on file size
        total_size_mb = self._estimate_total_file_size_mb(policy_files)
        use_streaming = total_size_mb > self.streaming_threshold_mb
        
        if use_streaming:
            self.logger.info(f"Auto-enabling streaming mode for {total_size_mb:.1f}MB of policy files")
        else:
            self.logger.debug(f"Using standard mode for {total_size_mb:.1f}MB of policy files")
            
        return use_streaming

    def combine_policies_for_router(self, 
                                   router_hostname: str,
                                   policy_files: List[Path],
                                   output_dir: Path,
                                   format: str = "juniper") -> CombinedPolicyResult:
        """
        Combine multiple policy files for a single router
        
        Args:
            router_hostname: Hostname of the router
            policy_files: List of policy file paths to combine
            output_dir: Directory to save combined policy
            format: Output format (juniper, set, hierarchical)
            
        Returns:
            CombinedPolicyResult with operation details
        """
        try:
            self.logger.info(f"Combining {len(policy_files)} policies for {router_hostname}")
            
            if not policy_files:
                return CombinedPolicyResult(
                    router_hostname=router_hostname,
                    policies_combined=0,
                    output_file="",
                    success=False,
                    error_message="No policy files provided"
                )
                
            # Determine if we should use streaming
            use_streaming = self._should_use_streaming(policy_files)
            self.streaming_enabled = use_streaming
            
            # Save combined policy using appropriate method
            output_file = output_dir / f"{router_hostname}_combined_policy.txt"
            
            if use_streaming:
                return self._combine_policies_streaming(
                    router_hostname, policy_files, output_file, format
                )
            else:
                return self._combine_policies_standard(
                    router_hostname, policy_files, output_file, format
                )
            
        except Exception as e:
            self.logger.error(f"Failed to combine policies for {router_hostname}: {e}")
            return CombinedPolicyResult(
                router_hostname=router_hostname,
                policies_combined=0,
                output_file="",
                success=False,
                error_message=str(e)
            )
    
    def _combine_policies_streaming(self, 
                                  router_hostname: str,
                                  policy_files: List[Path],
                                  output_file: Path,
                                  format: str) -> CombinedPolicyResult:
        """
        Combine policies using streaming approach for memory efficiency
        """
        start_memory = self._get_memory_usage_mb()
        self.memory_peak_mb = start_memory
        policies_processed = 0
        total_prefixes = 0
        
        try:
            self.logger.info(f"Using streaming mode for {len(policy_files)} policy files")
            
            # Direct streaming approach - write output immediately without accumulating
            with open(output_file, 'w') as output:
                # Write header
                timestamp = datetime.now().isoformat()
                output.write(f"/* Combined BGP policies for {router_hostname} */\n")
                output.write(f"/* Generated: {timestamp} */\n")
                output.write(f"/* Total policies: {len(policy_files)} */\n")
                output.write("\n")
                output.write("policy-options {\n")
                
                # Process each policy file individually without loading all into memory
                valid_as_numbers = []
                
                for policy_file in policy_files:
                    if not policy_file.exists():
                        self.logger.warning(f"Policy file not found: {policy_file}")
                        continue
                        
                    as_number = self._extract_as_number_from_filename(policy_file.name)
                    if as_number == 0:
                        self.logger.warning(f"Could not extract AS number from {policy_file.name}")
                        continue
                        
                    valid_as_numbers.append(as_number)
                    
                    # Stream this individual policy file directly to output
                    self._stream_single_policy_file(output, policy_file, as_number)
                    
                    policies_processed += 1
                    
                    # Track memory usage
                    current_memory = self._get_memory_usage_mb()
                    self.memory_peak_mb = max(self.memory_peak_mb, current_memory)
                    
                    # Force garbage collection after each file to minimize memory accumulation
                    gc.collect()
                
                # Close policy-options block
                output.write("}\n")
            
            # Count total prefixes by scanning the output file
            import re
            with open(output_file, 'r') as f:
                for line in f:
                    if '/' in line and re.search(r'\d+\.\d+\.\d+\.\d+/\d+', line):
                        total_prefixes += 1
            
            end_memory = self._get_memory_usage_mb()
            self.logger.info(f"Streaming combination complete. Memory peak: {self.memory_peak_mb:.1f}MB")
            
            return CombinedPolicyResult(
                router_hostname=router_hostname,
                policies_combined=policies_processed,
                output_file=str(output_file),
                success=True,
                total_prefixes=total_prefixes,
                memory_peak_mb=self.memory_peak_mb,
                streaming_enabled=True
            )
            
        finally:
            # Force final garbage collection
            gc.collect()
    
    def _stream_single_policy_file(self, output_file: TextIO, policy_file: Path, as_number: int) -> None:
        """Stream a single policy file directly to output without loading into memory"""
        
        output_file.write(f"    /* AS{as_number} */\n")
        output_file.write(f"    prefix-list AS{as_number} {{\n")
        
        # Use a set to deduplicate prefixes for this AS only (memory efficient)
        prefixes_seen = set()
        
        # Stream through the file line by line
        with open(policy_file, 'r') as input_file:
            for line in input_file:
                prefix = self._extract_prefix_from_line(line)
                if prefix and prefix not in prefixes_seen:
                    prefixes_seen.add(prefix)
                    output_file.write(f"        {prefix};\n")
        
        output_file.write("    }\n")
        output_file.write("\n")
        
        # Clear the prefix set for this AS to free memory immediately
        prefixes_seen.clear()
        del prefixes_seen
    
    def _combine_policies_standard(self, 
                                 router_hostname: str,
                                 policy_files: List[Path],
                                 output_file: Path,
                                 format: str) -> CombinedPolicyResult:
        """
        Combine policies using standard (non-streaming) approach
        """
        start_memory = self._get_memory_usage_mb()
        
        # Read all policy files (original implementation)
        policies = []
        for policy_file in policy_files:
            if policy_file.exists():
                content = policy_file.read_text()
                as_number = self._extract_as_number_from_filename(policy_file.name)
                policies.append({
                    "as_number": as_number,
                    "content": content,
                    "file": policy_file.name
                })
            else:
                self.logger.warning(f"Policy file not found: {policy_file}")
        
        if not policies:
            return CombinedPolicyResult(
                router_hostname=router_hostname,
                policies_combined=0,
                output_file="",
                success=False,
                error_message="No valid policy files found"
            )
        
        # Generate combined policy based on format
        if format == "juniper":
            combined_content = self._combine_juniper_format(router_hostname, policies)
        elif format == "set":
            combined_content = self._combine_set_format(router_hostname, policies)
        elif format == "hierarchical":
            combined_content = self._combine_hierarchical_format(router_hostname, policies)
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        # Count total prefixes
        total_prefixes = combined_content.count("prefix")
        
        # Save combined policy
        output_file.write_text(combined_content)
        
        end_memory = self._get_memory_usage_mb()
        self.memory_peak_mb = max(start_memory, end_memory)
        
        self.logger.info(f"Standard combination complete. Memory peak: {self.memory_peak_mb:.1f}MB")
        
        return CombinedPolicyResult(
            router_hostname=router_hostname,
            policies_combined=len(policies),
            output_file=str(output_file),
            success=True,
            total_prefixes=total_prefixes,
            memory_peak_mb=self.memory_peak_mb,
            streaming_enabled=False
        )
    
    def _get_memory_usage_mb(self) -> float:
        """Get current memory usage in MB"""
        try:
            import psutil
            process = psutil.Process()
            return process.memory_info().rss / (1024 * 1024)
        except ImportError:
            # Fallback to approximate memory tracking
            import resource
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # On macOS, ru_maxrss is in bytes
    
    def _extract_prefix_from_line(self, line: str) -> Optional[str]:
        """Extract a prefix from a policy line"""
        import re
        
        # Match IP prefix patterns (IPv4/CIDR)
        match = re.search(r'(\d+\.\d+\.\d+\.\d+/\d+)', line.strip())
        if match:
            return match.group(1)
        return None
    
    def _write_juniper_format_streaming(self, 
                                      output_file: TextIO,
                                      router_hostname: str,
                                      as_numbers: List[int],
                                      prefix_builder: StreamingPrefixListBuilder) -> None:
        """Write Juniper format using streaming approach"""
        
        # Write header
        timestamp = datetime.now().isoformat()
        output_file.write(f"/* Combined BGP policies for {router_hostname} */\n")
        output_file.write(f"/* Generated: {timestamp} */\n")
        output_file.write(f"/* Total policies: {len(as_numbers)} */\n")
        output_file.write("\n")
        output_file.write("policy-options {\n")
        
        # Stream each AS policy
        for as_number in sorted(as_numbers):
            output_file.write(f"    /* AS{as_number} */\n")
            output_file.write(f"    prefix-list AS{as_number} {{\n")
            
            # Stream prefixes for this AS
            prefix_count = 0
            for prefix in prefix_builder.get_all_prefixes_deduplicated(as_number):
                output_file.write(f"        {prefix};\n")
                prefix_count += 1
                
                # Periodic garbage collection for very large prefix lists
                if prefix_count % 1000 == 0:
                    gc.collect()
                    
            output_file.write("    }\n")
            output_file.write("\n")
        
        output_file.write("}\n")
    
    def _write_set_format_streaming(self, 
                                  output_file: TextIO,
                                  router_hostname: str,
                                  as_numbers: List[int],
                                  prefix_builder: StreamingPrefixListBuilder) -> None:
        """Write set command format using streaming approach"""
        
        # Write header
        timestamp = datetime.now().isoformat()
        output_file.write(f"# Combined BGP policies for {router_hostname}\n")
        output_file.write(f"# Generated: {timestamp}\n")
        output_file.write(f"# Total policies: {len(as_numbers)}\n")
        output_file.write("\n")
        
        # Stream each AS policy as set commands
        for as_number in sorted(as_numbers):
            output_file.write(f"# AS{as_number}\n")
            
            prefix_count = 0
            for prefix in prefix_builder.get_all_prefixes_deduplicated(as_number):
                output_file.write(f"set policy-options prefix-list AS{as_number} {prefix}\n")
                prefix_count += 1
                
                # Periodic garbage collection
                if prefix_count % 1000 == 0:
                    gc.collect()
                    
            output_file.write("\n")
    
    def _write_hierarchical_format_streaming(self, 
                                           output_file: TextIO,
                                           router_hostname: str,
                                           as_numbers: List[int],
                                           prefix_builder: StreamingPrefixListBuilder) -> None:
        """Write hierarchical format using streaming approach"""
        
        # Write header
        timestamp = datetime.now().isoformat()
        output_file.write("/*\n")
        output_file.write(" * BGP Policy Configuration\n")
        output_file.write(f" * Router: {router_hostname}\n")
        output_file.write(f" * Generated: {timestamp}\n")
        output_file.write(f" * Policies: {len(as_numbers)}\n")
        output_file.write(" */\n")
        output_file.write("\n")
        output_file.write("policy-options {\n")
        
        # Categorize AS numbers
        transit_as = []
        customer_as = []
        cdn_as = []
        
        for as_number in as_numbers:
            if 13000 <= as_number <= 14000:
                cdn_as.append(as_number)
            elif as_number >= 64512:
                customer_as.append(as_number)
            else:
                transit_as.append(as_number)
        
        # Write sections in streaming fashion
        if transit_as:
            output_file.write("    /* TRANSIT PROVIDERS */\n")
            for as_number in sorted(transit_as):
                self._write_as_section_streaming(output_file, as_number, prefix_builder, indent=1)
        
        if cdn_as:
            output_file.write("    /* CDN PROVIDERS */\n")
            for as_number in sorted(cdn_as):
                self._write_as_section_streaming(output_file, as_number, prefix_builder, indent=1)
        
        if customer_as:
            output_file.write("    /* CUSTOMERS */\n")
            for as_number in sorted(customer_as):
                self._write_as_section_streaming(output_file, as_number, prefix_builder, indent=1)
        
        output_file.write("}\n")
    
    def _write_as_section_streaming(self, 
                                  output_file: TextIO,
                                  as_number: int,
                                  prefix_builder: StreamingPrefixListBuilder,
                                  indent: int = 0) -> None:
        """Write a single AS section using streaming"""
        
        indent_str = "    " * indent
        output_file.write(f"{indent_str}prefix-list AS{as_number} {{\n")
        
        prefix_count = 0
        for prefix in prefix_builder.get_all_prefixes_deduplicated(as_number):
            output_file.write(f"{indent_str}    {prefix};\n")
            prefix_count += 1
            
            # Periodic garbage collection
            if prefix_count % 1000 == 0:
                gc.collect()
                
        output_file.write(f"{indent_str}}}\n")
        output_file.write("\n")
    
    def _combine_juniper_format(self, router_hostname: str, policies: List[Dict]) -> str:
        """
        Combine policies in Juniper hierarchical format
        
        Args:
            router_hostname: Router hostname for header
            policies: List of policy dictionaries
            
        Returns:
            Combined policy configuration
        """
        # Optimize header generation with batch operations
        timestamp = datetime.now().isoformat()
        header_lines = [
            f"/* Combined BGP policies for {router_hostname} */",
            f"/* Generated: {timestamp} */",
            f"/* Total policies: {len(policies)} */",
            ""
        ]
        lines = header_lines.copy()
        
        # Main policy-options block
        lines.append("policy-options {")
        
        # Process each policy
        prefix_lists = {}
        for policy in policies:
            as_number = policy["as_number"]
            content = policy["content"]
            
            # Extract prefix-list content
            prefix_list = self._extract_prefix_list(content)
            if prefix_list:
                list_name = prefix_list.get("name", f"AS{as_number}")
                if list_name not in prefix_lists:
                    prefix_lists[list_name] = {
                        "as_number": as_number,
                        "prefixes": []
                    }
                prefix_lists[list_name]["prefixes"].extend(prefix_list.get("prefixes", []))
        
        # Write deduplicated prefix lists with optimized string building
        for list_name, data in prefix_lists.items():
            # Deduplicate prefixes first
            unique_prefixes = sorted(set(data["prefixes"]))
            
            # Build prefix list section efficiently
            prefix_section = [
                f"    /* AS{data['as_number']} */",
                f"    prefix-list {list_name} {{",
                *[f"        {prefix};" for prefix in unique_prefixes],
                "    }",
                ""
            ]
            lines.extend(prefix_section)
        
        # Close policy-options
        lines.append("}")
        
        return "\n".join(lines)
    
    def _combine_set_format(self, router_hostname: str, policies: List[Dict]) -> str:
        """
        Combine policies in Juniper set command format
        
        Args:
            router_hostname: Router hostname for header
            policies: List of policy dictionaries
            
        Returns:
            Combined policy as set commands
        """
        # Optimize header generation with batch operations
        timestamp = datetime.now().isoformat()
        header_lines = [
            f"# Combined BGP policies for {router_hostname}",
            f"# Generated: {timestamp}",
            f"# Total policies: {len(policies)}",
            ""
        ]
        lines = header_lines.copy()
        
        # Process each policy with optimized command generation
        seen_commands = set()
        for policy in policies:
            as_number = policy["as_number"]
            content = policy["content"]
            
            # Convert to set commands
            set_commands = self._convert_to_set_commands(content)
            new_commands = [cmd for cmd in set_commands if cmd not in seen_commands]
            
            if new_commands:
                policy_section = [f"# AS{as_number}"] + new_commands + [""]
                lines.extend(policy_section)
                seen_commands.update(new_commands)
        
        return "\n".join(lines)
    
    def _combine_hierarchical_format(self, router_hostname: str, policies: List[Dict]) -> str:
        """
        Combine policies with clear hierarchical organization
        
        Args:
            router_hostname: Router hostname for header
            policies: List of policy dictionaries
            
        Returns:
            Hierarchically organized combined policy
        """
        # Optimize header generation with batch operations
        timestamp = datetime.now().isoformat()
        header_lines = [
            "/*",
            " * BGP Policy Configuration",
            f" * Router: {router_hostname}",
            f" * Generated: {timestamp}",
            f" * Policies: {len(policies)}",
            " */",
            ""
        ]
        lines = header_lines.copy()
        
        # Group policies by type
        transit_policies = []
        customer_policies = []
        cdn_policies = []
        
        for policy in policies:
            as_number = policy["as_number"]
            # Categorize based on AS number ranges (example logic)
            if 13000 <= as_number <= 14000:
                cdn_policies.append(policy)
            elif as_number >= 64512:
                customer_policies.append(policy)
            else:
                transit_policies.append(policy)
        
        lines.append("policy-options {")
        
        # Transit providers section
        if transit_policies:
            lines.append("    /* TRANSIT PROVIDERS */")
            for policy in transit_policies:
                lines.extend(self._format_policy_section(policy, indent=1))
        
        # CDN providers section
        if cdn_policies:
            lines.append("    /* CDN PROVIDERS */")
            for policy in cdn_policies:
                lines.extend(self._format_policy_section(policy, indent=1))
        
        # Customer section
        if customer_policies:
            lines.append("    /* CUSTOMERS */")
            for policy in customer_policies:
                lines.extend(self._format_policy_section(policy, indent=1))
        
        lines.append("}")
        
        return "\n".join(lines)
    
    def _extract_prefix_list(self, policy_content: str) -> Optional[Dict]:
        """
        Extract prefix-list information from policy content
        
        Args:
            policy_content: Raw policy configuration
            
        Returns:
            Dictionary with prefix-list name and prefixes
        """
        import re
        
        # Find prefix-list block
        list_match = re.search(r'prefix-list\s+(\S+)\s*{([^}]*)}', policy_content, re.DOTALL)
        if not list_match:
            return None
        
        list_name = list_match.group(1)
        list_content = list_match.group(2)
        
        # Extract prefixes
        prefixes = re.findall(r'(\d+\.\d+\.\d+\.\d+/\d+)', list_content)
        
        return {
            "name": list_name,
            "prefixes": prefixes
        }
    
    def _extract_as_number_from_filename(self, filename: str) -> int:
        """
        Extract AS number from policy filename
        
        Args:
            filename: Policy filename (e.g., "AS65001_policy.txt")
            
        Returns:
            AS number or 0 if not found
        """
        import re
        
        match = re.search(r'AS(\d+)', filename)
        if match:
            return int(match.group(1))
        return 0
    
    def _convert_to_set_commands(self, policy_content: str) -> List[str]:
        """
        Convert hierarchical policy to set commands
        
        Args:
            policy_content: Hierarchical policy configuration
            
        Returns:
            List of set commands
        """
        import re
        
        commands = []
        
        # Extract prefix-list entries
        list_match = re.search(r'prefix-list\s+(\S+)\s*{([^}]*)}', policy_content, re.DOTALL)
        if list_match:
            list_name = list_match.group(1)
            list_content = list_match.group(2)
            
            prefixes = re.findall(r'(\d+\.\d+\.\d+\.\d+/\d+)', list_content)
            for prefix in prefixes:
                commands.append(f"set policy-options prefix-list {list_name} {prefix}")
        
        return commands
    
    def _format_policy_section(self, policy: Dict, indent: int = 0) -> List[str]:
        """
        Format a policy section with proper indentation
        
        Args:
            policy: Policy dictionary
            indent: Indentation level
            
        Returns:
            List of formatted lines
        """
        lines = []
        indent_str = "    " * indent
        
        as_number = policy["as_number"]
        content = policy["content"]
        
        # Extract and format prefix-list
        prefix_list = self._extract_prefix_list(content)
        if prefix_list:
            lines.append(f"{indent_str}prefix-list AS{as_number} {{")
            for prefix in prefix_list["prefixes"]:
                lines.append(f"{indent_str}    {prefix};")
            lines.append(f"{indent_str}}}")
            lines.append("")
        
        return lines
    
    def merge_policy_directories(self, 
                                router_dirs: List[Path],
                                output_dir: Path,
                                format: str = "juniper") -> List[CombinedPolicyResult]:
        """
        Merge policies from multiple router directories
        
        Args:
            router_dirs: List of router directories containing policies
            output_dir: Output directory for combined policies
            format: Output format
            
        Returns:
            List of CombinedPolicyResult for each router
        """
        results = []
        
        for router_dir in router_dirs:
            if not router_dir.exists():
                self.logger.warning(f"Router directory not found: {router_dir}")
                continue
            
            # Get router hostname from directory name
            router_hostname = router_dir.name
            
            # Find all policy files in directory
            policy_files = list(router_dir.glob("AS*_policy.txt"))
            
            if policy_files:
                result = self.combine_policies_for_router(
                    router_hostname=router_hostname,
                    policy_files=policy_files,
                    output_dir=output_dir,
                    format=format
                )
                results.append(result)
            else:
                self.logger.warning(f"No policy files found in {router_dir}")
        
        return results