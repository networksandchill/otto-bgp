# otto_bgp.generators Module - Developer Guide

## Overview

The `generators` module provides **secure BGP policy generation** using bgpq4 with comprehensive input validation and command injection prevention. This module transforms AS numbers into Juniper policy-options configurations through IRR database queries.

**Security Status**: Production-ready with strict input validation and command injection prevention

## Architecture Role

```
BGP Pipeline Flow:
Collection → Processing → [GENERATORS] → Application

Key Responsibilities:
- BGP policy generation using bgpq4 IRR queries
- Input validation and sanitization
- Command injection prevention
- Router-specific policy formatting
- Output file management and organization
```

## Core Components

### 1. BGPq4Wrapper (`bgpq4_wrapper.py`)
**Purpose**: Secure interface to bgpq4 with comprehensive input validation

**Key Features**:
- Command injection prevention through strict input validation
- Support for native bgpq4, Docker, and Podman execution
- Batch processing for efficient IRR queries
- Router-specific policy generation
- Comprehensive error handling and logging

**Security Architecture**:
```python
def validate_as_number(as_number: Union[int, str]) -> int:
    """Strict AS number validation to prevent command injection"""
    try:
        as_int = int(as_number)
        if not (0 <= as_int <= 4294967295):
            raise ValueError(f"AS number {as_int} outside valid range (0-4294967295)")
        return as_int
    except ValueError as e:
        raise ValueError(f"Invalid AS number format: {as_number}") from e

def sanitize_policy_name(name: str) -> str:
    """Sanitize policy names to prevent command injection"""
    # Allow only alphanumeric, underscore, hyphen
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', name)
    if not sanitized:
        raise ValueError("Policy name contains no valid characters")
    return sanitized
```

### 2. PolicyCombiner (`combiner.py`)
**Purpose**: Combine and format policies for router-specific output

**Key Features**:
- Router-aware policy combination
- Output format management (combined vs separate files)
- Policy metadata generation
- File organization and naming

## Security Architecture

### Command Injection Prevention
**CRITICAL**: This module prevents shell command injection through rigorous input validation.

#### AS Number Validation
```python
class ASNumberValidator:
    """Comprehensive AS number validation"""
    
    MIN_AS = 0
    MAX_AS = 4294967295  # 32-bit unsigned integer max
    
    @classmethod
    def validate(cls, as_number: Union[int, str]) -> int:
        """Validate AS number with strict type checking"""
        if isinstance(as_number, str):
            # Remove AS prefix if present
            if as_number.upper().startswith('AS'):
                as_number = as_number[2:]
            
            # Validate string contains only digits
            if not as_number.isdigit():
                raise ValueError(f"AS number contains non-numeric characters: {as_number}")
        
        # Convert to integer
        try:
            as_int = int(as_number)
        except ValueError as e:
            raise ValueError(f"Cannot convert AS number to integer: {as_number}") from e
        
        # Range validation
        if not (cls.MIN_AS <= as_int <= cls.MAX_AS):
            raise ValueError(
                f"AS number {as_int} outside valid range ({cls.MIN_AS}-{cls.MAX_AS})"
            )
        
        return as_int
```

#### Policy Name Sanitization
```python
def sanitize_policy_name(name: str) -> str:
    """Sanitize policy names for safe shell usage"""
    if not isinstance(name, str):
        raise TypeError("Policy name must be string")
    
    # Remove dangerous characters
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', name)
    
    # Ensure non-empty result
    if not sanitized:
        raise ValueError("Policy name contains no valid characters")
    
    # Length limits
    if len(sanitized) > 64:
        raise ValueError("Policy name too long (max 64 characters)")
    
    return sanitized
```

### Safe Command Construction
```python
def build_bgpq4_command(self, as_number: int, policy_name: str) -> List[str]:
    """Build bgpq4 command with validated inputs"""
    
    # Validate inputs (raises exceptions on invalid data)
    validated_as = self.validate_as_number(as_number)
    validated_name = self.sanitize_policy_name(policy_name)
    
    # Build command as list (not shell string)
    command = [
        self.bgpq4_path,
        '-Jl',  # Juniper format, prefix-list
        validated_name,
        f'AS{validated_as}'
    ]
    
    return command
```

