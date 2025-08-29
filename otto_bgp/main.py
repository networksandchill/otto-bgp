#!/usr/bin/env python3
"""
Otto BGP - Orchestrated Transit Traffic Optimizer

Usage examples:
otto-bgp pipeline devices.csv --output-dir ./policies    
"""

import argparse
import sys
import os
import subprocess
import atexit
import signal
from pathlib import Path
from typing import Optional, List, Dict

# Import our modules
from otto_bgp.collectors.juniper_ssh import JuniperSSHCollector
from otto_bgp.processors.as_extractor import ASNumberExtractor, BGPTextProcessor
from otto_bgp.generators.bgpq4_wrapper import BGPq4Wrapper
from otto_bgp.pipeline.workflow import run_pipeline
from otto_bgp.utils.logging import setup_logging, log_system_info
from otto_bgp.utils.config import get_config_manager
from otto_bgp.models import RouterProfile, DeviceInfo
from otto_bgp.discovery import RouterInspector, YAMLGenerator
from otto_bgp.utils.directories import DirectoryManager
from otto_bgp.appliers import JuniperPolicyApplier, PolicyAdapter, UnifiedSafetyManager, create_safety_manager
from otto_bgp.appliers.exit_codes import OttoExitCodes
from otto_bgp.validators.rpki import RPKIValidator
from otto_bgp.utils.error_handling import (
    handle_errors, ErrorFormatter, ParameterValidator, validate_common_args,
    print_success, print_warning, print_error, print_fatal, print_usage,
    OttoError, ValidationError, ConfigurationError
)
from otto_bgp.utils.error_handling import ConnectionError as OttoConnectionError

# Global resource tracking for emergency cleanup
_active_connections = set()
_active_locks = set()
_temp_files = set()

# Removed unused resource registration functions

def emergency_cleanup():
    """Emergency cleanup handler for atexit and signal handling"""
    from otto_bgp.utils.logging import get_logger
    logger = get_logger('otto-bgp.cleanup')
    
    # Close active connections
    for connection in list(_active_connections):
        try:
            if hasattr(connection, 'close'):
                connection.close()
            elif hasattr(connection, 'disconnect'):
                connection.disconnect()
        except Exception:
            pass  # Silent cleanup - don't interfere with exit
    
    # Release locks
    for lock_path in list(_active_locks):
        try:
            if os.path.exists(lock_path):
                os.unlink(lock_path)
        except Exception:
            pass  # Silent cleanup
    
    # Clean up temporary files
    for temp_file in list(_temp_files):
        try:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
        except Exception:
            pass  # Silent cleanup

def signal_handler(signum, frame):
    """Handle signals with proper cleanup"""
    emergency_cleanup()
    sys.exit(128 + signum)  # Standard Unix exit code for signals

# Register cleanup handlers
atexit.register(emergency_cleanup)
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def setup_app_logging(verbose: bool = False, quiet: bool = False):
    """Configure logging for the application"""
    if quiet:
        level = 'WARNING'
    elif verbose:
        level = 'DEBUG'
    else:
        level = 'INFO'
    
    # Use our centralized logging setup
    from otto_bgp.utils.logging import setup_logging as setup_toolkit_logging
    setup_toolkit_logging(level=level, console_colors=True)
    
    # Log system information
    if not quiet:
        log_system_info()


@handle_errors('otto-bgp.collect')
def cmd_collect(args):
    """BGP data collection from Juniper devices"""
    from otto_bgp.utils.logging import get_logger
    logger = get_logger('otto-bgp.collect')
    
    # Initialize SSH collector
    collector = JuniperSSHCollector(
        connection_timeout=args.timeout,
        command_timeout=args.command_timeout
    )
    
    # Collect BGP data from devices
    logger.info(f"Starting BGP data collection from {args.devices_csv}")
    bgp_data = collector.collect_bgp_data_from_csv(args.devices_csv)
    
    # Write output files
    if args.output_dir:
        output_files = collector.write_outputs(bgp_data, args.output_dir)
    else:
        output_files = collector.write_outputs(bgp_data)
    
    # Report results
    successful = sum(1 for data in bgp_data if data.success)
    total = len(bgp_data)
    
    print_success("BGP data collection complete:")
    print(f"  Devices processed: {total}")
    print(f"  Successful: {successful}")
    print(f"  Failed: {total - successful}")
    print(f"  Output files: {', '.join(output_files)}")
    
    return 0 if successful > 0 else 1


@handle_errors('otto-bgp.process')
def cmd_process(args):
    """AS number extraction and BGP text processing"""
    from otto_bgp.utils.logging import get_logger
    logger = get_logger('otto-bgp.process')
    
    # Initialize processor
    processor = ASNumberExtractor()
    
    # Process input file
    logger.info(f"Processing BGP file: {args.input_file}")
    
    if args.extract_as:
        # AS number extraction mode
        as_result = processor.extract_as_numbers_from_file(args.input_file)
        
        as_list = sorted(as_result.as_numbers)
        
        # Write AS numbers to output file
        if args.output:
            output_path = Path(args.output)
            with open(output_path, 'w') as f:
                for as_num in as_list:
                    f.write(f"AS{as_num}\n")
            
            print_success("AS extraction complete:")
            print(f"  AS numbers found: {len(as_list)}")
            print(f"  Output file: {output_path}")
        else:
            print_success(f"AS numbers found ({len(as_list)}):")
            for as_num in as_list:
                print(f"  AS{as_num}")
        
    else:
        # Text processing mode (clean and deduplicate)
        bgp_processor = BGPTextProcessor()
        result = bgp_processor.process_file(args.input_file, args.output)
        
        print_success("BGP text processing complete:")
        print(f"  Original lines: {result.original_lines}")
        print(f"  Processed lines: {result.processed_lines}")
        print(f"  Duplicates removed: {result.duplicates_removed}")
        if args.output:
            print(f"  Output file: {args.output}")
    
    return 0


