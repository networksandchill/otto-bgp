# otto_bgp.processors Module - Developer Guide

## Overview

The `processors` module provides **AS number extraction and validation** from BGP configurations and mixed text data. It implements RFC-compliant AS number validation with security controls to prevent processing invalid or malicious data.

**Security Status**: Production-ready with comprehensive input validation and range checking

## Architecture Role

```
BGP Pipeline Flow:
Collection → Discovery → [PROCESSORS] → Generators → Application

Key Responsibilities:
- Extract AS numbers from raw text and BGP configurations  
- Validate AS numbers against RFC specifications
- Filter invalid ranges and reserved AS numbers
- Sanitize and normalize AS number formats
- Support both strict and lenient processing modes
```

## Core Components

### 1. ASNumberExtractor (`as_extractor.py`)
**Purpose**: Secure AS number extraction with comprehensive validation

**Key Features**:
- RFC 6793 compliant 32-bit AS number validation (0-4294967295)
- Reserved AS range detection and warnings
- IP octet filtering to prevent false positives
- Multiple input format support (AS prefix, bare numbers)
- Strict and lenient validation modes

**Security Architecture**:
```python
class ASNumberExtractor:
    """Secure AS number extraction with validation"""
    
    # RFC-defined AS number ranges
    AS_RANGE_MIN = 0
    AS_RANGE_MAX = 4294967295  # 32-bit maximum
    
    # Reserved AS number ranges (RFC 7607, RFC 6996)
    RESERVED_RANGES = {
        (0, 0): "Reserved",
        (23456, 23456): "AS_TRANS (RFC 6793)",
        (64496, 64511): "Reserved for use in documentation (RFC 5398)",
        (64512, 65534): "Reserved for Private Use (RFC 6996)",
        (65535, 65535): "Reserved",
        (65536, 65551): "Reserved for use in documentation (RFC 5398)",
        (4200000000, 4294967294): "Reserved for Private Use (RFC 6996)",
        (4294967295, 4294967295): "Reserved"
    }
```

## Security Architecture

### AS Number Validation
**CRITICAL**: Prevents processing of invalid AS numbers that could cause issues in policy generation.

#### Range Validation
```python
def validate_as_number(self, as_number: int, strict_mode: bool = True) -> ValidationResult:
    """Comprehensive AS number validation"""
    
    # Basic range check
    if not (self.AS_RANGE_MIN <= as_number <= self.AS_RANGE_MAX):
        return ValidationResult(
            valid=False,
            as_number=as_number,
            error=f"AS number {as_number} outside valid range ({self.AS_RANGE_MIN}-{self.AS_RANGE_MAX})"
        )
    
    # Check for reserved ranges
    reserved_info = self.check_reserved_range(as_number)
    if reserved_info:
        if strict_mode:
            return ValidationResult(
                valid=False,
                as_number=as_number,
                warning=f"AS {as_number} is in reserved range: {reserved_info['description']}"
            )
        else:
            # Allow with warning in lenient mode
            logger.warning(f"Processing reserved AS {as_number}: {reserved_info['description']}")
    
    return ValidationResult(valid=True, as_number=as_number)

def check_reserved_range(self, as_number: int) -> Optional[Dict]:
    """Check if AS number is in reserved range"""
    for (range_start, range_end), description in self.RESERVED_RANGES.items():
        if range_start <= as_number <= range_end:
            return {
                'range': (range_start, range_end),
                'description': description
            }
    return None
```

#### Input Sanitization
```python
def sanitize_as_input(self, text: str) -> str:
    """Sanitize input text before AS extraction"""
    
    # Remove dangerous characters
    sanitized = re.sub(r'[^\w\s\-\.\:\/]', '', text)
    
    # Limit input size to prevent DoS
    max_size = 1024 * 1024  # 1MB limit
    if len(sanitized) > max_size:
        raise ValueError(f"Input text too large: {len(sanitized)} bytes (max {max_size})")
    
    return sanitized
```

### IP Octet Filtering
```python
def filter_ip_octets(self, numbers: List[int]) -> List[int]:
    """Filter out IP address octets to prevent false positives"""
    
    # Filter numbers that are likely IP octets (0-255)
    # but allow some common small AS numbers
    filtered = []
    
    for num in numbers:
        if num <= 255:
            # Check if this might be a valid small AS number
            if self.is_likely_as_number(num):
                filtered.append(num)
            else:
                logger.debug(f"Filtered potential IP octet: {num}")
        else:
            filtered.append(num)
    
    return filtered

def is_likely_as_number(self, num: int) -> bool:
    """Determine if small number is likely an AS number vs IP octet"""
    
    # Common small AS numbers that should not be filtered
    known_small_as = {
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10,  # Very early AS assignments
        13, 15, 16, 17, 18, 19, 20       # Historic assignments
    }
    
    return num in known_small_as
```

## Design Choices

### RFC-Compliant Validation
**Choice**: Strict adherence to RFC 6793 32-bit AS number specifications
**Rationale**:
- Ensures compatibility with modern BGP implementations
- Prevents processing of invalid AS numbers
- Provides clear validation error messages
- Supports both 16-bit and 32-bit AS numbers