## Code Structure

### Class Hierarchy
```
BGPq4Wrapper
├── ASNumberValidator (input validation)
├── PolicyNameSanitizer (name cleaning)
├── CommandBuilder (safe command construction)
├── ExecutionEngine (bgpq4 execution)
└── ResultProcessor (output handling)

PolicyCombiner
├── RouterPolicyManager (router-specific policies)
├── FileManager (output file operations)
├── MetadataGenerator (policy metadata)
└── FormatValidator (output validation)
```

### Data Flow
```python
# 1. Input validation
validated_as_numbers = []
for as_number in raw_as_numbers:
    validated_as = validator.validate_as_number(as_number)
    validated_as_numbers.append(validated_as)

# 2. Policy generation
policies = []
for as_number in validated_as_numbers:
    policy_name = f"AS{as_number}"
    sanitized_name = sanitizer.sanitize_policy_name(policy_name)
    
    # Generate policy via bgpq4
    policy = wrapper.generate_policy(as_number, sanitized_name)
    policies.append(policy)

# 3. Output combination and formatting
if separate_files:
    combiner.write_separate_files(policies, output_dir)
else:
    combiner.write_combined_file(policies, output_file)
```

## Design Choices

### Input Validation First
**Choice**: Validate all inputs before any processing
**Rationale**:
- Prevents command injection attacks
- Fails fast on invalid data
- Clear error messages for operators
- Audit trail of validation failures

### List-Based Command Construction
**Choice**: Build commands as lists, not shell strings
**Rationale**:
- Eliminates shell injection vulnerabilities
- Precise argument control
- Cross-platform compatibility
- Easier testing and debugging

### Multiple Execution Modes
**Choice**: Support native, Docker, and Podman execution
**Rationale**:
- Flexibility for different deployment environments
- Fallback options when native bgpq4 unavailable
- Container isolation for security
- Development environment support

### Separate Validation Classes
**Choice**: Dedicated validator classes for different input types
**Rationale**:
- Single responsibility principle
- Testable validation logic
- Reusable across modules
- Clear error classification

## BGP Policy Generation

### bgpq4 Integration Patterns
```python
class BGPq4Wrapper:
    """Secure wrapper for bgpq4 policy generation"""
    
    def __init__(self, bgpq4_path: str = "bgpq4", mode: str = "auto"):
        self.bgpq4_path = bgpq4_path
        self.mode = mode  # "native", "docker", "podman", "auto"
        
        # Validate bgpq4 availability
        self._validate_bgpq4_available()
    
    def generate_policy(self, as_number: int, policy_name: str) -> PolicyResult:
        """Generate single policy with validation"""
        
        # Input validation
        validated_as = self.validate_as_number(as_number)
        validated_name = self.sanitize_policy_name(policy_name)
        
        # Build command
        command = self.build_bgpq4_command(validated_as, validated_name)
        
        # Execute with timeout
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=True  # Raise on non-zero exit
            )
            
            return PolicyResult(
                as_number=validated_as,
                policy_name=validated_name,
                content=result.stdout,
                success=True
            )
            
        except subprocess.TimeoutExpired:
            raise BGPq4TimeoutError(f"bgpq4 timeout for AS{validated_as}")
        except subprocess.CalledProcessError as e:
            raise BGPq4ExecutionError(f"bgpq4 failed for AS{validated_as}: {e.stderr}")
```