@handle_errors('otto-bgp.policy')
def cmd_policy(args):
    """BGP policy generation using bgpq4"""
    from otto_bgp.utils.logging import get_logger
    logger = get_logger('otto-bgp.policy')
    
    # Initialize bgpq4 wrapper with proxy support
    from otto_bgp.generators.bgpq4_wrapper import BGPq4Mode
    mode = BGPq4Mode.PODMAN if getattr(args, 'dev', False) else BGPq4Mode.AUTO
    
    # Check for proxy configuration
    proxy_manager = None
    try:
        config_manager = get_config_manager()
        config = config_manager.get_config()
        
        if config.irr_proxy and config.irr_proxy.enabled:
            logger.info("IRR proxy enabled - initializing proxy manager")
            from otto_bgp.proxy import IRRProxyManager, ProxyConfig
            
            proxy_config = ProxyConfig(
                enabled=config.irr_proxy.enabled,
                method=config.irr_proxy.method,
                jump_host=config.irr_proxy.jump_host,
                jump_user=config.irr_proxy.jump_user,
                ssh_key_file=config.irr_proxy.ssh_key_file,
                known_hosts_file=config.irr_proxy.known_hosts_file,
                connection_timeout=config.irr_proxy.connection_timeout,
                tunnels=config.irr_proxy.tunnels
            )
            proxy_manager = IRRProxyManager(proxy_config, logger)
            try:
                proxy_manager.establish_all_tunnels()
            except Exception as e:
                logger.warning(f"Failed to establish proxy tunnels: {e}")
    except Exception as e:
        logger.warning(f"Failed to initialize proxy manager: {e}")
    
    bgpq4 = BGPq4Wrapper(
        mode=mode,
        command_timeout=getattr(args, 'timeout', 30),
        proxy_manager=proxy_manager
    )
    
    # Test connection if requested  
    if getattr(args, 'test', False):
        test_as = getattr(args, 'test_as', 7922)
        # Validate test AS number
        validator = ParameterValidator()
        test_as = validator.validate_as_number(test_as, "test_as")
        
        success = bgpq4.test_bgpq4_connection(test_as)
        if success:
            print_success(f"bgpq4 connectivity test: PASSED")
        else:
            print_error(f"bgpq4 connectivity test: FAILED", 
                       "Check network connectivity and bgpq4 installation")
        return 0 if success else 1
    
    # Extract AS numbers from input file
    logger.info(f"Extracting AS numbers from {args.input_file}")
    as_extractor = ASNumberExtractor()
    as_result = as_extractor.extract_as_numbers_from_file(args.input_file)
    
    if not as_result.as_numbers:
        print_error("No AS numbers found in input file",
                   "Check that the input file contains valid AS numbers (e.g., AS12345 or 12345)")
        return 1
    
    as_list = sorted(as_result.as_numbers)
    print(f"Found {len(as_list)} AS numbers: {as_list}")
    
    # RPKI validation for extracted AS numbers (unless explicitly disabled)
    rpki_status = {}
    if not getattr(args, 'no_rpki', False):
        try:
            from otto_bgp.validators.rpki import RPKIValidator
            from otto_bgp.utils.config import get_config_manager
            
            config = get_config_manager().get_config()
            if config.rpki and config.rpki.enabled:
                logger.info("Performing RPKI validation on extracted AS numbers")
                rpki_validator = RPKIValidator(
                    vrp_cache_path=Path(config.rpki.vrp_cache_path),
                    allowlist_path=Path(config.rpki.allowlist_path),
                    fail_closed=config.rpki.fail_closed,
                    max_vrp_age_hours=config.rpki.max_vrp_age_hours,
                    logger=logger
                )
                
                # Validate each AS
                for as_number in as_list:
                    result = rpki_validator.check_as_validity(as_number)
                    rpki_status[as_number] = result
                    
                    # Warn about problematic AS numbers
                    if result['state'].value == 'invalid':
                        print_warning(f"AS{as_number}: RPKI INVALID - {result['message']}")
                    elif result['state'].value == 'notfound':
                        logger.info(f"AS{as_number}: No ROAs found in RPKI")
                    elif result['state'].value == 'error':
                        print_warning(f"AS{as_number}: RPKI check failed - {result['message']}")
            else:
                logger.info("RPKI validation disabled in configuration")
        except Exception as e:
            logger.warning(f"RPKI validation failed: {e} - continuing without validation")
    
    # Generate policies
    try:
        logger.info(f"Generating policies for {len(as_list)} AS numbers")
        batch_result = bgpq4.generate_policies_batch(
            as_list,
            rpki_status=rpki_status
        )
        
        # Write output files
        output_dir = args.output_dir or "policies"
        created_files = bgpq4.write_policies_to_files(
            batch_result,
            output_dir=output_dir,
            separate_files=args.separate,
            combined_filename=args.output or "bgpq4_output.txt",
            rpki_status=rpki_status
        )
        
        # Report results
        print_success("Policy generation complete:")
        print(f"  AS numbers processed: {batch_result.total_as_count}")
        print(f"  Successful: {batch_result.successful_count}")
        print(f"  Failed: {batch_result.failed_count}")
        print(f"  Execution time: {batch_result.total_execution_time:.2f}s")
        print(f"  Output files: {len(created_files)} files in {output_dir}/")
        
        if batch_result.failed_count > 0:
            print_warning("Some AS numbers failed to generate policies:")
            for result in batch_result.results:
                if not result.success:
                    print(f"  AS{result.as_number}: {result.error_message}")
        
        return 0 if batch_result.successful_count > 0 else 1
    finally:
        try:
            if proxy_manager:
                proxy_manager.cleanup_all_tunnels()
        except Exception as e:
            logger.warning(f"Failed to cleanup proxy tunnels: {e}")


def cmd_discover(args):
    """Discover BGP configurations and generate mappings"""
    from otto_bgp.utils.logging import get_logger
    logger = get_logger('otto-bgp.discover')
    
    try:
        from otto_bgp.collectors.juniper_ssh import JuniperSSHCollector
        from otto_bgp.discovery import RouterInspector, YAMLGenerator
        from pathlib import Path
        
        # Initialize components
        collector = JuniperSSHCollector()
        inspector = RouterInspector()
        yaml_gen = YAMLGenerator(output_dir=Path(args.output_dir) / "discovered")
        
        # Load devices from CSV
        devices = collector.load_devices_from_csv(args.devices_csv)
        if not devices:
            print_error("No devices found in CSV file", f"Check {args.devices_csv}")
            return 1
        
        logger.info(f"Discovering BGP configurations for {len(devices)} devices")
        profiles = []
        
        # Use parallel discovery for efficiency
        from otto_bgp.utils.parallel import parallel_discover_routers
        profiles, discovery_results = parallel_discover_routers(devices, collector, inspector)
        
        if not profiles:
            print_error("No profiles discovered", "Check device connectivity and credentials")
            return 1
        
        # Generate and save mappings
        mappings = yaml_gen.generate_mappings(profiles)
        yaml_gen.save_with_history(mappings)
        
        # Show diff if requested
        if getattr(args, 'show_diff', False):
            diff_content = yaml_gen.generate_diff_report()
            if diff_content:
                print("\nChanges detected:")
                print(diff_content)
            else:
                print("\nNo changes detected since last discovery")
        
        # Summary
        total_as_numbers = sum(len(profile.discovered_as_numbers) for profile in profiles)
        print_success("Discovery completed:")
        print(f"  Routers discovered: {len(profiles)}")
        print(f"  Total AS numbers: {total_as_numbers}")
        print(f"  Output directory: {yaml_gen.output_dir}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Discovery command failed: {e}")
        print_error("Discovery command failed", str(e))
        return 1