### Reserved Range Handling
**Choice**: Detect and warn about reserved AS numbers but allow processing
**Rationale**:
- Reserved ranges may be used in lab/test environments
- Provides visibility into potential configuration issues
- Maintains operational flexibility while ensuring awareness
- Supports educational and documentation use cases

### Dual Processing Modes
**Choice**: Strict and lenient validation modes
**Rationale**:
- Strict mode for production environments
- Lenient mode for research and analysis
- Debugging and troubleshooting flexibility

### Input Size Limits
**Choice**: Implement input size restrictions
**Rationale**:
- Prevent denial-of-service attacks
- Manage memory usage during processing
- Ensure reasonable processing times
- Protect against malformed input

## AS Number Extraction Patterns

### Text Pattern Matching
```python
class ASNumberExtractor:
    """Extract AS numbers from various text formats"""
    
    # Compiled regex patterns for performance
    AS_PATTERNS = [
        re.compile(r'\bAS(\d+)\b', re.IGNORECASE),           # AS12345
        re.compile(r'\bas\s+(\d+)\b', re.IGNORECASE),        # as 12345
        re.compile(r'\bpeer-as\s+(\d+)\b', re.IGNORECASE),   # peer-as 12345
        re.compile(r'\bremote-as\s+(\d+)\b', re.IGNORECASE), # remote-as 12345
        re.compile(r'\b(\d{4,10})\b'),                        # Bare numbers (4-10 digits)
    ]
    
    def extract_from_text(self, text: str, strict_mode: bool = True) -> ExtractionResult:
        """Extract AS numbers from text with validation"""
        
        # Sanitize input
        clean_text = self.sanitize_as_input(text)
        
        # Extract potential AS numbers
        potential_as = set()
        
        for pattern in self.AS_PATTERNS:
            matches = pattern.findall(clean_text)
            for match in matches:
                try:
                    as_number = int(match)
                    potential_as.add(as_number)
                except ValueError:
                    logger.warning(f"Invalid AS number format: {match}")
        
        # Filter IP octets
        filtered_as = self.filter_ip_octets(list(potential_as))
        
        # Validate each AS number
        valid_as = []
        invalid_as = []
        warnings = []
        
        for as_number in filtered_as:
            validation = self.validate_as_number(as_number, strict_mode)
            
            if validation.valid:
                valid_as.append(as_number)
                if validation.warning:
                    warnings.append(validation.warning)
            else:
                invalid_as.append(as_number)
                logger.error(f"Invalid AS number {as_number}: {validation.error}")
        
        return ExtractionResult(
            valid_as_numbers=sorted(valid_as),
            invalid_as_numbers=invalid_as,
            warnings=warnings,
            total_extracted=len(potential_as),
            filtered_count=len(potential_as) - len(filtered_as)
        )
```

### BGP Configuration Parsing
```python
def extract_from_bgp_config(self, config: str, strict_mode: bool = True) -> ExtractionResult:
    """Extract AS numbers specifically from BGP configuration"""
    
    # BGP-specific patterns
    bgp_patterns = [
        re.compile(r'neighbor\s+[\d\.]+\s*{\s*peer-as\s+(\d+)', re.MULTILINE),
        re.compile(r'group\s+\w+\s*{\s*[^}]*peer-as\s+(\d+)', re.MULTILINE | re.DOTALL),
        re.compile(r'protocols\s+bgp\s+[^{]*{\s*[^}]*as\s+(\d+)', re.MULTILINE | re.DOTALL),
    ]
    
    as_numbers = set()
    
    for pattern in bgp_patterns:
        matches = pattern.findall(config)
        for match in matches:
            try:
                as_numbers.add(int(match))
            except ValueError:
                logger.warning(f"Invalid AS number in BGP config: {match}")
    
    # Use standard validation
    return self.validate_extracted_as_numbers(list(as_numbers), strict_mode)
```

### File Processing
```python
def extract_from_file(self, file_path: Path, strict_mode: bool = True) -> ExtractionResult:
    """Extract AS numbers from file with size and format validation"""
    
    # Validate file exists and is readable
    if not file_path.exists():
        raise FileNotFoundError(f"AS number file not found: {file_path}")
    
    if not file_path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")
    
    # Check file size
    file_size = file_path.stat().st_size
    max_size = 10 * 1024 * 1024  # 10MB limit
    
    if file_size > max_size:
        raise ValueError(f"File too large: {file_size} bytes (max {max_size})")
    
    # Read and process file
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        return self.extract_from_text(content, strict_mode)
        
    except UnicodeDecodeError as e:
        logger.error(f"File encoding error: {e}")
        # Try with different encodings
        for encoding in ['latin1', 'ascii']:
            try:
                with open(file_path, 'r', encoding=encoding, errors='replace') as f:
                    content = f.read()
                return self.extract_from_text(content, strict_mode)
            except UnicodeDecodeError:
                continue
        
        raise ValueError(f"Unable to read file with any supported encoding: {file_path}")
```

