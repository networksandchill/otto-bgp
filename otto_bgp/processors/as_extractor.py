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
from dataclasses import dataclass
from typing import Set, List, Optional, Dict, Union
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


class ASNumberExtractor:
    """Extract AS numbers from various text sources with RFC-compliant validation"""
    
    # Default regex patterns for AS number extraction
    AS_PATTERNS = {
        'standard': r'(?:AS)?(\d+)',  # Matches AS12345 or 12345
        'peer_as': r'peer-as\s+(\d+)',  # Matches "peer-as 12345"
        'explicit_as': r'AS(\d+)',  # Matches only AS12345 format
        'autonomous_system': r'autonomous-system\s+(\d+)'  # Matches "autonomous-system 12345"
    }
    
    # RFC-compliant AS number ranges (as of 2025)
    # Based on IANA AS Number Registry and various RFCs
    RESERVED_AS_RANGES = [
        (0, 0),                    # Reserved (RFC 7607)
        (23456, 23456),           # AS_TRANS (RFC 6793)
        (64496, 64511),           # Documentation/Sample Use (RFC 5398)
        (64512, 65534),           # Private Use (RFC 6996)
        (65535, 65535),           # Reserved (RFC 7300)
        (65536, 65551),           # Documentation/Sample Use (RFC 5398)
        (4200000000, 4294967294), # Private Use 32-bit (RFC 6996)
        (4294967295, 4294967295), # Reserved (RFC 7300)
    ]
    
    # AS number validation constants
    AS_NUMBER_MIN = 0
    AS_NUMBER_MAX = 4294967295  # 32-bit unsigned integer maximum
    
    def __init__(self, 
                 min_as_number: int = 256,
                 max_as_number: int = 4294967295,
                 patterns: Optional[Dict[str, str]] = None,
                 warn_reserved: bool = True,
                 strict_validation: bool = True):
        """
        Initialize AS number extractor with enhanced security validation
        
        Args:
            min_as_number: Minimum valid AS number (default 256 to exclude IP octets)
            max_as_number: Maximum valid AS number (32-bit max)
            patterns: Custom regex patterns for AS extraction
            warn_reserved: Log warnings for reserved AS number ranges
            strict_validation: Enable strict RFC-compliant validation
        """
        self.logger = logging.getLogger(__name__)
        
        # Validate initialization parameters
        if not isinstance(min_as_number, int) or not isinstance(max_as_number, int):
            raise ValueError("AS number limits must be integers")
        
        if not self.AS_NUMBER_MIN <= min_as_number <= max_as_number <= self.AS_NUMBER_MAX:
            raise ValueError(f"Invalid AS number range: {min_as_number}-{max_as_number}")
        
        self.min_as_number = min_as_number
        self.max_as_number = max_as_number
        self.patterns = patterns or self.AS_PATTERNS.copy()
        self.warn_reserved = warn_reserved
        self.strict_validation = strict_validation
        
        self.logger.info(f"AS extractor initialized: range {min_as_number}-{max_as_number}, "
                        f"reserved_warnings={warn_reserved}, strict={strict_validation}")
    
    def extract_as_numbers_from_text(self, 
                                   text: str, 
                                   pattern_name: str = 'standard') -> ASExtractionResult:
        """
        Extract AS numbers from text using specified pattern
        
        Args:
            text: Input text to process
            pattern_name: Name of regex pattern to use
            
        Returns:
            ASExtractionResult with extracted AS numbers
        """
        if pattern_name not in self.patterns:
            raise ValueError(f"Unknown pattern: {pattern_name}. Available: {list(self.patterns.keys())}")
        
        pattern = self.patterns[pattern_name]
        as_numbers = set()
        lines_processed = 0
        
        self.logger.debug(f"Extracting AS numbers using pattern '{pattern_name}': {pattern}")
        
        for line in text.split('\n'):
            line = line.strip()
            lines_processed += 1
            
            if not line:
                continue
            
            # Find all AS number matches in the line
            matches = re.findall(pattern, line, re.IGNORECASE)
            
            for match in matches:
                try:
                    as_num = int(match)
                    
                    # Apply strict validation if enabled
                    if self.strict_validation:
                        validation_result = self._validate_as_number_strict(as_num, line[:50])
                        if validation_result['valid']:
                            as_numbers.add(as_num)
                            self.logger.debug(f"Extracted AS{as_num} from line: {line[:50]}...")
                        # Logging handled in _validate_as_number_strict
                    else:
                        # Legacy range-based filtering
                        if self.min_as_number <= as_num <= self.max_as_number:
                            as_numbers.add(as_num)
                            self.logger.debug(f"Extracted AS{as_num} from line: {line[:50]}...")
                        else:
                            self.logger.debug(f"Filtered AS{as_num} (out of range) from line: {line[:50]}...")
                        
                except ValueError:
                    self.logger.warning(f"Invalid AS number format: {match}")
        
        result = ASExtractionResult(
            as_numbers=as_numbers,
            total_lines_processed=lines_processed,
            extraction_method=pattern_name,
            filters_applied=[f"range_{self.min_as_number}_{self.max_as_number}"]
        )
        
        self.logger.info(f"Extracted {len(as_numbers)} unique AS numbers from {lines_processed} lines")
        return result
    
    def extract_as_numbers_from_file(self, 
                                   file_path: Union[str, Path], 
                                   pattern_name: str = 'standard') -> ASExtractionResult:
        """
        Extract AS numbers from file
        
        Args:
            file_path: Path to input file
            pattern_name: Name of regex pattern to use
            
        Returns:
            ASExtractionResult with extracted AS numbers
        """
        file_path = Path(file_path)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            
            result = self.extract_as_numbers_from_text(text, pattern_name)
            result.source_file = str(file_path)
            
            self.logger.info(f"Processed file {file_path}: {len(result.as_numbers)} AS numbers extracted")
            return result
            
        except FileNotFoundError:
            self.logger.error(f"File not found: {file_path}")
            raise
        except Exception as e:
            self.logger.error(f"Error reading file {file_path}: {e}")
            raise
    
    def extract_as_numbers_multi_pattern(self, 
                                       text: str, 
                                       pattern_names: List[str] = None) -> ASExtractionResult:
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
                
                self.logger.debug(f"Pattern '{pattern_name}' found {len(result.as_numbers)} AS numbers")
                
            except Exception as e:
                self.logger.warning(f"Pattern '{pattern_name}' failed: {e}")
        
        result = ASExtractionResult(
            as_numbers=combined_as_numbers,
            total_lines_processed=total_lines,
            extraction_method=f"multi:{','.join(methods_used)}",
            filters_applied=[f"range_{self.min_as_number}_{self.max_as_number}"]
        )
        
        self.logger.info(f"Multi-pattern extraction: {len(combined_as_numbers)} unique AS numbers using {len(methods_used)} patterns")
        return result
    
    def _validate_as_number_strict(self, as_num: int, context: str = "") -> Dict[str, any]:
        """
        Perform strict RFC-compliant AS number validation
        
        Args:
            as_num: AS number to validate
            context: Context string for logging (optional)
            
        Returns:
            Dictionary with validation result and details
        """
        result = {
            'valid': False,
            'reason': '',
            'warning': ''
        }
        
        # Basic range check
        if not self.AS_NUMBER_MIN <= as_num <= self.AS_NUMBER_MAX:
            result['reason'] = f"AS{as_num} out of valid range ({self.AS_NUMBER_MIN}-{self.AS_NUMBER_MAX})"
            self.logger.debug(f"{result['reason']} in context: {context}")
            return result
        
        # User-defined range check
        if not self.min_as_number <= as_num <= self.max_as_number:
            result['reason'] = f"AS{as_num} out of configured range ({self.min_as_number}-{self.max_as_number})"
            self.logger.debug(f"{result['reason']} in context: {context}")
            return result
        
        # Check reserved ranges
        for start, end in self.RESERVED_AS_RANGES:
            if start <= as_num <= end:
                if self.warn_reserved:
                    range_type = self._get_reserved_range_type(start, end)
                    warning = f"AS{as_num} is in reserved range [{start}-{end}] ({range_type})"
                    result['warning'] = warning
                    self.logger.warning(f"{warning} in context: {context}")
                # Still mark as valid but with warning
                break
        
        # Filter out likely IP octets (common source of false positives)
        if as_num <= 255:
            result['reason'] = f"AS{as_num} likely IP octet (≤255), filtering out"
            self.logger.debug(f"{result['reason']} in context: {context}")
            return result
        
        # Passed all checks
        result['valid'] = True
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
        return result['valid']