def cmd_list(args):
    """List discovered routers, AS numbers, or BGP groups"""
    from otto_bgp.utils.logging import get_logger
    logger = get_logger('otto-bgp.list')
    
    try:
        yaml_gen = YAMLGenerator(output_dir=Path(args.output_dir) / "discovered")
        
        # Load existing mappings
        mappings = yaml_gen.load_previous_mappings()
        if not mappings:
            print("No discovered data found. Run 'otto-bgp discover' first.")
            return 1
        
        if args.list_type == "routers":
            print("Discovered Routers:")
            print("-" * 50)
            for hostname, data in mappings.get("routers", {}).items():
                as_count = len(data.get("discovered_as_numbers", []))
                group_count = len(data.get("bgp_groups", []))
                print(f"  {hostname:<30} AS: {as_count:3d}  Groups: {group_count:2d}")
        
        elif args.list_type == "as":
            print("Discovered AS Numbers:")
            print("-" * 50)
            as_numbers = mappings.get("as_numbers", {})
            for as_num in sorted(as_numbers.keys(), key=int):
                data = as_numbers[as_num]
                router_count = len(data.get("routers", []))
                groups = ", ".join(data.get("groups", []))
                print(f"  AS{as_num:<10} Routers: {router_count:2d}  Groups: {groups}")
        
        elif args.list_type == "groups":
            print("Discovered BGP Groups:")
            print("-" * 50)
            for group_name, data in mappings.get("bgp_groups", {}).items():
                as_count = len(data.get("as_numbers", []))
                router_count = len(data.get("routers", []))
                print(f"  {group_name:<25} AS: {as_count:3d}  Routers: {router_count:2d}")
        
        return 0
        
    except FileNotFoundError as e:
        logger.error(f"Discovery data not found: {e}")
        print(f"Error: Discovery data not found - run 'otto-bgp discover' first")
        return 1
    except KeyError as e:
        logger.error(f"Invalid discovery data format: {e}")
        print(f"Error: Invalid discovery data format - {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error in list command: {e}")
        print(f"Unexpected error: {e}")
        return 1


def cmd_apply(args):
    """Apply BGP policies to router via NETCONF/PyEZ"""
    from otto_bgp.utils.logging import get_logger
    logger = get_logger('otto-bgp.apply')
    
    # Check for NETCONF credentials from environment if not provided
    import os
    if not args.username:
        args.username = os.environ.get('NETCONF_USERNAME')
    if not args.password:
        args.password = os.environ.get('NETCONF_PASSWORD')
    if not args.ssh_key:
        args.ssh_key = os.environ.get('NETCONF_SSH_KEY')
    
    # Validate credentials
    if not args.username:
        logger.error("NETCONF username not provided")
        print("Error: NETCONF username required")
        print("Provide via --username or set NETCONF_USERNAME environment variable")
        return 1
    
    if not (args.password or args.ssh_key):
        logger.error("NETCONF authentication not provided")
        print("Error: NETCONF authentication required")
        print("Provide via --password, --ssh-key, or environment variables")
        print("  NETCONF_PASSWORD or NETCONF_SSH_KEY")
        return 1
    
    try:
        # Import here to fail gracefully if PyEZ not installed
        from otto_bgp.appliers.juniper_netconf import JuniperPolicyApplier
        from otto_bgp.appliers.adapter import PolicyAdapter
        
        # Initialize components
        safety = create_safety_manager()
        applier = JuniperPolicyApplier(logger, safety_manager=safety)
        adapter = PolicyAdapter(logger)
        
        # Determine policy directory
        policy_dir = Path(args.policy_dir) / "routers" / args.router
        if not policy_dir.exists():
            print(f"Error: No policies found for router {args.router}")
            print(f"  Looking in: {policy_dir}")
            print(f"  Run 'otto-bgp discover' and 'otto-bgp policy' first")
            return 1
        
        # Load policies
        logger.info(f"Loading policies from {policy_dir}")
        policies = applier.load_router_policies(policy_dir)
        
        if not policies:
            print(f"No policies found for router {args.router}")
            return 1
        
        print(f"Loaded {len(policies)} policies for {args.router}")
        
        # Safety validation
        if not args.skip_safety:
            print("\nPerforming safety validation...")
            safety_result = safety.validate_policies_before_apply(policies)
            
            # Display safety report
            if args.verbose or not safety_result.safe_to_proceed:
                print(safety.generate_safety_report(safety_result))
            
            if not safety_result.safe_to_proceed:
                print("\nSafety validation FAILED - cannot proceed with application")
                print("Review the errors above and fix the issues before retrying.")
                return 2
            
            if safety_result.risk_level in ['high', 'critical'] and not args.force:
                print(f"\nRisk level: {safety_result.risk_level.upper()}")
                print("Use --force to proceed despite high risk (NOT RECOMMENDED)")
                return 2
        
        # Check autonomous mode decision
        autonomous_mode = getattr(args, 'autonomous', False)
        if autonomous_mode:
            # Use UnifiedSafetyManager to determine if policies can be auto-applied
            can_auto_apply = safety.should_auto_apply(policies)
            
            if can_auto_apply:
                print("\n✓ Autonomous mode: Policies approved for automatic application")
                print("  Risk level: LOW - proceeding without manual confirmation")
                # Set args.yes to skip user confirmation later
                args.yes = True
            else:
                print("\n⚠ Autonomous mode: Manual approval required")
                print("  Reason: Risk level too high or autonomous mode disabled")
                print("  Falling back to manual confirmation process")
        
        # Connect to router
        print(f"\nConnecting to {args.router}...")
        try:
            # Use SSH key if provided, otherwise password
            connect_params = {
                'hostname': args.router,
                'username': args.username,
                'port': args.port or int(os.environ.get('NETCONF_PORT', 830)),
                'timeout': args.timeout or int(os.environ.get('NETCONF_TIMEOUT', 30))
            }
            
            if args.ssh_key:
                # SSH key authentication (preferred)
                connect_params['ssh_private_key_file'] = args.ssh_key
            else:
                # Password authentication (less secure)
                connect_params['password'] = args.password
            
            device = applier.connect_to_router(**connect_params)
            print(f"Connected to {device.facts.get('hostname', args.router)}")
            print(f"  Model: {device.facts.get('model', 'Unknown')}")
            print(f"  Version: {device.facts.get('version', 'Unknown')}")
        except Exception as e:
            print(f"Failed to connect to {args.router}: {e}")
            return 1
        
        # Preview changes
        print("\nGenerating configuration preview...")
        try:
            diff = applier.preview_changes(policies, format=args.diff_format)
            
            if args.dry_run:
                print("\n" + "=" * 60)
                print("DRY RUN - Configuration Diff Preview")
                print("=" * 60)
                print(diff)
                print("=" * 60)
                print("\nDry run complete - no changes applied")
                applier.disconnect()
                return 0
            
            # Show diff and confirm
            print("\n" + "=" * 60)
            print("Configuration Changes to Apply")
            print("=" * 60)
            print(diff)
            print("=" * 60)
            
            # Check BGP impact
            bgp_impact = safety.check_bgp_session_impact(diff)
            if bgp_impact:
                print("\nPotential BGP Session Impact:")
                for session, impact in bgp_impact.items():
                    print(f"  {session}: {impact}")
            
            if not args.yes:
                response = input("\nProceed with applying these changes? [y/N]: ")
                if response.lower() != 'y':
                    print("Application cancelled by user")
                    applier.disconnect()
                    return 0
            
        except Exception as e:
            print(f"Failed to generate preview: {e}")
            applier.disconnect()
            return 1
        
        # Apply policies with mode-aware finalization
        confirm_timeout = args.confirm_timeout if args.confirm else 120  # Default timeout
        print(f"\nApplying policies using mode-aware finalization...")
        
        result = applier.apply_with_confirmation(
            policies=policies,
            confirm_timeout=confirm_timeout,
            comment=args.comment or f"Otto BGP policy update for {args.router}"
        )
        
        # Report results
        if result.success:
            print(f"\n✓ Successfully applied {result.policies_applied} policies to {args.router}")
            if result.commit_id:
                print(f"  Commit ID: {result.commit_id}")
            print("  Mode-aware finalization completed")
        else:
            print(f"\n✗ Failed to apply policies: {result.error_message}")
            return 1
        
        # Disconnect
        applier.disconnect()
        return 0
        
    except KeyboardInterrupt:
        print("\nInterrupted - rolling back any pending changes...")
        if 'applier' in locals() and applier.connected:
            applier.rollback_changes()
            applier.disconnect()
        return 130
    except Exception as e:
        logger.error(f"Apply command failed: {e}")
        print(f"Error: {e}")
        if 'applier' in locals() and applier.connected:
            applier.disconnect()
        return 1


