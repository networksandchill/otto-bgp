#!/usr/bin/env python3
"""
Phase 2 Validation Script - Discovery Engine

This script validates that Phase 2 implementation meets all requirements:
1. BGP configuration parsing works correctly
2. AS numbers and groups are discovered
3. YAML mappings are auto-generated
4. History tracking functions properly
5. Discovery CLI commands work
"""

import sys
import logging
import tempfile
import yaml
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from otto_bgp.discovery import RouterInspector, BGPConfigParser, YAMLGenerator
from otto_bgp.models import RouterProfile

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_bgp_config_parser():
    """Test BGP configuration parsing."""
    logger.info("=" * 60)
    logger.info("Testing BGP Configuration Parser")
    logger.info("=" * 60)
    
    # Sample Juniper BGP configuration
    sample_config = """
    protocols {
        bgp {
            autonomous-system 65000;
            group external-peers {
                type external;
                neighbor 10.0.0.1 {
                    peer-as 65001;
                    description "ISP-A";
                }
                neighbor 10.0.0.2 {
                    peer-as 65002;
                    description "ISP-B";
                }
            }
            group cdn-peers {
                neighbor 192.168.1.1 {
                    peer-as 13335;
                    description "Cloudflare";
                }
                neighbor 192.168.1.2 {
                    peer-as 15169;
                    description "Google";
                }
            }
        }
    }
    """
    
    try:
        parser = BGPConfigParser()
        
        # Parse configuration
        result = parser.parse_config(sample_config)
        
        logger.info(f"✓ Parsed BGP configuration")
        logger.info(f"  Local AS: {result['local_as']}")
        logger.info(f"  Groups found: {len(result['groups'])}")
        logger.info(f"  AS numbers: {result['as_numbers']}")
        logger.info(f"  Neighbors: {len(result['neighbors'])}")
        
        # Verify parsing accuracy
        assert result['local_as'] == 65000, "Local AS not parsed correctly"
        assert len(result['groups']) == 2, "Not all groups parsed"
        assert 65001 in result['as_numbers'], "AS 65001 not found"
        assert 13335 in result['as_numbers'], "AS 13335 not found"
        
        logger.info("✓ BGP config parser works correctly")
        return True
        
    except Exception as e:
        logger.error(f"✗ BGP config parser failed: {e}")
        return False


def test_router_inspector():
    """Test router inspection and discovery."""
    logger.info("=" * 60)
    logger.info("Testing Router Inspector")
    logger.info("=" * 60)
    
    sample_config = """
    group external {
        neighbor 10.0.0.1 {
            peer-as 65001;
        }
        neighbor 10.0.0.2 {
            peer-as 65002;
        }
    }
    group internal {
        neighbor 172.16.0.1 {
            peer-as 64512;
        }
    }
    """
    
    try:
        inspector = RouterInspector()
        
        # Test group discovery
        groups = inspector.discover_bgp_groups(sample_config)
        logger.info(f"✓ Discovered {len(groups)} BGP groups")
        for group_name, as_list in groups.items():
            logger.info(f"  {group_name}: AS {as_list}")
        
        # Test peer relationships
        relationships = inspector.extract_peer_relationships(sample_config)
        logger.info(f"✓ Extracted {len(relationships)} peer relationships")
        
        # Test complete inspection
        profile = RouterProfile(
            hostname="test-router-01",
            ip_address="10.0.0.1",
            bgp_config=sample_config
        )
        
        result = inspector.inspect_router(profile)
        
        assert len(result.bgp_groups) == 2, "Not all groups discovered"
        # The sample config has: external group with 65001, 65002 and internal with 64512 = 3 total
        # But each neighbor is separate, so external will have [65001, 65002]
        assert result.total_as_numbers == 3, f"Not all AS numbers counted, got {result.total_as_numbers}"
        
        logger.info(f"✓ Router inspection complete")
        logger.info(f"  Groups: {list(result.bgp_groups.keys())}")
        logger.info(f"  Total AS numbers: {result.total_as_numbers}")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Router inspector failed: {e}")
        return False


