# otto_bgp.appliers Module - Developer Guide

## Overview

The `appliers` module provides **NETCONF-based policy application** to Juniper routers via PyEZ. This is a **security-critical module** that can modify production router configurations and includes comprehensive safety mechanisms.

**Current Status**: Production-ready autonomous operation (v0.3.1)

## Architecture Role

```
BGP Pipeline Flow:
Collection → Processing → Policy Generation → [APPLIERS] → Router Configuration

Key Responsibilities:
- Policy adaptation for router contexts
- Safety validation before application
- NETCONF/PyEZ integration
- Rollback and confirmation mechanisms
```

## Core Components

### 1. JuniperPolicyApplier (`juniper_netconf.py`)
**Purpose**: Main NETCONF interface for policy application

**Key Features**:
- PyEZ-based NETCONF connection management
- Confirmed commits with automatic rollback
- Dry-run capability for change preview
- Connection pooling and error handling

**Design Patterns**:
```python
# Context manager for safe connections
with applier.get_connection(router) as device:
    result = applier.apply_policies(device, policies)

# Confirmation pattern for safety
result = applier.apply_with_confirmation(
    policies=policies,
    confirm_timeout=120  # Auto-rollback after 2 minutes
)
```

#### Enhanced Features (v0.3.1)

**1. SafetyManager Integration**
```python
# Enhanced constructor with safety_manager parameter
applier = JuniperPolicyApplier(logger=logger, safety_manager=safety_mgr)

# Autonomous mode operation
if safety_mgr.should_auto_apply(policies):
    result = applier.apply_with_confirmation(policies, autonomous_mode=True)
```

**2. NETCONF Event Notification Integration**

The JuniperPolicyApplier now automatically sends email notifications for all NETCONF operations:

```python
# Connection Events
def connect_to_router(self, hostname: str, username: str, **kwargs):
    try:
        self.device = Device(host=hostname, username=username, **kwargs)
        self.device.open()
        
        # SUCCESS notification
        if self.autonomous_mode:
            self.safety_manager.send_netconf_event_notification(
                'connect', hostname, True, {}, self.config
            )
        return self.device
    except ConnectError as e:
        # FAILURE notification
        if self.autonomous_mode:
            self.safety_manager.send_netconf_event_notification(
                'connect', hostname, False, {'error': str(e)}, self.config
            )
        raise

# Preview Events
def preview_changes(self, policies: List[Dict]) -> str:
    try:
        diff = self.config.diff()
        
        # SUCCESS notification
        if self.autonomous_mode:
            self.safety_manager.send_netconf_event_notification(
                'preview', self.hostname, True, {'diff': diff}, self.config
            )
        return diff
    except Exception as e:
        # FAILURE notification
        if self.autonomous_mode:
            self.safety_manager.send_netconf_event_notification(
                'preview', self.hostname, False, {'error': str(e)}, self.config
            )
        raise

# Commit Events
def apply_with_confirmation(self, policies: List[Dict], **kwargs):
    try:
        commit_result = self.config.commit(confirm=confirm_timeout, **kwargs)
        
        # SUCCESS notification
        if self.autonomous_mode:
            self.safety_manager.send_netconf_event_notification(
                'commit', self.hostname, True, {
                    'commit_id': str(commit_result.commit_id),
                    'policies': policies,
                    'diff': self.preview_changes(policies)
                }, self.config
            )
        return result
    except CommitError as e:
        # FAILURE notification with rollback status
        if self.autonomous_mode:
            self.safety_manager.send_netconf_event_notification(
                'commit', self.hostname, False, {
                    'error': str(e),
                    'policies': policies,
                    'rollback_status': 'Automatic rollback attempted'
                }, self.config
            )
        raise

# Disconnect Events
def disconnect(self):
    if self.connected and self.device:
        # Send disconnect notification
        if self.autonomous_mode:
            self.safety_manager.send_netconf_event_notification(
                'disconnect', self.hostname, True, {}, self.config
            )
        self.device.close()
        self.connected = False
```

**3. Autonomous Mode Configuration**
```python
# Constructor enhancements
def __init__(self, logger=None, safety_manager=None, autonomous_mode=False):
    self.logger = logger or get_logger(__name__)
    self.safety_manager = safety_manager
    self.autonomous_mode = autonomous_mode
    self.config = get_config_manager().get_config()
    
    # Initialize connection state
    self.device = None
    self.connected = False
    self.hostname = None
```