def cmd_pipeline(args):
    """Unified pipeline for both system and autonomous modes"""
    from otto_bgp.utils.logging import get_logger
    logger = get_logger('otto-bgp.pipeline')
    
    # Mode detection - single point of configuration
    mode = getattr(args, 'mode', 'system')
    if os.getenv('OTTO_BGP_AUTONOMOUS') == 'true':
        mode = 'autonomous'
    
    logger.info(f"Executing Otto BGP pipeline in {mode} mode")
    
    try:
        # Load configuration
        config = get_config_manager().get_config()
        
        # Create RPKI configuration if enabled
        rpki_config = None
        if hasattr(config, 'rpki') and config.rpki.enabled:
            rpki_config = config.rpki
        
        # Single safety manager - no duplicates
        safety_manager = UnifiedSafetyManager()
        
        # Pass RPKI flag to pipeline
        rpki_enabled = not getattr(args, 'no_rpki', False)
        
        # Direct file input handling
        if hasattr(args, 'input_file') and args.input_file:
            # Direct file processing mode
            result = run_pipeline(
                devices_file='',  # Not used in direct mode
                output_dir=getattr(args, 'output_dir', 'output'),
                separate_files=getattr(args, 'separate', False),
                input_file=args.input_file,
                dev_mode=getattr(args, 'dev', False),
                rpki_enabled=rpki_enabled
            )
            
            # Report results
            print(f"\nPipeline execution complete:")
            print(f"  Success: {result.success}")
            print(f"  Execution time: {result.execution_time:.2f}s")
            return 0 if result.success else 1
        
        # Unified pipeline
        if not hasattr(args, 'devices_csv') or not args.devices_csv:
            logger.error("Device CSV file required for unified pipeline")
            print("Error: Device CSV file required")
            return OttoExitCodes.VALIDATION_FAILED
        
        # Load devices with bulletproof validation
        devices = load_device_config(args.devices_csv)
        
        # DEFENSIVE VALIDATION: Bulletproof device list validation
        if devices is None:
            logger.error("Device loading returned None - possible internal error")
            print("Error: Device loading failed internally")
            return OttoExitCodes.VALIDATION_FAILED
            
        if not isinstance(devices, list):
            logger.error(f"Device loading returned unexpected type: {type(devices).__name__}")
            print("Error: Invalid device data structure")
            return OttoExitCodes.VALIDATION_FAILED
            
        if not devices:
            logger.error("No devices loaded from CSV file")
            print("Error: No devices found in CSV file")
            return OttoExitCodes.VALIDATION_FAILED
            
        if len(devices) == 0:  # Double-check for safety
            logger.error("Device list has zero length")
            print("Error: Empty device list")
            return OttoExitCodes.VALIDATION_FAILED
        
        # DEFENSIVE VALIDATION: Validate device objects
        valid_devices = []
        for i, device in enumerate(devices):
            if device is None:
                logger.warning(f"Device at index {i} is None, skipping")
                continue
            if not hasattr(device, 'hostname'):
                logger.warning(f"Device at index {i} missing hostname attribute, skipping")
                continue
            if not hasattr(device, 'address'):
                logger.warning(f"Device at index {i} missing address attribute, skipping")
                continue
            valid_devices.append(device)
            
        if not valid_devices:
            logger.error("No valid devices found after validation")
            print("Error: All devices failed validation")
            return OttoExitCodes.VALIDATION_FAILED
            
        devices = valid_devices  # Use only validated devices
        logger.info(f"Validated {len(devices)} devices for processing")
        
        # Generate policies for all devices
        policies = generate_policies_for_devices(devices)
        
        # DEFENSIVE VALIDATION: Bulletproof policy validation
        if policies is None:
            logger.error("Policy generation returned None")
            print("Error: Policy generation failed internally")
            return OttoExitCodes.VALIDATION_FAILED
            
        if not isinstance(policies, list):
            logger.error(f"Policy generation returned unexpected type: {type(policies).__name__}")
            print("Error: Invalid policy data structure")
            return OttoExitCodes.VALIDATION_FAILED
            
        if not policies:
            logger.error("No policies generated")
            print("Error: No policies generated")
            return OttoExitCodes.VALIDATION_FAILED
        
        logger.info(f"Generated {len(policies)} policies for {len(devices)} devices")
        
        # Execute unified pipeline for each device
        results = []
        failed_count = 0
        
        # DEFENSIVE VALIDATION: Final safety check before iteration
        if not devices or len(devices) == 0:
            logger.error("Device list became invalid before iteration")
            print("Error: Device list corruption detected")
            return OttoExitCodes.VALIDATION_FAILED
        
        for device in devices:
            # DEFENSIVE VALIDATION: Per-device safety checks
            if device is None:
                logger.error("Encountered None device during iteration")
                continue
                
            if not hasattr(device, 'hostname'):
                logger.error(f"Device missing hostname: {device}")
                continue
            # DEFENSIVE VALIDATION: Safe policy lookup
            try:
                device_policies = [p for p in policies if p and p.get('device_hostname') == device.hostname]
            except Exception as e:
                logger.error(f"Error filtering policies for device {device.hostname}: {e}")
                continue
            
            if not device_policies:
                logger.warning(f"No policies for device {device.hostname}")
                continue
            
            # Execute unified pipeline with mode parameter
            result = safety_manager.execute_pipeline(
                policies=device_policies,
                hostname=device.hostname,
                mode=mode
            )
            
            results.append(result)
            
            if not result.success:
                failed_count += 1
                logger.error(f"Pipeline failed for {device.hostname}: exit code {result.exit_code}")
            else:
                logger.info(f"Pipeline completed successfully for {device.hostname}")
        
        # Report unified results
        successful_count = len(results) - failed_count
        print(f"\nUnified pipeline execution complete:")
        print(f"  Mode: {mode}")
        print(f"  Devices processed: {len(devices)}")
        print(f"  Successful: {successful_count}")
        print(f"  Failed: {failed_count}")
        print(f"  Policies generated: {len(policies)}")
        
        # Exit code handling - return instead of sys.exit to allow cleanup
        if failed_count > 0:
            exit_code = results[0].exit_code if results else OttoExitCodes.UNEXPECTED_ERROR
            logger.error(f"Pipeline failed with exit code {exit_code}")
            return exit_code
        
        logger.info("Pipeline completed successfully")
        return OttoExitCodes.SUCCESS
        
    except Exception as e:
        logger.error(f"Unexpected pipeline error: {e}")
        print(f"Unexpected error: {e}")
        return OttoExitCodes.UNEXPECTED_ERROR


