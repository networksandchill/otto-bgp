#!/usr/bin/env python3
"""
AS Number Extraction and BGP Data Processing

Modern implementation combining functionality from:
- bgpq3_processor.py (AS number extraction)
- AS-info.py (text cleaning and deduplication)

Features:
- Robust AS number extraction with configurable filtering
- BGP configuration text cleaning
- In-memory processing with structured data objects
- Comprehensive logging and error handling
"""

import re
import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Set, List, Optional, Dict, Union, Iterator
from pathlib import Path


@dataclass
class ASExtractionResult:
    """Result of AS number extraction from text"""

    as_numbers: Set[int]
    source_file: Optional[str] = None
    total_lines_processed: int = 0
    extraction_method: str = "regex"
    filters_applied: List[str] = None


@dataclass
class BGPProcessingResult:
    """Result of BGP configuration text processing"""

    processed_text: str
    original_lines: int
    processed_lines: int
    duplicates_removed: int
    substrings_removed: List[str] = None


class MemoryEfficientASSet:
    """Memory-optimized AS number collection with aggressive overflow management"""

    def __init__(self, max_memory_mb: int = 10):  # Much lower memory limit
        self.max_memory = max_memory_mb * 1024 * 1024  # Convert to bytes
        self._as_numbers = set()
        self._overflow_file = None
        self._overflow_count = 0
        self._total_added = 0
        self._flush_threshold = 1000  # Flush every 1000 AS numbers
        self.logger = logging.getLogger(__name__)

    def add_as_numbers(self, as_numbers: Union[Set[int], List[int]]):
        """Add AS numbers with aggressive memory management"""
        for as_num in as_numbers:
            self.add(as_num)

    def add(self, as_num: int):
        """Add single AS number with frequent flushing"""
        self._as_numbers.add(as_num)
        self._total_added += 1

        # Flush frequently to keep memory low
        if len(self._as_numbers) >= self._flush_threshold:
            self._flush_to_disk()

    def get_all_as_numbers(self) -> Set[int]:
        """Retrieve all AS numbers, consolidating from disk if needed"""
        # Flush any remaining numbers
        if self._as_numbers:
            self._flush_to_disk()

        if self._overflow_file is None:
            return set()  # No data

        # Read all numbers from disk and deduplicate
        all_as_numbers = set()

        try:
            self._overflow_file.seek(0)
            for line in self._overflow_file:
                try:
                    as_num = int(line.strip())
                    all_as_numbers.add(as_num)
                except ValueError:
                    continue
        except IOError as e:
            self.logger.warning(f"Error reading overflow file: {e}")

        return all_as_numbers

    def _estimate_memory_usage(self) -> int:
        """Estimate current memory usage in bytes"""
        # Conservative estimate: each int in set uses ~28 bytes (Python overhead)
        return len(self._as_numbers) * 28

    def _flush_to_disk(self):
        """Flush AS numbers to temporary file"""
        if self._overflow_file is None:
            self._overflow_file = tempfile.NamedTemporaryFile(mode="w+", delete=False)
            self.logger.debug(f"Creating overflow file: {self._overflow_file.name}")

        # Write current AS numbers to disk
        for as_num in self._as_numbers:
            self._overflow_file.write(f"{as_num}\n")
        self._overflow_file.flush()

        self._overflow_count += len(self._as_numbers)
        self._as_numbers.clear()

        self.logger.debug(
            f"Flushed {self._overflow_count} AS numbers to disk (memory freed)"
        )

    def __len__(self):
        """Return total count including overflow"""
        return len(self._as_numbers) + self._overflow_count

    def __del__(self):
        """Cleanup overflow file"""
        if self._overflow_file:
            try:
                os.unlink(self._overflow_file.name)
            except (OSError, AttributeError):
                pass


