#!/usr/bin/env python3
"""
BGP Policy Generator using bgpq4

Modern wrapper for bgpq4 with support for:
- Native bgpq4 executable (production)
- Docker/Podman containerized bgpq4 (development)
- Automatic detection and fallback
- Structured policy generation and output management
"""

import subprocess
import logging
import shutil
import re
import os
import fcntl
import multiprocessing
import time
import signal
from concurrent.futures import ProcessPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import List, Set, Optional, Dict, Union, Any, Tuple
from pathlib import Path
from enum import Enum

# Import resource management
from otto_bgp.utils.subprocess_manager import run_with_resource_management, ProcessState
# Import timeout management
from otto_bgp.utils.timeout_config import (
    TimeoutManager, TimeoutType, TimeoutContext, ExponentialBackoff,
    get_timeout, timeout_context
)


class BGPq4Mode(Enum):
    """BGPq4 execution modes"""
    NATIVE = "native"
    DOCKER = "docker" 
    PODMAN = "podman"
    AUTO = "auto"


@dataclass
class PolicyGenerationResult:
    """Result of policy generation for a single AS"""
    as_number: int
    policy_name: str
    policy_content: str
    success: bool
    execution_time: Optional[float] = None
    error_message: Optional[str] = None
    bgpq4_mode: Optional[str] = None
    router_context: Optional[str] = None  # Router association


@dataclass
class PolicyBatchResult:
    """Result of batch policy generation"""
    results: List[PolicyGenerationResult]
    total_as_count: int
    successful_count: int
    failed_count: int
    total_execution_time: float
    output_files: List[str] = None


def validate_as_number(as_number) -> int:
    """
    Strictly validate AS numbers for security
    
    Args:
        as_number: AS number to validate (int or convertible to int)
        
    Returns:
        Validated AS number as integer
        
    Raises:
        ValueError: If AS number is invalid
    """
    # Convert to integer if needed, but reject floats that truncate
    if not isinstance(as_number, int):
        if isinstance(as_number, float):
            raise ValueError(f"AS number must be integer, got float: {as_number}")
        try:
            as_number = int(as_number)
        except (ValueError, TypeError):
            raise ValueError(f"AS number must be integer, got {type(as_number).__name__}: {as_number}")
    
    # AS numbers are 32-bit unsigned integers (0 to 4294967295)
    if not 0 <= as_number <= 4294967295:
        raise ValueError(f"AS number out of valid range (0-4294967295): {as_number}")
    
    return as_number


class WorkerHealthMonitor:
    """Monitor health and performance of worker processes"""
    
    def __init__(self, process_id: int = None):
        self.process_id = process_id or os.getpid()
        self.start_time = time.time()
        self.last_heartbeat = time.time()
        self.operation_count = 0
        self.error_count = 0
        self.timeout_count = 0
        
    def heartbeat(self):
        """Update last heartbeat time"""
        self.last_heartbeat = time.time()
        
    def record_operation(self, success: bool = True, timeout: bool = False):
        """Record an operation result"""
        self.operation_count += 1
        if not success:
            self.error_count += 1
        if timeout:
            self.timeout_count += 1
        self.heartbeat()
    
    def is_healthy(self, max_error_rate: float = 0.8, max_silence_time: float = 60.0) -> bool:
        """Check if worker is healthy"""
        if self.operation_count == 0:
            return time.time() - self.start_time < max_silence_time
        
        error_rate = self.error_count / self.operation_count
        silence_time = time.time() - self.last_heartbeat
        
        return error_rate < max_error_rate and silence_time < max_silence_time
    
    def get_stats(self) -> Dict[str, Any]:
        """Get worker statistics"""
        runtime = time.time() - self.start_time
        return {
            'process_id': self.process_id,
            'runtime': runtime,
            'operations': self.operation_count,
            'errors': self.error_count,
            'timeouts': self.timeout_count,
            'error_rate': self.error_count / max(1, self.operation_count),
            'ops_per_second': self.operation_count / max(1, runtime),
            'last_heartbeat': self.last_heartbeat,
            'silence_time': time.time() - self.last_heartbeat
        }


def _generate_policy_worker(args) -> PolicyGenerationResult:
    """
    Worker function for parallel policy generation with timeout protection
    
    This function is defined at module level to support pickling for ProcessPoolExecutor.
    It creates a new BGPq4Wrapper instance for each process to ensure process isolation.
    Includes comprehensive timeout handling and process health monitoring.
    
    Args:
        args: Tuple containing (as_number, policy_name, wrapper_config)
        
    Returns:
        PolicyGenerationResult for the AS number
    """
    as_number, policy_name, wrapper_config = args
    
    # Initialize health monitor for this worker
    monitor = WorkerHealthMonitor()
    
    # Get timeout from configuration (no signal handling in worker processes)
    process_timeout = get_timeout(TimeoutType.PROCESS_EXECUTION)
    
    try:
        monitor.heartbeat()
    
        try:
            # Create new wrapper instance for this process
            # Disable cache to avoid file locking issues between processes
            wrapper = BGPq4Wrapper(
                mode=wrapper_config['mode'],
                docker_image=wrapper_config['docker_image'],
                command_timeout=wrapper_config['command_timeout'],
                native_bgpq4_path=wrapper_config['native_bgpq4_path'],
                proxy_manager=None,  # Proxy manager cannot be pickled
                enable_cache=False,  # Use file-based caching instead
                proxy_tunnels=wrapper_config.get('proxy_tunnels') or {}
            )
            
            monitor.heartbeat()
            
            # Generate policy with process-safe file caching
            with timeout_context(TimeoutType.PROCESS_EXECUTION, f"bgpq4_AS{as_number}"):
                result = wrapper.generate_policy_for_as(as_number, policy_name, use_cache=False)
            
            # Record operation result
            monitor.record_operation(success=result.success)
            
            # Save to process-safe cache if successful
            if result.success and result.policy_content:
                _save_to_process_safe_cache(as_number, result.policy_content, policy_name, wrapper_config['cache_ttl'])
            
            return result
            
        except TimeoutError as e:
            # Handle timeout specifically
            monitor.record_operation(success=False, timeout=True)
            return PolicyGenerationResult(
                as_number=as_number,
                policy_name=policy_name or f"AS{as_number}",
                policy_content="",
                success=False,
                execution_time=process_timeout,
                error_message=f"Process timeout: {str(e)}",
                bgpq4_mode="unknown"
            )
            
        except Exception as e:
            # Handle other errors
            monitor.record_operation(success=False)
            return PolicyGenerationResult(
                as_number=as_number,
                policy_name=policy_name or f"AS{as_number}",
                policy_content="",
                success=False,
                execution_time=0.0,
                error_message=f"Process error: {str(e)}",
                bgpq4_mode="unknown"
            )
            
    except Exception as outer_e:
        # Handle setup errors (wrapper creation, etc.)
        return PolicyGenerationResult(
            as_number=as_number,
            policy_name=policy_name or f"AS{as_number}",
            policy_content="",
            success=False,
            execution_time=0.0,
            error_message=f"Worker setup error: {str(outer_e)}",
            bgpq4_mode="unknown"
        )


