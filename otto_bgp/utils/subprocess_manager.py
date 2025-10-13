#!/usr/bin/env python3
"""
Subprocess Resource Manager for Otto BGP

Provides comprehensive subprocess resource management with leak prevention:
- Context managers for process lifecycle
- Automatic cleanup on all exit paths
- Signal handling for graceful termination
- Resource monitoring and leak detection
"""

import logging
import signal
import subprocess
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class ProcessState(Enum):
    """Process execution states"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    TIMEOUT = "timeout"
    KILLED = "killed"
    FAILED = "failed"


@dataclass
class ProcessResult:
    """Result from managed subprocess execution"""

    returncode: int
    stdout: str
    stderr: str
    state: ProcessState
    execution_time: float
    command: List[str]
    pid: Optional[int] = None
    error_message: Optional[str] = None


class ManagedProcess:
    """
    Context manager for subprocess execution with comprehensive resource management

    Features:
    - Automatic process cleanup on all exit paths
    - Signal forwarding for graceful shutdown
    - Timeout handling with graceful termination
    - Resource monitoring and leak detection
    """

    def __init__(
        self,
        command: List[str],
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        capture_output: bool = True,
        text: bool = True,
        input_data: Optional[str] = None,
    ):
        """
        Initialize managed process

        Args:
            command: Command and arguments to execute
            timeout: Execution timeout in seconds
            cwd: Working directory for process
            env: Environment variables
            capture_output: Capture stdout/stderr
            text: Use text mode for I/O
            input_data: Data to send to stdin
        """
        self.command = command
        self.timeout = timeout
        self.cwd = cwd
        self.env = env
        self.capture_output = capture_output
        self.text = text
        self.input_data = input_data

        self.process: Optional[subprocess.Popen] = None
        self.start_time: Optional[float] = None
        self.logger = logging.getLogger(__name__)
        self._cleanup_done = False

        # Track active process for monitoring
        self._process_registry = ProcessRegistry.get_instance()

    def __enter__(self) -> "ManagedProcess":
        """Start the process and register it for cleanup"""
        try:
            self.start_time = time.time()

            # Configure subprocess options
            kwargs = {"cwd": self.cwd, "env": self.env, "text": self.text}

            if self.capture_output:
                kwargs.update(
                    {
                        "stdout": subprocess.PIPE,
                        "stderr": subprocess.PIPE,
                        "stdin": subprocess.PIPE
                        if self.input_data
                        else subprocess.DEVNULL,
                    }
                )

            # Start process
            self.process = subprocess.Popen(self.command, **kwargs)

            # Register for cleanup
            self._process_registry.register_process(self.process.pid, self.process)

            self.logger.debug(
                f"Started process {self.process.pid}: {' '.join(self.command)}"
            )

            return self

        except Exception as e:
            self.logger.error(f"Failed to start process: {e}")
            self._cleanup()
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensure process cleanup on exit"""
        self._cleanup()

    def wait_for_completion(self) -> ProcessResult:
        """
        Wait for process completion with proper resource management

        Returns:
            ProcessResult with execution details
        """
        if not self.process:
            raise RuntimeError("Process not started - use within context manager")

        try:
            # Handle timeout
            if self.timeout:
                stdout, stderr = self.process.communicate(
                    input=self.input_data, timeout=self.timeout
                )
            else:
                stdout, stderr = self.process.communicate(input=self.input_data)

            execution_time = time.time() - self.start_time if self.start_time else 0.0

            # Determine state based on exit code
            if self.process.returncode == 0:
                state = ProcessState.COMPLETED
            else:
                state = ProcessState.FAILED

            return ProcessResult(
                returncode=self.process.returncode,
                stdout=stdout or "",
                stderr=stderr or "",
                state=state,
                execution_time=execution_time,
                command=self.command,
                pid=self.process.pid,
            )

        except subprocess.TimeoutExpired:
            execution_time = time.time() - self.start_time if self.start_time else 0.0

            # Handle timeout with graceful termination
            self.logger.warning(
                f"Process {self.process.pid} timeout after {self.timeout}s"
            )

            # Try graceful termination first
            self.process.terminate()
            try:
                stdout, stderr = self.process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if graceful termination fails
                self.logger.warning(f"Force killing process {self.process.pid}")
                self.process.kill()
                stdout, stderr = self.process.communicate()

            return ProcessResult(
                returncode=self.process.returncode or -1,
                stdout=stdout or "",
                stderr=stderr or "",
                state=ProcessState.TIMEOUT,
                execution_time=execution_time,
                command=self.command,
                pid=self.process.pid,
                error_message=f"Process timeout after {self.timeout}s",
            )

        except Exception as e:
            execution_time = time.time() - self.start_time if self.start_time else 0.0
            self.logger.error(f"Error executing process {self.process.pid}: {e}")

            return ProcessResult(
                returncode=-1,
                stdout="",
                stderr=str(e),
                state=ProcessState.FAILED,
                execution_time=execution_time,
                command=self.command,
                pid=self.process.pid if self.process else None,
                error_message=str(e),
            )

    def terminate_gracefully(self, timeout: int = 5):
        """
        Gracefully terminate the process

        Args:
            timeout: Time to wait for graceful termination before force kill
        """
        if not self.process:
            return

        try:
            # Send SIGTERM
            self.process.terminate()
            self.process.wait(timeout=timeout)
            self.logger.debug(f"Process {self.process.pid} terminated gracefully")

        except subprocess.TimeoutExpired:
            # Force kill if graceful termination fails
            self.logger.warning(
                f"Force killing unresponsive process {self.process.pid}"
            )
            self.process.kill()
            self.process.wait()

    def _cleanup(self):
        """Internal cleanup method"""
        if self._cleanup_done:
            return

        self._cleanup_done = True

        if self.process:
            try:
                # Unregister from process registry
                self._process_registry.unregister_process(self.process.pid)

                # Ensure process is terminated
                if self.process.poll() is None:
                    self.terminate_gracefully()

                self.logger.debug(f"Cleaned up process {self.process.pid}")

            except Exception as e:
                self.logger.error(f"Error during process cleanup: {e}")


