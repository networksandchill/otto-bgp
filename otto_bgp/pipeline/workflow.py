#!/usr/bin/env python3
"""
Pipeline Orchestration - Otto BGP Workflow Management

Implements the complete BGP policy generation pipeline combining:
1. SSH data collection from Juniper devices
2. AS number extraction and BGP text processing
3. BGP policy generation using bgpq4
4. In-memory data flow with no intermediate files

This module replaces the manual 3-script workflow:
legacy_scripts/show-peers-juniper.py → AS-info.py → bgpq4_processor.py
"""

import logging
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from ..collectors.juniper_ssh import JuniperSSHCollector, BGPPeerData, DeviceInfo
from ..processors.as_extractor import ASNumberExtractor, ASExtractionResult
from ..generators.bgpq4_wrapper import BGPq4Wrapper, PolicyGenerationResult
from ..utils.config import ConfigManager
from ..utils.logging import setup_logging
from ..models import RouterProfile
from ..discovery import RouterInspector


@dataclass
class PipelineConfig:
    """Pipeline execution configuration"""
    devices_file: str
    output_directory: str = "policies"
    separate_files: bool = False
    skip_ssh: bool = False
    input_file: Optional[str] = None  # For direct file processing
    dev_mode: bool = False  # Use Docker for bgpq4
    router_aware: bool = True  # v0.3.0 router-specific generation
    rpki_enabled: bool = True  # v0.3.2 RPKI validation


@dataclass
class PipelineResult:
    """Complete pipeline execution results"""
    success: bool
    devices_processed: int
    routers_configured: int
    as_numbers_found: int
    policies_generated: int
    execution_time: float
    output_files: List[str]
    router_directories: List[str]
    errors: List[str]