### 2. SafetyManager (`safety.py`) 
**Purpose**: Pre-application validation, risk assessment, and autonomous decision logic

**Safety Checks**:
- Policy syntax validation
- BGP session impact analysis
- Prefix count thresholds
- Configuration conflict detection

**Risk Levels**:
- `low`: Safe for automatic application
- `medium`: Requires review
- `high`: Manual intervention required

**Autonomous Features (v0.3.1)**:
- `should_auto_apply()`: Risk-based autonomous decision logic
- `send_netconf_event_notification()`: Complete email audit trail for all NETCONF events
- Email notifications for connect/preview/commit/rollback/disconnect events
- SMTP integration using Python standard library

#### Enhanced Methods (v0.3.1)

**1. Autonomous Decision Logic**
```python
def should_auto_apply(self, policies: List[Dict], config: Dict) -> bool:
    """
    Autonomous decision logic for policy application
    
    Decision Criteria:
    - Autonomous mode must be enabled in configuration
    - Risk level must be 'low' (only low-risk changes auto-applied)
    - Threshold is informational only - never blocks operations
    
    Returns:
        True if safe for automatic application
    """
    # Check autonomous mode enabled
    autonomous_config = config.get('autonomous_mode', {})
    if not autonomous_config.get('enabled', False):
        return False
    
    # Use existing safety validation
    safety_result = self.validate_policies_before_apply(policies)
    
    # Only auto-apply low-risk changes
    if safety_result.risk_level != 'low':
        self.logger.info(f"Risk level {safety_result.risk_level} - manual approval required")
        return False
    
    # Log threshold for notification context only
    threshold = autonomous_config.get('auto_apply_threshold', 100)
    prefix_count = self._count_total_prefixes(policies)
    self.logger.info(f"Auto-apply approved: {prefix_count} prefixes, threshold={threshold}")
    
    return True
```

**2. NETCONF Event Notifications**
```python
def send_netconf_event_notification(self, 
                                   event_type: str,
                                   hostname: str,
                                   success: bool,
                                   details: Dict,
                                   config: Dict) -> bool:
    """
    Send email notification for NETCONF events
    
    Event Types:
    - 'connect': Router connection establishment
    - 'preview': Configuration diff generation
    - 'commit': Configuration commit operation
    - 'rollback': Configuration rollback operation
    - 'disconnect': Router disconnection
    
    Features:
    - Immediate email notifications for ALL NETCONF operations
    - Success and failure event coverage
    - Complete audit trail via email archive
    - Context information (prefix counts, thresholds, etc.)
    """
    email_cfg = config.get('autonomous_mode', {}).get('notifications', {}).get('email', {})
    
    if not email_cfg.get('enabled'):
        return False
    
    # Format email content
    subject = f"{event_type.upper()} - {'SUCCESS' if success else 'FAILED'}"
    body = self._format_netconf_event(event_type, hostname, success, details)
    
    # Add threshold context for commit events
    if event_type == 'commit' and 'policies' in details:
        prefix_count = self._count_total_prefixes(details['policies'])
        threshold = config.get('autonomous_mode', {}).get('auto_apply_threshold', 100)
        body += f"\nPrefix Count: {prefix_count} (Reference threshold: {threshold})"
    
    return self._send_email(email_cfg, subject, body)
```

**3. Email Content Formatting**
```python
def _format_netconf_event(self, event_type: str, hostname: str, 
                          success: bool, details: Dict) -> str:
    """
    Format event-specific email content
    
    Email Templates:
    - Connection events: Include error details for failures
    - Preview events: Include diff line counts
    - Commit events: Include commit ID, policy details, configuration diff
    - Rollback events: Include rollback target and status
    - Disconnect events: Simple confirmation
    """
    from datetime import datetime
    
    timestamp = datetime.now().isoformat()
    base_info = f"""NETCONF Event Notification
==========================
Event Type: {event_type.upper()}
Status: {'SUCCESS' if success else 'FAILED'}
Router: {hostname}
Timestamp: {timestamp}"""
    
    if event_type == 'commit':
        if success:
            policies = details.get('policies', [])
            as_numbers = [p.get('as_number') for p in policies if p.get('as_number')]
            return base_info + f"""
Commit ID: {details.get('commit_id', 'N/A')}
Policies Applied: {len(policies)}
AS Numbers: {', '.join(f'AS{n}' for n in as_numbers)}

Configuration Diff:
{details.get('diff', 'Not available')}"""
        else:
            return base_info + f"""
Error: {details.get('error', 'Unknown error')}
Rollback Status: {details.get('rollback_status', 'N/A')}"""
    
    # Other event type formatting...
    return base_info
```