### Batch Processing
```python
def generate_policies_batch(self, as_numbers: List[int]) -> List[PolicyResult]:
    """Generate multiple policies efficiently"""
    
    results = []
    failed_as = []
    
    for as_number in as_numbers:
        try:
            policy_name = f"AS{as_number}"
            result = self.generate_policy(as_number, policy_name)
            results.append(result)
            
        except (BGPq4TimeoutError, BGPq4ExecutionError) as e:
            logger.error(f"Policy generation failed for AS{as_number}: {e}")
            failed_as.append(as_number)
            
            # Create failure result
            results.append(PolicyResult(
                as_number=as_number,
                policy_name=f"AS{as_number}",
                content="",
                success=False,
                error_message=str(e)
            ))
    
    # Log batch summary
    success_count = len([r for r in results if r.success])
    logger.info(f"Batch generation: {success_count}/{len(as_numbers)} successful")
    
    if failed_as:
        logger.warning(f"Failed AS numbers: {failed_as}")
    
    return results
```

### Router-Specific Generation
```python
def generate_for_router(self, router_profile: RouterProfile) -> RouterPolicyResult:
    """Generate policies for specific router context"""
    
    router_as_numbers = router_profile.discovered_as_numbers
    router_hostname = router_profile.hostname
    
    # Generate policies for router's AS numbers
    policies = self.generate_policies_batch(list(router_as_numbers))
    
    # Create router-specific output
    return RouterPolicyResult(
        router_hostname=router_hostname,
        policies=policies,
        bgp_groups=router_profile.bgp_groups,
        metadata={
            'generated_at': datetime.now().isoformat(),
            'as_count': len(router_as_numbers),
            'router_ip': router_profile.ip_address
        }
    )
```

## Security Considerations

### Input Sanitization
- **AS numbers**: 32-bit unsigned integer validation
- **Policy names**: Alphanumeric, underscore, hyphen only
- **File paths**: Absolute paths with directory validation
- **Command arguments**: No shell metacharacters allowed

### Command Execution Security
- **List-based commands**: No shell interpretation
- **Process isolation**: Subprocess with limited environment
- **Timeout controls**: Prevent hanging processes
- **Resource limits**: Memory and CPU constraints

### Output Security
- **File permission controls**: Restricted write access
- **Path traversal prevention**: Validate output directories
- **Content validation**: Verify generated policy syntax
- **Temporary file cleanup**: Secure cleanup of intermediate files

## Integration Points

### CLI Interface
```bash
# Generate policies from AS list
./otto-bgp policy as_numbers.txt -o policies.txt

# Generate separate files per AS
./otto-bgp policy as_numbers.txt -s --output-dir ./policies

# Test bgpq4 connectivity
./otto-bgp policy as_numbers.txt --test --test-as 13335

# Use containerized bgpq4
./otto-bgp --dev policy as_numbers.txt -s
```

### Python API
```python
from otto_bgp.generators import BGPq4Wrapper, PolicyCombiner

wrapper = BGPq4Wrapper(mode="native", timeout=45)
combiner = PolicyCombiner()

# Single policy generation
policy = wrapper.generate_policy(13335, "AS13335")

# Batch generation
policies = wrapper.generate_policies_batch([13335, 15169, 7922])

# Write to files
combiner.write_separate_files(policies, output_dir="./policies")
```

### Pipeline Integration
- **Input**: Validated AS numbers from processors
- **Output**: Generated policy files in specified format
- **Error Handling**: Detailed generation results with failure reasons
- **Logging**: Comprehensive operation logging for monitoring

## Error Handling

### Generation Failures
```python
class PolicyGenerationError(Exception):
    """Base class for policy generation errors"""
    pass

class BGPq4TimeoutError(PolicyGenerationError):
    """bgpq4 command timeout"""
    pass

class BGPq4ExecutionError(PolicyGenerationError):
    """bgpq4 execution failure"""
    pass

class ValidationError(PolicyGenerationError):
    """Input validation failure"""
    pass

# Error handling pattern
def safe_generate_policy(self, as_number: int) -> PolicyResult:
    try:
        return self.generate_policy(as_number, f"AS{as_number}")
    except ValidationError as e:
        logger.error(f"Validation failed for AS{as_number}: {e}")
        return PolicyResult(as_number=as_number, success=False, error_type="validation")
    except BGPq4TimeoutError as e:
        logger.warning(f"Timeout for AS{as_number}: {e}")
        return PolicyResult(as_number=as_number, success=False, error_type="timeout")
    except BGPq4ExecutionError as e:
        logger.error(f"Execution failed for AS{as_number}: {e}")
        return PolicyResult(as_number=as_number, success=False, error_type="execution")
```