def load_device_config(devices_csv: str) -> List[DeviceInfo]:
    """Load device configuration from CSV file with bulletproof validation
    
    Args:
        devices_csv: Path to CSV file containing device information
        
    Returns:
        List[DeviceInfo]: List of validated device objects (never None)
        
    Raises:
        Never raises - returns empty list on any error
    """
    from otto_bgp.utils.logging import get_logger
    logger = get_logger('otto-bgp.pipeline')
    
    # DEFENSIVE VALIDATION: Input parameter validation
    if devices_csv is None:
        logger.error("load_device_config: devices_csv parameter is None")
        return []
        
    if not isinstance(devices_csv, str):
        logger.error(f"load_device_config: devices_csv must be string, got {type(devices_csv).__name__}")
        return []
        
    if not devices_csv.strip():
        logger.error("load_device_config: devices_csv is empty or whitespace-only")
        return []
    
    try:
        # DEFENSIVE VALIDATION: Check file exists and is readable
        import os
        if not os.path.exists(devices_csv):
            logger.error(f"load_device_config: CSV file does not exist: {devices_csv}")
            return []
            
        if not os.path.isfile(devices_csv):
            logger.error(f"load_device_config: Path is not a file: {devices_csv}")
            return []
            
        if not os.access(devices_csv, os.R_OK):
            logger.error(f"load_device_config: CSV file is not readable: {devices_csv}")
            return []
        
        # Use the existing JuniperSSHCollector to load devices
        collector = JuniperSSHCollector()
        devices = collector.load_devices_from_csv(devices_csv)
        
        # DEFENSIVE VALIDATION: Validate return value from collector
        if devices is None:
            logger.error(f"load_device_config: collector returned None for {devices_csv}")
            return []
            
        if not isinstance(devices, list):
            logger.error(f"load_device_config: collector returned non-list: {type(devices).__name__}")
            return []
            
        # Additional validation of individual devices
        valid_devices = []
        for i, device in enumerate(devices):
            if device is None:
                logger.warning(f"load_device_config: Device {i} is None, skipping")
                continue
                
            if not hasattr(device, 'hostname') or not hasattr(device, 'address'):
                logger.warning(f"load_device_config: Device {i} missing required attributes, skipping")
                continue
                
            valid_devices.append(device)
        
        logger.info(f"Loaded {len(valid_devices)} valid devices from {devices_csv}")
        return valid_devices
        
    except Exception as e:
        logger.error(f"Failed to load devices from {devices_csv}: {e}")
        return []  # Always return empty list, never None


def generate_policies_for_devices(devices: List[DeviceInfo]) -> List[Dict]:
    """Generate BGP policies for all devices with bulletproof validation
    
    Args:
        devices: List of DeviceInfo objects to process
        
    Returns:
        List[Dict]: List of policy dictionaries (never None)
        
    Raises:
        Never raises - returns empty list on any error
    """
    from otto_bgp.utils.logging import get_logger
    logger = get_logger('otto-bgp.pipeline')
    
    # DEFENSIVE VALIDATION: Input parameter validation
    if devices is None:
        logger.error("generate_policies_for_devices: devices parameter is None")
        return []
        
    if not isinstance(devices, list):
        logger.error(f"generate_policies_for_devices: devices must be list, got {type(devices).__name__}")
        return []
        
    if not devices:
        logger.info("generate_policies_for_devices: empty device list provided")
        return []
    
    try:
        # Collect BGP data from all devices
        collector = JuniperSSHCollector()
        as_extractor = ASNumberExtractor()
        bgpq4 = BGPq4Wrapper()
        all_policies = []
        
        # Initialize RPKI validator if enabled
        rpki_validator = None
        try:
            from otto_bgp.utils.config import get_config_manager
            config_mgr = get_config_manager()
            config = config_mgr.get_config()
            
            # Use centralized RPKI config function (pass empty args since no CLI override here)
            import argparse
            empty_args = argparse.Namespace()
            rpki_settings = _get_rpki_config(config, empty_args)
            
            if rpki_settings['enabled']:
                from otto_bgp.validators.rpki import RPKIValidator
                rpki_validator = RPKIValidator(
                    vrp_cache_path=Path(rpki_settings['vrp_cache_path']),
                    allowlist_path=Path(rpki_settings['allowlist_path']),
                    fail_closed=rpki_settings['fail_closed'],
                    max_vrp_age_hours=rpki_settings['max_vrp_age_hours'],
                    logger=logger,
                )
                logger.info("RPKI validator initialized for unified pipeline")
        except Exception as e:
            logger.warning(f"RPKI validator initialization failed: {e}")
            rpki_validator = None
        
        # DEFENSIVE VALIDATION: Validate each device before processing
        valid_devices = []
        for i, device in enumerate(devices):
            if device is None:
                logger.warning(f"generate_policies_for_devices: Device {i} is None, skipping")
                continue
                
            if not hasattr(device, 'hostname'):
                logger.warning(f"generate_policies_for_devices: Device {i} missing hostname, skipping")
                continue
                
            if not hasattr(device, 'address'):
                logger.warning(f"generate_policies_for_devices: Device {i} missing address, skipping")
                continue
                
            valid_devices.append(device)
            
        if not valid_devices:
            logger.error("generate_policies_for_devices: No valid devices found")
            return []
            
        logger.info(f"Processing {len(valid_devices)} valid devices for policy generation")
        
        for device in valid_devices:
            # Additional per-device safety check
            if device is None:
                logger.error("generate_policies_for_devices: Device became None during iteration")
                continue
            try:
                # Collect BGP data from individual device
                bgp_data = collector.collect_bgp_data_from_device(device)
                
                if bgp_data.success:
                    # Extract AS numbers from BGP data
                    as_result = as_extractor.extract_as_numbers_from_text(bgp_data.bgp_text)
                    
                    if as_result.as_numbers:
                        # Perform RPKI validation if enabled
                        rpki_status = {}
                        if rpki_validator:
                            logger.debug(f"Performing RPKI validation for {device.hostname}")
                            for as_number in as_result.as_numbers:
                                try:
                                    result = rpki_validator.check_as_validity(as_number)
                                    rpki_status[as_number] = result
                                    logger.debug(f"RPKI validation for AS{as_number}: {result['state']}")
                                except Exception as e:
                                    logger.warning(f"RPKI validation failed for AS{as_number}: {e}")
                                    rpki_status[as_number] = {'state': 'error', 'message': str(e)}
                        
                        # Generate policies in parallel for efficiency
                        from otto_bgp.utils.parallel import parallel_generate_policies
                        policy_results = parallel_generate_policies(list(as_result.as_numbers), bgpq4)
                        
                        # Convert to policy format with device information and RPKI annotations
                        for policy_result in policy_results:
                            if policy_result.success:
                                # Get RPKI result for this AS number
                                rpki_result = rpki_status.get(policy_result.as_number, {})
                                state = rpki_result.get('state', 'unknown')
                                
                                # Add RPKI comment to policy content
                                policy_content = f"# RPKI Status: {state.upper()}\n"
                                if state == 'invalid':
                                    policy_content += f"# WARNING: Origin validation failed\n"
                                elif state == 'valid':
                                    policy_content += f"# INFO: Origin validation passed\n"
                                elif state == 'notfound':
                                    policy_content += f"# INFO: No ROA found for this origin\n"
                                policy_content += policy_result.policy_content
                                
                                policy = {
                                    'device_hostname': device.hostname,
                                    'device_address': device.address,
                                    'as_number': policy_result.as_number,
                                    'policy_name': policy_result.policy_name,
                                    'policy_content': policy_content,
                                    'rpki_status': state
                                }
                                all_policies.append(policy)
                    else:
                        logger.warning(f"No AS numbers found for device {device.hostname}")
                else:
                    logger.error(f"Failed to collect BGP data from {device.hostname}: {bgp_data.error_message}")
            except Exception as e:
                logger.error(f"Error processing device {device.hostname}: {e}")
                continue
        
        # DEFENSIVE VALIDATION: Validate final result
        if all_policies is None:
            logger.error("generate_policies_for_devices: all_policies became None")
            return []
            
        if not isinstance(all_policies, list):
            logger.error(f"generate_policies_for_devices: all_policies is not a list: {type(all_policies).__name__}")
            return []
            
        # Validate individual policies
        valid_policies = []
        for i, policy in enumerate(all_policies):
            if policy is None:
                logger.warning(f"generate_policies_for_devices: Policy {i} is None, skipping")
                continue
                
            if not isinstance(policy, dict):
                logger.warning(f"generate_policies_for_devices: Policy {i} is not a dict, skipping")
                continue
                
            # Check required keys
            required_keys = ['device_hostname', 'device_address', 'as_number', 'policy_name', 'policy_content']
            if all(key in policy for key in required_keys):
                valid_policies.append(policy)
            else:
                logger.warning(f"generate_policies_for_devices: Policy {i} missing required keys")
                
        logger.info(f"Generated {len(valid_policies)} valid policies for {len(valid_devices)} devices")
        return valid_policies
        
    except Exception as e:
        logger.error(f"Failed to generate policies: {e}")
        return []  # Always return empty list, never None


