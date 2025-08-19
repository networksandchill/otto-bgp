# otto_bgp.pipeline Module - Developer Guide

## Overview

The `pipeline` module provides **workflow orchestration** for Otto BGP's complete processing pipeline. It coordinates data flow between collectors, discovery, processors, generators, and appliers while managing error handling, progress tracking, and result aggregation.

**Design Philosophy**: Orchestrated workflow with checkpoint-based execution and comprehensive error recovery

## Architecture Role

```
Pipeline Orchestration Flow:
[PIPELINE] ──> Collectors ──> Discovery ──> Processors ──> Generators ──> [Results]
     │              │             │            │             │
     └─── Error ────┴─── Error ───┴─ Error ────┴─── Error ───┘
     │         Handling    Handling    Handling       Handling
     └─── Progress Tracking & Checkpoint Management ───────────┘
```

**Key Responsibilities**:
- Coordinate execution across all Otto BGP modules
- Manage data flow and state transitions
- Implement error recovery and partial failure handling
- Provide progress tracking and status reporting
- Handle resource management and cleanup

## Core Components

### 1. WorkflowOrchestrator (`workflow.py`)
**Purpose**: Main pipeline execution coordinator

**Key Features**:
- Sequential stage execution with checkpoint validation
- Error recovery and partial failure handling
- Progress tracking with real-time status updates
- Resource management and cleanup
- Parallel processing where appropriate

**Execution Pattern**:
```python
class WorkflowOrchestrator:
    def execute_pipeline(self, devices: List[DeviceInfo]) -> PipelineResult:
        """Execute complete Otto BGP pipeline"""
        
        # Initialize pipeline state
        context = PipelineContext(devices=devices)
        
        try:
            # Stage 1: Device Collection
            context = self.execute_collection_stage(context)
            
            # Stage 2: BGP Discovery
            context = self.execute_discovery_stage(context)
            
            # Stage 3: AS Processing
            context = self.execute_processing_stage(context)
            
            # Stage 4: Policy Generation
            context = self.execute_generation_stage(context)
            
            # Stage 5: Policy Application (v0.3.2)
            context = self.execute_application_stage(context)
            
            # Stage 6: Results Compilation
            return self.compile_results(context)
            
        except PipelineExecutionError as e:
            return self.handle_pipeline_failure(context, e)
        finally:
            self.cleanup_resources(context)
```

## Design Choices

### Stage-Based Execution
**Choice**: Sequential stages with checkpoint validation
**Rationale**:
- Clear separation of concerns between modules
- Checkpoint-based error recovery
- Progress tracking and status reporting
- Easier debugging and testing
- Resource management at stage boundaries

### Context Object Pattern
**Choice**: Immutable context passed between stages
**Rationale**:
- Thread safety for parallel operations
- Clear data flow documentation
- Rollback capability for error recovery
- Audit trail of pipeline execution
- State isolation between stages

### Graceful Degradation
**Choice**: Continue execution on partial failures
**Rationale**:
- Maximize useful output from partial data
- Operational resilience in production
- Clear error reporting without total failure
- Progressive enhancement pattern

### Resource Management
**Choice**: Explicit resource cleanup at stage boundaries
**Rationale**:
- Prevent resource leaks in long-running operations
- Clean up temporary files and connections
- Memory management for large datasets
- Proper shutdown handling

## Pipeline Execution Model

### PipelineContext Structure
```python
@dataclass
class PipelineContext:
    """Immutable context passed between pipeline stages"""
    
    # Input data
    devices: List[DeviceInfo]
    
    # Stage results
    collection_results: List[DeviceCollectionResult] = field(default_factory=list)
    router_profiles: List[RouterProfile] = field(default_factory=list)
    discovery_mappings: Dict = field(default_factory=dict)
    as_extraction_results: Dict = field(default_factory=dict)
    policy_results: List[PolicyResult] = field(default_factory=list)
    
    # Pipeline state
    current_stage: str = "initialized"
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    start_time: datetime = field(default_factory=datetime.now)
    stage_timings: Dict[str, float] = field(default_factory=dict)
    
    # Error tracking
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    failed_devices: List[str] = field(default_factory=list)
    
    # Configuration
    config: Dict = field(default_factory=dict)
    output_dir: Path = Path("./output")
    parallel_workers: int = 5
```

