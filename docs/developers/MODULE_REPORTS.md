# otto_bgp.reports Module - Developer Guide

## Overview

The `reports` module provides **operational reporting and analysis** capabilities for Otto BGP pipeline execution. It generates comprehensive reports, matrices, and visualizations for monitoring network discovery, policy generation success rates, and operational health.

**Design Philosophy**: Data-driven operational insights with clear visualizations and actionable metrics

## Architecture Role

```
Otto BGP Reporting Flow:
Pipeline Results → [REPORTS] → Operational Dashboards
     │                ↑              ↑
     │                │              │
Discovery Data ────────┴─── Analysis ┴─── Monitoring Systems
AS Numbers                  Matrices      Alerting
Router Status              Statistics    Trend Analysis
```

**Key Responsibilities**:
- Generate execution summary reports
- Create router/AS discovery matrices
- Produce operational health dashboards
- Track performance metrics and trends
- Provide change detection reporting
- Support monitoring system integration

## Core Components

### 1. MatrixGenerator (`matrix.py`)
**Purpose**: Generate router-AS relationship matrices and discovery reports

**Key Features**:
- Router-to-AS mapping visualizations
- Discovery success/failure matrices
- Change detection between discovery runs
- AS distribution analysis across routers
- Performance metrics compilation

**Report Types**:
```python
class MatrixGenerator:
    """Generate operational matrices and reports"""
    
    def generate_discovery_matrix(self, pipeline_result: PipelineResult) -> DiscoveryMatrix:
        """Generate router discovery success matrix"""
        
    def generate_as_distribution_matrix(self, router_profiles: List[RouterProfile]) -> ASDistributionMatrix:
        """Generate AS number distribution across routers"""
        
    def generate_change_detection_report(self, previous: Dict, current: Dict) -> ChangeReport:
        """Generate report of changes between discovery runs"""
        
    def generate_performance_summary(self, pipeline_result: PipelineResult) -> PerformanceReport:
        """Generate pipeline performance metrics"""
```

## Design Choices

### Matrix-Based Visualization
**Choice**: Use matrix/tabular formats for router-AS relationships
**Rationale**:
- Clear visualization of complex relationships
- Easy identification of patterns and anomalies
- Support for large-scale network analysis
- Integration with existing monitoring tools

### Modular Report Generation
**Choice**: Separate report types with standardized interfaces
**Rationale**:
- Flexible reporting based on operational needs
- Easy extension with new report types
- Independent testing and maintenance
- Custom formatting for different audiences

### Time-Series Change Tracking
**Choice**: Compare current state with historical data
**Rationale**:
- Operational change detection and alerting
- Trend analysis for capacity planning
- Audit trail for network modifications
- Support for rollback decision making

### Machine-Readable Output
**Choice**: Structured output formats (JSON, CSV, YAML)
**Rationale**:
- Integration with monitoring and alerting systems
- Automated processing and analysis
- Data pipeline compatibility
- Custom dashboard development

## Report Generation Implementation