class UltraMemoryEfficientASExtractor:
    """Ultra memory-efficient AS extractor using minimal memory footprint"""

    def __init__(self, memory_limit_mb: int = 5):
        self.memory_limit_mb = memory_limit_mb
        self.logger = logging.getLogger(__name__)

    def extract_as_numbers_minimal_memory(
        self, file_path: Union[str, Path], pattern: re.Pattern, validator_func
    ) -> Set[int]:
        """Extract AS numbers with minimal memory usage using disk-based processing and external sort"""
        file_path = Path(file_path)

        # Use temporary files for processing
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_as_file:
            temp_as_path = temp_as_file.name
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_sorted_file:
            temp_sorted_path = temp_sorted_file.name

        lines_processed = 0

        try:
            # First pass: Extract all AS numbers to temporary file (no deduplication)
            with open(file_path, "r", encoding="utf-8", buffering=4096) as input_file:
                with open(temp_as_path, "w") as temp_file:
                    for line in input_file:
                        lines_processed += 1

                        # Extract AS numbers from this line only
                        matches = pattern.findall(line)
                        for match in matches:
                            try:
                                as_num = int(match)
                                if validator_func(as_num):
                                    temp_file.write(f"{as_num}\n")
                            except ValueError:
                                continue

                        # Periodic progress for very large files
                        if lines_processed % 100000 == 0:
                            self.logger.debug(f"Processed {lines_processed} lines")

            # Second pass: External sort using system sort command for efficiency
            import subprocess

            try:
                # Use system sort with unique flag for memory-efficient deduplication
                # Proper file handle management with context manager
                with open(temp_sorted_path, "w") as sorted_file:
                    result = subprocess.run(
                        ["sort", "-n", "-u", temp_as_path],
                        stdout=sorted_file,
                        stderr=subprocess.PIPE,
                        timeout=300,
                    )

                if result.returncode != 0:
                    raise RuntimeError(f"Sort command failed: {result.stderr.decode()}")

                self.logger.debug("External sort completed successfully")

            except subprocess.TimeoutExpired as e:
                # Ensure proper cleanup on timeout
                self.logger.warning(f"Sort command timed out after 300 seconds: {e}")
                # Clean up partial sorted file if it exists
                try:
                    if os.path.exists(temp_sorted_path):
                        os.unlink(temp_sorted_path)
                except OSError:
                    pass  # File cleanup failed, but continue
                return self._fallback_disk_deduplication(temp_as_path)
            except FileNotFoundError:
                # Fallback to Python-based sorting if system sort unavailable
                self.logger.warning("System sort unavailable, using Python fallback")
                return self._fallback_disk_deduplication(temp_as_path)

            # Third pass: Read sorted unique numbers with minimal memory usage
            final_as_numbers = set()
            batch_size = 5000  # Very small batches
            current_batch = []

            with open(temp_sorted_path, "r") as sorted_file:
                for line in sorted_file:
                    try:
                        as_num = int(line.strip())
                        current_batch.append(as_num)

                        if len(current_batch) >= batch_size:
                            # Process small batch and immediately clear
                            final_as_numbers.update(current_batch)
                            current_batch.clear()

                    except ValueError:
                        continue

                # Process final batch
                if current_batch:
                    final_as_numbers.update(current_batch)

            self.logger.info(
                f"Ultra-efficient extraction complete: {lines_processed} lines processed, "
                f"{len(final_as_numbers)} unique AS numbers found"
            )

            return final_as_numbers

        except Exception as e:
            self.logger.error(f"Error during ultra-efficient extraction: {e}")
            raise
        finally:
            # Clean up temporary files
            for temp_path in [temp_as_path, temp_sorted_path]:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    def _fallback_disk_deduplication(self, temp_file_path: str) -> Set[int]:
        """Fallback deduplication using disk-based approach when system sort unavailable"""
        self.logger.info("Using disk-based deduplication fallback")

        # Read numbers in small batches, track in bloom filter approximation
        seen_ranges = {}  # Range-based tracking to reduce memory
        final_as_numbers = set()
        batch_size = 1000
        current_batch = []

        with open(temp_file_path, "r") as temp_file:
            for line in temp_file:
                try:
                    as_num = int(line.strip())

                    # Range-based deduplication check
                    range_key = as_num // 1000  # Group by thousands
                    if range_key not in seen_ranges:
                        seen_ranges[range_key] = set()

                    if as_num not in seen_ranges[range_key]:
                        seen_ranges[range_key].add(as_num)
                        current_batch.append(as_num)

                    if len(current_batch) >= batch_size:
                        final_as_numbers.update(current_batch)
                        current_batch.clear()

                except ValueError:
                    continue

            # Process final batch
            if current_batch:
                final_as_numbers.update(current_batch)

        return final_as_numbers