class BGPPolicyPipeline:
    """Complete BGP policy generation pipeline orchestrator"""
    
    def __init__(self, config: PipelineConfig, logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        
        # Initialize pipeline components  
        from ..generators.bgpq4_wrapper import BGPq4Mode
        bgpq4_mode = BGPq4Mode.PODMAN if config.dev_mode else BGPq4Mode.AUTO
        
        # Initialize proxy manager if configured
        proxy_manager = None
        try:
            from ..utils.config import get_config_manager
            config_manager = get_config_manager()
            irr_config = config_manager.get_config()
            
            if irr_config.irr_proxy and irr_config.irr_proxy.enabled:
                self.logger.info("Pipeline: IRR proxy enabled - initializing proxy manager")
                from ..proxy import IRRProxyManager, ProxyConfig
                
                proxy_config = ProxyConfig(
                    enabled=irr_config.irr_proxy.enabled,
                    method=irr_config.irr_proxy.method,
                    jump_host=irr_config.irr_proxy.jump_host,
                    jump_user=irr_config.irr_proxy.jump_user,
                    ssh_key_file=irr_config.irr_proxy.ssh_key_file,
                    known_hosts_file=irr_config.irr_proxy.known_hosts_file,
                    connection_timeout=irr_config.irr_proxy.connection_timeout,
                    tunnels=irr_config.irr_proxy.tunnels
                )
                proxy_manager = IRRProxyManager(proxy_config, self.logger)
        except Exception as e:
            self.logger.warning(f"Pipeline: Failed to initialize proxy manager: {e}")
        
        self.ssh_collector = JuniperSSHCollector()
        self.as_extractor = ASNumberExtractor()
        self.bgp_generator = BGPq4Wrapper(mode=bgpq4_mode, proxy_manager=proxy_manager)
        self.router_inspector = RouterInspector()
        
        # Pipeline state - properly isolated between runs
        self._reset_pipeline_state()
        self._pipeline_used = False  # Track if pipeline has been used

    def _reset_pipeline_state(self):
        """Reset all pipeline state to ensure clean runs"""
        self.start_time = None
        self.bgp_data_collection = []
        self.as_extraction_results = None
        self.policy_results = []
        self.router_profiles = []  # v0.3.0 router awareness
        
    def _ensure_fresh_pipeline(self):
        """Enforce single-use pattern or reset state for reuse"""
        if self._pipeline_used:
            self.logger.warning("Pipeline instance being reused - resetting state to prevent contamination")
            self._reset_pipeline_state()
        self._pipeline_used = True
        
    def run_complete_pipeline(self) -> PipelineResult:
        """Execute the complete BGP policy generation pipeline (v0.3.0 router-aware)"""
        self._ensure_fresh_pipeline()  # Ensure clean state for this run
        if self.config.router_aware:
            return self.run_router_aware_pipeline()
        else:
            return self._run_legacy_pipeline()
    
    def _run_legacy_pipeline(self) -> PipelineResult:
        """
        Execute the complete BGP policy generation pipeline
        
        Workflow:
        1. Device discovery and SSH data collection
        2. BGP text processing and AS extraction
        3. BGP policy generation
        4. Output file management
        
        Returns:
            PipelineResult with execution summary
        """
        self.start_time = time.time()
        errors = []
        
        try:
            self.logger.info("Starting BGP policy generation pipeline")
            
            # Phase 1: Data Collection
            if not self.config.skip_ssh:
                self.logger.info("Phase 1: Collecting BGP data from devices")
                bgp_text = self._collect_bgp_data()
                if not bgp_text:
                    errors.append("No BGP data collected from devices")
                    return self._create_error_result(errors)
            else:
                # Direct file processing mode
                self.logger.info("Phase 1: Reading BGP data from file")
                bgp_text = self._read_input_file()
                if not bgp_text:
                    errors.append(f"Failed to read input file: {self.config.input_file}")
                    return self._create_error_result(errors)
            
            # Phase 2: AS Extraction
            self.logger.info("Phase 2: Extracting AS numbers and processing BGP text")
            as_numbers = self._extract_as_numbers(bgp_text)
            if not as_numbers:
                errors.append("No valid AS numbers extracted from BGP data")
                return self._create_error_result(errors)
            
            # Phase 3: Policy Generation
            self.logger.info(f"Phase 3: Generating BGP policies for {len(as_numbers)} AS numbers")
            success_count = self._generate_policies(as_numbers)
            
            # Phase 4: Output Management
            self.logger.info("Phase 4: Managing output files")
            output_files = self._manage_output_files()
            
            execution_time = time.time() - self.start_time
            
            result = PipelineResult(
                success=True,
                devices_processed=len(self.bgp_data_collection),
                routers_configured=0,  # Not tracked in legacy mode
                as_numbers_found=len(as_numbers),
                policies_generated=success_count,
                execution_time=execution_time,
                output_files=output_files,
                router_directories=[],  # Not used in legacy mode
                errors=errors
            )
            
            self.logger.info(f"Pipeline completed successfully in {execution_time:.2f}s")
            return result
            
        except Exception as e:
            errors.append(f"Pipeline execution failed: {str(e)}")
            self.logger.error(f"Pipeline execution failed: {str(e)}", exc_info=True)
            return self._create_error_result(errors)
    
    def _collect_bgp_data(self) -> str:
        """
        Collect BGP data from Juniper devices via SSH
        
        Returns:
            Combined BGP configuration text
        """
        devices = self._load_devices()
        if not devices:
            raise ValueError(f"No devices found in {self.config.devices_file}")
        
        self.logger.info(f"Collecting BGP data from {len(devices)} devices")
        
        # Collect data from all devices
        bgp_data_results = self.ssh_collector.collect_from_devices(devices)
        self.bgp_data_collection = bgp_data_results
        
        # Combine all BGP configurations
        combined_bgp_text = ""
        successful_collections = 0
        
        for result in bgp_data_results:
            if result.success:
                combined_bgp_text += f"\n# Device: {result.device.address}\n"
                combined_bgp_text += result.bgp_config + "\n"
                successful_collections += 1
            else:
                self.logger.warning(f"Failed to collect from {result.device.address}: {result.error_message}")
        
        self.logger.info(f"Successfully collected BGP data from {successful_collections}/{len(devices)} devices")
        
        if not combined_bgp_text.strip():
            raise ValueError("No BGP data collected from any devices")
        
        return combined_bgp_text
    
    def _read_input_file(self) -> str:
        """Read BGP data from input file for direct processing"""
        if not self.config.input_file:
            raise ValueError("Input file not specified for direct processing mode")
        
        input_path = Path(self.config.input_file)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        self.logger.info(f"Reading BGP data from {input_path}")
        return input_path.read_text()
    
    def _extract_as_numbers(self, bgp_text: str) -> List[int]:
        """
        Extract and process AS numbers from BGP text
        
        Args:
            bgp_text: Raw BGP configuration text
            
        Returns:
            List of unique AS numbers
        """
        # Create temporary file for AS extraction
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
            temp_file.write(bgp_text)
            temp_file.flush()
            
            # Extract AS numbers
            self.as_extraction_results = self.as_extractor.extract_as_numbers_from_file(temp_file.name)
        
        # Clean up temp file
        import os
        os.unlink(temp_file.name)
        
        if not self.as_extraction_results.as_numbers:
            raise ValueError("No AS numbers found in BGP data")
        
        as_list = list(self.as_extraction_results.as_numbers)
        self.logger.info(f"Extracted {len(as_list)} unique AS numbers")
        self.logger.debug(f"AS numbers: {sorted(as_list)}")
        
        return as_list
    
    def _generate_policies(self, as_numbers: List[int]) -> int:
        """
        Generate BGP policies for all AS numbers
        
        Args:
            as_numbers: List of AS numbers to generate policies for
            
        Returns:
            Number of successfully generated policies
        """
        self.logger.info(f"Generating policies for {len(as_numbers)} AS numbers")
        
        # Generate policies using bgpq4
        results = self.bgp_generator.generate_policies_batch(as_numbers)
        self.policy_results = results
        
        # Count successful generations
        success_count = sum(1 for result in results if result.success)
        failure_count = len(results) - success_count
        
        if failure_count > 0:
            self.logger.warning(f"Failed to generate {failure_count} policies")
            for result in results:
                if not result.success:
                    self.logger.error(f"AS{result.as_number}: {result.error_message}")
        
        self.logger.info(f"Successfully generated {success_count}/{len(as_numbers)} policies")
        return success_count
    
    def _manage_output_files(self) -> List[str]:
        """
        Manage policy output files based on configuration
        
        Returns:
            List of created output files
        """
        output_dir = Path(self.config.output_directory)
        output_dir.mkdir(exist_ok=True)
        
        output_files = []
        
        if self.config.separate_files:
            # Create separate file for each AS
            for result in self.policy_results:
                if result.success:
                    filename = f"AS{result.as_number}_policy.txt"
                    output_path = output_dir / filename
                    output_path.write_text(result.policy_config)
                    output_files.append(str(output_path))
                    self.logger.debug(f"Created policy file: {output_path}")
        else:
            # Create combined output file
            combined_filename = "combined_bgp_policies.txt"
            output_path = output_dir / combined_filename
            
            combined_content = ""
            for result in self.policy_results:
                if result.success:
                    combined_content += f"\n# AS{result.as_number}\n"
                    combined_content += result.policy_config + "\n"
            
            output_path.write_text(combined_content)
            output_files.append(str(output_path))
            self.logger.info(f"Created combined policy file: {output_path}")
        
        return output_files
    
    def _load_devices(self) -> List[DeviceInfo]:
        """Load device information from CSV file"""
        devices_path = Path(self.config.devices_file)
        if not devices_path.exists():
            raise FileNotFoundError(f"Devices file not found: {devices_path}")
        
        devices = []
        try:
            import pandas as pd
            df = pd.read_csv(devices_path)
            
            # Handle different CSV formats
            if 'address' in df.columns:
                address_col = 'address'
            elif 'ip' in df.columns:
                address_col = 'ip'
            elif 'host' in df.columns:
                address_col = 'host'
            else:
                # Assume first column is address
                address_col = df.columns[0]
            
            for _, row in df.iterrows():
                device = DeviceInfo(address=str(row[address_col]))
                devices.append(device)
            
            self.logger.info(f"Loaded {len(devices)} devices from {devices_path}")
            return devices
            
        except Exception as e:
            raise ValueError(f"Failed to load devices from {devices_path}: {str(e)}")
    
    def _create_error_result(self, errors: List[str]) -> PipelineResult:
        """Create a failed pipeline result"""
        execution_time = time.time() - self.start_time if self.start_time else 0
        
        return PipelineResult(
            success=False,
            devices_processed=len(self.bgp_data_collection),
            routers_configured=0,
            as_numbers_found=0,
            policies_generated=0,
            execution_time=execution_time,
            output_files=[],
            router_directories=[],
            errors=errors
        )


    def run_router_aware_pipeline(self) -> PipelineResult:
        """
        Execute the v0.3.0 router-aware BGP policy generation pipeline
        
        Workflow:
        1. Load router profiles from devices CSV
        2. Discover BGP configurations per router
        3. Generate router-specific policies
        4. Create per-router output directories
        
        Returns:
            PipelineResult with router-aware execution summary
        """
        self.start_time = time.time()
        errors = []
        router_directories = []
        total_policies = 0
        
        try:
            self.logger.info("Starting router-aware BGP policy generation pipeline (v0.3.0)")
            
            # Phase 1: Load Router Profiles
            self.logger.info("Phase 1: Loading router profiles")
            self.router_profiles = self._load_router_profiles()
            if not self.router_profiles:
                errors.append("No router profiles loaded")
                return self._create_error_result(errors)
            
            # Phase 2: Discovery & BGP Collection per router
            self.logger.info(f"Phase 2: Discovering BGP configurations for {len(self.router_profiles)} routers")
            all_as_numbers = set()
            
            for profile in self.router_profiles:
                self.logger.info(f"Processing router: {profile.hostname}")
                
                # Collect BGP configuration if not in skip_ssh mode
                if not self.config.skip_ssh:
                    try:
                        bgp_config = self.ssh_collector.collect_bgp_config(profile.ip_address)
                        profile.bgp_config = bgp_config
                    except Exception as e:
                        self.logger.error(f"Failed to collect BGP config from {profile.hostname}: {e}")
                        errors.append(f"{profile.hostname}: Collection failed")
                        continue
                
                # Discover AS numbers from BGP config
                if profile.bgp_config:
                    discovery_result = self.router_inspector.inspect_router(profile)
                    if discovery_result.total_as_numbers > 0:
                        all_as_numbers.update(profile.discovered_as_numbers)
                        self.logger.info(f"  Discovered {discovery_result.total_as_numbers} AS numbers for {profile.hostname}")
                    else:
                        self.logger.warning(f"  No AS numbers discovered for {profile.hostname}")
            
            # Phase 3: Generate Policies per Router
            self.logger.info(f"Phase 3: Generating router-specific policies")
            
            for profile in self.router_profiles:
                if not profile.discovered_as_numbers:
                    self.logger.warning(f"Skipping {profile.hostname} - no AS numbers discovered")
                    continue
                
                # Create router-specific output directory
                router_dir = self._create_router_directory(profile)
                router_directories.append(str(router_dir))
                
                # RPKI validation if enabled
                if self.config.rpki_enabled and profile.discovered_as_numbers:
                    self.logger.info(f"Performing RPKI validation for {profile.hostname}")
                    try:
                        from ..validators.rpki import RPKIValidator
                        from ..utils.config import get_config_manager
                        
                        config_mgr = get_config_manager()
                        rpki_config = config_mgr.get_config().rpki
                        
                        if rpki_config and rpki_config.enabled:
                            rpki_validator = RPKIValidator(
                                vrp_cache_path=rpki_config.vrp_cache_path,
                                allowlist_path=rpki_config.allowlist_path,
                                fail_closed=rpki_config.fail_closed,
                                max_vrp_age_hours=rpki_config.max_vrp_age_hours
                            )
                            
                            # Validate all AS numbers for this router
                            as_list = list(profile.discovered_as_numbers)
                            rpki_results = {}
                            for as_number in as_list:
                                result = rpki_validator.validate_as_number(as_number)
                                rpki_results[as_number] = result
                                if result.status == "invalid":
                                    self.logger.warning(f"  AS{as_number}: RPKI validation failed - {result.details}")
                                elif result.status == "valid":
                                    self.logger.debug(f"  AS{as_number}: RPKI validation passed")
                            
                            # Store RPKI results in profile for metadata
                            profile.rpki_validation_results = rpki_results
                    except ImportError:
                        self.logger.warning("RPKI validation requested but RPKIValidator not available")
                    except Exception as e:
                        self.logger.error(f"RPKI validation failed for {profile.hostname}: {e}")
                
                # Generate policies for this router's AS numbers
                self.logger.info(f"Generating policies for {profile.hostname}: {len(profile.discovered_as_numbers)} AS numbers")
                success_count = self._generate_router_policies(profile, router_dir)
                total_policies += success_count
                
                # Create metadata file for this router
                self._create_router_metadata(profile, router_dir, success_count)
            
            # Phase 4: Generate Reports
            self.logger.info("Phase 4: Generating deployment reports")
            self._generate_deployment_reports()
            
            execution_time = time.time() - self.start_time
            
            result = PipelineResult(
                success=True,
                devices_processed=len(self.router_profiles),
                routers_configured=len([p for p in self.router_profiles if p.discovered_as_numbers]),
                as_numbers_found=len(all_as_numbers),
                policies_generated=total_policies,
                execution_time=execution_time,
                output_files=self._list_output_files(),
                router_directories=router_directories,
                errors=errors
            )
            
            self.logger.info(f"Router-aware pipeline completed in {execution_time:.2f}s")
            self.logger.info(f"  Routers configured: {result.routers_configured}")
            self.logger.info(f"  Total AS numbers: {result.as_numbers_found}")
            self.logger.info(f"  Policies generated: {result.policies_generated}")
            
            return result
            
        except Exception as e:
            errors.append(f"Router-aware pipeline failed: {str(e)}")
            self.logger.error(f"Router-aware pipeline failed: {str(e)}", exc_info=True)
            return self._create_error_result(errors)
    
    def _load_router_profiles(self) -> List[RouterProfile]:
        """Load router profiles from devices CSV (v0.3.0 format)"""
        devices = self.ssh_collector.load_devices_from_csv(self.config.devices_file)
        profiles = []
        
        for device in devices:
            profile = RouterProfile(
                hostname=device.hostname,
                ip_address=device.address,
                bgp_config=""
            )
            profiles.append(profile)
            
        self.logger.info(f"Loaded {len(profiles)} router profiles")
        return profiles
    
    def _create_router_directory(self, profile: RouterProfile) -> Path:
        """Create output directory for a specific router"""
        base_dir = Path(self.config.output_directory)
        router_dir = base_dir / "routers" / profile.hostname
        router_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.debug(f"Created router directory: {router_dir}")
        return router_dir
    
    def _generate_router_policies(self, profile: RouterProfile, output_dir: Path) -> int:
        """Generate policies for a specific router's AS numbers"""
        if not profile.discovered_as_numbers:
            return 0
        
        as_list = sorted(list(profile.discovered_as_numbers))
        success_count = 0
        
        for as_number in as_list:
            try:
                result = self.bgp_generator.generate_policy(as_number)
                if result.success:
                    # Save policy to router's directory
                    policy_file = output_dir / f"AS{as_number}_policy.txt"
                    policy_file.write_text(result.policy_config)
                    success_count += 1
                    self.logger.debug(f"  Generated policy for AS{as_number}")
                else:
                    self.logger.error(f"  Failed to generate policy for AS{as_number}: {result.error_message}")
            except Exception as e:
                self.logger.error(f"  Error generating policy for AS{as_number}: {e}")
        
        return success_count
    
    def _create_router_metadata(self, profile: RouterProfile, output_dir: Path, policies_generated: int):
        """Create metadata.json for a router"""
        import json
        from datetime import datetime
        
        metadata = {
            "router": {
                "hostname": profile.hostname,
                "ip_address": profile.ip_address,
                "site": profile.site or "unknown",
                "role": profile.role or "unknown"
            },
            "discovery": {
                "timestamp": datetime.now().isoformat(),
                "as_numbers_discovered": len(profile.discovered_as_numbers) if profile.discovered_as_numbers else 0,
                "as_numbers": sorted(list(profile.discovered_as_numbers)) if profile.discovered_as_numbers else [],
                "bgp_groups": profile.bgp_groups or {},
                "policies_generated": policies_generated
            },
            "version": "0.3.2"
        }
        
        metadata_file = output_dir / "metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        self.logger.debug(f"Created metadata for {profile.hostname}")
    
    def _generate_deployment_reports(self):
        """Generate deployment matrix and summary reports"""
        from ..reports import generate_deployment_matrix
        from ..generators.combiner import PolicyCombiner
        
        reports_dir = Path(self.config.output_directory) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate deployment matrix
        report_files = generate_deployment_matrix(self.router_profiles, str(reports_dir))
        self.logger.info(f"Generated deployment reports: {', '.join(report_files.keys())}")
        
        # Combine policies per router if requested
        if self.config.separate_files:
            combiner = PolicyCombiner(self.logger)
            router_dirs = [Path(self.config.output_directory) / "routers" / p.hostname 
                          for p in self.router_profiles if p.discovered_as_numbers]
            
            combined_results = combiner.merge_policy_directories(
                router_dirs=router_dirs,
                output_dir=Path(self.config.output_directory) / "combined",
                format="juniper"
            )
            
            success_count = sum(1 for r in combined_results if r.success)
            self.logger.info(f"Combined policies for {success_count} routers")
    
    def _list_output_files(self) -> List[str]:
        """List all generated output files"""
        output_files = []
        base_dir = Path(self.config.output_directory)
        
        if base_dir.exists():
            for file_path in base_dir.rglob("*.txt"):
                output_files.append(str(file_path))
            for file_path in base_dir.rglob("*.json"):
                output_files.append(str(file_path))
        
        return output_files


def run_pipeline(devices_file: str, 
                output_dir: str = "output",
                separate_files: bool = False,
                input_file: Optional[str] = None,
                dev_mode: bool = False,
                rpki_enabled: bool = True) -> PipelineResult:
    """
    Convenience function to run the complete BGP policy pipeline
    
    Args:
        devices_file: CSV file with device information
        output_dir: Directory for output files
        separate_files: Create separate files per AS
        input_file: Direct file input (skips SSH collection)
        dev_mode: Use Docker for bgpq4
        rpki_enabled: Enable RPKI validation during policy generation (default: True)
        
    Returns:
        Pipeline execution results
    """
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Create pipeline configuration
    config = PipelineConfig(
        devices_file=devices_file,
        output_directory=output_dir,
        separate_files=separate_files,
        skip_ssh=bool(input_file),
        input_file=input_file,
        dev_mode=dev_mode,
        rpki_enabled=rpki_enabled
    )
    
    # Execute pipeline
    pipeline = BGPPolicyPipeline(config, logger)
    result = pipeline.run_complete_pipeline()
    
    # Log summary
    if result.success:
        logger.info(f"Pipeline completed: {result.policies_generated} policies generated in {result.execution_time:.2f}s")
    else:
        logger.error(f"Pipeline failed: {', '.join(result.errors)}")
    
    return result