class BGPTextProcessor:
    """Process and clean BGP configuration text"""
    
    # Default substrings to remove (from legacy AS-info.py)
    DEFAULT_REMOVE_SUBSTRINGS = [
        "    peer-as ",
        ";"
    ]
    
    def __init__(self, remove_substrings: Optional[List[str]] = None):
        """
        Initialize BGP text processor
        
        Args:
            remove_substrings: List of substrings to remove (default: peer-as formatting)
        """
        self.logger = logging.getLogger(__name__)
        self.remove_substrings = remove_substrings or self.DEFAULT_REMOVE_SUBSTRINGS.copy()
        
        self.logger.info(f"BGP text processor initialized with {len(self.remove_substrings)} removal patterns")
    
    def clean_bgp_text(self, text: str) -> BGPProcessingResult:
        """
        Clean BGP configuration text by removing unwanted substrings
        
        Args:
            text: Input BGP configuration text
            
        Returns:
            BGPProcessingResult with cleaned text
        """
        original_lines = len(text.split('\n'))
        processed_text = text
        
        # Remove specified substrings
        for substring in self.remove_substrings:
            processed_text = processed_text.replace(substring, "")
        
        processed_lines = len(processed_text.split('\n'))
        
        result = BGPProcessingResult(
            processed_text=processed_text,
            original_lines=original_lines,
            processed_lines=processed_lines,
            duplicates_removed=0,  # Will be updated by deduplicate_lines
            substrings_removed=self.remove_substrings.copy()
        )
        
        self.logger.debug(f"Cleaned BGP text: removed substrings {self.remove_substrings}")
        return result
    
    def deduplicate_lines(self, text: str) -> BGPProcessingResult:
        """
        Remove duplicate lines from text while preserving order
        
        Args:
            text: Input text with potential duplicates
            
        Returns:
            BGPProcessingResult with deduplicated text
        """
        lines = text.split('\n')
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
        
        processed_text = '\n'.join(unique_lines)
        processed_count = len(unique_lines)
        duplicates_removed = original_count - processed_count
        
        result = BGPProcessingResult(
            processed_text=processed_text,
            original_lines=original_count,
            processed_lines=processed_count,
            duplicates_removed=duplicates_removed
        )
        
        self.logger.info(f"Deduplicated text: {duplicates_removed} duplicate lines removed")
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
        
        self.logger.info(f"Full BGP processing complete: {final_result.original_lines} -> {final_result.processed_lines} lines")
        return final_result
    
    def process_file(self, 
                    input_path: Union[str, Path], 
                    output_path: Optional[Union[str, Path]] = None) -> BGPProcessingResult:
        """
        Process BGP text file and optionally write results
        
        Args:
            input_path: Path to input file
            output_path: Path to output file (optional)
            
        Returns:
            BGPProcessingResult with processing results
        """
        input_path = Path(input_path)
        
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                text = f.read()
            
            result = self.process_bgp_text_full(text)
            
            if output_path:
                output_path = Path(output_path)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(result.processed_text)
                
                self.logger.info(f"Processed BGP file: {input_path} -> {output_path}")
            
            return result
            
        except FileNotFoundError:
            self.logger.error(f"Input file not found: {input_path}")
            raise
        except Exception as e:
            self.logger.error(f"Error processing file {input_path}: {e}")
            raise