**4. SMTP Email Sending**
```python
def _send_email(self, email_cfg: Dict, subject: str, body: str) -> bool:
    """
    Send email using Python standard library
    
    Features:
    - TLS encryption support
    - SMTP authentication (optional)
    - Best-effort delivery (failures don't break autonomous operations)
    - Comprehensive error logging
    """
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        msg = MIMEMultipart()
        msg['From'] = email_cfg['from_address']
        msg['To'] = ', '.join(email_cfg['to_addresses'])
        msg['Subject'] = f"{email_cfg['subject_prefix']} {subject}"
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP(email_cfg['smtp_server'], email_cfg['smtp_port']) as server:
            if email_cfg.get('smtp_use_tls'):
                server.starttls()
            if email_cfg.get('smtp_username'):
                server.login(email_cfg['smtp_username'], email_cfg['smtp_password'])
            server.send_message(msg)
        
        return True
    except Exception as e:
        self.logger.error(f"Email notification failed: {e}")
        return False  # Best-effort, don't break autonomous operation
```

### 3. PolicyAdapter (`adapter.py`)
**Purpose**: Transform generic policies for specific router contexts

**Adaptations**:
- Router-specific BGP group targeting
- Policy name normalization
- Platform-specific configuration syntax
- Import/export policy assignment

## Security Architecture

### Authentication
```python
# Key-based authentication only
netconf_config = {
    'host': router.address,
    'user': 'otto-bgp',
    'ssh_private_key_file': '/var/lib/otto-bgp/ssh-keys/netconf-key'
    # Never use password authentication
}
```

### Access Control
- Restricted Juniper user class (`bgp-policy-admin`)
- Limited to `policy-options prefix-list` modifications
- No system or interface configuration access

### Safety Mechanisms
1. **Risk-Based Autonomous Decisions**: Only low-risk changes are auto-applied
2. **Complete Email Audit Trail**: All NETCONF events generate email notifications
3. **Confirmed Commits**: All changes include confirmation timeout
4. **Dry-Run Validation**: Preview changes before application
5. **Session Monitoring**: Track BGP session stability
6. **Automatic Rollback**: Revert on timeout or error
7. **Threshold Monitoring**: Informational limits with notification context

## Code Structure

### Class Hierarchy
```
JuniperPolicyApplier
├── ConnectionManager (NETCONF sessions)
├── PolicyValidator (syntax checking)
├── ChangePreview (diff generation)
└── SafetyMonitor (BGP health tracking)

SafetyManager
├── PolicyAnalyzer (risk assessment)
├── ImpactCalculator (session/route analysis)
└── ThresholdChecker (safety limits)

PolicyAdapter
├── GroupMapper (BGP group targeting)
├── NameNormalizer (policy naming)
└── SyntaxTransformer (platform adaptation)
```

### Data Flow
```python
# 1. Load and adapt policies
policies = adapter.adapt_for_router(raw_policies, router_profile)

# 2. Safety validation
safety_result = safety_manager.validate_policies_before_apply(policies)
if not safety_result.safe_to_proceed:
    return ApplicationResult(success=False, reason=safety_result.risk_factors)

# 3. Preview changes
preview = applier.generate_preview(policies, router)
log_change_preview(preview)

# 4. Apply with confirmation
result = applier.apply_with_confirmation(
    policies=policies,
    router=router,
    confirm_timeout=120,
    comment="Otto BGP v0.3.2 automated update"
)
```

## Design Choices

### PyEZ Integration
**Choice**: Use Juniper's PyEZ library for NETCONF operations
**Rationale**: 
- Native Juniper support and optimization
- Built-in error handling and commit mechanisms
- Extensive documentation and community support

### Confirmed Commits Only
**Choice**: All commits include confirmation timeout
**Rationale**:
- Automatic rollback prevents configuration corruption
- Allows manual intervention during confirmation window
- Standard practice for automated network changes

### Autonomous Operation (v0.3.1)
**Choice**: Enable production-ready autonomous application with risk-based decisions
**Rationale**:
- Low-risk changes can be safely automated with proper controls
- Complete email audit trail provides oversight and compliance
- Risk assessment prevents high-impact changes from being auto-applied
- Comprehensive safety validation maintains operational stability

