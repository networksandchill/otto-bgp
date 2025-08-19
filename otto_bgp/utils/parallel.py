"""
Parallel Processing Utilities for Otto BGP

Provides thread pool execution with progress tracking and error handling.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Callable, Any, Dict, Optional, Tuple
from dataclasses import dataclass

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
    """Execute tasks in parallel with progress tracking"""
    
    def __init__(self, max_workers: int = 4, show_progress: bool = True):
        """
        Initialize parallel executor
        
        Args:
            max_workers: Maximum concurrent threads
            show_progress: Display progress indicators
        """
        self.max_workers = max_workers
        self.show_progress = show_progress
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def execute_batch(self, 
                     items: List[Any],
                     task_func: Callable,
                     task_name: str = "Processing",
                     **kwargs) -> List[ParallelResult]:
        """
        Execute task function on items in parallel
        
        Args:
            items: List of items to process
            task_func: Function to execute for each item
            task_name: Description for progress display
            **kwargs: Additional arguments for task_func
            
        Returns:
            List of ParallelResult objects
        """
        results = []
        total = len(items)
        completed = 0
        
        if self.show_progress:
            print(f"\n{task_name} {total} items with {self.max_workers} workers...")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_item = {
                executor.submit(self._execute_task, task_func, item, **kwargs): item
                for item in items
            }
            
            # Process results as they complete
            for future in as_completed(future_to_item):
                item = future_to_item[future]
                result = future.result()
                results.append(result)
                
                completed += 1
                if self.show_progress:
                    self._show_progress(completed, total, result.success)
        
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
                             max_workers: int = 4) -> Tuple[List, List]:
    """
    Discover routers in parallel
    
    Args:
        devices: List of DeviceInfo objects
        collector: JuniperSSHCollector instance
        inspector: RouterInspector instance
        max_workers: Maximum parallel connections
        
    Returns:
        Tuple of (profiles, discovery_results)
    """
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
                              max_workers: int = 4) -> List:
    """
    Generate BGP policies in parallel
    
    Args:
        as_numbers: List of AS numbers
        wrapper: BGPq4Wrapper instance
        max_workers: Maximum parallel bgpq4 processes
        
    Returns:
        List of PolicyGenerationResult objects
    """
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