class StreamingASExtractor:
    """Memory-efficient streaming AS number extractor"""

    def __init__(
        self,
        chunk_size: int = 8192,
        memory_limit_mb: int = 50,
        dedup_frequency: int = 10000,
    ):
        """
        Initialize streaming AS extractor

        Args:
            chunk_size: Buffer size for file reading
            memory_limit_mb: Memory limit for AS number collection
            dedup_frequency: Lines processed before deduplication
        """
        self.chunk_size = chunk_size
        self.memory_limit_mb = memory_limit_mb
        self.dedup_frequency = dedup_frequency
        self.logger = logging.getLogger(__name__)

    def extract_as_numbers_streaming(
        self, file_path: Union[str, Path], pattern: re.Pattern, validator_func
    ) -> Set[int]:
        """Extract AS numbers using streaming file processing with aggressive memory management"""
        # Validate file_path input
        if not file_path or (isinstance(file_path, str) and not file_path.strip()):
            raise ValueError("file_path cannot be empty or None")

        file_path = Path(file_path)

        # Check if file exists and is a file
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        as_collection = MemoryEfficientASSet(self.memory_limit_mb)
        lines_processed = 0

        try:
            with open(file_path, "r", encoding="utf-8", buffering=self.chunk_size) as f:
                for line in f:  # Process line-by-line, not entire file
                    lines_processed += 1

                    # Extract AS numbers from this line
                    line_as_numbers = self._extract_from_line(
                        line.strip(), pattern, validator_func
                    )

                    # Add to collection (with frequent disk flushing)
                    for as_num in line_as_numbers:
                        as_collection.add(as_num)

                    # Periodic progress logging for large files
                    if lines_processed % 50000 == 0:
                        self.logger.debug(
                            f"Processed {lines_processed} lines, {len(as_collection)} AS numbers found"
                        )

        except Exception as e:
            self.logger.error(
                f"Error during streaming extraction from {file_path}: {e}"
            )
            raise

        final_as_numbers = as_collection.get_all_as_numbers()
        self.logger.info(
            f"Streaming extraction complete: {lines_processed} lines processed, "
            f"{len(final_as_numbers)} unique AS numbers found"
        )

        return final_as_numbers

    def extract_as_numbers_ultra_efficient(
        self, file_path: Union[str, Path], pattern: re.Pattern, validator_func
    ) -> Set[int]:
        """Extract AS numbers using ultra-efficient minimal memory approach"""
        ultra_extractor = UltraMemoryEfficientASExtractor(memory_limit_mb=5)
        return ultra_extractor.extract_as_numbers_minimal_memory(
            file_path, pattern, validator_func
        )

    def _extract_from_line(
        self, line: str, pattern: re.Pattern, validator_func
    ) -> List[int]:
        """Extract AS numbers from a single line"""
        as_numbers = []

        try:
            matches = pattern.findall(line)
            for match in matches:
                try:
                    as_num = int(match)
                    if validator_func(as_num):
                        as_numbers.append(as_num)
                except ValueError:
                    continue
        except Exception as e:
            self.logger.debug(f"Error processing line: {e}")

        return as_numbers


class TextStreamProcessor:
    """Memory-efficient text streaming processor for BGP configurations"""

    def __init__(self, buffer_lines: int = 1000):
        self.buffer_lines = buffer_lines
        self.logger = logging.getLogger(__name__)

    def process_text_streaming(self, file_path: Union[str, Path]) -> Iterator[str]:
        """Stream text processing without loading entire file"""
        file_path = Path(file_path)

        with open(file_path, "r", encoding="utf-8") as f:
            current_buffer = []

            for line_num, line in enumerate(f, 1):
                # Apply line-level preprocessing
                processed_line = self._preprocess_line(line)
                if processed_line.strip():  # Skip empty lines
                    current_buffer.append(processed_line)

                # Process in chunks to manage memory
                if len(current_buffer) >= self.buffer_lines:
                    yield from self._process_text_chunk(current_buffer)
                    current_buffer.clear()

            # Process final chunk
            if current_buffer:
                yield from self._process_text_chunk(current_buffer)

    def _preprocess_line(self, line: str) -> str:
        """Apply line-level preprocessing"""
        # Remove control characters but preserve structure
        cleaned = "".join(char for char in line if ord(char) >= 32 or char in "\n\r\t")

        # Normalize whitespace but preserve indentation
        cleaned = re.sub(r"[ \t]+", " ", cleaned.rstrip())

        return cleaned

    def _process_text_chunk(self, lines: List[str]) -> Iterator[str]:
        """Process a chunk of lines"""
        for line in lines:
            yield line


