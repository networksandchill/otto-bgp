#!/usr/bin/env python3
"""
Phase 3 Validation Script - Router-Specific Policy Generation

This script validates that Phase 3 implementation meets all requirements:
1. Router-aware pipeline processing
2. Per-router policy directories
3. Deployment matrix generation
4. Policy combination functionality
5. Correct router isolation (no cross-contamination)
"""

import sys
import logging
import tempfile
import json
import csv
from pathlib import Path
from unittest.mock import Mock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from otto_bgp.pipeline.workflow import BGPPolicyPipeline, PipelineConfig
from otto_bgp.models import RouterProfile, DeviceInfo
from otto_bgp.reports import DeploymentMatrix
from otto_bgp.generators.combiner import PolicyCombiner

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_router_aware_pipeline():
    """Test router-aware pipeline functionality"""
    logger.info("=" * 60)
    logger.info("Testing Router-Aware Pipeline")
    logger.info("=" * 60)
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create pipeline config
            config = PipelineConfig(
                devices_file="test_devices.csv",
                output_directory=temp_dir,
                router_aware=True,
                skip_ssh=True
            )
            
            # Create pipeline
            pipeline = BGPPolicyPipeline(config)
            
            # Create test profiles
            test_profiles = [
                RouterProfile(
                    hostname="edge-router-01.nyc",
                    ip_address="10.0.0.1",
                    discovered_as_numbers={65001, 65002, 13335},
                    bgp_groups={"external": [65001, 65002], "cdn": [13335]},
                    site="nyc",
                    role="edge"
                ),
                RouterProfile(
                    hostname="core-router-01.sjc",
                    ip_address="10.0.0.2",
                    discovered_as_numbers={65001, 65003, 15169},
                    bgp_groups={"external": [65001, 65003], "cdn": [15169]},
                    site="sjc",
                    role="core"
                )
            ]
            
            # Test router directory creation
            for profile in test_profiles:
                router_dir = pipeline._create_router_directory(profile)
                assert router_dir.exists(), f"Router directory not created for {profile.hostname}"
                logger.info(f"✓ Created router directory: {router_dir}")
            
            # Test metadata generation
            for profile in test_profiles:
                router_dir = pipeline._create_router_directory(profile)
                pipeline._create_router_metadata(profile, router_dir, 3)
                
                metadata_file = router_dir / "metadata.json"
                assert metadata_file.exists(), f"Metadata not created for {profile.hostname}"
                
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                
                assert metadata["router"]["hostname"] == profile.hostname
                assert metadata["version"] == "0.3.0"
                logger.info(f"✓ Generated metadata for {profile.hostname}")
            
            logger.info("✓ Router-aware pipeline components work correctly")
            return True
            
    except Exception as e:
        logger.error(f"✗ Router-aware pipeline test failed: {e}")
        return False