### Stage Implementation Pattern
```python
def execute_collection_stage(self, context: PipelineContext) -> PipelineContext:
    """Execute device collection stage with error handling"""
    
    logger.info(f"Starting collection stage - {len(context.devices)} devices")
    stage_start = time.time()
    
    try:
        # Initialize collector
        collector = JuniperSSHCollector(
            ssh_username=context.config.get('ssh_username'),
            ssh_key_path=context.config.get('ssh_key_path'),
            connection_timeout=context.config.get('connection_timeout', 30)
        )
        
        # Execute parallel collection
        collection_results = collector.collect_from_devices_parallel(
            devices=context.devices,
            max_workers=context.parallel_workers
        )
        
        # Process results
        successful_results = [r for r in collection_results if r.success]
        failed_results = [r for r in collection_results if not r.success]
        
        # Convert successful collections to router profiles
        router_profiles = []
        for result in successful_results:
            profile = result.device.to_router_profile()
            profile.bgp_config = result.bgp_data
            router_profiles.append(profile)
        
        # Track failures
        failed_devices = [r.device.hostname for r in failed_results]
        
        # Update context
        new_context = dataclasses.replace(
            context,
            collection_results=collection_results,
            router_profiles=router_profiles,
            failed_devices=context.failed_devices + failed_devices,
            current_stage="collection_complete",
            stage_timings={
                **context.stage_timings,
                'collection': time.time() - stage_start
            }
        )
        
        # Log stage completion
        logger.info(f"Collection stage complete - {len(successful_results)}/{len(context.devices)} successful")
        
        if failed_devices:
            logger.warning(f"Collection failures: {failed_devices}")
            new_context = dataclasses.replace(
                new_context,
                warnings=context.warnings + [f"Collection failed for: {', '.join(failed_devices)}"]
            )
        
        return new_context
        
    except Exception as e:
        logger.error(f"Collection stage failed: {e}")
        raise PipelineExecutionError(f"Collection stage failure: {e}") from e
```

### Discovery Stage Implementation
```python
def execute_discovery_stage(self, context: PipelineContext) -> PipelineContext:
    """Execute BGP discovery stage"""
    
    if not context.router_profiles:
        logger.warning("No router profiles available for discovery")
        return dataclasses.replace(
            context,
            current_stage="discovery_skipped",
            warnings=context.warnings + ["Discovery skipped - no successful collections"]
        )
    
    logger.info(f"Starting discovery stage - {len(context.router_profiles)} routers")
    stage_start = time.time()
    
    try:
        # Initialize discovery components
        inspector = RouterInspector()
        yaml_generator = YAMLGenerator(output_dir=context.output_dir)
        
        # Enhance profiles with discovery data
        enhanced_profiles = []
        discovery_errors = []
        
        for profile in context.router_profiles:
            try:
                # Inspect router BGP configuration
                discovery_result = inspector.inspect_router(profile)
                
                # Update profile with discovery results
                profile.discovered_as_numbers = discovery_result.as_numbers
                profile.bgp_groups = discovery_result.bgp_groups
                
                enhanced_profiles.append(profile)
                
            except Exception as e:
                logger.error(f"Discovery failed for {profile.hostname}: {e}")
                discovery_errors.append(f"{profile.hostname}: {e}")
                
                # Keep original profile
                enhanced_profiles.append(profile)
        
        # Generate YAML mappings
        mappings = yaml_generator.generate_mappings(enhanced_profiles)
        yaml_generator.save_with_history(mappings, context.output_dir)
        
        # Update context
        new_context = dataclasses.replace(
            context,
            router_profiles=enhanced_profiles,
            discovery_mappings=mappings,
            current_stage="discovery_complete",
            stage_timings={
                **context.stage_timings,
                'discovery': time.time() - stage_start
            }
        )
        
        if discovery_errors:
            new_context = dataclasses.replace(
                new_context,
                warnings=context.warnings + [f"Discovery errors: {'; '.join(discovery_errors)}"]
            )
        
        logger.info(f"Discovery stage complete - {len(enhanced_profiles)} routers processed")
        return new_context
        
    except Exception as e:
        logger.error(f"Discovery stage failed: {e}")
        raise PipelineExecutionError(f"Discovery stage failure: {e}") from e
```

