"""
Parallel Processing Utilities for Otto BGP

Provides thread pool execution with progress tracking and error handling.
"""

import logging
import time
import signal
import atexit
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, ProcessPoolExecutor
from typing import List, Callable, Any, Dict, Optional, Tuple
from dataclasses import dataclass
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@dataclass
class ParallelResult:
    """Result from parallel execution"""
    item: Any
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    duration: float = 0.0


class ParallelExecutor:
    """Execute tasks in parallel with progress tracking and resource management"""
    
    def __init__(self, max_workers: int = 4, show_progress: bool = True):
        """
        Initialize parallel executor with resource leak prevention
        
        Args:
            max_workers: Maximum concurrent threads
            show_progress: Display progress indicators
        """
        self.max_workers = max_workers
        self.show_progress = show_progress
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Resource tracking
        self._active_executors = set()
        self._cleanup_lock = threading.Lock()
        self._shutdown_requested = False
        
        # Register cleanup on exit
        atexit.register(self._emergency_cleanup)
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup"""
        self.shutdown()
        return False  # Don't suppress exceptions
    
    def shutdown(self):
        """Explicitly shutdown all resources"""
        self.logger.debug("Shutting down ParallelExecutor")
        self._shutdown_requested = True
        self._cleanup_all_executors()
    
    def execute_batch(self, 
                     items: List[Any],
                     task_func: Callable,
                     task_name: str = "Processing",
                     **kwargs) -> List[ParallelResult]:
        """
        Execute task function on items in parallel with enhanced resource management
        
        Args:
            items: List of items to process
            task_func: Function to execute for each item
            task_name: Description for progress display
            **kwargs: Additional arguments for task_func
            
        Returns:
            List of ParallelResult objects
        """
        if self._shutdown_requested:
            self.logger.warning("Executor shutdown requested, aborting batch execution")
            return []
        
        results = []
        total = len(items)
        completed = 0
        
        if self.show_progress:
            print(f"\n{task_name} {total} items with {self.max_workers} workers...")
        
        # Use managed thread pool for resource safety
        with self._managed_thread_pool() as executor:
            if executor is None:
                self.logger.error("Failed to create thread pool executor")
                return []
            
            try:
                # Submit all tasks
                future_to_item = {
                    executor.submit(self._execute_task, task_func, item, **kwargs): item
                    for item in items
                }
                
                # Process results as they complete
                for future in as_completed(future_to_item):
                    if self._shutdown_requested:
                        self.logger.warning("Shutdown requested during execution, terminating batch")
                        break
                    
                    item = future_to_item[future]
                    try:
                        result = future.result(timeout=300)  # 5 minute timeout per task
                    except Exception as e:
                        self.logger.error(f"Task failed for item {item}: {e}")
                        result = ParallelResult(
                            item=item,
                            success=False,
                            error=str(e),
                            duration=0.0
                        )
                    
                    results.append(result)
                    
                    completed += 1
                    if self.show_progress:
                        self._show_progress(completed, total, result.success)
                        
            except Exception as e:
                self.logger.error(f"Error during batch execution: {e}")
                # Return partial results
                pass
        
        if self.show_progress:
            successful = sum(1 for r in results if r.success)
            print(f"\n{task_name} complete: {successful}/{total} successful")
        
        return results
    
    def _execute_task(self, task_func: Callable, item: Any, **kwargs) -> ParallelResult:
        """
        Execute single task with error handling
        
        Args:
            task_func: Function to execute
            item: Item to process
            **kwargs: Additional arguments for task_func
            
        Returns:
            ParallelResult with execution details
        """
        start_time = time.time()
        
        try:
            result = task_func(item, **kwargs)
            duration = time.time() - start_time
            
            return ParallelResult(
                item=item,
                success=True,
                result=result,
                duration=duration
            )
            
        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(f"Task failed for {item}: {e}")
            
            return ParallelResult(
                item=item,
                success=False,
                error=str(e),
                duration=duration
            )
    
    @contextmanager
    def _managed_thread_pool(self):
        """Context manager for thread pool with resource leak prevention"""
        executor = None
        try:
            executor = ThreadPoolExecutor(max_workers=self.max_workers)
            
            # Track active executor
            with self._cleanup_lock:
                self._active_executors.add(executor)
                
            yield executor
            
        except Exception as e:
            self.logger.error(f"Error creating thread pool executor: {e}")
            yield None
            
        finally:
            if executor is not None:
                try:
                    # Ensure proper shutdown
                    executor.shutdown(wait=True, timeout=30)
                    
                    # Remove from tracking
                    with self._cleanup_lock:
                        self._active_executors.discard(executor)
                        
                except Exception as e:
                    self.logger.warning(f"Error shutting down thread pool: {e}")
    
    def _signal_handler(self, signum, frame):
        """Handle termination signals with resource cleanup"""
        self.logger.info(f"Received signal {signum}, initiating graceful shutdown")
        self._shutdown_requested = True
        self._cleanup_all_executors()
    
    def _cleanup_all_executors(self):
        """Clean up all active executors"""
        with self._cleanup_lock:
            if not self._active_executors:
                return
            
            self.logger.info(f"Cleaning up {len(self._active_executors)} active executors")
            
            for executor in list(self._active_executors):
                try:
                    executor.shutdown(wait=False)  # Don't wait during emergency cleanup
                except Exception as e:
                    self.logger.warning(f"Error shutting down executor: {e}")
            
            self._active_executors.clear()
    
    def _emergency_cleanup(self):
        """Emergency cleanup for atexit handler"""
        try:
            self._cleanup_all_executors()
        except Exception:
            pass  # Silent cleanup in emergency
    
    def _show_progress(self, completed: int, total: int, last_success: bool):
        """
        Display progress indicator
        
        Args:
            completed: Number of completed tasks
            total: Total number of tasks
            last_success: Whether last task succeeded
        """
        percentage = (completed / total) * 100
        bar_length = 40
        filled = int(bar_length * completed / total)
        bar = '=' * filled + '-' * (bar_length - filled)
        
        status = "✓" if last_success else "✗"
        print(f"\r[{bar}] {percentage:.1f}% ({completed}/{total}) {status}", end='', flush=True)


def parallel_discover_routers(devices: List, 
                             collector,
                             inspector,
                             max_workers: Optional[int] = None) -> Tuple[List, List]:
    """
    Discover routers in parallel
    
    Args:
        devices: List of DeviceInfo objects
        collector: JuniperSSHCollector instance
        inspector: RouterInspector instance
        max_workers: Maximum parallel connections (None for auto-sizing)
        
    Returns:
        Tuple of (profiles, discovery_results)
    """
    # Adaptive worker sizing
    if max_workers is None:
        import os
        cpu_count = os.cpu_count() or 4
        max_workers = min(cpu_count * 2, len(devices), 16) or 1
    
    logger.info(f"Parallel workers selected: {max_workers} (items={len(devices)}, cpus={os.cpu_count()})")
    executor = ParallelExecutor(max_workers=max_workers)
    
    def discover_single_router(device):
        """Discover single router"""
        # Create profile
        profile = device.to_router_profile()
        
        # Collect BGP configuration
        bgp_config = collector.collect_bgp_config(device.address)
        profile.bgp_config = bgp_config
        
        # Perform discovery
        result = inspector.inspect_router(profile)
        
        return (profile, result)
    
    # Execute discovery in parallel
    results = executor.execute_batch(
        items=devices,
        task_func=discover_single_router,
        task_name="Discovering routers"
    )
    
    # Separate successful results
    profiles = []
    discovery_results = []
    
    for result in results:
        if result.success and result.result:
            profile, discovery = result.result
            profiles.append(profile)
            discovery_results.append(discovery)
    
    return profiles, discovery_results


def parallel_generate_policies(as_numbers: List[int],
                              wrapper,
                              max_workers: Optional[int] = None) -> List:
    """
    Generate BGP policies in parallel
    
    Args:
        as_numbers: List of AS numbers
        wrapper: BGPq4Wrapper instance
        max_workers: Maximum parallel bgpq4 processes (None for auto-sizing)
        
    Returns:
        List of PolicyGenerationResult objects
    """
    # Adaptive worker sizing  
    if max_workers is None:
        import os
        cpu_count = os.cpu_count() or 4
        max_workers = min(cpu_count * 2, len(as_numbers), 16) or 1
    
    logger.info(f"Parallel workers selected: {max_workers} (items={len(as_numbers)}, cpus={os.cpu_count()})")
    executor = ParallelExecutor(max_workers=max_workers)
    
    def generate_single_policy(as_number):
        """Generate policy for single AS"""
        return wrapper.generate_policy_for_as(as_number)
    
    # Execute generation in parallel
    results = executor.execute_batch(
        items=as_numbers,
        task_func=generate_single_policy,
        task_name="Generating policies"
    )
    
    # Extract policy results
    policy_results = []
    for result in results:
        if result.success and result.result:
            policy_results.append(result.result)
        else:
            # Create failed result
            from otto_bgp.generators.bgpq4_wrapper import PolicyGenerationResult
            policy_results.append(PolicyGenerationResult(
                as_number=result.item,
                policy_name=f"AS{result.item}",
                policy_content="",
                success=False,
                error_message=result.error or "Generation failed"
            ))
    
    return policy_results