### Discovery Matrix Generation
```python
@dataclass
class DiscoveryMatrix:
    """Router discovery results matrix"""
    routers: List[str]                          # Router hostnames
    discovery_status: Dict[str, bool]           # Success/failure per router
    as_count_per_router: Dict[str, int]        # AS numbers discovered per router
    bgp_groups_per_router: Dict[str, int]      # BGP groups per router
    collection_time_per_router: Dict[str, float]  # Collection duration per router
    errors_per_router: Dict[str, List[str]]    # Error messages per router
    
    @property
    def success_rate(self) -> float:
        """Calculate overall discovery success rate"""
        if not self.routers:
            return 0.0
        successful = sum(1 for status in self.discovery_status.values() if status)
        return successful / len(self.routers)
    
    def to_csv(self) -> str:
        """Export matrix to CSV format"""
        lines = ["Router,Status,AS_Count,BGP_Groups,Collection_Time,Errors"]
        
        for router in self.routers:
            status = "SUCCESS" if self.discovery_status.get(router, False) else "FAILED"
            as_count = self.as_count_per_router.get(router, 0)
            bgp_groups = self.bgp_groups_per_router.get(router, 0)
            collection_time = self.collection_time_per_router.get(router, 0.0)
            errors = "; ".join(self.errors_per_router.get(router, []))
            
            lines.append(f"{router},{status},{as_count},{bgp_groups},{collection_time:.2f},\"{errors}\"")
        
        return "\n".join(lines)

def generate_discovery_matrix(self, pipeline_result: PipelineResult) -> DiscoveryMatrix:
    """Generate comprehensive discovery matrix"""
    
    routers = [profile.hostname for profile in pipeline_result.router_profiles]
    discovery_status = {}
    as_count_per_router = {}
    bgp_groups_per_router = {}
    collection_time_per_router = {}
    errors_per_router = {}
    
    # Process each router profile
    for profile in pipeline_result.router_profiles:
        hostname = profile.hostname
        
        # Determine discovery status
        has_bgp_config = bool(profile.bgp_config)
        has_as_numbers = bool(profile.discovered_as_numbers)
        discovery_status[hostname] = has_bgp_config and has_as_numbers
        
        # Count discovered elements
        as_count_per_router[hostname] = len(profile.discovered_as_numbers)
        bgp_groups_per_router[hostname] = len(profile.bgp_groups)
        
        # Extract timing information
        collection_time = profile.metadata.get('collection_duration', 0.0)
        collection_time_per_router[hostname] = collection_time
        
        # Collect errors
        router_errors = []
        if not has_bgp_config:
            router_errors.append("No BGP configuration collected")
        if not has_as_numbers:
            router_errors.append("No AS numbers discovered")
        
        errors_per_router[hostname] = router_errors
    
    return DiscoveryMatrix(
        routers=routers,
        discovery_status=discovery_status,
        as_count_per_router=as_count_per_router,
        bgp_groups_per_router=bgp_groups_per_router,
        collection_time_per_router=collection_time_per_router,
        errors_per_router=errors_per_router
    )
```

### AS Distribution Analysis
```python
@dataclass
class ASDistributionMatrix:
    """AS number distribution across routers"""
    as_numbers: List[int]                      # All discovered AS numbers
    router_names: List[str]                    # All router hostnames
    as_router_matrix: Dict[int, List[str]]     # AS -> routers mapping
    router_as_matrix: Dict[str, List[int]]     # Router -> AS numbers mapping
    as_frequency: Dict[int, int]               # How many routers have each AS
    
    def get_common_as_numbers(self, min_routers: int = 2) -> List[int]:
        """Get AS numbers present on multiple routers"""
        return [as_num for as_num, count in self.as_frequency.items() if count >= min_routers]
    
    def get_unique_as_numbers(self) -> Dict[str, List[int]]:
        """Get AS numbers unique to each router"""
        unique_as = {}
        for router, as_numbers in self.router_as_matrix.items():
            unique_as[router] = [as_num for as_num in as_numbers if self.as_frequency[as_num] == 1]
        return unique_as
    
    def to_json(self) -> str:
        """Export distribution matrix to JSON"""
        data = {
            'summary': {
                'total_as_numbers': len(self.as_numbers),
                'total_routers': len(self.router_names),
                'common_as_numbers': len(self.get_common_as_numbers()),
                'avg_as_per_router': sum(len(as_list) for as_list in self.router_as_matrix.values()) / len(self.router_names) if self.router_names else 0
            },
            'as_distribution': {
                str(as_num): {
                    'router_count': count,
                    'routers': self.as_router_matrix[as_num]
                }
                for as_num, count in self.as_frequency.items()
            },
            'router_distribution': {
                router: {
                    'as_count': len(as_list),
                    'as_numbers': as_list,
                    'unique_as': len([as_num for as_num in as_list if self.as_frequency[as_num] == 1])
                }
                for router, as_list in self.router_as_matrix.items()
            }
        }
        
        return json.dumps(data, indent=2)

def generate_as_distribution_matrix(self, router_profiles: List[RouterProfile]) -> ASDistributionMatrix:
    """Generate AS distribution analysis"""
    
    # Collect all AS numbers and router mappings
    all_as_numbers = set()
    router_as_mapping = {}
    
    for profile in router_profiles:
        as_numbers = list(profile.discovered_as_numbers)
        router_as_mapping[profile.hostname] = as_numbers
        all_as_numbers.update(as_numbers)
    
    # Build reverse mapping (AS -> routers)
    as_router_mapping = {}
    as_frequency = {}
    
    for as_number in all_as_numbers:
        routers_with_as = []
        for router, as_list in router_as_mapping.items():
            if as_number in as_list:
                routers_with_as.append(router)
        
        as_router_mapping[as_number] = routers_with_as
        as_frequency[as_number] = len(routers_with_as)
    
    return ASDistributionMatrix(
        as_numbers=sorted(all_as_numbers),
        router_names=sorted(router_as_mapping.keys()),
        as_router_matrix=as_router_mapping,
        router_as_matrix=router_as_mapping,
        as_frequency=as_frequency
    )
```