### Generation Stage Implementation
```python
def execute_generation_stage(self, context: PipelineContext) -> PipelineContext:
    """Execute policy generation stage"""
    
    # Collect all AS numbers from all routers
    all_as_numbers = set()
    for profile in context.router_profiles:
        all_as_numbers.update(profile.discovered_as_numbers)
    
    if not all_as_numbers:
        logger.warning("No AS numbers discovered for policy generation")
        return dataclasses.replace(
            context,
            current_stage="generation_skipped",
            warnings=context.warnings + ["Generation skipped - no AS numbers discovered"]
        )
    
    logger.info(f"Starting generation stage - {len(all_as_numbers)} AS numbers")
    stage_start = time.time()
    
    try:
        # Initialize generator
        wrapper = BGPq4Wrapper(
            mode=context.config.get('bgpq4_mode', 'auto'),
            timeout=context.config.get('bgpq4_timeout', 45)
        )
        
        combiner = PolicyCombiner()
        
        # Generate policies for all AS numbers
        policy_results = wrapper.generate_policies_batch(list(all_as_numbers))
        
        # Organize policies by router if router-specific output requested
        if context.config.get('separate_files', False):
            for profile in context.router_profiles:
                if profile.discovered_as_numbers:
                    router_policies = [
                        p for p in policy_results 
                        if p.as_number in profile.discovered_as_numbers and p.success
                    ]
                    
                    if router_policies:
                        router_dir = context.output_dir / "routers" / profile.hostname
                        combiner.write_separate_files(router_policies, router_dir)
        else:
            # Write combined policy file
            successful_policies = [p for p in policy_results if p.success]
            if successful_policies:
                output_file = context.output_dir / "bgp_policies.txt"
                combiner.write_combined_file(successful_policies, output_file)
        
        # Update context
        new_context = dataclasses.replace(
            context,
            policy_results=policy_results,
            current_stage="generation_complete",
            stage_timings={
                **context.stage_timings,
                'generation': time.time() - stage_start
            }
        )
        
        # Track failures
        failed_policies = [p for p in policy_results if not p.success]
        if failed_policies:
            failed_as = [str(p.as_number) for p in failed_policies]
            new_context = dataclasses.replace(
                new_context,
                warnings=context.warnings + [f"Policy generation failed for AS: {', '.join(failed_as)}"]
            )
        
        successful_count = len([p for p in policy_results if p.success])
        logger.info(f"Generation stage complete - {successful_count}/{len(policy_results)} policies generated")
        
        return new_context
        
    except Exception as e:
        logger.error(f"Generation stage failed: {e}")
        raise PipelineExecutionError(f"Generation stage failure: {e}") from e
```

### Application Stage Implementation (v0.3.2)

The application stage provides autonomous policy application with comprehensive safety controls and email audit trails.