class ASProcessor:
    """Combined AS extraction and BGP text processing"""
    
    def __init__(self, 
                 as_extractor: Optional[ASNumberExtractor] = None,
                 bgp_processor: Optional[BGPTextProcessor] = None):
        """
        Initialize combined AS processor
        
        Args:
            as_extractor: AS number extractor (default: create new)
            bgp_processor: BGP text processor (default: create new)
        """
        self.logger = logging.getLogger(__name__)
        self.as_extractor = as_extractor or ASNumberExtractor()
        self.bgp_processor = bgp_processor or BGPTextProcessor()
    
    def process_bgp_file_to_as_numbers(self, 
                                     file_path: Union[str, Path],
                                     pattern_name: str = 'peer_as') -> ASExtractionResult:
        """
        Process BGP file: clean text and extract AS numbers
        
        Args:
            file_path: Path to BGP configuration file
            pattern_name: AS extraction pattern to use
            
        Returns:
            ASExtractionResult with extracted AS numbers
        """
        file_path = Path(file_path)
        
        try:
            # Read and clean BGP text
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            
            self.logger.info(f"Processing BGP file for AS extraction: {file_path}")
            
            # Clean the BGP text first
            bgp_result = self.bgp_processor.process_bgp_text_full(text)
            
            # Extract AS numbers from cleaned text
            as_result = self.as_extractor.extract_as_numbers_from_text(
                bgp_result.processed_text, 
                pattern_name
            )
            as_result.source_file = str(file_path)
            
            self.logger.info(f"Extracted {len(as_result.as_numbers)} AS numbers from {file_path}")
            return as_result
            
        except Exception as e:
            self.logger.error(f"Error processing BGP file {file_path}: {e}")
            raise
    
    def get_sorted_as_list(self, as_numbers: Set[int]) -> List[int]:
        """Get sorted list of AS numbers"""
        return sorted(as_numbers)