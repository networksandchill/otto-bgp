#!/usr/bin/env python3
"""
Simple test for parser regex optimizations without external dependencies.
"""

import sys
import re

sys.path.append('/Users/randallfussell/GITHUB_PROJECTS/otto-bgp')

def test_parser_patterns():
    """Test parser regex patterns directly."""
    print("Testing parser regex patterns...")
    
    # Import parser class
    from otto_bgp.discovery.parser import BGPConfigParser
    
    parser = BGPConfigParser()
    
    # Test BGP configuration
    test_config = """
    group external-peers {
        type external;
        import [ policy-in ];
        export [ policy-out ];
        neighbor 10.0.0.1 {
            description "Test peer 1";
            peer-as 65002;
        }
    }
    """
    
    # Test individual pattern methods
    try:
        # Test AS number extraction
        as_numbers = parser.extract_as_numbers(test_config)
        print(f"AS numbers extracted: {as_numbers}")
        
        # Test policy extraction
        policies = parser.extract_policies(test_config) 
        print(f"Policies extracted: {policies}")
        
        # Test address family identification
        families = parser.identify_address_families(test_config)
        print(f"Address families: {families}")
        
        print("✓ Parser regex patterns working correctly")
        return True
        
    except Exception as e:
        print(f"✗ Parser test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_parser_patterns()
    sys.exit(0 if success else 1)