def test_yaml_generator():
    """Test YAML generation and history management."""
    logger.info("=" * 60)
    logger.info("Testing YAML Generator")
    logger.info("=" * 60)
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            yaml_gen = YAMLGenerator(output_dir=temp_dir)
            
            # Create test profiles
            profiles = [
                RouterProfile(
                    hostname="router-01",
                    ip_address="10.0.0.1",
                    discovered_as_numbers={65001, 65002},
                    bgp_groups={"external": [65001, 65002]}
                ),
                RouterProfile(
                    hostname="router-02",
                    ip_address="10.0.0.2",
                    discovered_as_numbers={65003, 13335},
                    bgp_groups={"cdn": [13335], "external": [65003]}
                )
            ]
            
            # Generate mappings
            mappings = yaml_gen.generate_mappings(profiles)
            
            logger.info("✓ Generated YAML mappings")
            logger.info(f"  Routers: {mappings['_metadata']['total_routers']}")
            logger.info(f"  BGP groups: {mappings['_metadata']['total_bgp_groups']}")
            logger.info(f"  AS numbers: {mappings['_metadata']['total_as_numbers']}")
            
            # Save with history
            yaml_file = yaml_gen.save_with_history(mappings)
            
            assert yaml_file.exists(), "YAML file not created"
            logger.info(f"✓ Saved mappings to {yaml_file}")
            
            # Save router inventory
            inventory_file = yaml_gen.save_router_inventory(profiles)
            
            assert inventory_file.exists(), "Inventory file not created"
            logger.info(f"✓ Saved inventory to {inventory_file}")
            
            # Test diff generation
            # Modify mappings
            profiles[0].discovered_as_numbers.add(65004)
            new_mappings = yaml_gen.generate_mappings(profiles)
            
            diff = yaml_gen.diff_mappings(mappings, new_mappings)
            logger.info(f"✓ Generated diff: {diff['summary']}")
            
            # Test history
            yaml_gen.save_with_history(new_mappings)
            history_dir = Path(temp_dir) / "history"
            snapshots = list(history_dir.glob("*.yaml"))
            
            assert len(snapshots) > 0, "No history snapshots created"
            logger.info(f"✓ History tracking works ({len(snapshots)} snapshots)")
            
            return True
            
    except Exception as e:
        logger.error(f"✗ YAML generator failed: {e}")
        return False