def test_router_isolation():
    """Test that routers only get their assigned AS policies"""
    logger.info("=" * 60)
    logger.info("Testing Router Isolation")
    logger.info("=" * 60)
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = PipelineConfig(
                devices_file="test_devices.csv",
                output_directory=temp_dir,
                router_aware=True,
                skip_ssh=True
            )
            
            pipeline = BGPPolicyPipeline(config)
            
            # Create routers with different AS sets
            router_a = RouterProfile(
                hostname="router-A",
                ip_address="10.0.0.1",
                discovered_as_numbers={65001, 65002, 65003}
            )
            
            router_b = RouterProfile(
                hostname="router-B",
                ip_address="10.0.0.2",
                discovered_as_numbers={65004, 65005, 65006}
            )
            
            # Mock policy generation
            with patch.object(pipeline.bgp_generator, 'generate_policy') as mock_gen:
                mock_gen.return_value = Mock(
                    success=True,
                    policy_config="test policy",
                    as_number=65001
                )
                
                # Generate for router A
                router_a_dir = pipeline._create_router_directory(router_a)
                count_a = pipeline._generate_router_policies(router_a, router_a_dir)
                
                # Generate for router B
                router_b_dir = pipeline._create_router_directory(router_b)
                count_b = pipeline._generate_router_policies(router_b, router_b_dir)
            
            # Verify isolation
            router_a_policies = list(router_a_dir.glob("AS*_policy.txt"))
            router_b_policies = list(router_b_dir.glob("AS*_policy.txt"))
            
            # Extract AS numbers from filenames
            router_a_as = {int(p.stem.replace("AS", "").replace("_policy", "")) 
                          for p in router_a_policies}
            router_b_as = {int(p.stem.replace("AS", "").replace("_policy", "")) 
                          for p in router_b_policies}
            
            # Check no overlap (since AS sets are disjoint)
            assert router_a_as.isdisjoint(router_b_as), "AS policies leaked between routers!"
            
            logger.info(f"✓ Router A has policies for AS: {router_a_as}")
            logger.info(f"✓ Router B has policies for AS: {router_b_as}")
            logger.info("✓ Router isolation verified - no cross-contamination")
            
            return True
            
    except Exception as e:
        logger.error(f"✗ Router isolation test failed: {e}")
        return False


def test_deployment_matrix():
    """Test deployment matrix generation"""
    logger.info("=" * 60)
    logger.info("Testing Deployment Matrix Generation")
    logger.info("=" * 60)
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            matrix_gen = DeploymentMatrix(temp_dir)
            
            # Create test profiles with shared AS
            profiles = [
                RouterProfile(
                    hostname="router-01",
                    ip_address="10.0.0.1",
                    discovered_as_numbers={65001, 65002},
                    bgp_groups={"external": [65001, 65002]},
                    site="nyc",
                    role="edge"
                ),
                RouterProfile(
                    hostname="router-02",
                    ip_address="10.0.0.2",
                    discovered_as_numbers={65002, 65003},  # 65002 is shared
                    bgp_groups={"external": [65002, 65003]},
                    site="sjc",
                    role="core"
                ),
                RouterProfile(
                    hostname="router-03",
                    ip_address="10.0.0.3",
                    discovered_as_numbers=set(),  # Router with no AS
                    bgp_groups={},
                    site="lon",
                    role="backup"
                )
            ]
            
            # Generate matrix
            matrix = matrix_gen.generate_router_as_matrix(profiles)
            
            # Verify structure
            assert "_metadata" in matrix
            assert "routers" in matrix
            assert "as_numbers" in matrix
            assert "statistics" in matrix
            
            logger.info(f"✓ Generated matrix for {len(profiles)} routers")
            
            # Verify statistics
            stats = matrix["statistics"]
            assert stats["total_routers"] == 3
            assert stats["total_as_numbers"] == 3  # 65001, 65002, 65003
            assert len(stats["routers_with_no_as"]) == 1  # router-03
            assert "router-03" in stats["routers_with_no_as"]
            
            logger.info(f"✓ Statistics: {stats['total_routers']} routers, {stats['total_as_numbers']} AS numbers")
            
            # Verify shared AS tracking
            assert 65002 in matrix["as_numbers"]
            assert len(matrix["as_numbers"][65002]["routers"]) == 2
            assert "router-01" in matrix["as_numbers"][65002]["routers"]
            assert "router-02" in matrix["as_numbers"][65002]["routers"]
            
            logger.info("✓ Shared AS numbers tracked correctly")
            
            # Export reports
            reports = matrix_gen.generate_all_reports(profiles)
            
            assert "csv" in reports
            assert "json" in reports
            assert "summary" in reports
            
            for report_type, path in reports.items():
                assert path.exists(), f"{report_type} report not created"
                logger.info(f"✓ Generated {report_type} report: {path.name}")
            
            return True
            
    except Exception as e:
        logger.error(f"✗ Deployment matrix test failed: {e}")
        return False