## Integration Points

### CLI Interface
```bash
# Extract AS numbers from file
./otto-bgp process bgp-config.txt --extract-as -o as-numbers.txt

# Strict mode (default)
./otto-bgp process bgp-config.txt --extract-as --strict

# Lenient mode for research
./otto-bgp process bgp-config.txt --extract-as --lenient

# Process with custom patterns
./otto-bgp process bgp-config.txt --extract-as --pattern peer_as --pattern remote_as
```

### Python API
```python
from otto_bgp.processors import ASNumberExtractor

extractor = ASNumberExtractor()

# Extract from text
result = extractor.extract_from_text(bgp_config_text, strict_mode=True)

# Extract from file
result = extractor.extract_from_file(Path("bgp-config.txt"), strict_mode=False)

# Process results
print(f"Found {len(result.valid_as_numbers)} valid AS numbers")
print(f"Filtered {result.filtered_count} potential IP octets")

for warning in result.warnings:
    print(f"Warning: {warning}")
```

### Pipeline Integration
```python
def process_router_profiles(router_profiles: List[RouterProfile]) -> List[RouterProfile]:
    """Extract AS numbers from router BGP configurations"""
    
    extractor = ASNumberExtractor()
    
    for profile in router_profiles:
        if profile.bgp_config:
            # Extract AS numbers from BGP configuration
            result = extractor.extract_from_bgp_config(
                profile.bgp_config, 
                strict_mode=True
            )
            
            # Update profile with extracted AS numbers
            profile.discovered_as_numbers.update(result.valid_as_numbers)
            
            # Log extraction results
            logger.info(f"Extracted {len(result.valid_as_numbers)} AS numbers from {profile.hostname}")
            
            for warning in result.warnings:
                logger.warning(f"{profile.hostname}: {warning}")
    
    return router_profiles
```

## Error Handling

### Validation Errors
```python
@dataclass
class ValidationResult:
    """Result of AS number validation"""
    valid: bool
    as_number: int
    error: Optional[str] = None
    warning: Optional[str] = None

@dataclass
class ExtractionResult:
    """Result of AS number extraction"""
    valid_as_numbers: List[int]
    invalid_as_numbers: List[int]
    warnings: List[str]
    total_extracted: int
    filtered_count: int
    
    @property
    def success_rate(self) -> float:
        """Calculate extraction success rate"""
        if self.total_extracted == 0:
            return 0.0
        return len(self.valid_as_numbers) / self.total_extracted
```

### Exception Handling
```python
class ASProcessingError(Exception):
    """Base exception for AS processing errors"""
    pass

class ValidationError(ASProcessingError):
    """AS number validation error"""
    pass

class ExtractionError(ASProcessingError):
    """AS number extraction error"""
    pass

# Error handling pattern
def safe_extract_as_numbers(self, text: str) -> ExtractionResult:
    """Extract AS numbers with comprehensive error handling"""
    
    try:
        return self.extract_from_text(text, strict_mode=True)
        
    except ValidationError as e:
        logger.error(f"AS validation failed: {e}")
        return ExtractionResult(
            valid_as_numbers=[],
            invalid_as_numbers=[],
            warnings=[f"Validation error: {e}"],
            total_extracted=0,
            filtered_count=0
        )
        
    except Exception as e:
        logger.error(f"AS extraction failed: {e}")
        raise ExtractionError(f"Failed to extract AS numbers: {e}") from e
```

## Development Guidelines

### Testing Strategy
```python
# Unit tests for validation
def test_as_number_validation():
    extractor = ASNumberExtractor()
    
    # Valid AS numbers
    assert extractor.validate_as_number(13335).valid
    assert extractor.validate_as_number(65000).valid
    
    # Invalid range
    assert not extractor.validate_as_number(-1).valid
    assert not extractor.validate_as_number(4294967296).valid
    
    # Reserved ranges
    result = extractor.validate_as_number(64512)  # Private use
    assert result.warning is not None

# Integration tests with real data
def test_bgp_config_extraction():
    extractor = ASNumberExtractor()
    
    bgp_config = """
    protocols {
        bgp {
            group CUSTOMERS {
                neighbor 192.168.1.1 {
                    peer-as 64512;
                }
            }
        }
    }
    """
    
    result = extractor.extract_from_bgp_config(bgp_config)
    assert 64512 in result.valid_as_numbers
```

### Performance Testing
- **Large file processing** with size limits
- **Memory usage monitoring** during extraction
- **Pattern matching performance** with various text formats
- **Validation speed** with large AS number sets

## Best Practices

### Security
- Always validate AS number ranges before processing
- Implement input size limits to prevent DoS
- Sanitize input text before pattern matching
- Log validation warnings for security monitoring

### Performance
- Use compiled regex patterns for repeated operations
- Implement reasonable file size limits
- Cache validation results when appropriate
- Profile extraction performance with large datasets

### Reliability
- Handle various text encodings gracefully
- Provide detailed error messages for validation failures
- Implement comprehensive logging for troubleshooting
- Support both strict and lenient processing modes