def cmd_test_proxy(args):
    """Test IRR proxy configuration and connectivity"""
    from otto_bgp.utils.logging import get_logger
    logger = get_logger('otto-bgp.test-proxy')
    
    try:
        # Get configuration
        config_manager = get_config_manager()
        proxy_config = config_manager.get_config().irr_proxy
        
        if not proxy_config.enabled:
            print("IRR proxy is not enabled in configuration")
            print("Set OTTO_BGP_PROXY_ENABLED=true or enable in config file")
            return 1
        
        print("IRR Proxy Configuration Test")
        print("=" * 50)
        print(f"Jump Host: {proxy_config.jump_host}")
        print(f"Jump User: {proxy_config.jump_user}")
        print(f"SSH Key: {proxy_config.ssh_key_file or 'Not set'}")
        print(f"Known Hosts: {proxy_config.known_hosts_file or 'Not set'}")
        print(f"Tunnels: {len(proxy_config.tunnels)}")
        print()
        
        # Validate configuration
        issues = config_manager.validate_config()
        proxy_issues = [issue for issue in issues if 'proxy' in issue.lower()]
        
        if proxy_issues:
            print("Configuration Issues:")
            for issue in proxy_issues:
                print(f"  ✗ {issue}")
            print()
            return 1
        
        # Test proxy setup
        from otto_bgp.proxy import IRRProxyManager, ProxyConfig
        
        # Convert config
        tunnel_config = ProxyConfig(
            enabled=proxy_config.enabled,
            method=proxy_config.method,
            jump_host=proxy_config.jump_host,
            jump_user=proxy_config.jump_user,
            ssh_key_file=proxy_config.ssh_key_file,
            known_hosts_file=proxy_config.known_hosts_file,
            connection_timeout=proxy_config.connection_timeout,
            tunnels=proxy_config.tunnels
        )
        
        proxy_manager = IRRProxyManager(tunnel_config, logger)
        
        print("Testing tunnel setup...")
        success_count = 0
        
        for tunnel_cfg in proxy_config.tunnels:
            tunnel_name = tunnel_cfg.get('name', 'unknown')
            print(f"  Setting up tunnel {tunnel_name}...")
            
            try:
                status = proxy_manager.setup_tunnel(tunnel_cfg)
                
                if status.state.value == 'connected':
                    print(f"    ✓ Tunnel {tunnel_name} established on port {status.local_port}")
                    
                    # Test connectivity
                    if proxy_manager.test_tunnel_connectivity(tunnel_name):
                        print(f"    ✓ Connectivity test passed")
                        success_count += 1
                    else:
                        print(f"    ✗ Connectivity test failed")
                else:
                    print(f"    ✗ Failed to establish tunnel: {status.error_message}")
                    
            except Exception as e:
                print(f"    ✗ Error: {e}")
        
        print()
        
        if args.test_bgpq4 and success_count > 0:
            print("Testing bgpq4 through proxy...")
            
            # Test with bgpq4
            from otto_bgp.generators.bgpq4_wrapper import BGPq4Wrapper
            
            try:
                wrapper = BGPq4Wrapper(proxy_manager=proxy_manager)
                test_result = wrapper.generate_policy_for_as(7922, "PROXY_TEST")
                
                if test_result.success:
                    print("  ✓ bgpq4 test through proxy successful")
                    if args.verbose:
                        print(f"  Policy content preview: {test_result.policy_content[:100]}...")
                else:
                    print(f"  ✗ bgpq4 test failed: {test_result.error_message}")
                    
            except Exception as e:
                print(f"  ✗ bgpq4 test error: {e}")
        
        # Cleanup
        print("\nCleaning up tunnels...")
        proxy_manager.cleanup_all_tunnels()
        
        print(f"\nProxy test completed: {success_count}/{len(proxy_config.tunnels)} tunnels successful")
        return 0 if success_count > 0 else 1
        
    except Exception as e:
        logger.error(f"Proxy test failed: {e}")
        print(f"Error: {e}")
        return 1


def _get_rpki_config(config, args):
    """Extract consistent RPKI settings (dataclass-aware)"""
    rpki_config = getattr(config, 'rpki', None)
    return {
        'enabled': (rpki_config.enabled if rpki_config else False) and not getattr(args, 'no_rpki', False),
        'fail_closed': (rpki_config.fail_closed if rpki_config else True),
        'max_vrp_age_hours': (rpki_config.max_vrp_age_hours if rpki_config else 24),
        'vrp_cache_path': (rpki_config.vrp_cache_path if rpki_config else '/var/lib/otto-bgp/rpki/vrp_cache.json'),
        'allowlist_path': (rpki_config.allowlist_path if rpki_config else '/var/lib/otto-bgp/rpki/allowlist.json')
    }