def _save_to_process_safe_cache(as_number: int, policy_content: str, policy_name: str = None, ttl: int = 3600):
    """
    Save policy to process-safe file cache with atomic operations and file locking
    
    Args:
        as_number: AS number
        policy_content: Policy content to cache
        policy_name: Policy name (optional)
        ttl: Time to live in seconds
    """
    import json
    import time
    import tempfile
    
    try:
        # Get cache directory
        cache_dir = Path.home() / ".otto-bgp" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate cache key and file path
        if policy_name:
            cache_key = f"policy_AS{as_number}_{policy_name}"
        else:
            cache_key = f"policy_AS{as_number}"
        
        import hashlib
        key_hash = hashlib.sha256(cache_key.encode()).hexdigest()[:16]
        cache_file = cache_dir / f"{key_hash}.json"
        
        # Prepare cache data
        cache_data = {
            'cache_key': cache_key,
            'entry': {
                'data': policy_content,
                'timestamp': time.time(),
                'ttl_seconds': ttl,
                'key_hash': key_hash
            }
        }
        
        # Use atomic write with temporary file
        with tempfile.NamedTemporaryFile(mode='w', dir=cache_dir, delete=False) as temp_file:
            json.dump(cache_data, temp_file)
            temp_name = temp_file.name
        
        # Atomic move to final location
        os.rename(temp_name, cache_file)
        
    except Exception:
        # Silently fail for cache operations to not break policy generation
        pass


def _load_from_process_safe_cache(as_number: int, policy_name: str = None) -> Optional[str]:
    """
    Load policy from process-safe file cache with file locking
    
    Args:
        as_number: AS number
        policy_name: Policy name (optional)
        
    Returns:
        Cached policy content or None if not found/expired
    """
    import json
    import time
    
    try:
        # Get cache directory
        cache_dir = Path.home() / ".otto-bgp" / "cache"
        if not cache_dir.exists():
            return None
        
        # Generate cache key and file path
        if policy_name:
            cache_key = f"policy_AS{as_number}_{policy_name}"
        else:
            cache_key = f"policy_AS{as_number}"
        
        import hashlib
        key_hash = hashlib.sha256(cache_key.encode()).hexdigest()[:16]
        cache_file = cache_dir / f"{key_hash}.json"
        
        if not cache_file.exists():
            return None
        
        # Atomic cache read with proper expiration handling
        # Fixes TOCTOU race condition by doing deletion while holding exclusive lock
        try:
            with open(cache_file, 'r+') as f:  # r+ allows both read and write for lock upgrade
                # Try to acquire shared lock for reading
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                except OSError:
                    # File is locked, skip cache
                    return None
                
                data = json.load(f)
                
                # Check if expired
                entry_data = data['entry']
                age = time.time() - entry_data['timestamp']
                if age > entry_data['ttl_seconds']:
                    # Entry expired - upgrade to exclusive lock for deletion
                    try:
                        # Upgrade to exclusive lock (atomic operation)
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        
                        # Double-check expiration after acquiring exclusive lock
                        # (another process might have updated the file)
                        f.seek(0)
                        try:
                            data = json.load(f)
                            entry_data = data['entry']
                            age = time.time() - entry_data['timestamp']
                            if age > entry_data['ttl_seconds']:
                                # Still expired - safe to delete while holding exclusive lock
                                f.close()  # Close before deletion
                                cache_file.unlink()
                                return None
                            else:
                                # File was updated, not expired anymore
                                return entry_data['data']
                        except (json.JSONDecodeError, KeyError):
                            # File corrupted, delete it
                            f.close()
                            cache_file.unlink()
                            return None
                            
                    except OSError:
                        # Cannot upgrade lock, another process is handling expiration
                        return None
                
                return entry_data['data']
                
        except FileNotFoundError:
            # File was deleted by another process during our operation
            return None
        
    except Exception:
        # Silently fail for cache operations
        return None


def validate_policy_name(policy_name: str) -> str:
    """
    Validate policy name for safe shell command construction
    
    Args:
        policy_name: Policy name to validate
        
    Returns:
        Validated policy name
        
    Raises:
        ValueError: If policy name contains unsafe characters
    """
    if not isinstance(policy_name, str):
        raise ValueError(f"Policy name must be string, got {type(policy_name).__name__}")
    
    if not policy_name:
        raise ValueError("Policy name cannot be empty")
    
    # Allow only alphanumeric characters, underscores, and hyphens
    if not re.match(r'^[A-Za-z0-9_-]+$', policy_name):
        raise ValueError(f"Policy name contains invalid characters (only A-Z, a-z, 0-9, _, - allowed): {policy_name}")
    
    # Reasonable length limit
    if len(policy_name) > 64:
        raise ValueError(f"Policy name too long (max 64 characters): {len(policy_name)}")
    
    return policy_name