class ASNumberExtractor:
    """Extract AS numbers from various text sources with RFC-compliant validation"""

    # Default regex patterns for AS number extraction
    AS_PATTERNS = {
        "standard": r"(?:AS)?(\d+)",  # Matches AS12345 or 12345
        "peer_as": r"peer-as\s+(\d+)",  # Matches "peer-as 12345"
        "explicit_as": r"AS(\d+)",  # Matches only AS12345 format
        "autonomous_system": r"autonomous-system\s+(\d+)",  # Matches "autonomous-system 12345"
    }

    # RFC-compliant AS number ranges (as of 2025)
    # Based on IANA AS Number Registry and various RFCs
    RESERVED_AS_RANGES = [
        (0, 0),  # Reserved (RFC 7607)
        (23456, 23456),  # AS_TRANS (RFC 6793)
        (64496, 64511),  # Documentation/Sample Use (RFC 5398)
        (64512, 65534),  # Private Use (RFC 6996)
        (65535, 65535),  # Reserved (RFC 7300)
        (65536, 65551),  # Documentation/Sample Use (RFC 5398)
        (4200000000, 4294967294),  # Private Use 32-bit (RFC 6996)
        (4294967295, 4294967295),  # Reserved (RFC 7300)
    ]

    # AS number validation constants
    AS_NUMBER_MIN = 0
    AS_NUMBER_MAX = 4294967295  # 32-bit unsigned integer maximum

    def __init__(
        self,
        min_as_number: int = 256,
        max_as_number: int = 4294967295,
        patterns: Optional[Dict[str, str]] = None,
        warn_reserved: bool = True,
        strict_validation: bool = True,
        streaming_memory_limit_mb: int = 50,
        streaming_chunk_size: int = 8192,
        ultra_efficient_mode: bool = False,
    ):
        """
        Initialize AS number extractor with enhanced security validation and streaming support

        Args:
            min_as_number: Minimum valid AS number (default 256 to exclude IP octets)
            max_as_number: Maximum valid AS number (32-bit max)
            patterns: Custom regex patterns for AS extraction
            warn_reserved: Log warnings for reserved AS number ranges
            strict_validation: Enable strict RFC-compliant validation
            streaming_memory_limit_mb: Memory limit for streaming mode (MB)
            streaming_chunk_size: Buffer size for streaming file reads
            ultra_efficient_mode: Enable ultra-efficient mode for very large files
        """
        self.logger = logging.getLogger(__name__)

        # Validate initialization parameters
        if not isinstance(min_as_number, int) or not isinstance(max_as_number, int):
            raise ValueError("AS number limits must be integers")

        if (
            not self.AS_NUMBER_MIN
            <= min_as_number
            <= max_as_number
            <= self.AS_NUMBER_MAX
        ):
            raise ValueError(
                f"Invalid AS number range: {min_as_number}-{max_as_number}"
            )

        self.min_as_number = min_as_number
        self.max_as_number = max_as_number
        self.patterns = patterns or self.AS_PATTERNS.copy()
        self.warn_reserved = warn_reserved
        self.strict_validation = strict_validation

        # Streaming configuration
        self.streaming_memory_limit_mb = streaming_memory_limit_mb
        self.streaming_chunk_size = streaming_chunk_size
        self.ultra_efficient_mode = ultra_efficient_mode

        # Check environment variable for ultra-efficient mode
        env_ultra = os.environ.get("OTTO_BGP_AS_EXTRACTOR_ULTRA", "false").lower()
        if env_ultra == "true":
            self.ultra_efficient_mode = True

        # Pre-compile all regex patterns for performance optimization
        self._compiled_patterns = {
            name: re.compile(pattern, re.IGNORECASE)
            for name, pattern in self.patterns.items()
        }

        # Initialize streaming extractor
        self._streaming_extractor = StreamingASExtractor(
            chunk_size=streaming_chunk_size, memory_limit_mb=streaming_memory_limit_mb
        )

        self.logger.info(
            f"AS extractor initialized: range {min_as_number}-{max_as_number}, "
            f"reserved_warnings={warn_reserved}, strict={strict_validation}, "
            f"streaming=enabled"
        )

    def extract_as_numbers_from_text(
        self, text: str, pattern_name: str = "standard"
    ) -> ASExtractionResult:
        """
        Extract AS numbers from text using specified pattern

        Args:
            text: Input text to process
            pattern_name: Name of regex pattern to use

        Returns:
            ASExtractionResult with extracted AS numbers
        """
        if pattern_name not in self.patterns:
            raise ValueError(
                f"Unknown pattern: {pattern_name}. Available: {list(self.patterns.keys())}"
            )

        pattern = self.patterns[pattern_name]
        as_numbers = set()
        lines_processed = 0

        self.logger.debug(
            f"Extracting AS numbers using pattern '{pattern_name}': {pattern}"
        )

        # Optimize by processing entire text at once, then split for line counting
        compiled_pattern = self._compiled_patterns[pattern_name]
        all_matches = compiled_pattern.findall(text)

        # Count lines for reporting
        lines = text.split("\n")
        lines_processed = len(lines)

        # Process all matches efficiently
        for match in all_matches:
            try:
                as_num = int(match)

                # Apply strict validation if enabled
                if self.strict_validation:
                    validation_result = self._validate_as_number_strict(as_num, "")
                    if validation_result["valid"]:
                        as_numbers.add(as_num)
                        self.logger.debug(f"Extracted AS{as_num}")
                    # Logging handled in _validate_as_number_strict
                else:
                    # Legacy range-based filtering
                    if self.min_as_number <= as_num <= self.max_as_number:
                        as_numbers.add(as_num)
                        self.logger.debug(f"Extracted AS{as_num}")
                    else:
                        self.logger.debug(f"Filtered AS{as_num} (out of range)")

            except ValueError:
                self.logger.warning(f"Invalid AS number format: {match}")

        result = ASExtractionResult(
            as_numbers=as_numbers,
            total_lines_processed=lines_processed,
            extraction_method=pattern_name,
            filters_applied=[f"range_{self.min_as_number}_{self.max_as_number}"],
        )

        self.logger.info(
            f"Extracted {len(as_numbers)} unique AS numbers from {lines_processed} lines"
        )
        return result

    def extract_as_numbers_from_file(
        self, file_path: Union[str, Path], pattern_name: str = "standard"
    ) -> ASExtractionResult:
        """
        Extract AS numbers from file (streaming only)
        """
        return self.extract_as_numbers_from_file_streaming(file_path, pattern_name)

    def extract_as_numbers_from_file_streaming(
        self, file_path: Union[str, Path], pattern_name: str = "standard"
    ) -> ASExtractionResult:
        """
        Extract AS numbers from file using memory-efficient streaming

        Args:
            file_path: Path to input file
            pattern_name: Name of regex pattern to use

        Returns:
            ASExtractionResult with extracted AS numbers
        """
        file_path = Path(file_path)

        if pattern_name not in self.patterns:
            raise ValueError(
                f"Unknown pattern: {pattern_name}. Available: {list(self.patterns.keys())}"
            )

        try:
            # Determine extraction method based on file size and configuration
            use_ultra_efficient = self._should_use_ultra_efficient(file_path)

            if use_ultra_efficient:
                self.logger.debug(f"Using ultra-efficient extraction for {file_path}")
                extraction_method = f"{pattern_name}_ultra_efficient"
            else:
                self.logger.debug(
                    f"Using standard streaming extraction for {file_path}"
                )
                extraction_method = f"{pattern_name}_streaming"

            # Get compiled pattern and validation function
            pattern = self._compiled_patterns[pattern_name]
            validator_func = self._create_validator_function()

            # Choose extraction method
            if use_ultra_efficient:
                as_numbers = (
                    self._streaming_extractor.extract_as_numbers_ultra_efficient(
                        file_path, pattern, validator_func
                    )
                )
            else:
                as_numbers = self._streaming_extractor.extract_as_numbers_streaming(
                    file_path, pattern, validator_func
                )

            # Count lines for reporting (lightweight pass)
            lines_processed = self._count_file_lines(file_path)

            result = ASExtractionResult(
                as_numbers=as_numbers,
                source_file=str(file_path),
                total_lines_processed=lines_processed,
                extraction_method=extraction_method,
                filters_applied=[f"range_{self.min_as_number}_{self.max_as_number}"],
            )

            self.logger.info(
                f"Processed file {file_path} ({extraction_method}): {len(result.as_numbers)} AS numbers extracted"
            )
            return result

        except FileNotFoundError:
            self.logger.error(f"File not found: {file_path}")
            raise
        except Exception as e:
            self.logger.error(f"Error reading file {file_path}: {e}")
            raise

    def _should_use_ultra_efficient(self, file_path: Path) -> bool:
        """
        Determine if ultra-efficient mode should be used based on file size and configuration

        Args:
            file_path: Path to the file

        Returns:
            True if ultra-efficient mode should be used
        """
        # If explicitly configured, use that setting
        if self.ultra_efficient_mode:
            return True

        try:
            # Auto-detect based on file size
            file_size = file_path.stat().st_size

            # Use ultra-efficient for files larger than 25MB
            size_threshold = 25 * 1024 * 1024  # 25MB

            use_ultra = file_size > size_threshold

            self.logger.debug(
                f"File size: {file_size:,} bytes, "
                f"ultra threshold: {size_threshold:,} bytes, "
                f"using ultra-efficient: {use_ultra}"
            )

            return use_ultra

        except OSError:
            # If we can't get file size, default to standard streaming
            return False

    def _create_validator_function(self):
        """Create a validator function for streaming extraction"""

        def validator(as_num: int) -> bool:
            if self.strict_validation:
                validation_result = self._validate_as_number_strict(as_num)
                return validation_result["valid"]
            else:
                return self.min_as_number <= as_num <= self.max_as_number

        return validator

    def _count_file_lines(self, file_path: Path) -> int:
        """Count lines in file efficiently for reporting"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0

    def extract_as_numbers_multi_pattern(
        self, text: str, pattern_names: List[str] = None
    ) -> ASExtractionResult:
        """
        Extract AS numbers using multiple patterns and combine results

        Args:
            text: Input text to process
            pattern_names: List of pattern names to use (default: all patterns)

        Returns:
            Combined ASExtractionResult
        """
        if pattern_names is None:
            pattern_names = list(self.patterns.keys())

        combined_as_numbers = set()
        total_lines = 0
        methods_used = []

        for pattern_name in pattern_names:
            try:
                result = self.extract_as_numbers_from_text(text, pattern_name)
                combined_as_numbers.update(result.as_numbers)
                total_lines = max(total_lines, result.total_lines_processed)
                methods_used.append(pattern_name)

                self.logger.debug(
                    f"Pattern '{pattern_name}' found {len(result.as_numbers)} AS numbers"
                )

            except Exception as e:
                self.logger.warning(f"Pattern '{pattern_name}' failed: {e}")

        result = ASExtractionResult(
            as_numbers=combined_as_numbers,
            total_lines_processed=total_lines,
            extraction_method=f"multi:{','.join(methods_used)}",
            filters_applied=[f"range_{self.min_as_number}_{self.max_as_number}"],
        )

        self.logger.info(
            f"Multi-pattern extraction: {len(combined_as_numbers)} unique AS numbers using {len(methods_used)} patterns"
        )
        return result

    def _validate_as_number_strict(
        self, as_num: int, context: str = ""
    ) -> Dict[str, any]:
        """
        Perform strict RFC-compliant AS number validation

        Args:
            as_num: AS number to validate
            context: Context string for logging (optional)

        Returns:
            Dictionary with validation result and details
        """
        result = {"valid": False, "reason": "", "warning": ""}

        # Basic range check
        if not self.AS_NUMBER_MIN <= as_num <= self.AS_NUMBER_MAX:
            result["reason"] = (
                f"AS{as_num} out of valid range ({self.AS_NUMBER_MIN}-{self.AS_NUMBER_MAX})"
            )
            self.logger.debug(f"{result['reason']} in context: {context}")
            return result

        # User-defined range check
        if not self.min_as_number <= as_num <= self.max_as_number:
            result["reason"] = (
                f"AS{as_num} out of configured range ({self.min_as_number}-{self.max_as_number})"
            )
            self.logger.debug(f"{result['reason']} in context: {context}")
            return result

        # Check reserved ranges
        for start, end in self.RESERVED_AS_RANGES:
            if start <= as_num <= end:
                if self.warn_reserved:
                    range_type = self._get_reserved_range_type(start, end)
                    warning = f"AS{as_num} is in reserved range [{start}-{end}] ({range_type})"
                    result["warning"] = warning
                    self.logger.warning(f"{warning} in context: {context}")
                # Still mark as valid but with warning
                break

        # Filter out likely IP octets (common source of false positives)
        if as_num <= 255:
            result["reason"] = f"AS{as_num} likely IP octet (≤255), filtering out"
            self.logger.debug(f"{result['reason']} in context: {context}")
            return result

        # Passed all checks
        result["valid"] = True
        return result

    def _get_reserved_range_type(self, start: int, end: int) -> str:
        """Get human-readable description of reserved AS range"""
        range_descriptions = {
            (0, 0): "Reserved",
            (23456, 23456): "AS_TRANS",
            (64496, 64511): "Documentation/Sample Use",
            (64512, 65534): "Private Use 16-bit",
            (65535, 65535): "Reserved",
            (65536, 65551): "Documentation/Sample Use",
            (4200000000, 4294967294): "Private Use 32-bit",
            (4294967295, 4294967295): "Reserved",
        }
        return range_descriptions.get((start, end), "Unknown Reserved")

    def _is_valid_as_number(self, as_num: int) -> bool:
        """
        Backward compatibility wrapper for tests

        Args:
            as_num: AS number to validate

        Returns:
            Boolean indicating if AS number is valid
        """
        result = self._validate_as_number_strict(as_num)
        return result["valid"]


class BGPTextProcessor:
    """Process and clean BGP configuration text"""

    # Default substrings to remove (from legacy AS-info.py)
    DEFAULT_REMOVE_SUBSTRINGS = ["    peer-as ", ";"]

    def __init__(self, remove_substrings: Optional[List[str]] = None):
        """
        Initialize BGP text processor

        Args:
            remove_substrings: List of substrings to remove (default: peer-as formatting)
        """
        self.logger = logging.getLogger(__name__)
        self.remove_substrings = (
            remove_substrings or self.DEFAULT_REMOVE_SUBSTRINGS.copy()
        )

        self.logger.info(
            f"BGP text processor initialized with {len(self.remove_substrings)} removal patterns"
        )

    def _batch_replace(self, text: str, substrings: List[str]) -> str:
        """
        Optimized batch replacement of multiple substrings

        Args:
            text: Input text
            substrings: List of substrings to remove

        Returns:
            Text with all substrings removed
        """
        if not substrings:
            return text

        # For small numbers of substrings or short text, simple string replacement is faster
        # For larger datasets, regex can be more efficient
        if len(substrings) <= 3 or len(text) < 10000:
            # Use simple string replacement for small operations
            result = text
            for substring in substrings:
                result = result.replace(substring, "")
            return result
        else:
            # Use regex for larger operations
            import re

            # Escape special regex characters in substrings
            escaped_substrings = [re.escape(sub) for sub in substrings]

            # Create pattern that matches any of the substrings
            pattern = "|".join(escaped_substrings)

            # Replace all matches with empty string
            return re.sub(pattern, "", text)

    def clean_bgp_text(self, text: str) -> BGPProcessingResult:
        """
        Clean BGP configuration text by removing unwanted substrings

        Args:
            text: Input BGP configuration text

        Returns:
            BGPProcessingResult with cleaned text
        """
        # Cache split result to avoid redundant operations
        original_lines_list = text.split("\n")
        original_lines = len(original_lines_list)

        # Optimize multiple replace operations using batch processing
        processed_text = self._batch_replace(text, self.remove_substrings)

        # Split once for processed text
        processed_lines = len(processed_text.split("\n"))

        result = BGPProcessingResult(
            processed_text=processed_text,
            original_lines=original_lines,
            processed_lines=processed_lines,
            duplicates_removed=0,  # Will be updated by deduplicate_lines
            substrings_removed=self.remove_substrings.copy(),
        )

        self.logger.debug(
            f"Cleaned BGP text: removed substrings {self.remove_substrings}"
        )
        return result

    def deduplicate_lines(self, text: str) -> BGPProcessingResult:
        """
        Remove duplicate lines from text while preserving order

        Args:
            text: Input text with potential duplicates

        Returns:
            BGPProcessingResult with deduplicated text
        """
        lines = text.split("\n")
        original_count = len(lines)
        seen_lines = set()
        unique_lines = []

        for line in lines:
            stripped_line = line.strip()

            # Keep empty lines but don't track them for duplicates
            if not stripped_line:
                unique_lines.append(line)
                continue

            if stripped_line not in seen_lines:
                seen_lines.add(stripped_line)
                unique_lines.append(line)

        processed_text = "\n".join(unique_lines)
        processed_count = len(unique_lines)
        duplicates_removed = original_count - processed_count

        result = BGPProcessingResult(
            processed_text=processed_text,
            original_lines=original_count,
            processed_lines=processed_count,
            duplicates_removed=duplicates_removed,
        )

        self.logger.info(
            f"Deduplicated text: {duplicates_removed} duplicate lines removed"
        )
        return result

    def process_bgp_text_full(self, text: str) -> BGPProcessingResult:
        """
        Apply full BGP text processing: cleaning + deduplication

        Args:
            text: Input BGP configuration text

        Returns:
            BGPProcessingResult with fully processed text
        """
        # First clean the text
        clean_result = self.clean_bgp_text(text)

        # Then deduplicate
        final_result = self.deduplicate_lines(clean_result.processed_text)

        # Combine results
        final_result.substrings_removed = clean_result.substrings_removed

        self.logger.info(
            f"Full BGP processing complete: {final_result.original_lines} -> {final_result.processed_lines} lines"
        )
        return final_result

    def process_file(
        self,
        input_path: Union[str, Path],
        output_path: Optional[Union[str, Path]] = None,
        use_streaming: Optional[bool] = None,
    ) -> BGPProcessingResult:
        """
        Process BGP text file and optionally write results with streaming support

        Args:
            input_path: Path to input file
            output_path: Path to output file (optional)
            use_streaming: Force streaming mode (auto-detect if None)

        Returns:
            BGPProcessingResult with processing results
        """
        input_path = Path(input_path)

        # Determine if streaming should be used (same logic as AS extractor)
        should_stream = use_streaming
        if should_stream is None:
            try:
                file_size = input_path.stat().st_size
                should_stream = file_size > (10 * 1024 * 1024)  # 10MB threshold
            except OSError:
                should_stream = False

        # Always use streaming
        return self._process_file_streaming(input_path, output_path)

    def _process_file_streaming(
        self, input_path: Path, output_path: Optional[Path]
    ) -> BGPProcessingResult:
        """Process file using streaming approach"""
        try:
            self.logger.debug(f"Using streaming BGP processing for {input_path}")

            processed_lines = []
            original_count = 0
            seen_lines = set()
            duplicates_removed = 0

            with open(input_path, "r", encoding="utf-8") as f:
                for line in f:
                    original_count += 1

                    # Apply text processing line by line
                    processed_line = self._batch_replace(line, self.remove_substrings)

                    # Deduplication
                    stripped_line = processed_line.strip()
                    if not stripped_line:
                        processed_lines.append(processed_line)
                        continue

                    if stripped_line not in seen_lines:
                        seen_lines.add(stripped_line)
                        processed_lines.append(processed_line)
                    else:
                        duplicates_removed += 1

            # Join processed lines
            processed_text = "".join(processed_lines)
            processed_count = len(processed_lines)

            result = BGPProcessingResult(
                processed_text=processed_text,
                original_lines=original_count,
                processed_lines=processed_count,
                duplicates_removed=duplicates_removed,
                substrings_removed=self.remove_substrings.copy(),
            )

            if output_path:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(result.processed_text)
                self.logger.info(
                    f"Processed BGP file (streaming): {input_path} -> {output_path}"
                )

            return result

        except FileNotFoundError:
            self.logger.error(f"Input file not found: {input_path}")
            raise
        except Exception as e:
            self.logger.error(f"Error processing file {input_path}: {e}")
            raise


class ASProcessor:
    """Combined AS extraction and BGP text processing"""

    def __init__(
        self,
        as_extractor: Optional[ASNumberExtractor] = None,
        bgp_processor: Optional[BGPTextProcessor] = None,
    ):
        """
        Initialize combined AS processor

        Args:
            as_extractor: AS number extractor (default: create new)
            bgp_processor: BGP text processor (default: create new)
        """
        self.logger = logging.getLogger(__name__)
        self.as_extractor = as_extractor or ASNumberExtractor()
        self.bgp_processor = bgp_processor or BGPTextProcessor()

    def process_bgp_file_to_as_numbers(
        self,
        file_path: Union[str, Path],
        pattern_name: str = "peer_as",
        use_streaming: Optional[bool] = None,
    ) -> ASExtractionResult:
        """
        Process BGP file: clean text and extract AS numbers with optional streaming

        Args:
            file_path: Path to BGP configuration file
            pattern_name: AS extraction pattern to use
            use_streaming: Force streaming mode (auto-detect if None)

        Returns:
            ASExtractionResult with extracted AS numbers
        """
        file_path = Path(file_path)

        # Determine if streaming should be used
        should_stream = use_streaming
        if should_stream is None:
            try:
                file_size = file_path.stat().st_size
                should_stream = file_size > (10 * 1024 * 1024)  # 10MB threshold
            except OSError:
                should_stream = False

        # Always use streaming
        return self._process_bgp_file_streaming(file_path, pattern_name)

    def _process_bgp_file_streaming(
        self, file_path: Path, pattern_name: str
    ) -> ASExtractionResult:
        """Process BGP file using streaming approach"""
        try:
            self.logger.info(
                f"Processing BGP file for AS extraction (streaming): {file_path}"
            )

            # Use temporary file for intermediate processing
            with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
                temp_path = Path(temp_file.name)

                # First pass: Clean BGP text using streaming
                bgp_result = self.bgp_processor._process_file_streaming(
                    file_path, temp_path
                )
                self.logger.debug(
                    "Streaming clean result: original=%d processed=%d duplicates_removed=%d",
                    getattr(bgp_result, "original_lines", 0),
                    getattr(bgp_result, "processed_lines", 0),
                    getattr(bgp_result, "duplicates_removed", 0),
                )

                # Second pass: Extract AS numbers using streaming
                as_result = self.as_extractor.extract_as_numbers_from_file_streaming(
                    temp_path, pattern_name
                )
                as_result.source_file = str(file_path)

                # Clean up temporary file
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

            self.logger.info(
                f"Extracted {len(as_result.as_numbers)} AS numbers from {file_path} (streaming)"
            )
            return as_result

        except Exception as e:
            self.logger.error(f"Error processing BGP file {file_path}: {e}")
            raise

    def get_sorted_as_list(self, as_numbers: Set[int]) -> List[int]:
        """Get sorted list of AS numbers"""
        return sorted(as_numbers)


# Backward compatibility alias for existing imports
ASExtractor = ASNumberExtractor


class MemoryBenchmark:
    """Memory usage monitoring and benchmarking utilities"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        try:
            import psutil

            self.psutil = psutil
            self.memory_monitoring_available = True
        except ImportError:
            self.psutil = None
            self.memory_monitoring_available = False
            self.logger.warning("psutil not available, memory monitoring disabled")

    def get_memory_usage(self) -> Dict[str, float]:
        """Get current memory usage in MB"""
        if not self.memory_monitoring_available:
            return {"rss": 0, "vms": 0, "percent": 0}

        try:
            process = self.psutil.Process()
            memory_info = process.memory_info()
            memory_percent = process.memory_percent()

            return {
                "rss": memory_info.rss / 1024 / 1024,  # Resident Set Size in MB
                "vms": memory_info.vms / 1024 / 1024,  # Virtual Memory Size in MB
                "percent": memory_percent,
            }
        except Exception as e:
            self.logger.warning(f"Error getting memory usage: {e}")
            return {"rss": 0, "vms": 0, "percent": 0}

    def generate_test_file(
        self, output_path: Union[str, Path], size_mb: int = 10, as_density: int = 100
    ) -> Path:
        """Generate a test BGP configuration file for benchmarking"""
        output_path = Path(output_path)

        self.logger.info(f"Generating test file: {output_path} ({size_mb}MB)")

        # Calculate approximate lines needed
        avg_line_length = 50  # bytes per line
        target_bytes = size_mb * 1024 * 1024
        target_lines = target_bytes // avg_line_length

        as_number = 10000

        with open(output_path, "w", encoding="utf-8") as f:
            for i in range(target_lines):
                if i % as_density == 0:
                    # BGP neighbor configuration line with AS
                    line = f"neighbor 192.168.{(i // 256) % 256}.{i % 256} {{ peer-as {as_number}; }}\n"
                    as_number += 1
                else:
                    # Filler configuration line
                    line = f'interface ge-0/0/{i % 48} {{ description "Link {i}"; }}\n'

                f.write(line)

        actual_size = output_path.stat().st_size / 1024 / 1024
        self.logger.info(
            f"Generated test file: {actual_size:.1f}MB with ~{(target_lines // as_density)} AS numbers"
        )

        return output_path