def test_policy_combiner():
    """Test policy combination functionality"""
    logger.info("=" * 60)
    logger.info("Testing Policy Combiner")
    logger.info("=" * 60)
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            combiner = PolicyCombiner()
            
            # Create test router directory with policies
            router_dir = temp_path / "routers" / "test-router"
            router_dir.mkdir(parents=True)
            
            # Create sample policies with duplicate prefixes
            policy1 = router_dir / "AS65001_policy.txt"
            policy1.write_text("""policy-options {
    prefix-list AS65001 {
        192.168.1.0/24;
        10.0.0.0/8;
    }
}""")
            
            policy2 = router_dir / "AS65002_policy.txt"
            policy2.write_text("""policy-options {
    prefix-list AS65002 {
        172.16.0.0/12;
        192.168.1.0/24;
    }
}""")
            
            # Test Juniper format combination
            result = combiner.combine_policies_for_router(
                router_hostname="test-router",
                policy_files=[policy1, policy2],
                output_dir=temp_path,
                format="juniper"
            )
            
            assert result.success, "Policy combination failed"
            assert result.policies_combined == 2
            
            output_file = Path(result.output_file)
            assert output_file.exists()
            
            content = output_file.read_text()
            
            # Check deduplication
            assert content.count("192.168.1.0/24") == 1, "Duplicate prefix not deduplicated"
            
            logger.info(f"✓ Combined {result.policies_combined} policies")
            logger.info(f"✓ Output file: {output_file.name}")
            logger.info("✓ Prefix deduplication working")
            
            # Test set format
            result_set = combiner.combine_policies_for_router(
                router_hostname="test-router",
                policy_files=[policy1],
                output_dir=temp_path,
                format="set"
            )
            
            assert result_set.success
            set_content = Path(result_set.output_file).read_text()
            assert "set policy-options prefix-list" in set_content
            
            logger.info("✓ Set format generation working")
            
            # Test hierarchical format
            result_hier = combiner.combine_policies_for_router(
                router_hostname="test-router",
                policy_files=[policy1, policy2],
                output_dir=temp_path,
                format="hierarchical"
            )
            
            assert result_hier.success
            hier_content = Path(result_hier.output_file).read_text()
            assert "BGP Policy Configuration" in hier_content
            
            logger.info("✓ Hierarchical format generation working")
            
            return True
            
    except Exception as e:
        logger.error(f"✗ Policy combiner test failed: {e}")
        return False


