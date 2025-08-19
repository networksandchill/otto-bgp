#!/usr/bin/env python3
"""
BGP Policy Generator using bgpq3

Modern wrapper for bgpq3 with support for:
- Native bgpq3 executable (production)
- Docker/Podman containerized bgpq3 (development)
- Automatic detection and fallback
- Structured policy generation and output management
"""

import subprocess
import logging
import shutil
import re
from dataclasses import dataclass
from typing import List, Set, Optional, Dict, Union
from pathlib import Path
from enum import Enum


class BGPq3Mode(Enum):
    """BGPq3 execution modes"""
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
    bgpq3_mode: Optional[str] = None


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


class BGPq3Wrapper:
    """Wrapper for bgpq3 BGP policy generation tool"""
    
    # Default bgpq3 executable paths to check
    NATIVE_BGPQ3_PATHS = [
        '/opt/homebrew/bin/bgpq3',  # Homebrew on macOS
        '/usr/bin/bgpq3',           # Standard Linux
        '/usr/local/bin/bgpq3',     # Local installation
        'bgpq3'                     # System PATH
    ]
    
    # Docker image configurations
    DOCKER_IMAGES = {
        'default': 'mirceaulinic/bgpq3',
        'alternative': 'bgpq3/bgpq3'
    }
    
    def __init__(self, 
                 mode: BGPq3Mode = BGPq3Mode.AUTO,
                 docker_image: str = None,
                 command_timeout: int = 30,
                 native_bgpq3_path: str = None):
        """
        Initialize bgpq3 wrapper
        
        Args:
            mode: Execution mode (native, docker, podman, auto)
            docker_image: Docker image to use (default: mirceaulinic/bgpq3)
            command_timeout: Command execution timeout in seconds
            native_bgpq3_path: Custom path to native bgpq3 executable
        """
        self.logger = logging.getLogger(__name__)
        self.mode = mode
        self.docker_image = docker_image or self.DOCKER_IMAGES['default']
        self.command_timeout = command_timeout
        self.native_bgpq3_path = native_bgpq3_path
        
        # Detected execution configuration
        self.detected_mode = None
        self.bgpq3_command = None
        
        # Initialize and detect available bgpq3
        self._detect_bgpq3_availability()
        
        self.logger.info(f"BGPq3 wrapper initialized: mode={self.detected_mode}, command={self.bgpq3_command}")
    
    def _detect_bgpq3_availability(self):
        """Detect available bgpq3 execution methods"""
        
        if self.mode == BGPq3Mode.NATIVE or self.mode == BGPq3Mode.AUTO:
            # Check for native bgpq3
            if self.native_bgpq3_path and shutil.which(self.native_bgpq3_path):
                self.detected_mode = BGPq3Mode.NATIVE
                self.bgpq3_command = [self.native_bgpq3_path]
                self.logger.info(f"Using custom native bgpq3: {self.native_bgpq3_path}")
                return
            
            # Check standard paths
            for path in self.NATIVE_BGPQ3_PATHS:
                if shutil.which(path):
                    self.detected_mode = BGPq3Mode.NATIVE
                    self.bgpq3_command = [path]
                    self.logger.info(f"Found native bgpq3: {path}")
                    if self.mode == BGPq3Mode.NATIVE:
                        return
                    break
        
        if self.mode == BGPq3Mode.PODMAN or (self.mode == BGPq3Mode.AUTO and self.detected_mode is None):
            # Check for podman
            if shutil.which('podman'):
                self.detected_mode = BGPq3Mode.PODMAN
                self.bgpq3_command = ['podman', 'run', '--rm', '-i', self.docker_image, 'bgpq3']
                self.logger.info(f"Using podman with image: {self.docker_image}")
                if self.mode == BGPq3Mode.PODMAN:
                    return
        
        if self.mode == BGPq3Mode.DOCKER or (self.mode == BGPq3Mode.AUTO and self.detected_mode is None):
            # Check for docker
            if shutil.which('docker'):
                self.detected_mode = BGPq3Mode.DOCKER
                self.bgpq3_command = ['docker', 'run', '--rm', '-i', self.docker_image, 'bgpq3']
                self.logger.info(f"Using docker with image: {self.docker_image}")
                return
        
        # No bgpq3 available
        if self.detected_mode is None:
            error_msg = "No bgpq3 available. Install bgpq3 natively or ensure Docker/Podman is running."
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def _build_bgpq3_command(self, as_number: int, policy_name: str = None) -> List[str]:
        """
        Build bgpq3 command for given AS number with security validation
        
        Args:
            as_number: AS number to generate policy for
            policy_name: Custom policy name (default: AS<number>)
            
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
        command = self.bgpq3_command.copy()
        
        # Add bgpq3 arguments: -J (Juniper), -l (prefix-list), policy_name, AS_number
        # Using validated inputs prevents command injection
        command.extend(['-Jl', policy_name, f'AS{validated_as}'])
        
        self.logger.debug(f"Built secure bgpq3 command for AS{validated_as}: {' '.join(command)}")
        return command
    
    def generate_policy_for_as(self, 
                              as_number: int, 
                              policy_name: str = None) -> PolicyGenerationResult:
        """
        Generate BGP policy for single AS number
        
        Args:
            as_number: AS number to generate policy for
            policy_name: Custom policy name (default: AS<number>)
            
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
            
            self.logger.info(f"Generating policy for AS{validated_as} (policy: {policy_name})")
            
            command = self._build_bgpq3_command(validated_as, policy_name)
            start_time = time.time()
            
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
                bgpq3_mode=self.detected_mode.value if self.detected_mode else "unknown"
            )
        
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.command_timeout
            )
            
            execution_time = time.time() - start_time
            
            if result.returncode == 0:
                self.logger.debug(f"Successfully generated policy for AS{validated_as} in {execution_time:.2f}s")
                
                return PolicyGenerationResult(
                    as_number=validated_as,
                    policy_name=policy_name,
                    policy_content=result.stdout,
                    success=True,
                    execution_time=execution_time,
                    bgpq3_mode=self.detected_mode.value
                )
            else:
                error_msg = f"bgpq3 error (code {result.returncode}): {result.stderr.strip()}"
                self.logger.warning(f"Failed to generate policy for AS{validated_as}: {error_msg}")
                
                return PolicyGenerationResult(
                    as_number=validated_as,
                    policy_name=policy_name,
                    policy_content="",
                    success=False,
                    execution_time=execution_time,
                    error_message=error_msg,
                    bgpq3_mode=self.detected_mode.value
                )
                
        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            error_msg = f"Command timeout after {self.command_timeout}s"
            self.logger.warning(f"Timeout generating policy for AS{validated_as}")
            
            return PolicyGenerationResult(
                as_number=validated_as,
                policy_name=policy_name,
                policy_content="",
                success=False,
                execution_time=execution_time,
                error_message=error_msg,
                bgpq3_mode=self.detected_mode.value
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Execution error: {str(e)}"
            self.logger.error(f"Error generating policy for AS{validated_as}: {error_msg}")
            
            return PolicyGenerationResult(
                as_number=validated_as,
                policy_name=policy_name,
                policy_content="",
                success=False,
                execution_time=execution_time,
                error_message=error_msg,
                bgpq3_mode=self.detected_mode.value
            )
    
    def generate_policies_batch(self, 
                               as_numbers: Union[List[int], Set[int]],
                               custom_policy_names: Dict[int, str] = None) -> PolicyBatchResult:
        """
        Generate BGP policies for multiple AS numbers
        
        Args:
            as_numbers: List or set of AS numbers
            custom_policy_names: Optional mapping of AS number to custom policy name
            
        Returns:
            PolicyBatchResult with all policy generation results
        """
        import time
        
        if isinstance(as_numbers, set):
            as_numbers = sorted(as_numbers)
        
        custom_policy_names = custom_policy_names or {}
        
        self.logger.info(f"Starting batch policy generation for {len(as_numbers)} AS numbers")
        
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
        
        self.logger.info(f"Batch generation complete: {successful_count}/{len(as_numbers)} successful in {total_time:.2f}s")
        
        return batch_result
    
    def write_policies_to_files(self, 
                               batch_result: PolicyBatchResult,
                               output_dir: Union[str, Path] = "policies",
                               separate_files: bool = True,
                               combined_filename: str = "bgpq3_output.txt") -> List[str]:
        """
        Write policy generation results to files
        
        Args:
            batch_result: Result from generate_policies_batch
            output_dir: Directory to write policy files
            separate_files: Create separate file for each AS (default: True)
            combined_filename: Filename for combined output (when separate_files=False)
            
        Returns:
            List of created file paths
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)
        
        created_files = []
        
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
                        f.write(result.policy_content)
                        f.write("\n")
            
            created_files.append(str(combined_path))
            self.logger.info(f"Written combined policy file: {combined_path}")
        
        # Update batch result with output files
        batch_result.output_files = created_files
        
        self.logger.info(f"Policy files written: {len(created_files)} files in {output_dir}")
        return created_files
    
    def test_bgpq3_connection(self, test_as: int = 7922) -> bool:
        """
        Test bgpq3 connectivity with a known working AS
        
        Args:
            test_as: AS number to test with (default: 7922 - Comcast)
            
        Returns:
            True if bgpq3 is working, False otherwise
        """
        self.logger.info(f"Testing bgpq3 connectivity with AS{test_as}")
        
        try:
            result = self.generate_policy_for_as(test_as)
            
            if result.success and result.policy_content:
                self.logger.info(f"bgpq3 test successful: generated {len(result.policy_content)} characters in {result.execution_time:.2f}s")
                return True
            else:
                self.logger.error(f"bgpq3 test failed: {result.error_message}")
                return False
                
        except Exception as e:
            self.logger.error(f"bgpq3 test error: {e}")
            return False
    
    def get_status_info(self) -> Dict[str, str]:
        """Get status information about bgpq3 configuration"""
        return {
            'mode': self.detected_mode.value if self.detected_mode else 'unknown',
            'command': ' '.join(self.bgpq3_command) if self.bgpq3_command else 'none',
            'docker_image': self.docker_image,
            'timeout': str(self.command_timeout)
        }