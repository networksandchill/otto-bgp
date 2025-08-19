#!/usr/bin/env python3
"""
Test script for bgpq4 refactoring
Tests the bgpq4 wrapper directly without full module dependencies
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bgp_toolkit.generators.bgpq4_wrapper import BGPq4Wrapper, BGPq4Mode

def test_bgpq4():
    print("Testing bgpq4 wrapper...")
    
    # Initialize wrapper
    wrapper = BGPq4Wrapper(mode=BGPq4Mode.AUTO)
    
    print(f"Detected mode: {wrapper.detected_mode}")
    print(f"Command: {wrapper.bgpq4_command}")
    
    # Test connectivity
    print("\nTesting bgpq4 connectivity with AS13335 (Cloudflare)...")
    success = wrapper.test_bgpq4_connection(13335)
    
    if success:
        print("✅ bgpq4 connectivity test PASSED")
        
        # Generate a test policy
        print("\nGenerating policy for AS13335...")
        result = wrapper.generate_policy_for_as(13335)
        
        if result.success:
            print(f"✅ Policy generated successfully")
            print(f"   Execution time: {result.execution_time:.2f}s")
            print(f"   Policy size: {len(result.policy_content)} characters")
            print(f"   First 500 chars of policy:")
            print("   " + "-" * 40)
            print(result.policy_content[:500])
        else:
            print(f"❌ Policy generation failed: {result.error_message}")
    else:
        print("❌ bgpq4 connectivity test FAILED")
        print("   Make sure bgpq4 is installed and in PATH")
    
    return success

if __name__ == "__main__":
    success = test_bgpq4()
    sys.exit(0 if success else 1)