def test_end_to_end_scenario():
    """Test complete end-to-end router-specific generation scenario"""
    logger.info("=" * 60)
    logger.info("Testing End-to-End Scenario")
    logger.info("=" * 60)
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # Simulate 3 routers with overlapping and unique AS numbers
            profiles = [
                RouterProfile(
                    hostname="edge-nyc-01",
                    ip_address="10.1.1.1",
                    discovered_as_numbers={65001, 65002, 13335},  # Cloudflare shared
                    bgp_groups={"transit": [65001, 65002], "cdn": [13335]},
                    site="nyc",
                    role="edge"
                ),
                RouterProfile(
                    hostname="edge-sjc-01", 
                    ip_address="10.2.1.1",
                    discovered_as_numbers={65003, 65004, 13335, 15169},  # Cloudflare + Google
                    bgp_groups={"transit": [65003, 65004], "cdn": [13335, 15169]},
                    site="sjc",
                    role="edge"
                ),
                RouterProfile(
                    hostname="core-dal-01",
                    ip_address="10.3.1.1",
                    discovered_as_numbers={65001, 65003, 65005},  # Mix of transit
                    bgp_groups={"transit": [65001, 65003, 65005]},
                    site="dal",
                    role="core"
                )
            ]
            
            # Generate deployment matrix
            matrix_gen = DeploymentMatrix(temp_dir)
            matrix = matrix_gen.generate_router_as_matrix(profiles)
            
            # Verify statistics
            stats = matrix["statistics"]
            
            logger.info("Deployment Statistics:")
            logger.info(f"  Total routers: {stats['total_routers']}")
            logger.info(f"  Total AS numbers: {stats['total_as_numbers']}")
            logger.info(f"  Average AS per router: {stats['average_as_per_router']}")
            
            # Verify shared AS numbers
            shared_as = {item["as_number"] for item in stats["shared_as_numbers"]}
            
            assert 13335 in shared_as, "Cloudflare AS not identified as shared"
            assert 65001 in shared_as, "Transit AS 65001 not identified as shared"
            assert 65003 in shared_as, "Transit AS 65003 not identified as shared"
            
            logger.info(f"✓ Identified {len(shared_as)} shared AS numbers: {shared_as}")
            
            # Verify unique AS assignment
            unique_to_nyc = {65002}
            unique_to_sjc = {65004, 15169}
            unique_to_dal = {65005}
            
            nyc_as = set(matrix["routers"]["edge-nyc-01"]["as_numbers"])
            sjc_as = set(matrix["routers"]["edge-sjc-01"]["as_numbers"])
            dal_as = set(matrix["routers"]["core-dal-01"]["as_numbers"])
            
            assert unique_to_nyc.issubset(nyc_as)
            assert unique_to_sjc.issubset(sjc_as)
            assert unique_to_dal.issubset(dal_as)
            
            logger.info("✓ Unique AS numbers correctly assigned to routers")
            
            # Generate all reports
            reports = matrix_gen.generate_all_reports(profiles)
            
            # Verify CSV has correct data
            csv_path = reports["csv"]
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            
            assert len(rows) == 3, "CSV should have 3 router rows"
            
            for row in rows:
                hostname = row["Router"]
                as_count = int(row["AS Count"])
                
                if hostname == "edge-nyc-01":
                    assert as_count == 3
                elif hostname == "edge-sjc-01":
                    assert as_count == 4
                elif hostname == "core-dal-01":
                    assert as_count == 3
            
            logger.info("✓ CSV report contains correct router data")
            
            # Verify relationships
            relationships = matrix["relationships"]
            assert len(relationships) > 0, "No relationships identified"
            
            for rel in relationships:
                if rel["as_number"] == 13335:
                    assert len(rel["routers"]) == 2, "Cloudflare should be on 2 routers"
                    assert "edge-nyc-01" in rel["routers"]
                    assert "edge-sjc-01" in rel["routers"]
            
            logger.info("✓ Router relationships correctly identified")
            
            logger.info("✓ End-to-end scenario completed successfully")
            
            return True
            
    except Exception as e:
        logger.error(f"✗ End-to-end scenario failed: {e}")
        return False


def main():
    """Run all Phase 3 validation tests"""
    logger.info("╔" + "=" * 58 + "╗")
    logger.info("║" + " Phase 3 Validation: Router-Specific Generation ".center(58) + "║")
    logger.info("╚" + "=" * 58 + "╝")
    
    tests = [
        ("Router-Aware Pipeline", test_router_aware_pipeline),
        ("Router Isolation", test_router_isolation),
        ("Deployment Matrix", test_deployment_matrix),
        ("Policy Combiner", test_policy_combiner),
        ("End-to-End Scenario", test_end_to_end_scenario)
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
        logger.info("🎉 Phase 3 Validation COMPLETE - All tests passed!")
        logger.info("✓ Router-aware pipeline functional")
        logger.info("✓ Policy isolation per router verified")
        logger.info("✓ Deployment matrix generation working")
        logger.info("✓ Policy combination operational")
        logger.info("✓ No cross-contamination between routers")
        logger.info("")
        logger.info("Phase 3: Router-Specific Policy Generation is COMPLETE")
        return 0
    else:
        logger.error("❌ Phase 3 Validation FAILED - Some tests did not pass")
        return 1


if __name__ == "__main__":
    sys.exit(main())