```python
def execute_application_stage(self, context: PipelineContext) -> PipelineContext:
    """Execute policy application stage with autonomous mode support"""
    
    # Skip application if no policies generated
    if not context.policy_results or not any(p.success for p in context.policy_results):
        logger.warning("No successful policies available for application")
        return dataclasses.replace(
            context,
            current_stage="application_skipped",
            warnings=context.warnings + ["Application skipped - no successful policies"]
        )
    
    # Check if autonomous mode is enabled
    autonomous_config = context.config.get('autonomous_mode', {})
    autonomous_enabled = autonomous_config.get('enabled', False)
    
    if not autonomous_enabled:
        logger.info("Autonomous mode disabled - policies generated but not applied")
        return dataclasses.replace(
            context,
            current_stage="application_manual",
            warnings=context.warnings + ["Manual policy application required"]
        )
    
    logger.info(f"Starting autonomous application stage")
    stage_start = time.time()
    
    try:
        # Initialize unified safety manager and applier
        unified_safety_manager = UnifiedSafetyManager()
        
        application_results = []
        
        # Process each router with policies
        for profile in context.router_profiles:
            if not profile.discovered_as_numbers:
                continue
            
            # Get policies for this router
            router_policies = [
                p for p in context.policy_results 
                if p.as_number in profile.discovered_as_numbers and p.success
            ]
            
            if not router_policies:
                continue
            
            logger.info(f"Processing {profile.hostname} - {len(router_policies)} policies")
            
            # Autonomous decision logic
            can_auto_apply = unified_safety_manager.should_auto_apply(router_policies, context.config)
            
            if can_auto_apply:
                # Apply policies autonomously
                result = self._apply_policies_autonomous(
                    profile, router_policies, unified_safety_manager, context.config
                )
                application_results.append(result)
            else:
                # Log manual application requirement
                logger.info(f"Manual approval required for {profile.hostname}")
                application_results.append(ApplicationResult(
                    router=profile.hostname,
                    success=False,
                    autonomous=False,
                    reason="Manual approval required - high risk or large change set"
                ))
        
        # Update context with application results
        new_context = dataclasses.replace(
            context,
            application_results=application_results,
            current_stage="application_complete",
            stage_timings={
                **context.stage_timings,
                'application': time.time() - stage_start
            }
        )
        
        # Track application statistics
        autonomous_count = len([r for r in application_results if r.autonomous])
        successful_count = len([r for r in application_results if r.success])
        
        logger.info(f"Application stage complete - {successful_count} successful, {autonomous_count} autonomous")
        
        return new_context
        
    except Exception as e:
        logger.error(f"Application stage failed: {e}")
        raise PipelineExecutionError(f"Application stage failure: {e}") from e

def _apply_policies_autonomous(self, profile: RouterProfile, policies: List[PolicyResult], 
                              unified_safety_manager: UnifiedSafetyManager, config: Dict) -> ApplicationResult:
    """Apply policies autonomously with safety controls and email notifications"""
    
    try:
        # Initialize applier with unified safety manager integration
        applier = JuniperPolicyApplier(
            logger=self.logger,
            unified_safety_manager=unified_safety_manager,
            autonomous_mode=True
        )
        
        # Apply policies with confirmation
        result = applier.apply_with_confirmation(
            policies=policies,
            router=profile.hostname,
            confirm_timeout=120,
            comment=f"Otto BGP autonomous update - {len(policies)} policies"
        )
        
        return ApplicationResult(
            router=profile.hostname,
            success=result.success,
            autonomous=True,
            policies_applied=len(policies),
            commit_id=result.commit_id,
            email_notifications_sent=result.email_notifications_sent
        )
        
    except Exception as e:
        logger.error(f"Autonomous application failed for {profile.hostname}: {e}")
        
        return ApplicationResult(
            router=profile.hostname,
            success=False,
            autonomous=True,
            error_message=str(e),
            rollback_attempted=True
        )
```

#### Autonomous Mode Integration

**Risk-Based Decision Flow:**
```python
# 1. Safety Assessment
safety_result = unified_safety_manager.validate_policies_before_apply(policies)

# 2. Autonomous Decision
if safety_result.risk_level == 'low' and autonomous_config.get('enabled'):
    # Auto-apply with email notifications
    result = apply_with_full_audit_trail(policies)
else:
    # Require manual approval
    result = queue_for_manual_review(policies)
```

**Email Audit Trail Integration:**
```python
# Email notifications sent automatically for all NETCONF events:
# - Connection establishment/failure
# - Configuration preview generation
# - Commit success/failure with full diff
# - Rollback operations
# - Disconnection confirmation
```

**Three-Tier Operation Modes:**
- **User Mode**: Generation only, no application
- **System Mode**: Enhanced safety controls, manual application
- **Autonomous Mode**: Risk-based automatic application with email audit trail