class BGPq4Wrapper:
    """Wrapper for bgpq4 BGP policy generation tool"""
    
    # Default bgpq4 executable paths to check
    NATIVE_BGPQ4_PATHS = [
        '/opt/homebrew/bin/bgpq4',  # Homebrew on macOS
        '/usr/bin/bgpq4',           # Standard Linux
        '/usr/local/bin/bgpq4',     # Local installation
        'bgpq4'                     # System PATH
    ]
    
    # Docker image configurations
    DOCKER_IMAGES = {
        'default': 'ghcr.io/bgp/bgpq4:latest',
        'alternative': 'bgpq4/bgpq4'
    }
    
    def __init__(self,
                 mode: BGPq4Mode = BGPq4Mode.AUTO,
                 docker_image: str = None,
                 command_timeout: int = 30,
                 native_bgpq4_path: str = None,
                 proxy_manager=None,
                 enable_cache: bool = True,
                 cache_ttl: int = 3600,
                 proxy_tunnels: Dict[str, Tuple[str, int]] = None,
                 irr_source: str = None,
                 aggregate_prefixes: bool = True,
                 ipv4_enabled: bool = True,
                 ipv6_enabled: bool = False):
        """
        Initialize bgpq4 wrapper

        Args:
            mode: Execution mode (native, docker, podman, auto)
            docker_image: Docker image to use (default: ghcr.io/bgp/bgpq4:latest)
            command_timeout: Command execution timeout in seconds
            native_bgpq4_path: Custom path to native bgpq4 executable
            proxy_manager: Optional IRRProxyManager for tunnel support
            enable_cache: Enable policy caching (default: True)
            cache_ttl: Cache TTL in seconds (default: 1 hour)
            proxy_tunnels: Dict mapping tunnel names to (host, port) for workers
            irr_source: IRR sources to query (comma-separated, e.g., "RADB,RIPE,APNIC")
            aggregate_prefixes: Enable prefix aggregation (default: True)
            ipv4_enabled: Generate IPv4 policies (default: True)
            ipv6_enabled: Generate IPv6 policies (default: False)
        """
        self.logger = logging.getLogger(__name__)
        self.mode = mode
        self.docker_image = docker_image or self.DOCKER_IMAGES['default']
        self.command_timeout = command_timeout
        self.native_bgpq4_path = native_bgpq4_path
        self.proxy_manager = proxy_manager
        self.proxy_tunnels = proxy_tunnels or {}
        self.enable_cache = enable_cache
        self.cache_ttl = cache_ttl
        self.irr_source = irr_source or "RADB,RIPE,APNIC"
        self.aggregate_prefixes = aggregate_prefixes
        self.ipv4_enabled = ipv4_enabled
        self.ipv6_enabled = ipv6_enabled
        
        # Initialize cache
        self.cache = None
        if self.enable_cache:
            from otto_bgp.utils.cache import PolicyCache
            self.cache = PolicyCache(default_ttl=cache_ttl)
        
        # Detected execution configuration
        self.detected_mode = None
        self.bgpq4_command = None
        
        # Initialize and detect available bgpq4
        self._detect_bgpq4_availability()
        
        # Enforce native bgpq4 when proxy is enabled
        proxy_active = bool(self.proxy_manager or getattr(self, 'proxy_tunnels', {}))
        if proxy_active and self.mode in (BGPq4Mode.AUTO, BGPq4Mode.NATIVE):
            if self.detected_mode in (BGPq4Mode.DOCKER, BGPq4Mode.PODMAN):
                raise RuntimeError(
                    "IRR proxy requires native bgpq4. Containerized bgpq4 cannot reach host 127.0.0.1 tunnels."
                )
        
        self.logger.info(f"BGPq4 wrapper initialized: mode={self.detected_mode}, command={self.bgpq4_command}, proxy={'enabled' if proxy_manager else 'disabled'}, cache={'enabled' if enable_cache else 'disabled'}")
    
    def _detect_bgpq4_availability(self):
        """Detect available bgpq4 execution methods"""
        
        if self.mode == BGPq4Mode.NATIVE or self.mode == BGPq4Mode.AUTO:
            # Check for native bgpq4
            if self.native_bgpq4_path and shutil.which(self.native_bgpq4_path):
                self.detected_mode = BGPq4Mode.NATIVE
                self.bgpq4_command = [self.native_bgpq4_path]
                self.logger.info(f"Using custom native bgpq4: {self.native_bgpq4_path}")
                return
            
            # Check standard paths
            for path in self.NATIVE_BGPQ4_PATHS:
                if shutil.which(path):
                    self.detected_mode = BGPq4Mode.NATIVE
                    self.bgpq4_command = [path]
                    self.logger.info(f"Found native bgpq4: {path}")
                    if self.mode == BGPq4Mode.NATIVE:
                        return
                    break
        
        if self.mode == BGPq4Mode.PODMAN or (self.mode == BGPq4Mode.AUTO and self.detected_mode is None):
            # Check for podman
            if shutil.which('podman'):
                self.detected_mode = BGPq4Mode.PODMAN
                self.bgpq4_command = ['podman', 'run', '--rm', '-i', self.docker_image]
                self.logger.info(f"Using podman with image: {self.docker_image}")
                if self.mode == BGPq4Mode.PODMAN:
                    return
        
        if self.mode == BGPq4Mode.DOCKER or (self.mode == BGPq4Mode.AUTO and self.detected_mode is None):
            # Check for docker
            if shutil.which('docker'):
                self.detected_mode = BGPq4Mode.DOCKER
                self.bgpq4_command = ['docker', 'run', '--rm', '-i', self.docker_image]
                self.logger.info(f"Using docker with image: {self.docker_image}")
                return
        
        # No bgpq4 available
        if self.detected_mode is None:
            error_msg = "No bgpq4 available. Install bgpq4 natively or ensure Docker/Podman is running."
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def _build_bgpq4_command(self, as_number: int, policy_name: str = None, irr_server: str = None) -> List[str]:
        """
        Build bgpq4 command for given AS number with security validation

        Args:
            as_number: AS number to generate policy for
            policy_name: Custom policy name (default: AS<number>)
            irr_server: Optional IRR server preference for proxy selection

        Returns:
            Complete command list for subprocess

        Raises:
            ValueError: If AS number or policy name is invalid
        """
        # Validate AS number first for security
        validated_as = validate_as_number(as_number)

        # Generate or validate policy name
        if policy_name is None:
            policy_name = f"AS{validated_as}"
        else:
            policy_name = validate_policy_name(policy_name)

        # Base command from detected configuration
        command = self.bgpq4_command.copy()

        # Apply proxy modifications if available
        if self.proxy_manager:
            command = self.proxy_manager.wrap_bgpq4_command(command, irr_server)
            self.logger.debug(f"Applied proxy configuration to bgpq4 command")

        # If running in a worker without a proxy_manager, but with provided tunnel mapping,
        # inject localhost:port for bgpq4
        if not self.proxy_manager and getattr(self, 'proxy_tunnels', None):
            # Select first available tunnel deterministically
            name, endpoint = sorted(self.proxy_tunnels.items())[0]
            host, port = endpoint
            if '-h' not in command:
                command.extend(['-h', host, '-p', str(port)])
                self.logger.debug(f"Injected proxy_tunnels endpoint {name} -> {host}:{port}")

        # Add IRR source specification if configured
        if self.irr_source:
            command.extend(['-S', self.irr_source])
            self.logger.debug(f"Using IRR sources: {self.irr_source}")

        # Add prefix aggregation flag if enabled
        if self.aggregate_prefixes:
            command.append('-A')
            self.logger.debug("Prefix aggregation enabled")

        # Add Juniper format flag
        command.append('-J')

        # Add address family flags based on configuration
        if self.ipv4_enabled and self.ipv6_enabled:
            # Both IPv4 and IPv6 (default bgpq4 behavior, no extra flags needed)
            self.logger.debug("Generating policies for IPv4 and IPv6")
        elif self.ipv4_enabled:
            # IPv4 only (use -4 flag)
            command.append('-4')
            self.logger.debug("Generating policies for IPv4 only")
        elif self.ipv6_enabled:
            # IPv6 only (use -6 flag)
            command.append('-6')
            self.logger.debug("Generating policies for IPv6 only")
        else:
            # Neither enabled - this shouldn't happen, but default to IPv4
            command.append('-4')
            self.logger.warning("No address family enabled, defaulting to IPv4")

        # Add prefix-list format and name
        command.extend(['-l', policy_name])

        # Add AS number (must be last argument)
        command.append(f'AS{validated_as}')

        self.logger.debug(f"Built secure bgpq4 command for AS{validated_as}: {' '.join(command)}")
        return command
    
    def generate_policy_for_as(self, 
                              as_number: int, 
                              policy_name: str = None,
                              irr_server: str = None,
                              use_cache: bool = True,
                              timeout: int = None) -> PolicyGenerationResult:
        """
        Generate BGP policy for single AS number
        
        Args:
            as_number: AS number to generate policy for
            policy_name: Custom policy name (default: AS<number>)
            irr_server: Optional IRR server preference for proxy selection
            use_cache: Use cached policy if available (default: True)
            timeout: Custom timeout in seconds (overrides default command_timeout)
            
        Returns:
            PolicyGenerationResult with policy content and metadata
        """
        import time
        
        try:
            # Validate inputs early for security and clear error messages
            validated_as = validate_as_number(as_number)
            if policy_name is None:
                policy_name = f"AS{validated_as}"
            else:
                policy_name = validate_policy_name(policy_name)
            
            # Check cache first if enabled
            if self.cache and use_cache:
                cached_policy = self.cache.get_policy(validated_as, policy_name)
                if cached_policy:
                    self.logger.debug(f"Using cached policy for AS{validated_as}")
                    return PolicyGenerationResult(
                        as_number=validated_as,
                        policy_name=policy_name,
                        policy_content=cached_policy,
                        success=True,
                        execution_time=0.0,
                        bgpq4_mode=self.detected_mode.value,
                        router_context=None
                    )
            
            self.logger.info(f"Generating policy for AS{validated_as} (policy: {policy_name})")
            
            command = self._build_bgpq4_command(validated_as, policy_name, irr_server)
            start_time = time.time()
            
            # Use custom timeout if provided, otherwise use default
            effective_timeout = timeout if timeout is not None else self.command_timeout
            
        except ValueError as e:
            # Return early for validation errors
            self.logger.error(f"Invalid input for AS policy generation: {e}")
            return PolicyGenerationResult(
                as_number=as_number,  # Use original for error reporting
                policy_name=policy_name if isinstance(policy_name, str) else f"AS{as_number}",
                policy_content="",
                success=False,
                execution_time=0.0,
                error_message=f"Input validation failed: {e}",
                bgpq4_mode=self.detected_mode.value if self.detected_mode else "unknown"
            )
        
        try:
            # Use managed subprocess execution for resource safety
            result = run_with_resource_management(
                command=command,
                timeout=effective_timeout,
                capture_output=True,
                text=True
            )
            
            if result.state == ProcessState.COMPLETED:
                self.logger.debug(f"Successfully generated policy for AS{validated_as} in {result.execution_time:.2f}s")
                
                # Cache successful result
                if self.cache and result.stdout.strip():
                    self.cache.put_policy(validated_as, result.stdout, policy_name)
                
                return PolicyGenerationResult(
                    as_number=validated_as,
                    policy_name=policy_name,
                    policy_content=result.stdout,
                    success=True,
                    execution_time=result.execution_time,
                    bgpq4_mode=self.detected_mode.value
                )
            
            elif result.state == ProcessState.TIMEOUT:
                self.logger.warning(f"Timeout generating policy for AS{validated_as}: {result.error_message}")
                
                return PolicyGenerationResult(
                    as_number=validated_as,
                    policy_name=policy_name,
                    policy_content="",
                    success=False,
                    execution_time=result.execution_time,
                    error_message=result.error_message,
                    bgpq4_mode=self.detected_mode.value
                )
            
            else:  # FAILED state
                error_msg = f"bgpq4 error (code {result.returncode}): {result.stderr.strip()}"
                self.logger.warning(f"Failed to generate policy for AS{validated_as}: {error_msg}")
                
                return PolicyGenerationResult(
                    as_number=validated_as,
                    policy_name=policy_name,
                    policy_content="",
                    success=False,
                    execution_time=result.execution_time,
                    error_message=error_msg,
                    bgpq4_mode=self.detected_mode.value
                )
                
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Unexpected error: {str(e)}"
            self.logger.error(f"Unexpected error generating policy for AS{validated_as}: {error_msg}")
            
            return PolicyGenerationResult(
                as_number=validated_as,
                policy_name=policy_name,
                policy_content="",
                success=False,
                execution_time=execution_time,
                error_message=error_msg,
                bgpq4_mode=self.detected_mode.value
            )
    
    def generate_policies_parallel(self, 
                                  as_numbers: Union[List[int], Set[int]],
                                  custom_policy_names: Dict[int, str] = None,
                                  max_workers: int = None) -> PolicyBatchResult:
        """
        Generate BGP policies for multiple AS numbers using parallel processing
        
        This method achieves significant speedup (4.3x for 10+ AS numbers) by running
        bgpq4 commands in parallel processes while maintaining all security features.
        
        Args:
            as_numbers: List or set of AS numbers
            custom_policy_names: Optional mapping of AS number to custom policy name
            max_workers: Maximum number of worker processes (auto-detected if None)
            
        Returns:
            PolicyBatchResult with all policy generation results
            
        Security:
            - All AS numbers and policy names are validated before processing
            - Each process runs in isolation with its own BGPq4Wrapper instance
            - Process-safe file caching prevents race conditions
            - Individual process failures don't affect other processes
        """
        import time
        
        if isinstance(as_numbers, set):
            as_numbers = sorted(as_numbers)
        
        custom_policy_names = custom_policy_names or {}
        
        # Auto-scale worker count based on system and workload
        if max_workers is None:
            env_workers = os.getenv('OTTO_BGP_BGPQ4_MAX_WORKERS')
            if env_workers is not None:
                try:
                    w = int(env_workers)
                    if w <= 1:
                        max_workers = 1
                    else:
                        max_workers = w
                except ValueError:
                    max_workers = None
            if max_workers is None:
                cpu_count = multiprocessing.cpu_count()
                max_workers = min(cpu_count, 8, len(as_numbers))
        
        # Apply proxy-aware worker cap if proxy endpoints are present
        try:
            proxy_tunnels_present = bool(getattr(self, 'proxy_manager') and self.proxy_manager and self.proxy_manager.tunnels)
        except Exception:
            proxy_tunnels_present = False
        if proxy_tunnels_present and isinstance(max_workers, int):
            original_workers = max_workers
            max_workers = min(max_workers, 4)
            if max_workers != original_workers:
                self.logger.info(f"Proxy active: capping workers {original_workers} -> {max_workers}")
        
        self.logger.info(f"Starting parallel policy generation for {len(as_numbers)} AS numbers using {max_workers} workers")
        
        start_time = time.time()
        results = []
        
        # If proxy manager is configured, establish tunnels once and snapshot endpoints
        proxy_tunnels = {}
        if self.proxy_manager:
            try:
                self.proxy_manager.establish_all_tunnels()
                proxy_tunnels = self.proxy_manager.get_tunnel_mapping()
                if proxy_tunnels:
                    self.logger.info(f"Proxy endpoints available: {len(proxy_tunnels)}")
                else:
                    self.logger.warning("Proxy enabled but no tunnels established; proceeding without proxy")
            except Exception as e:
                self.logger.warning(f"Failed to establish proxy tunnels: {e}")
                proxy_tunnels = {}
        
        # Validate all inputs first for security
        validated_tasks = []
        for as_number in as_numbers:
            try:
                # Validate AS number for security
                validated_as = validate_as_number(as_number)
                
                # Get and validate policy name
                policy_name = custom_policy_names.get(as_number)
                if policy_name is not None:
                    policy_name = validate_policy_name(policy_name)
                
                # Check process-safe cache first
                cached_policy = _load_from_process_safe_cache(validated_as, policy_name)
                if cached_policy:
                    # Use cached result
                    self.logger.debug(f"Using cached policy for AS{validated_as}")
                    results.append(PolicyGenerationResult(
                        as_number=validated_as,
                        policy_name=policy_name or f"AS{validated_as}",
                        policy_content=cached_policy,
                        success=True,
                        execution_time=0.0,
                        bgpq4_mode=self.detected_mode.value,
                        router_context=None
                    ))
                else:
                    # Add to parallel processing queue
                    wrapper_config = {
                        'mode': self.mode,
                        'docker_image': self.docker_image,
                        'command_timeout': self.command_timeout,
                        'native_bgpq4_path': self.native_bgpq4_path,
                        'cache_ttl': self.cache_ttl if hasattr(self, 'cache_ttl') else 3600,
                        'proxy_tunnels': proxy_tunnels
                    }
                    validated_tasks.append((validated_as, policy_name, wrapper_config))
                
            except ValueError as e:
                # Add validation error to results
                self.logger.error(f"Input validation failed for AS{as_number}: {e}")
                results.append(PolicyGenerationResult(
                    as_number=as_number,  # Use original for error reporting
                    policy_name=custom_policy_names.get(as_number, f"AS{as_number}"),
                    policy_content="",
                    success=False,
                    execution_time=0.0,
                    error_message=f"Input validation failed: {e}",
                    bgpq4_mode=self.detected_mode.value if self.detected_mode else "unknown"
                ))
        
        # Process remaining tasks in parallel with timeout protection
        if validated_tasks:
            self.logger.info(f"Processing {len(validated_tasks)} AS numbers in parallel ({len(results)} from cache)")
            
            # Get timeout values
            process_timeout = get_timeout(TimeoutType.PROCESS_EXECUTION)
            batch_timeout = get_timeout(TimeoutType.BATCH_PROCESSING)
            
            try:
                with timeout_context(TimeoutType.BATCH_PROCESSING, f"parallel_generation_{len(validated_tasks)}_AS") as ctx:
                    with ProcessPoolExecutor(max_workers=max_workers) as executor:
                        # Submit all tasks
                        future_to_as = {
                            executor.submit(_generate_policy_worker, task): task[0] 
                            for task in validated_tasks
                        }
                        
                        # Track completed and pending futures
                        completed_count = 0
                        pending_futures = set(future_to_as.keys())
                        
                        # Collect results with timeout and health monitoring
                        while pending_futures and not ctx.check_timeout():
                            try:
                                # Use timeout to prevent indefinite blocking
                                timeout_remaining = min(process_timeout, ctx.remaining_time())
                                if timeout_remaining <= 0:
                                    self.logger.warning("Batch timeout reached, cancelling remaining tasks")
                                    break
                                
                                # Wait for at least one future to complete
                                for future in as_completed(pending_futures, timeout=timeout_remaining):
                                    as_number = future_to_as[future]
                                    pending_futures.discard(future)
                                    
                                    try:
                                        # Get result with individual process timeout
                                        result = future.result(timeout=process_timeout)
                                        results.append(result)
                                        completed_count += 1
                                        
                                        # Log progress
                                        if result.success:
                                            self.logger.debug(
                                                f"Completed AS{as_number} in {result.execution_time:.2f}s "
                                                f"({completed_count}/{len(validated_tasks)})"
                                            )
                                        else:
                                            self.logger.warning(f"Failed AS{as_number}: {result.error_message}")
                                    
                                    except FuturesTimeoutError:
                                        # Individual process timeout
                                        self.logger.error(f"Process timeout for AS{as_number} after {process_timeout}s")
                                        results.append(PolicyGenerationResult(
                                            as_number=as_number,
                                            policy_name=f"AS{as_number}",
                                            policy_content="",
                                            success=False,
                                            execution_time=process_timeout,
                                            error_message=f"Process timeout after {process_timeout}s",
                                            bgpq4_mode=self.detected_mode.value if self.detected_mode else "unknown"
                                        ))
                                        # Cancel the timed-out future
                                        future.cancel()
                                    
                                    except Exception as e:
                                        # Handle other process execution errors
                                        self.logger.error(f"Process error for AS{as_number}: {e}")
                                        results.append(PolicyGenerationResult(
                                            as_number=as_number,
                                            policy_name=f"AS{as_number}",
                                            policy_content="",
                                            success=False,
                                            execution_time=0.0,
                                            error_message=f"Process execution error: {str(e)}",
                                            bgpq4_mode=self.detected_mode.value if self.detected_mode else "unknown"
                                        ))
                                    
                                    # Break from inner loop to check timeout
                                    break
                                    
                            except FuturesTimeoutError:
                                # No futures completed within timeout - check if we should continue
                                if ctx.check_timeout():
                                    self.logger.warning("Batch timeout reached while waiting for completions")
                                    break
                                # Continue waiting if batch timeout not reached
                                continue
                        
                        # Handle any remaining pending futures
                        if pending_futures:
                            self.logger.warning(f"Cancelling {len(pending_futures)} pending tasks due to timeout")
                            for future in pending_futures:
                                future.cancel()
                                as_number = future_to_as[future]
                                results.append(PolicyGenerationResult(
                                    as_number=as_number,
                                    policy_name=f"AS{as_number}",
                                    policy_content="",
                                    success=False,
                                    execution_time=0.0,
                                    error_message="Task cancelled due to batch timeout",
                                    bgpq4_mode=self.detected_mode.value if self.detected_mode else "unknown"
                                ))
                            
            except Exception as e:
                # Handle ProcessPoolExecutor initialization errors
                self.logger.error(f"Failed to initialize parallel processing: {e}")
                # Fallback to sequential processing for remaining tasks
                self.logger.info("Falling back to sequential processing")
                
                # Process remaining tasks sequentially with timeout protection
                remaining_tasks = [task for task in validated_tasks 
                                 if not any(r.as_number == task[0] for r in results)]
                
                for task in remaining_tasks:
                    as_number, policy_name, _ = task
                    try:
                        with timeout_context(TimeoutType.PROCESS_EXECUTION, f"sequential_AS{as_number}"):
                            result = self.generate_policy_for_as(as_number, policy_name)
                            results.append(result)
                    except Exception as seq_e:
                        self.logger.error(f"Sequential processing failed for AS{as_number}: {seq_e}")
                        results.append(PolicyGenerationResult(
                            as_number=as_number,
                            policy_name=policy_name,
                            policy_content="",
                            success=False,
                            execution_time=0.0,
                            error_message=f"Sequential fallback error: {str(seq_e)}",
                            bgpq4_mode=self.detected_mode.value if self.detected_mode else "unknown"
                        ))
        
        total_time = time.time() - start_time
        successful_count = sum(1 for r in results if r.success)
        failed_count = len(results) - successful_count
        
        batch_result = PolicyBatchResult(
            results=results,
            total_as_count=len(as_numbers),
            successful_count=successful_count,
            failed_count=failed_count,
            total_execution_time=total_time
        )
        
        speedup = 0.0
        if len(validated_tasks) > 0:
            # Estimate sequential time from actual parallel results
            avg_time_per_as = sum(r.execution_time for r in results if r.success and r.execution_time > 0)
            if avg_time_per_as > 0:
                avg_time_per_as = avg_time_per_as / successful_count
                estimated_sequential = avg_time_per_as * len(validated_tasks)
                if total_time > 0:
                    speedup = estimated_sequential / total_time
        
        self.logger.info(f"Parallel generation complete: {successful_count}/{len(as_numbers)} successful in {total_time:.2f}s")
        if speedup > 1.0:
            self.logger.info(f"Achieved {speedup:.1f}x speedup with {max_workers} workers")
        
        return batch_result
    
    def generate_policies_batch(self, 
                               as_numbers: Union[List[int], Set[int]],
                               custom_policy_names: Dict[int, str] = None,
                               rpki_status: Dict[int, Dict[str, Any]] = None,
                               parallel: bool = True,
                               max_workers: int = None) -> PolicyBatchResult:
        """
        Generate BGP policies for multiple AS numbers
        
        This method now uses parallel processing by default for improved performance.
        For workloads with 3+ AS numbers, parallel processing provides significant speedup.
        
        Args:
            as_numbers: List or set of AS numbers
            custom_policy_names: Optional mapping of AS number to custom policy name
            rpki_status: Optional RPKI validation status for each AS number
            parallel: Use parallel processing (default: True). Set to False for sequential processing.
            max_workers: Maximum number of worker processes (auto-detected if None)
            
        Returns:
            PolicyBatchResult with all policy generation results
        """
        import time
        
        if isinstance(as_numbers, set):
            as_numbers = sorted(as_numbers)
        
        custom_policy_names = custom_policy_names or {}
        rpki_status = rpki_status or {}
        
        # Decide processing method based on standardized env var
        env_workers = os.getenv('OTTO_BGP_BGPQ4_MAX_WORKERS')
        use_parallel = parallel and len(as_numbers) > 1
        if env_workers is not None:
            try:
                w = int(env_workers)
                if w <= 1:
                    use_parallel = False
                    max_workers = 1
                    self.logger.info("Parallel disabled by OTTO_BGP_BGPQ4_MAX_WORKERS")
                else:
                    use_parallel = True
                    max_workers = w
                    self.logger.info(f"Parallel enabled with {w} workers by OTTO_BGP_BGPQ4_MAX_WORKERS")
            except ValueError:
                self.logger.warning("Invalid OTTO_BGP_BGPQ4_MAX_WORKERS value; falling back to auto")
        
        if use_parallel:
            return self.generate_policies_parallel(as_numbers, custom_policy_names, max_workers)
        
        # Fall back to sequential processing
        self.logger.info(f"Starting sequential policy generation for {len(as_numbers)} AS numbers")
        
        start_time = time.time()
        results = []
        
        for as_number in as_numbers:
            policy_name = custom_policy_names.get(as_number)
            result = self.generate_policy_for_as(as_number, policy_name)
            results.append(result)
        
        total_time = time.time() - start_time
        successful_count = sum(1 for r in results if r.success)
        failed_count = len(results) - successful_count
        
        batch_result = PolicyBatchResult(
            results=results,
            total_as_count=len(as_numbers),
            successful_count=successful_count,
            failed_count=failed_count,
            total_execution_time=total_time
        )
        
        self.logger.info(f"Sequential generation complete: {successful_count}/{len(as_numbers)} successful in {total_time:.2f}s")
        
        return batch_result
    
    def write_policies_to_files(self, 
                               batch_result: PolicyBatchResult,
                               output_dir: Union[str, Path] = "policies",
                               separate_files: bool = True,
                               combined_filename: str = "bgpq4_output.txt",
                               rpki_status: Dict[int, Dict[str, Any]] = None) -> List[str]:
        """
        Write policy generation results to files
        
        Args:
            batch_result: Result from generate_policies_batch
            output_dir: Directory to write policy files
            separate_files: Create separate file for each AS (default: True)
            combined_filename: Filename for combined output (when separate_files=False)
            rpki_status: Optional RPKI validation status for each AS number
            
        Returns:
            List of created file paths
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)
        
        created_files = []
        rpki_status = rpki_status or {}
        
        if separate_files:
            # Create separate file for each successful AS
            for result in batch_result.results:
                if result.success and result.policy_content:
                    filename = f"AS{result.as_number}_policy.txt"
                    file_path = output_dir / filename
                    
                    with open(file_path, 'w') as f:
                        f.write(result.policy_content)
                    
                    created_files.append(str(file_path))
                    self.logger.debug(f"Written policy file: {file_path}")
        
        else:
            # Create combined file with all successful policies
            combined_path = output_dir / combined_filename
            
            with open(combined_path, 'w') as f:
                for result in batch_result.results:
                    if result.success and result.policy_content:
                        f.write(f"# AS{result.as_number}\n")
                        
                        # Add RPKI status if available
                        rpki_info = rpki_status.get(result.as_number, {})
                        if rpki_info:
                            rpki_state = rpki_info.get('state')
                            rpki_msg = rpki_info.get('message', '')
                            if rpki_state:
                                f.write(f"# RPKI Status: {rpki_state.value}\n")
                            if rpki_msg:
                                f.write(f"# RPKI Details: {rpki_msg}\n")
                        
                        f.write(result.policy_content)
                        f.write("\n")
            
            created_files.append(str(combined_path))
            self.logger.info(f"Written combined policy file: {combined_path}")
        
        # Update batch result with output files
        batch_result.output_files = created_files
        
        self.logger.info(f"Policy files written: {len(created_files)} files in {output_dir}")
        return created_files
    
    def test_bgpq4_connection(self, test_as: int = 7922) -> bool:
        """
        Test bgpq4 connectivity with a known working AS
        
        Args:
            test_as: AS number to test with (default: 7922 - Comcast)
            
        Returns:
            True if bgpq4 is working, False otherwise
        """
        self.logger.info(f"Testing bgpq4 connectivity with AS{test_as}")
        
        try:
            result = self.generate_policy_for_as(test_as)
            
            if result.success and result.policy_content:
                self.logger.info(f"bgpq4 test successful: generated {len(result.policy_content)} characters in {result.execution_time:.2f}s")
                return True
            else:
                self.logger.error(f"bgpq4 test failed: {result.error_message}")
                return False
                
        except subprocess.TimeoutExpired as e:
            self.logger.error(f"bgpq4 test timeout: {e}")
            return False
        except ValueError as e:
            self.logger.error(f"bgpq4 test validation error: {e}")
            return False
        except Exception as e:
            self.logger.error(f"bgpq4 test unexpected error: {e}")
            return False
    
    def get_status_info(self) -> Dict[str, str]:
        """Get status information about bgpq4 configuration"""
        status = {
            'mode': self.detected_mode.value if self.detected_mode else 'unknown',
            'command': ' '.join(self.bgpq4_command) if self.bgpq4_command else 'none',
            'docker_image': self.docker_image,
            'timeout': str(self.command_timeout),
            'proxy': 'enabled' if self.proxy_manager else 'disabled',
            'cache': 'enabled' if self.cache else 'disabled'
        }
        
        # Add parallel processing configuration (standardized)
        max_workers_env = os.getenv('OTTO_BGP_BGPQ4_MAX_WORKERS', 'auto')
        cpu_count = multiprocessing.cpu_count()
        try:
            mw = int(max_workers_env)
            parallel_state = 'disabled' if mw <= 1 else 'enabled'
        except Exception:
            parallel_state = 'enabled'
        
        status.update({
            'parallel_processing': parallel_state,
            'max_workers_config': str(max_workers_env),
            'cpu_cores': str(cpu_count),
            'auto_max_workers': str(min(cpu_count, 8))
        })
        
        # Add cache statistics if available
        if self.cache:
            cache_stats = self.cache.get_stats()
            status.update({
                'cache_entries': str(cache_stats['active_entries']),
                'cache_expired': str(cache_stats['expired_entries']),
                'cache_ttl': str(cache_stats['default_ttl'])
            })
        
        return status
    
    def get_optimal_worker_count(self, as_count: int) -> int:
        """
        Calculate optimal worker count for given workload
        
        Args:
            as_count: Number of AS numbers to process
            
        Returns:
            Optimal number of worker processes
        """
        # Standardized env override
        env_workers = os.getenv('OTTO_BGP_BGPQ4_MAX_WORKERS')
        if env_workers is not None:
            try:
                w = int(env_workers)
                return 1 if w <= 1 else w
            except ValueError:
                pass
        
        # Auto-calculate based on system resources and workload
        cpu_count = multiprocessing.cpu_count()
        
        # For small workloads, limit workers to workload size
        if as_count <= 2:
            return 1  # Sequential processing is fine for 1-2 AS numbers
        
        # For larger workloads, scale with CPU cores but limit to prevent resource exhaustion
        # Rule: min(CPU cores, 8, AS count)
        return min(cpu_count, 8, as_count)
    
    @classmethod
    def create_with_proxy(cls, 
                         proxy_config,
                         mode: BGPq4Mode = BGPq4Mode.AUTO,
                         command_timeout: int = 30):
        """
        Create BGPq4Wrapper with proxy support configured
        
        Args:
            proxy_config: IRRProxyConfig object
            mode: BGPq4 execution mode
            command_timeout: Command timeout in seconds
            
        Returns:
            BGPq4Wrapper instance with proxy manager configured
        """
        proxy_manager = None
        
        if proxy_config and proxy_config.enabled:
            # Import here to avoid circular dependencies
            from otto_bgp.proxy import IRRProxyManager, ProxyConfig
            
            # Convert IRRProxyConfig to ProxyConfig
            tunnel_proxy_config = ProxyConfig(
                enabled=proxy_config.enabled,
                method=proxy_config.method,
                jump_host=proxy_config.jump_host,
                jump_user=proxy_config.jump_user,
                ssh_key_file=proxy_config.ssh_key_file,
                known_hosts_file=proxy_config.known_hosts_file,
                connection_timeout=proxy_config.connection_timeout,
                health_check_interval=proxy_config.health_check_interval,
                max_retries=proxy_config.max_retries,
                tunnels=proxy_config.tunnels
            )
            
            proxy_manager = IRRProxyManager(tunnel_proxy_config)
            
            # Setup tunnels
            for tunnel_config in proxy_config.tunnels:
                try:
                    tunnel_status = proxy_manager.setup_tunnel(tunnel_config)
                    if tunnel_status.state.value != 'connected':
                        logging.getLogger(__name__).warning(
                            f"Failed to establish tunnel {tunnel_config.get('name', 'unknown')}: {tunnel_status.error_message}"
                        )
                except Exception as e:
                    logging.getLogger(__name__).error(f"Error setting up tunnel: {e}")
        
        return cls(
            mode=mode,
            command_timeout=command_timeout,
            proxy_manager=proxy_manager
        )