class ProcessRegistry:
    """
    Global registry for tracking active processes to prevent resource leaks

    Singleton that maintains a registry of all active subprocess instances
    and provides cleanup mechanisms for emergency situations.
    """

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.active_processes: Dict[int, subprocess.Popen] = {}
        self.process_lock = threading.Lock()
        self.logger = logging.getLogger(__name__)

        # Register signal handlers for cleanup
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    @classmethod
    def get_instance(cls):
        """Get singleton instance of process registry"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def register_process(self, pid: int, process: subprocess.Popen):
        """Register a process for tracking"""
        with self.process_lock:
            self.active_processes[pid] = process
            self.logger.debug(
                f"Registered process {pid} (total active: {len(self.active_processes)})"
            )

    def unregister_process(self, pid: int):
        """Unregister a process from tracking"""
        with self.process_lock:
            if pid in self.active_processes:
                del self.active_processes[pid]
                self.logger.debug(
                    f"Unregistered process {pid} (total active: {len(self.active_processes)})"
                )

    def cleanup_all_processes(self):
        """Emergency cleanup of all tracked processes"""
        with self.process_lock:
            if not self.active_processes:
                return

            self.logger.warning(
                f"Emergency cleanup of {len(self.active_processes)} active processes"
            )

            for pid, process in list(self.active_processes.items()):
                try:
                    if process.poll() is None:
                        self.logger.warning(f"Terminating orphaned process {pid}")
                        process.terminate()

                        # Give process time to terminate gracefully
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            self.logger.warning(
                                f"Force killing unresponsive process {pid}"
                            )
                            process.kill()
                            process.wait()

                    del self.active_processes[pid]

                except Exception as e:
                    self.logger.error(f"Error cleaning up process {pid}: {e}")

    def get_process_stats(self) -> Dict[str, Any]:
        """Get statistics about active processes"""
        with self.process_lock:
            stats = {"active_count": len(self.active_processes), "processes": []}

            for pid, process in self.active_processes.items():
                try:
                    # Check if process is still running
                    poll_result = process.poll()
                    stats["processes"].append(
                        {
                            "pid": pid,
                            "running": poll_result is None,
                            "returncode": poll_result,
                        }
                    )
                except Exception as e:
                    stats["processes"].append(
                        {"pid": pid, "running": False, "error": str(e)}
                    )

            return stats

    def _signal_handler(self, signum, frame):
        """Handle termination signals with process cleanup"""
        self.logger.info(
            f"Received signal {signum}, cleaning up {len(self.active_processes)} processes"
        )
        self.cleanup_all_processes()


@contextmanager
def managed_subprocess(command: List[str], **kwargs):
    """
    Convenience context manager for subprocess execution

    Args:
        command: Command and arguments to execute
        **kwargs: Additional arguments for ManagedProcess

    Yields:
        ProcessResult with execution details

    Example:
        with managed_subprocess(['bgpq4', '-Jl', 'test', 'AS65000']) as result:
            if result.state == ProcessState.COMPLETED:
                print(result.stdout)
    """
    with ManagedProcess(command, **kwargs) as managed:
        result = managed.wait_for_completion()
        yield result


def run_with_resource_management(
    command: List[str], timeout: Optional[int] = None, **kwargs
) -> ProcessResult:
    """
    Execute subprocess with comprehensive resource management

    This is a drop-in replacement for subprocess.run() with enhanced
    resource management and leak prevention.

    Args:
        command: Command and arguments to execute
        timeout: Execution timeout in seconds
        **kwargs: Additional subprocess arguments

    Returns:
        ProcessResult with execution details
    """
    with managed_subprocess(command, timeout=timeout, **kwargs) as result:
        return result
