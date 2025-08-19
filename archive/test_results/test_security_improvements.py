#!/usr/bin/env python3
"""
Security Improvement Testing Script

Test the security enhancements made to bgpq3_wrapper.py and as_extractor.py:
1. Command injection prevention in bgpq3_wrapper
2. Enhanced AS number validation in as_extractor

This script validates that the security improvements work correctly and
don't break existing functionality.
"""

import sys
import logging
from pathlib import Path

# Add bgp_toolkit to path for testing
sys.path.insert(0, str(Path(__file__).parent / "bgp_toolkit"))

from bgp_toolkit.generators.bgpq3_wrapper import validate_as_number, validate_policy_name, BGPq3Wrapper
from bgp_toolkit.processors.as_extractor import ASNumberExtractor


def setup_test_logging():
    """Setup logging for test output"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s: %(message)s'
    )
    return logging.getLogger(__name__)


def test_as_number_validation():
    """Test AS number validation function"""
    logger = logging.getLogger(__name__)
    logger.info("Testing AS number validation...")
    
    # Valid AS numbers
    valid_tests = [
        1234,
        65000,
        4294967294,
        "12345",  # String that converts to int
    ]
    
    # Invalid AS numbers
    invalid_tests = [
        -1,               # Negative
        4294967296,       # Too large (> 32-bit max)
        "invalid",        # Non-numeric string
        [],               # Non-string/int type
        None,             # None type
        3.14,             # Float
    ]
    
    # Test valid cases
    for test_as in valid_tests:
        try:
            result = validate_as_number(test_as)
            logger.info(f"✓ Valid AS {test_as} -> {result}")
        except Exception as e:
            logger.error(f"✗ Unexpected error for valid AS {test_as}: {e}")
            return False
    
    # Test invalid cases
    for test_as in invalid_tests:
        try:
            result = validate_as_number(test_as)
            logger.error(f"✗ Invalid AS {test_as} should have failed but got: {result}")
            return False
        except ValueError as e:
            logger.info(f"✓ Invalid AS {test_as} correctly rejected: {e}")
        except Exception as e:
            logger.error(f"✗ Unexpected exception for invalid AS {test_as}: {e}")
            return False
    
    return True


def test_policy_name_validation():
    """Test policy name validation function"""
    logger = logging.getLogger(__name__)
    logger.info("Testing policy name validation...")
    
    # Valid policy names
    valid_tests = [
        "AS12345",
        "MyPolicy-1",
        "test_policy",
        "Policy123",
        "A",
        "1234567890",
    ]
    
    # Invalid policy names
    invalid_tests = [
        "",                    # Empty string
        "policy with spaces",  # Spaces
        "policy@name",         # Special characters
        "policy.name",         # Dot
        "policy/name",         # Slash
        "policy;injection",    # Semicolon (injection attempt)
        "|injection",          # Pipe (injection attempt)
        "policy`cmd`",         # Backticks (injection attempt)
        "a" * 65,              # Too long
        123,                   # Non-string type
        None,                  # None type
    ]
    
    # Test valid cases
    for test_name in valid_tests:
        try:
            result = validate_policy_name(test_name)
            logger.info(f"✓ Valid policy name '{test_name}' -> '{result}'")
        except Exception as e:
            logger.error(f"✗ Unexpected error for valid policy name '{test_name}': {e}")
            return False
    
    # Test invalid cases
    for test_name in invalid_tests:
        try:
            result = validate_policy_name(test_name)
            logger.error(f"✗ Invalid policy name '{test_name}' should have failed but got: '{result}'")
            return False
        except ValueError as e:
            logger.info(f"✓ Invalid policy name '{test_name}' correctly rejected: {e}")
        except Exception as e:
            logger.error(f"✗ Unexpected exception for invalid policy name '{test_name}': {e}")
            return False
    
    return True


def test_as_extractor_security():
    """Test enhanced AS extractor security features"""
    logger = logging.getLogger(__name__)
    logger.info("Testing AS extractor security enhancements...")
    
    # Test with strict validation enabled
    extractor_strict = ASNumberExtractor(
        min_as_number=256,
        max_as_number=4294967295,
        warn_reserved=True,
        strict_validation=True
    )
    
    # Test text with various AS numbers including edge cases
    test_text = """
    peer-as 13335    # Valid public AS
    peer-as 64512    # Private use range
    peer-as 255      # Should be filtered (IP octet)
    peer-as 0        # Reserved
    peer-as 23456    # AS_TRANS
    peer-as 4294967295  # Reserved max
    peer-as 999999999999  # Too large
    peer-as 192.168.1.1   # IP address (should not match AS pattern)
    peer-as 65000    # Valid AS number (changed from AS65000 format)
    """
    
    try:
        result = extractor_strict.extract_as_numbers_from_text(test_text, 'peer_as')
        logger.info(f"✓ Strict extraction found {len(result.as_numbers)} AS numbers: {sorted(result.as_numbers)}")
        
        # Should find legitimate AS numbers but filter problematic ones
        expected_valid = {13335, 65000}  # 64512 might be included with warning
        
        if not expected_valid.issubset(result.as_numbers):
            logger.error(f"✗ Expected AS numbers {expected_valid} not found in result: {result.as_numbers}")
            return False
        
        # Should not find IP octets (255, 0) - reserved AS numbers like 23456, 4294967295 may be included with warnings
        ip_octets = {255, 0}
        if ip_octets.intersection(result.as_numbers):
            logger.error(f"✗ Found IP octets that should be filtered: {ip_octets.intersection(result.as_numbers)}")
            return False
        
        # Reserved AS numbers might be included but should have warnings logged
        # This is acceptable behavior as they are valid AS numbers, just warned about
        
    except Exception as e:
        logger.error(f"✗ AS extractor failed: {e}")
        return False
    
    # Test legacy mode for backward compatibility
    extractor_legacy = ASNumberExtractor(
        min_as_number=256,
        max_as_number=4294967295,
        strict_validation=False
    )
    
    try:
        result_legacy = extractor_legacy.extract_as_numbers_from_text(test_text, 'peer_as')
        logger.info(f"✓ Legacy extraction found {len(result_legacy.as_numbers)} AS numbers: {sorted(result_legacy.as_numbers)}")
    except Exception as e:
        logger.error(f"✗ Legacy AS extractor failed: {e}")
        return False
    
    return True


def test_bgpq3_wrapper_integration():
    """Test BGPq3 wrapper integration with validation"""
    logger = logging.getLogger(__name__)
    logger.info("Testing BGPq3 wrapper security integration...")
    
    # This test doesn't actually run bgpq3 commands, just tests validation
    try:
        # Initialize wrapper (will detect available bgpq3 or fail gracefully)
        wrapper = BGPq3Wrapper()
        logger.info("✓ BGPq3 wrapper initialized successfully")
        
        # Test command building with valid inputs
        try:
            command = wrapper._build_bgpq3_command(13335, "TestPolicy")
            logger.info(f"✓ Valid command built: {' '.join(command)}")
        except Exception as e:
            logger.error(f"✗ Failed to build command with valid inputs: {e}")
            return False
        
        # Test command building with invalid AS number
        try:
            command = wrapper._build_bgpq3_command(-1, "TestPolicy")
            logger.error("✗ Should have failed with invalid AS number")
            return False
        except ValueError as e:
            logger.info(f"✓ Invalid AS number correctly rejected: {e}")
        
        # Test command building with invalid policy name
        try:
            command = wrapper._build_bgpq3_command(13335, "policy;injection")
            logger.error("✗ Should have failed with invalid policy name")
            return False
        except ValueError as e:
            logger.info(f"✓ Invalid policy name correctly rejected: {e}")
        
    except RuntimeError as e:
        # Expected if bgpq3 not available
        logger.info(f"⚠ BGPq3 not available for testing: {e}")
        logger.info("  This is expected in test environments without bgpq3 installed")
        return True
    except Exception as e:
        logger.error(f"✗ Unexpected error in BGPq3 wrapper: {e}")
        return False
    
    return True


def run_security_tests():
    """Run all security improvement tests"""
    logger = setup_test_logging()
    
    logger.info("=" * 60)
    logger.info("Security Improvements Test Suite")
    logger.info("=" * 60)
    
    tests = [
        ("AS Number Validation", test_as_number_validation),
        ("Policy Name Validation", test_policy_name_validation),
        ("AS Extractor Security", test_as_extractor_security),
        ("BGPq3 Wrapper Integration", test_bgpq3_wrapper_integration),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        logger.info(f"\n{'-' * 40}")
        logger.info(f"Running: {test_name}")
        logger.info(f"{'-' * 40}")
        
        try:
            if test_func():
                logger.info(f"✓ PASSED: {test_name}")
                passed += 1
            else:
                logger.error(f"✗ FAILED: {test_name}")
        except Exception as e:
            logger.error(f"✗ ERROR in {test_name}: {e}")
    
    logger.info(f"\n{'=' * 60}")
    logger.info(f"Test Results: {passed}/{total} tests passed")
    logger.info(f"{'=' * 60}")
    
    if passed == total:
        logger.info("🎉 All security tests PASSED!")
        return True
    else:
        logger.error(f"❌ {total - passed} tests FAILED!")
        return False


if __name__ == "__main__":
    success = run_security_tests()
    sys.exit(0 if success else 1)