def cmd_rpki_check(args):
    """Validate RPKI cache freshness and structure (format-agnostic)"""
    from otto_bgp.utils.logging import get_logger
    logger = get_logger('otto-bgp.rpki-check')
    
    try:
        from otto_bgp.validators.rpki import RPKIValidator
        from otto_bgp.utils.config import get_config_manager
        import time
        
        # Get configuration
        config_manager = get_config_manager()
        config = config_manager.get_config()
        rpki_config = getattr(config, 'rpki', None)
        
        if not rpki_config or not rpki_config.enabled:
            logger.error("RPKI validation is not enabled in configuration")
            print("✗ RPKI validation is not enabled")
            return 1
        
        # Initialize validator to check configuration
        validator = RPKIValidator(
            vrp_cache_path=Path(rpki_config.vrp_cache_path),
            allowlist_path=Path(rpki_config.allowlist_path),
            fail_closed=rpki_config.fail_closed,
            max_vrp_age_hours=rpki_config.max_vrp_age_hours,
            logger=logger,
        )
        
        cache_path = validator.vrp_cache_path
        if not cache_path or not cache_path.exists():
            logger.error("VRP cache not found")
            print(f"✗ VRP cache not found: {cache_path}")
            return 1
        
        # Check cache age
        cache_age = time.time() - cache_path.stat().st_mtime
        max_age = args.max_age or (rpki_config.max_vrp_age_hours * 3600)
        
        if cache_age > max_age:
            logger.error(f"VRP cache stale: {cache_age/3600:.1f}h > {max_age/3600:.1f}h")
            print(f"✗ VRP cache stale: {cache_age/3600:.1f}h > {max_age/3600:.1f}h")
            return 1
        
        # Test cache readability
        try:
            # Test basic readability by attempting to load metadata
            test_result = validator.check_as_validity(64512)  # Use reserved AS for test
            if test_result['state'] in ['valid', 'invalid', 'notfound']:
                cache_readable = True
            else:
                cache_readable = False
        except Exception as e:
            logger.error(f"VRP cache unreadable: {e}")
            print(f"✗ VRP cache unreadable: {e}")
            return 1
        
        if cache_readable:
            logger.info(f"RPKI cache OK: age {cache_age/3600:.1f}h")
            print(f"✓ RPKI cache OK: age {cache_age/3600:.1f}h")
            print(f"✓ Cache path: {cache_path}")
            print(f"✓ Max age: {max_age/3600:.1f}h")
            return 0
        else:
            logger.error("VRP cache validation failed")
            print("✗ VRP cache validation failed")
            return 1
            
    except ImportError:
        logger.error("RPKI validator not available")
        print("✗ RPKI validator not available")
        return 2
    except Exception as e:
        logger.error(f"RPKI check failed: {e}")
        print(f"✗ RPKI check failed: {e}")
        return 2


def create_common_flags_parent():
    """Create a parent parser with common global flags and mutual exclusion groups"""
    parent_parser = argparse.ArgumentParser(add_help=False)
    
    # Verbose/quiet mutual exclusion
    verbose_group = parent_parser.add_mutually_exclusive_group()
    verbose_group.add_argument('-v', '--verbose', action='store_true',
                             help='Enable verbose logging')
    verbose_group.add_argument('-q', '--quiet', action='store_true',
                             help='Quiet mode (warnings only)')
    
    # System/autonomous mutual exclusion
    mode_group = parent_parser.add_mutually_exclusive_group()
    mode_group.add_argument('--autonomous', action='store_true',
                          help='Enable autonomous mode with automatic policy application')
    mode_group.add_argument('--system', action='store_true',
                          help='Use system-wide configuration and resources')
    
    # Common flags (no exclusions needed)
    parent_parser.add_argument('--dev', action='store_true',
                             help='Use Podman for bgpq4 (development mode)')
    parent_parser.add_argument('--auto-threshold', type=int, default=100, metavar='N',
                             help='Reference prefix count for notification context (informational only, default: 100)')
    parent_parser.add_argument('--no-rpki', action='store_true',
                             help='Disable RPKI validation during policy generation (not recommended)')
    
    
    return parent_parser