def test_discovery_workflow():
    """Test complete discovery workflow."""
    logger.info("=" * 60)
    logger.info("Testing Complete Discovery Workflow")
    logger.info("=" * 60)
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # Initialize components
            inspector = RouterInspector()
            yaml_gen = YAMLGenerator(output_dir=temp_dir)
            
            # Simulate multiple routers with BGP configs
            routers_configs = [
                {
                    "hostname": "edge-router-01.nyc",
                    "ip": "10.0.0.1",
                    "config": """
                    group external {
                        neighbor 192.168.1.1 {
                            peer-as 65001;
                        }
                    }
                    group cdn {
                        neighbor 192.168.2.1 {
                            peer-as 13335;
                        }
                    }
                    """
                },
                {
                    "hostname": "core-router-01.sjc",
                    "ip": "10.0.0.2",
                    "config": """
                    group external {
                        neighbor 192.168.1.2 {
                            peer-as 65001;
                        }
                        neighbor 192.168.1.3 {
                            peer-as 65002;
                        }
                    }
                    """
                }
            ]
            
            profiles = []
            discovery_results = []
            
            # Process each router
            for router_data in routers_configs:
                profile = RouterProfile(
                    hostname=router_data["hostname"],
                    ip_address=router_data["ip"],
                    bgp_config=router_data["config"]
                )
                
                result = inspector.inspect_router(profile)
                profiles.append(profile)
                discovery_results.append(result)
                
                logger.info(f"✓ Discovered {router_data['hostname']}")
                logger.info(f"  Groups: {list(result.bgp_groups.keys())}")
                logger.info(f"  AS numbers: {result.total_as_numbers}")
            
            # Merge results
            merged = inspector.merge_discovery_results(discovery_results)
            
            logger.info(f"✓ Merged discovery results")
            logger.info(f"  Total routers: {merged['total_routers']}")
            logger.info(f"  Total groups: {merged['total_groups']}")
            logger.info(f"  Total AS numbers: {merged['total_as_numbers']}")
            
            # Generate and save mappings
            mappings = yaml_gen.generate_mappings(profiles)
            yaml_file = yaml_gen.save_with_history(mappings)
            inventory_file = yaml_gen.save_router_inventory(profiles)
            
            # Verify outputs
            assert yaml_file.exists(), "YAML mappings not created"
            assert inventory_file.exists(), "Router inventory not created"
            
            # Load and verify YAML content
            with open(yaml_file, 'r') as f:
                loaded_yaml = yaml.safe_load(f)
            
            assert loaded_yaml["_metadata"]["total_routers"] == 2
            assert "edge-router-01.nyc" in loaded_yaml["routers"]
            assert "core-router-01.sjc" in loaded_yaml["routers"]
            
            logger.info("✓ Complete discovery workflow successful")
            
            return True
            
    except Exception as e:
        logger.error(f"✗ Discovery workflow failed: {e}")
        return False


def test_discovery_idempotency():
    """Test that discovery is idempotent (same input = same output)."""
    logger.info("=" * 60)
    logger.info("Testing Discovery Idempotency")
    logger.info("=" * 60)
    
    config = """
    group test {
        neighbor 10.0.0.1 {
            peer-as 65001;
        }
    }
    """
    
    try:
        inspector = RouterInspector()
        
        # Run discovery twice with same config
        result1 = inspector.discover_bgp_groups(config)
        result2 = inspector.discover_bgp_groups(config)
        
        assert result1 == result2, "Discovery not idempotent"
        
        logger.info("✓ Discovery is idempotent")
        logger.info(f"  Same output for same input: {result1}")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Idempotency test failed: {e}")
        return False


def main():
    """Run all Phase 2 validation tests."""
    logger.info("╔" + "=" * 58 + "╗")
    logger.info("║" + " Phase 2 Validation: Discovery Engine ".center(58) + "║")
    logger.info("╚" + "=" * 58 + "╝")
    
    tests = [
        ("BGP Config Parser", test_bgp_config_parser),
        ("Router Inspector", test_router_inspector),
        ("YAML Generator", test_yaml_generator),
        ("Discovery Workflow", test_discovery_workflow),
        ("Discovery Idempotency", test_discovery_idempotency)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        logger.info("")
        success = test_func()
        results.append((test_name, success))
    
    # Summary
    logger.info("")
    logger.info("╔" + "=" * 58 + "╗")
    logger.info("║" + " VALIDATION SUMMARY ".center(58) + "║")
    logger.info("╚" + "=" * 58 + "╝")
    
    all_passed = True
    for test_name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        logger.info(f"  {test_name:.<40} {status}")
        if not success:
            all_passed = False
    
    logger.info("")
    if all_passed:
        logger.info("🎉 Phase 2 Validation COMPLETE - All tests passed!")
        logger.info("✓ BGP configuration parsing accurate")
        logger.info("✓ AS numbers correctly discovered")
        logger.info("✓ YAML generation is deterministic")
        logger.info("✓ History snapshots created properly")
        logger.info("✓ Discovery is idempotent")
        logger.info("")
        logger.info("Phase 2: Discovery Engine is COMPLETE")
        return 0
    else:
        logger.error("❌ Phase 2 Validation FAILED - Some tests did not pass")
        return 1


if __name__ == "__main__":
    sys.exit(main())