### Change Detection Reporting
```python
@dataclass
class ChangeReport:
    """Report of changes between discovery runs"""
    timestamp: datetime
    previous_timestamp: Optional[datetime]
    
    # Router changes
    new_routers: List[str]
    removed_routers: List[str]
    modified_routers: List[str]
    
    # AS number changes
    new_as_numbers: List[int]
    removed_as_numbers: List[int]
    
    # Per-router AS changes
    router_as_changes: Dict[str, Dict[str, List[int]]]  # router -> {added: [...], removed: [...]}
    
    # BGP group changes
    bgp_group_changes: Dict[str, Dict[str, List[str]]]  # router -> {added: [...], removed: [...]}
    
    @property
    def has_changes(self) -> bool:
        """Check if any changes were detected"""
        return bool(
            self.new_routers or self.removed_routers or self.modified_routers or
            self.new_as_numbers or self.removed_as_numbers or
            any(changes['added'] or changes['removed'] for changes in self.router_as_changes.values())
        )
    
    def to_summary(self) -> str:
        """Generate human-readable change summary"""
        if not self.has_changes:
            return "No changes detected since previous discovery run"
        
        lines = [f"Discovery changes detected at {self.timestamp.isoformat()}"]
        
        if self.new_routers:
            lines.append(f"New routers: {', '.join(self.new_routers)}")
        
        if self.removed_routers:
            lines.append(f"Removed routers: {', '.join(self.removed_routers)}")
        
        if self.new_as_numbers:
            lines.append(f"New AS numbers: {', '.join(map(str, self.new_as_numbers))}")
        
        if self.removed_as_numbers:
            lines.append(f"Removed AS numbers: {', '.join(map(str, self.removed_as_numbers))}")
        
        if self.router_as_changes:
            lines.append("\nPer-router AS changes:")
            for router, changes in self.router_as_changes.items():
                if changes['added']:
                    lines.append(f"  {router}: +{', '.join(map(str, changes['added']))}")
                if changes['removed']:
                    lines.append(f"  {router}: -{', '.join(map(str, changes['removed']))}")
        
        return "\n".join(lines)

def generate_change_detection_report(self, previous_mappings: Dict, current_mappings: Dict) -> ChangeReport:
    """Generate change detection report between discovery runs"""
    
    current_time = datetime.now()
    previous_time = None
    
    # Extract timestamps
    if 'metadata' in previous_mappings:
        previous_time_str = previous_mappings['metadata'].get('generated_at')
        if previous_time_str:
            previous_time = datetime.fromisoformat(previous_time_str)
    
    # Extract router data
    previous_routers = set(previous_mappings.get('routers', {}).keys())
    current_routers = set(current_mappings.get('routers', {}).keys())
    
    new_routers = list(current_routers - previous_routers)
    removed_routers = list(previous_routers - current_routers)
    common_routers = current_routers & previous_routers
    
    # Detect AS number changes
    previous_as = set()
    current_as = set()
    
    for router_data in previous_mappings.get('routers', {}).values():
        previous_as.update(router_data.get('discovered_as_numbers', []))
    
    for router_data in current_mappings.get('routers', {}).values():
        current_as.update(router_data.get('discovered_as_numbers', []))
    
    new_as_numbers = list(current_as - previous_as)
    removed_as_numbers = list(previous_as - current_as)
    
    # Detect per-router changes
    router_as_changes = {}
    modified_routers = []
    
    for router in common_routers:
        prev_as = set(previous_mappings['routers'][router].get('discovered_as_numbers', []))
        curr_as = set(current_mappings['routers'][router].get('discovered_as_numbers', []))
        
        added_as = list(curr_as - prev_as)
        removed_as = list(prev_as - curr_as)
        
        if added_as or removed_as:
            router_as_changes[router] = {
                'added': added_as,
                'removed': removed_as
            }
            modified_routers.append(router)
    
    return ChangeReport(
        timestamp=current_time,
        previous_timestamp=previous_time,
        new_routers=new_routers,
        removed_routers=removed_routers,
        modified_routers=modified_routers,
        new_as_numbers=new_as_numbers,
        removed_as_numbers=removed_as_numbers,
        router_as_changes=router_as_changes,
        bgp_group_changes={}  # TODO: Implement BGP group change detection
    )
```