#### Pipeline Context Enhancement (v0.3.2)

```python
@dataclass
class PipelineContext:
    """Enhanced pipeline context with autonomous mode support"""
    
    # Existing fields
    devices: List[DeviceInfo] = field(default_factory=list)
    router_profiles: List[RouterProfile] = field(default_factory=list)
    policy_results: List[PolicyResult] = field(default_factory=list)
    
    # New autonomous mode fields (v0.3.2)
    application_results: List[ApplicationResult] = field(default_factory=list)
    autonomous_config: Dict = field(default_factory=dict)
    safety_manager: Optional[UnifiedSafetyManager] = None
    email_notifications_sent: int = 0
    
    # Enhanced configuration
    config: Dict = field(default_factory=dict)
    current_stage: str = "initialized"
    stage_timings: Dict[str, float] = field(default_factory=dict)

@dataclass
class ApplicationResult:
    """Result of policy application stage"""
    router: str
    success: bool
    autonomous: bool = False
    policies_applied: int = 0
    commit_id: Optional[str] = None
    error_message: Optional[str] = None
    rollback_attempted: bool = False
    email_notifications_sent: int = 0
    risk_level: str = "unknown"
    manual_approval_required: bool = False
```

## Error Handling Strategy

### Pipeline Exception Hierarchy
```python
class PipelineExecutionError(Exception):
    """Base exception for pipeline execution errors"""
    pass

class StageExecutionError(PipelineExecutionError):
    """Error during specific stage execution"""
    def __init__(self, stage: str, message: str, original_error: Exception = None):
        self.stage = stage
        self.original_error = original_error
        super().__init__(f"Stage '{stage}' failed: {message}")

class ResourceError(PipelineExecutionError):
    """Resource management error"""
    pass

class ConfigurationError(PipelineExecutionError):
    """Pipeline configuration error"""
    pass
```

### Graceful Degradation
```python
def handle_stage_failure(self, context: PipelineContext, stage: str, error: Exception) -> PipelineContext:
    """Handle stage failure with graceful degradation"""
    
    logger.error(f"Stage '{stage}' failed: {error}")
    
    # Determine if pipeline can continue
    can_continue = self.assess_continuation_viability(context, stage, error)
    
    if can_continue:
        # Log degraded operation
        logger.warning(f"Continuing pipeline with degraded functionality after {stage} failure")
        
        return dataclasses.replace(
            context,
            current_stage=f"{stage}_failed_continuing",
            errors=context.errors + [f"{stage}: {str(error)}"],
            warnings=context.warnings + [f"Pipeline continuing with degraded functionality"]
        )
    else:
        # Abort pipeline
        raise PipelineExecutionError(f"Critical failure in {stage}: {error}")

def assess_continuation_viability(self, context: PipelineContext, stage: str, error: Exception) -> bool:
    """Assess whether pipeline can continue after stage failure"""
    
    # Collection failure - can't continue without data
    if stage == "collection" and not context.router_profiles:
        return False
    
    # Discovery failure - can continue with basic AS extraction
    if stage == "discovery":
        return True
    
    # Generation failure - partial policies may be available
    if stage == "generation":
        return len([r for r in context.policy_results if r.success]) > 0
    
    return True
```

## Progress Tracking and Monitoring

### Progress Reporter
```python
class ProgressReporter:
    """Real-time progress tracking for pipeline execution"""
    
    def __init__(self, total_devices: int):
        self.total_devices = total_devices
        self.current_stage = "initializing"
        self.completed_devices = 0
        self.start_time = time.time()
        
    def update_stage(self, stage: str):
        """Update current stage"""
        self.current_stage = stage
        logger.info(f"Pipeline stage: {stage}")
    
    def update_device_progress(self, completed: int):
        """Update device processing progress"""
        self.completed_devices = completed
        progress_pct = (completed / self.total_devices) * 100
        
        elapsed = time.time() - self.start_time
        if completed > 0:
            estimated_total = elapsed * (self.total_devices / completed)
            remaining = estimated_total - elapsed
            
            logger.info(f"Progress: {completed}/{self.total_devices} devices ({progress_pct:.1f}%) - "
                       f"ETA: {remaining:.0f}s")
    
    def get_status(self) -> Dict:
        """Get current pipeline status"""
        return {
            'stage': self.current_stage,
            'progress': {
                'completed_devices': self.completed_devices,
                'total_devices': self.total_devices,
                'percentage': (self.completed_devices / self.total_devices) * 100
            },
            'timing': {
                'elapsed_seconds': time.time() - self.start_time,
                'start_time': self.start_time
            }
        }
```