### Adapter Pattern
**Choice**: Separate policy adaptation from application
**Rationale**:
- Clean separation of concerns
- Testable transformation logic
- Support for multiple router contexts

## Security Considerations

### Network Security
- NETCONF over SSH (port 830)
- Host key verification required
- No credential storage in logs
- Connection encryption mandatory

### Configuration Security
- Minimal required permissions
- Policy-only configuration access
- Audit logging of all changes
- Rollback capability maintained

### Process Security
- Signal handlers for cleanup
- Resource leak prevention
- Error state recovery
- Graceful degradation

## Integration Points

### CLI Interface
```bash
# Dry-run preview
./otto-bgp apply --router lab-router1 --dry-run

# Apply with confirmation
./otto-bgp apply --router lab-router1 --confirm --confirm-timeout 300

# Force application (skip safety checks)
./otto-bgp apply --router lab-router1 --force --yes
```

### Python API
```python
from otto_bgp.appliers import JuniperPolicyApplier, SafetyManager

applier = JuniperPolicyApplier()
safety = SafetyManager()

# Load router-specific policies
policies = applier.load_router_policies("policies/routers/edge-1")

# Safety validation
safety_result = safety.validate_policies_before_apply(policies)

# Apply if safe
if safety_result.safe_to_proceed:
    result = applier.apply_with_confirmation(policies, router="edge-1")
```

### Pipeline Integration
- Called after policy generation phase
- Receives router-specific policy files
- Returns detailed application results
- Logs all operations for audit

## Error Handling

### Connection Errors
```python
try:
    with applier.get_connection(router) as device:
        result = applier.apply_policies(device, policies)
except ConnectionError as e:
    return ApplicationResult(
        success=False,
        error_type='connection',
        error_message=str(e)
    )
```

### Commit Failures
- Parse commit errors from router response
- Classify errors (syntax, conflict, system)
- Automatic rollback on failure
- Detailed error reporting

### Safety Violations
- Block application on safety check failure
- Log risk factors and recommendations
- Provide manual override capability
- Generate safety reports

## Development Guidelines

### Testing Strategy
```python
# Mock NETCONF for unit tests
@patch('otto_bgp.appliers.juniper_netconf.Device')
def test_policy_application(mock_device):
    applier = JuniperPolicyApplier()
    result = applier.apply_policies(mock_device, test_policies)
    assert result.success

# Integration tests with real devices
def test_real_device_application():
    # Requires test lab setup
    applier = JuniperPolicyApplier()
    result = applier.apply_to_lab_device(test_policies)
    assert result.success
```

### Performance Considerations
- Connection pooling for multiple operations
- Batch policy application when possible
- Progress tracking for long operations
- Memory management for large configurations

### Logging Standards
```python
# Structured logging for operations
logger.info("Applying policies", extra={
    'router': router.hostname,
    'policy_count': len(policies),
    'operation_id': operation_id
})

# Security events
logger.warning("Safety check failed", extra={
    'router': router.hostname,
    'risk_level': safety_result.risk_level,
    'risk_factors': safety_result.risk_factors
})
```

## Future Enhancements (v0.3.1+)

### Production Mode
- Risk-based automatic application
- Change management integration
- Enhanced safety thresholds
- Production monitoring hooks

### Multi-Vendor Support
- Cisco IOS-XR adapter
- Arista EOS integration
- Generic NETCONF interface
- Vendor-specific optimizations

### Advanced Safety
- Machine learning risk assessment
- Historical change analysis
- Peer coordination mechanisms
- Real-time impact monitoring

## Dependencies

### Required
- `junos-eznc` (PyEZ library)
- `jxmlease` (XML parsing)
- `lxml` (XML processing)
- `ncclient` (NETCONF client)

### Optional
- `paramiko` (SSH fallback)
- `pycryptodome` (encryption)

## Best Practices

### Safety First
- Always test in lab before production
- Use confirmation timeouts appropriate for change size
- Monitor BGP sessions during and after application
- Maintain rollback plans

### Code Quality
- Comprehensive error handling
- Structured logging with context
- Resource cleanup in finally blocks
- Type hints for all public interfaces

### Security
- Never store credentials in code
- Validate all inputs before NETCONF operations
- Use minimal required permissions
- Audit all configuration changes