def create_parser():
    """Create and configure argument parser"""
    # Create parent parser with common flags
    common_flags_parent = create_common_flags_parent()
    
    # Main parser - inherits common flags for global positioning
    parser = argparse.ArgumentParser(
        prog='otto-bgp',
        description='Otto BGP - Orchestrated Transit Traffic Optimizer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
        parents=[common_flags_parent]
    )
    
    parser.add_argument('--version', action='version', version='otto-bgp 0.3.2')
    
    # Subcommands - each inherits common flags for flexible positioning
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # collect subcommand
    collect_parser = subparsers.add_parser('collect', 
                                          help='Collect BGP peer data from Juniper devices',
                                          parents=[common_flags_parent])
    collect_parser.add_argument('devices_csv', 
                               help='CSV file with device addresses (must have "address" column)')
    collect_parser.add_argument('--output-dir', default='.',
                               help='Output directory for BGP data files (default: current directory)')
    collect_parser.add_argument('--timeout', type=int, default=30,
                               help='SSH connection timeout in seconds (default: 30)')
    collect_parser.add_argument('--command-timeout', type=int, default=60,
                               help='Command execution timeout in seconds (default: 60)')
    
    # process subcommand  
    process_parser = subparsers.add_parser('process',
                                          help='Process BGP data and extract AS numbers',
                                          parents=[common_flags_parent])
    process_parser.add_argument('input_file',
                               help='Input file with BGP data or mixed text')
    process_parser.add_argument('-o', '--output',
                               help='Output file for processed data')
    process_parser.add_argument('--extract-as', action='store_true',
                               help='Extract AS numbers instead of text processing')
    process_parser.add_argument('--pattern', default='standard',
                               choices=['standard', 'peer_as', 'explicit_as', 'autonomous_system'],
                               help='AS number extraction pattern (default: standard)')
    
    # policy subcommand
    policy_parser = subparsers.add_parser('policy',
                                         help='Generate BGP policies using bgpq4',
                                         parents=[common_flags_parent])
    policy_parser.add_argument('input_file',
                              help='Input file containing AS numbers')
    policy_parser.add_argument('-o', '--output', default='bgpq4_output.txt',
                              help='Output file name (default: bgpq4_output.txt)')
    policy_parser.add_argument('-s', '--separate', action='store_true',
                              help='Create separate files for each AS')
    policy_parser.add_argument('--output-dir', default='policies',
                              help='Output directory for policy files (default: policies)')
    policy_parser.add_argument('--timeout', type=int, default=30,
                              help='bgpq4 command timeout in seconds (default: 30)')
    policy_parser.add_argument('--test', action='store_true',
                              help='Test bgpq4 connectivity and exit')
    policy_parser.add_argument('--test-as', type=int, default=7922,
                              help='AS number to use for connectivity test (default: 7922)')
    
    # discover subcommand
    discover_parser = subparsers.add_parser('discover',
                                           help='Discover BGP configurations and generate mappings',
                                           parents=[common_flags_parent])
    discover_parser.add_argument('devices_csv',
                                help='CSV file with device addresses and hostnames')
    discover_parser.add_argument('--output-dir', default='policies',
                                help='Output directory for discovered data (default: policies)')
    discover_parser.add_argument('--show-diff', action='store_true',
                                help='Generate diff report when changes detected')
    discover_parser.add_argument('--timeout', type=int, default=30,
                                help='SSH connection timeout in seconds (default: 30)')
    
    # list subcommand
    list_parser = subparsers.add_parser('list',
                                       help='List discovered routers, AS numbers, or BGP groups',
                                       parents=[common_flags_parent])
    list_parser.add_argument('list_type', choices=['routers', 'as', 'groups'],
                            help='What to list: routers, AS numbers, or BGP groups')
    list_parser.add_argument('--output-dir', default='policies',
                            help='Directory containing discovered data (default: policies)')
    
    # apply subcommand
    apply_parser = subparsers.add_parser('apply',
                                        help='Apply BGP policies to router via NETCONF',
                                        parents=[common_flags_parent])
    apply_parser.add_argument('--router', required=True,
                             help='Router hostname to apply policies to')
    apply_parser.add_argument('--policy-dir', default='policies',
                             help='Directory containing router policies (default: policies)')
    apply_parser.add_argument('--dry-run', action='store_true',
                             help='Preview changes without applying')
    apply_parser.add_argument('--confirm', action='store_true',
                             help='Use confirmed commit with automatic rollback')
    apply_parser.add_argument('--confirm-timeout', type=int, default=120,
                             help='Confirmation timeout in seconds (default: 120)')
    apply_parser.add_argument('--diff-format', choices=['text', 'set', 'xml'], default='text',
                             help='Format for configuration diff (default: text)')
    apply_parser.add_argument('--skip-safety', action='store_true',
                             help='Skip safety validation (NOT RECOMMENDED)')
    apply_parser.add_argument('--force', action='store_true',
                             help='Force application despite high risk')
    apply_parser.add_argument('--yes', '-y', action='store_true',
                             help='Skip confirmation prompt')
    apply_parser.add_argument('--username', help='NETCONF username (or set NETCONF_USERNAME env var)')
    apply_parser.add_argument('--password', help='NETCONF password (or set NETCONF_PASSWORD env var)')
    apply_parser.add_argument('--ssh-key', help='SSH private key for NETCONF (or set NETCONF_SSH_KEY env var)')
    apply_parser.add_argument('--port', type=int,
                             help='NETCONF port (default: 830 or NETCONF_PORT env var)')
    apply_parser.add_argument('--timeout', type=int, default=30,
                             help='Connection timeout in seconds (default: 30)')
    apply_parser.add_argument('--comment', help='Commit comment')
    
    # pipeline subcommand
    pipeline_parser = subparsers.add_parser('pipeline',
                                           help='Run complete BGP policy generation workflow',
                                           parents=[common_flags_parent])
    pipeline_parser.add_argument('devices_csv',
                                help='CSV file with device addresses')
    pipeline_parser.add_argument('--output-dir', default='bgp_pipeline_output',
                                help='Output directory for all pipeline results (default: bgp_pipeline_output)')
    pipeline_parser.add_argument('--mode', choices=['system', 'autonomous'], 
                                default='system', help='Execution mode (default: system)')
    pipeline_parser.add_argument('--timeout', type=int, default=30,
                                help='Command timeout in seconds (default: 30)')
    pipeline_parser.add_argument('--command-timeout', type=int, default=60,
                                help='SSH command timeout in seconds (default: 60)')
    
    # test-proxy subcommand
    test_proxy_parser = subparsers.add_parser('test-proxy',
                                             help='Test IRR proxy configuration and connectivity',
                                             parents=[common_flags_parent])
    test_proxy_parser.add_argument('--test-bgpq4', action='store_true',
                                  help='Test bgpq4 functionality through proxy')
    test_proxy_parser.add_argument('--timeout', type=int, default=10,
                                  help='Connection timeout in seconds (default: 10)')
    
    # RPKI Cache Check subcommand
    rpki_check_parser = subparsers.add_parser('rpki-check',
                                             help='Validate RPKI cache freshness and structure',
                                             parents=[common_flags_parent])
    rpki_check_parser.add_argument('--max-age', type=int,
                                  help='Maximum cache age in seconds (overrides config)')
    
    return parser


def validate_autonomous_mode(args, config):
    """Validate autonomous mode settings"""
    from otto_bgp.utils.logging import get_logger
    logger = get_logger('otto-bgp.main')
    
    
    # Check autonomous mode configuration
    if getattr(args, 'autonomous', False):
        autonomous_config = config.autonomous_mode
        
        if not autonomous_config.enabled:
            logger.warning("Autonomous mode requested but not enabled in configuration")
            print("⚠ Autonomous mode requires both configuration and runtime approval")
            print("  1. Configuration: autonomous_mode.enabled must be true")
            print("  2. Runtime flag: --autonomous (which you provided)")
            print("")
            print("To enable in configuration, either:")
            print("  • Run: ./install.sh --autonomous")
            print("  • Or edit config: autonomous_mode.enabled = true")
            return False
        
        # Recommend system installation for autonomous mode
        installation_config = config.installation_mode
        if not getattr(args, 'system', False) and installation_config.type != 'system':
            logger.warning("Autonomous mode works best with system installation")
            print("Warning: Autonomous mode works best with system installation (--system)")
            print("Consider running: ./install.sh --system --autonomous for optimal setup")
        
        # Warn about high auto-threshold values (informational only)
        auto_threshold = getattr(args, 'auto_threshold', 100)
        if auto_threshold > 1000:
            logger.warning(f"Auto-threshold {auto_threshold} is very high (informational only)")
            print(f"Warning: Auto-threshold {auto_threshold} is very high (informational only)")
            print("Note: Threshold is used for notification context and does not block operations")
        
        # Log autonomous mode activation
        logger.info(f"Autonomous mode enabled with threshold {auto_threshold} (informational)")
        print(f"Autonomous mode enabled: auto-apply threshold {auto_threshold} (informational only)")
    
    return True


def main():
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()
    
    # Setup logging
    setup_app_logging(args.verbose, args.quiet)
    
    # Load configuration and validate autonomous mode
    config = get_config_manager().get_config()
    if not validate_autonomous_mode(args, config):
        return 1
    
    # Check if command was provided
    if not args.command:
        parser.print_help()
        return 1
    
    # Validate common arguments before executing command
    try:
        args = validate_common_args(args)
    except ValidationError as e:
        print(ErrorFormatter.format_error(e))
        return 1
    except Exception as e:
        print(ErrorFormatter.format_error(e))
        return 1
    
    # Execute command
    command_functions = {
        'collect': cmd_collect,
        'process': cmd_process,
        'policy': cmd_policy,
        'discover': cmd_discover,
        'list': cmd_list,
        'apply': cmd_apply,
        'pipeline': cmd_pipeline,
        'test-proxy': cmd_test_proxy,
        'rpki-check': cmd_rpki_check
    }
    
    try:
        return command_functions[args.command](args)
    except KeyboardInterrupt:
        print_warning("Operation interrupted by user")
        return 130
    except Exception as e:
        from otto_bgp.utils.logging import get_logger
        logger = get_logger('otto-bgp.main')
        logger.error(f"Unexpected error: {e}")
        print(ErrorFormatter.format_error(e))
        return 1


if __name__ == '__main__':
    sys.exit(main())