### Performance Monitoring
```python
def monitor_pipeline_performance(self, context: PipelineContext) -> Dict:
    """Generate performance metrics for pipeline execution"""
    
    total_time = sum(context.stage_timings.values())
    
    metrics = {
        'execution_summary': {
            'total_time_seconds': total_time,
            'devices_processed': len(context.router_profiles),
            'as_numbers_discovered': len(context.discovery_mappings.get('as_to_routers', {})),
            'policies_generated': len([p for p in context.policy_results if p.success])
        },
        'stage_performance': {
            stage: {
                'duration_seconds': duration,
                'percentage_of_total': (duration / total_time) * 100 if total_time > 0 else 0
            }
            for stage, duration in context.stage_timings.items()
        },
        'throughput': {
            'devices_per_second': len(context.router_profiles) / total_time if total_time > 0 else 0,
            'policies_per_second': len(context.policy_results) / total_time if total_time > 0 else 0
        }
    }
    
    return metrics
```

## Integration Points

### CLI Interface
```python
def run_pipeline_command(args) -> int:
    """CLI entry point for pipeline execution"""
    
    try:
        # Load devices from CSV
        devices = load_devices_from_csv(args.devices_csv)
        
        # Initialize pipeline
        orchestrator = WorkflowOrchestrator()
        
        # Configure pipeline
        config = {
            'ssh_username': args.ssh_username,
            'ssh_key_path': args.ssh_key_path,
            'bgpq4_mode': 'dev' if args.dev else 'auto',
            'separate_files': args.separate,
            'parallel_workers': args.max_workers
        }
        
        # Execute pipeline
        result = orchestrator.execute_pipeline(devices, config, args.output_dir)
        
        # Display results
        print(result.to_summary())
        
        # Return appropriate exit code
        return 0 if result.success else 1
        
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        return 2
```

### Programmatic API
```python
from otto_bgp.pipeline import WorkflowOrchestrator
from otto_bgp.models import DeviceInfo

# Initialize pipeline
orchestrator = WorkflowOrchestrator()

# Configure devices
devices = [
    DeviceInfo(address="192.168.1.1", hostname="router1"),
    DeviceInfo(address="192.168.1.2", hostname="router2")
]

# Execute pipeline
result = orchestrator.execute_pipeline(
    devices=devices,
    config={'ssh_username': 'bgp-read'},
    output_dir=Path('./output')
)

# Process results
if result.success:
    print(f"Pipeline completed successfully")
    print(f"Processed {len(result.router_profiles)} routers")
    print(f"Generated policies for {len(result.get_all_as_numbers())} AS numbers")
else:
    print(f"Pipeline failed with {len(result.errors)} errors")
    for error in result.errors:
        print(f"  - {error}")
```

## Best Practices

### Pipeline Design
- Keep stages independent and testable
- Use immutable context objects
- Implement comprehensive error handling
- Provide clear progress feedback
- Clean up resources at stage boundaries

### Error Recovery
- Continue on partial failures when possible
- Provide detailed error context
- Implement retry logic for transient failures
- Log all errors with appropriate severity

### Performance
- Use parallel processing where appropriate
- Monitor and log stage performance
- Implement reasonable timeouts
- Optimize resource usage across stages

### Monitoring
- Provide real-time progress updates
- Log structured metrics for analysis
- Track stage-level performance
- Generate comprehensive execution reports