### Network Connectivity Issues
- **IRR server timeouts**: Retry with exponential backoff
- **DNS resolution failures**: Fallback to alternative servers
- **Network partitions**: Graceful degradation with cached results
- **Rate limiting**: Throttling and queue management

## Performance Optimization

### Batch Processing
```python
def generate_batch_optimized(self, as_numbers: List[int]) -> List[PolicyResult]:
    """Optimized batch generation with parallelization"""
    
    # Validate all inputs first
    validated_as_numbers = []
    for as_number in as_numbers:
        try:
            validated = self.validate_as_number(as_number)
            validated_as_numbers.append(validated)
        except ValidationError as e:
            logger.error(f"Skipping invalid AS number {as_number}: {e}")
    
    # Parallel generation with thread pool
    with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
        futures = {
            executor.submit(self.generate_policy, as_num, f"AS{as_num}"): as_num
            for as_num in validated_as_numbers
        }
        
        results = []
        for future in as_completed(futures):
            as_number = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error(f"Thread execution failed for AS{as_number}: {e}")
                results.append(PolicyResult(
                    as_number=as_number,
                    success=False,
                    error_message=str(e)
                ))
    
    return results
```

### Caching Strategy
- **Policy result caching**: Avoid redundant IRR queries
- **AS validation caching**: Cache validation results
- **bgpq4 output caching**: Short-term caching for identical queries
- **Connection pooling**: Reuse network connections when possible

## Development Guidelines

### Usage Examples
```python
# Example policy generation with mocked bgpq4
from unittest.mock import patch

@patch('subprocess.run')
def example_policy_generation(mock_subprocess):
    mock_subprocess.return_value.stdout = "policy-options { prefix-list AS13335 { 1.1.1.0/24; } }"
    mock_subprocess.return_value.returncode = 0
    
    wrapper = BGPq4Wrapper()
    result = wrapper.generate_policy(13335, "AS13335")
    
    if result.success:
        print(f"Generated policy: {result.content}")
    else:
        print(f"Generation failed: {result.error_message}")

# Security validation examples
def example_as_number_validation():
    wrapper = BGPq4Wrapper()
    
    try:
        wrapper.validate_as_number("'; rm -rf /; #")
    except ValidationError as e:
        print(f"Malicious input rejected: {e}")
    
    try:
        wrapper.validate_as_number(4294967296)  # Out of range
    except ValidationError as e:
        print(f"Invalid AS number rejected: {e}")

# Real bgpq4 usage example
def example_real_bgpq4_usage():
    wrapper = BGPq4Wrapper()
    result = wrapper.generate_policy(13335, "AS13335")
    if result.success and "prefix-list" in result.content:
        print("Policy generation successful")
    else:
        print(f"Policy generation failed: {result.error_message}")
```

### Performance Considerations
- **Batch processing** for large AS number sets
- **Timeout configuration** for unreachable IRR servers
- **Memory optimization** during batch operations
- **Thread safety** for concurrent access

### Security Implementation
- **Input validation** to prevent injection attacks
- **Command sanitization** with allowlist-based validation
- **Resource limits** to prevent exhaustion attacks
- **Secure file operations** with proper permissions

## Dependencies

### Required
- `subprocess` (command execution)
- `re` (input validation patterns)
- `pathlib` (file operations)

### Optional
- `docker` (containerized bgpq4)
- `concurrent.futures` (parallel processing)

## Best Practices

### Security
- Always validate inputs before processing
- Use list-based command construction
- Implement comprehensive logging for security events
- Regular security testing of validation functions

### Performance
- Use batch processing for multiple AS numbers
- Implement appropriate timeout values
- Monitor and optimize IRR query patterns
- Cache results when appropriate

### Reliability
- Handle network failures gracefully
- Provide detailed error messages
- Implement retry logic for transient failures
- Monitor bgpq4 service health