### Performance Reporting
```python
@dataclass
class PerformanceReport:
    """Pipeline performance metrics report"""
    execution_id: str
    start_time: datetime
    end_time: datetime
    total_duration: float
    
    # Stage timings
    stage_durations: Dict[str, float]
    stage_percentages: Dict[str, float]
    
    # Throughput metrics
    devices_per_second: float
    as_numbers_per_second: float
    policies_per_second: float
    
    # Resource usage
    peak_memory_mb: Optional[float]
    cpu_utilization: Optional[float]
    
    # Success metrics
    success_rates: Dict[str, float]
    error_counts: Dict[str, int]
    
    def to_dashboard_json(self) -> str:
        """Export for monitoring dashboard consumption"""
        dashboard_data = {
            'execution': {
                'id': self.execution_id,
                'start_time': self.start_time.isoformat(),
                'end_time': self.end_time.isoformat(),
                'duration_seconds': self.total_duration
            },
            'performance': {
                'throughput': {
                    'devices_per_second': self.devices_per_second,
                    'as_numbers_per_second': self.as_numbers_per_second,
                    'policies_per_second': self.policies_per_second
                },
                'stages': {
                    stage: {
                        'duration_seconds': duration,
                        'percentage_of_total': self.stage_percentages.get(stage, 0.0)
                    }
                    for stage, duration in self.stage_durations.items()
                }
            },
            'quality': {
                'success_rates': self.success_rates,
                'error_counts': self.error_counts
            }
        }
        
        if self.peak_memory_mb:
            dashboard_data['resources'] = {
                'peak_memory_mb': self.peak_memory_mb,
                'cpu_utilization': self.cpu_utilization
            }
        
        return json.dumps(dashboard_data, indent=2)
```

## Integration Points

### CLI Interface
```bash
# Generate discovery matrix
./otto-bgp report discovery-matrix --input policies/discovered/ --output reports/

# Generate AS distribution analysis  
./otto-bgp report as-distribution --input policies/discovered/ --format json

# Generate change detection report
./otto-bgp report changes --previous policies/discovered/history/previous.yaml --current policies/discovered/router_mappings.yaml

# Generate performance dashboard
./otto-bgp report performance --pipeline-log /var/log/otto-bgp/pipeline.log --output dashboard.json
```

### Pipeline Integration
```python
def generate_execution_reports(pipeline_result: PipelineResult, output_dir: Path):
    """Generate comprehensive execution reports"""
    
    matrix_gen = MatrixGenerator()
    
    # Discovery matrix
    discovery_matrix = matrix_gen.generate_discovery_matrix(pipeline_result)
    with open(output_dir / "discovery_matrix.csv", 'w') as f:
        f.write(discovery_matrix.to_csv())
    
    # AS distribution
    as_distribution = matrix_gen.generate_as_distribution_matrix(pipeline_result.router_profiles)
    with open(output_dir / "as_distribution.json", 'w') as f:
        f.write(as_distribution.to_json())
    
    # Performance metrics
    performance_report = matrix_gen.generate_performance_summary(pipeline_result)
    with open(output_dir / "performance.json", 'w') as f:
        f.write(performance_report.to_dashboard_json())
    
    logger.info(f"Reports generated in {output_dir}")
```

### Monitoring Integration
```python
def send_metrics_to_monitoring(performance_report: PerformanceReport):
    """Send metrics to monitoring system"""
    
    metrics = {
        'otto_bgp.pipeline.duration': performance_report.total_duration,
        'otto_bgp.pipeline.devices_per_second': performance_report.devices_per_second,
        'otto_bgp.pipeline.success_rate': performance_report.success_rates.get('overall', 0.0),
    }
    
    # Send to monitoring system (Prometheus, DataDog, etc.)
    for metric_name, value in metrics.items():
        monitoring_client.gauge(metric_name, value, tags=[
            f'execution_id:{performance_report.execution_id}',
            f'stage:pipeline'
        ])
```

## Best Practices

### Report Design
- Use consistent formatting across all report types
- Include both summary and detailed information
- Provide machine-readable output formats
- Support multiple visualization formats

### Performance Monitoring
- Track key operational metrics consistently
- Implement trend analysis for capacity planning
- Alert on significant performance degradation
- Monitor resource utilization patterns

### Change Detection
- Archive historical data for comparison
- Implement configurable change thresholds
- Provide actionable change summaries
- Support rollback decision making

### Operational Integration
- Generate reports automatically after pipeline execution
- Send critical alerts to monitoring systems
- Archive reports for audit and compliance
- Provide real-time status dashboards