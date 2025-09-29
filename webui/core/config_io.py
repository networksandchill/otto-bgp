import json
import os
import re
import tempfile
from datetime import datetime
from typing import Dict, Any, List
from webui.settings import CONFIG_PATH, CONFIG_DIR
from webui.core.fileops import atomic_write_json


def redact_sensitive_fields(config: Dict[str, Any]) -> Dict[str, Any]:
    """Redact passwords and sensitive data before sending to client"""
    cfg = config.copy()
    if 'ssh' in cfg and 'password' in cfg['ssh']:
        cfg['ssh']['password'] = "*****"
    if 'smtp' in cfg and 'password' in cfg['smtp']:
        cfg['smtp']['password'] = "*****"
    return cfg


def load_config_json_only() -> Dict[str, Any]:
    """Load configuration from config.json without env fallback"""
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge src dict into dst dict"""
    for key, value in src.items():
        if key in dst and isinstance(dst[key], dict) and isinstance(value, dict):
            deep_merge(dst[key], value)
        else:
            dst[key] = value
    return dst


def normalize_email_addresses(addresses: Any) -> List[str]:
    """Normalize and validate email addresses from CSV or list"""
    if not addresses:
        return []

    # Handle CSV string or list
    if isinstance(addresses, str):
        addr_list = [a.strip() for a in addresses.split(',')]
    elif isinstance(addresses, list):
        addr_list = [str(a).strip() for a in addresses]
    else:
        return []

    # Filter empty and validate format
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    valid_addresses = []
    seen_domains = set()

    for addr in addr_list:
        if not addr or len(addr) > 254:
            continue
        if not re.match(email_pattern, addr):
            continue

        # Deduplicate by lowercase domain
        parts = addr.split('@')
        if len(parts) == 2:
            domain_key = parts[0].lower() + '@' + parts[1].lower()
            if domain_key not in seen_domains:
                seen_domains.add(domain_key)
                valid_addresses.append(addr)

    # Cap at 50 recipients
    return valid_addresses[:50]


def update_core_email_config(ui_smtp: Dict[str, Any]) -> Dict[str, Any]:
    """Map UI SMTP config to core nested structure and update config.json"""
    # Load current config without env fallback
    config = load_config_json_only()

    # Ensure nested structure exists
    if 'autonomous_mode' not in config:
        config['autonomous_mode'] = {}
    if 'notifications' not in config['autonomous_mode']:
        config['autonomous_mode']['notifications'] = {}
    if 'email' not in config['autonomous_mode']['notifications']:
        config['autonomous_mode']['notifications']['email'] = {}

    # Map UI fields to core structure
    email_config = config['autonomous_mode']['notifications']['email']

    # Map each field with proper naming
    if 'host' in ui_smtp:
        email_config['smtp_server'] = ui_smtp['host']
    if 'port' in ui_smtp:
        email_config['smtp_port'] = int(ui_smtp['port'])
    if 'use_tls' in ui_smtp:
        email_config['smtp_use_tls'] = bool(ui_smtp['use_tls'])
    # Phase 1: Additional notification preferences
    if 'subject_prefix' in ui_smtp:
        email_config['subject_prefix'] = ui_smtp['subject_prefix']
    if 'send_on_success' in ui_smtp:
        email_config['send_on_success'] = bool(ui_smtp['send_on_success'])
    if 'send_on_failure' in ui_smtp:
        email_config['send_on_failure'] = bool(ui_smtp['send_on_failure'])
    if 'alert_on_manual' in ui_smtp:
        email_config['alert_on_manual'] = bool(ui_smtp['alert_on_manual'])
    if 'username' in ui_smtp:
        email_config['smtp_username'] = ui_smtp['username']
    if 'password' in ui_smtp:
        email_config['smtp_password'] = ui_smtp['password']
    if 'from_address' in ui_smtp:
        email_config['from_address'] = ui_smtp['from_address']
    if 'to_addresses' in ui_smtp:
        email_config['to_addresses'] = normalize_email_addresses(ui_smtp['to_addresses'])
    if 'enabled' in ui_smtp:
        email_config['enabled'] = bool(ui_smtp['enabled'])

    # Set default subject prefix if not present
    if 'subject_prefix' not in email_config:
        email_config['subject_prefix'] = '[Otto BGP Autonomous]'

    # Save updated config with atomic write
    atomic_write_json(CONFIG_PATH, config, mode=0o600)

    return email_config


def validate_smtp_config(smtp_dict: Dict) -> List[str]:
    """Validate SMTP configuration"""
    issues = []
    if not smtp_dict.get('host'):
        issues.append("SMTP host required")
    if not smtp_dict.get('from_address'):
        issues.append("From address required")
    return issues


def load_config_from_otto_env() -> Dict[str, Any]:
    """Load system configuration from otto.env file"""
    config: Dict[str, Any] = {}
    otto_env_path = CONFIG_DIR / 'otto.env'
    if not otto_env_path.exists():
        return config
    try:
        env_dict: Dict[str, str] = {}
        with open(otto_env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_dict[key.strip()] = value.strip()

        # SSH settings
        if 'SSH_USERNAME' in env_dict or 'SSH_PASSWORD' in env_dict or 'SSH_KEY_PATH' in env_dict:
            config['ssh'] = {}
            if 'SSH_USERNAME' in env_dict:
                config['ssh']['username'] = env_dict['SSH_USERNAME']
            if 'SSH_PASSWORD' in env_dict:
                config['ssh']['password'] = env_dict['SSH_PASSWORD']
            if 'SSH_KEY_PATH' in env_dict:
                config['ssh']['key_path'] = env_dict['SSH_KEY_PATH']

        # RPKI settings
        config['rpki'] = {
            'enabled': env_dict.get('OTTO_BGP_RPKI_ENABLED', 'false').lower() == 'true',
            'cache_dir': env_dict.get('OTTO_BGP_RPKI_CACHE_DIR', '/var/lib/otto-bgp/rpki'),
            'validator_url': env_dict.get('OTTO_BGP_RPKI_VALIDATOR_URL', ''),
            'refresh_interval': int(env_dict.get('OTTO_BGP_RPKI_REFRESH_INTERVAL', '24')),
            'strict_validation': env_dict.get('OTTO_BGP_RPKI_STRICT', 'false').lower() == 'true'
        }

        # BGPq4 settings
        config['bgpq4'] = {
            'mode': env_dict.get('OTTO_BGP_BGPQ4_MODE', 'auto'),
            'timeout': int(env_dict.get('OTTO_BGP_BGPQ4_TIMEOUT', '45')),
            'irr_source': env_dict.get('OTTO_BGP_IRR_SOURCE', 'RADB,RIPE,APNIC'),
            'aggregate_prefixes': env_dict.get('OTTO_BGP_AGGREGATE_PREFIXES', 'true').lower() == 'true',
            'ipv4_enabled': env_dict.get('OTTO_BGP_IPV4_ENABLED', 'true').lower() == 'true',
            'ipv6_enabled': env_dict.get('OTTO_BGP_IPV6_ENABLED', 'false').lower() == 'true'
        }

        # Guardrails settings (NEW CANONICAL SCHEMA)
        config['guardrails'] = {
            # Parse comma-separated enabled guardrails list
            # Critical guardrails are automatically enforced at runtime
            'enabled_guardrails': [
                g.strip()
                for g in env_dict.get('OTTO_BGP_GUARDRAILS', '').split(',')
                if g.strip()
            ],

            # Per-guardrail strictness levels
            'strictness': {
                'prefix_count': env_dict.get('OTTO_BGP_PREFIX_STRICTNESS', 'medium'),
                'bogon_prefix': env_dict.get('OTTO_BGP_BOGON_STRICTNESS', 'high'),
                'rpki_validation': env_dict.get('OTTO_BGP_RPKI_STRICTNESS', 'strict')
            },

            # Prefix count thresholds
            'prefix_count_thresholds': {
                'max_total_prefixes': int(env_dict.get('OTTO_BGP_PREFIX_MAX_TOTAL', '500000')),
                'max_prefixes_per_as': int(env_dict.get('OTTO_BGP_PREFIX_MAX_PER_AS', '100000')),
                'warning_threshold': float(env_dict.get('OTTO_BGP_PREFIX_WARNING', '0.8')),
                'critical_threshold': float(env_dict.get('OTTO_BGP_PREFIX_CRITICAL', '0.95'))
            }
        }

        # Network Security settings
        config['network_security'] = {
            'ssh_known_hosts': env_dict.get('OTTO_BGP_SSH_KNOWN_HOSTS', '/var/lib/otto-bgp/ssh-keys/known_hosts'),
            'ssh_connection_timeout': int(env_dict.get('OTTO_BGP_SSH_CONNECTION_TIMEOUT', '30')),
            'ssh_max_workers': int(float(env_dict.get('OTTO_BGP_SSH_MAX_WORKERS', '5'))),
            'strict_host_verification': env_dict.get('OTTO_BGP_STRICT_HOST_VERIFICATION', 'true').lower() == 'true',
            'allowed_networks': [
                n.strip() for n in env_dict.get('OTTO_BGP_ALLOWED_NETWORKS', '').split(',') if n.strip()
            ],
            'blocked_networks': [
                n.strip() for n in env_dict.get('OTTO_BGP_BLOCKED_NETWORKS', '').split(',') if n.strip()
            ],
        }

        # SMTP settings - read from env for backward compatibility
        if env_dict.get('OTTO_BGP_EMAIL_ENABLED', 'false').lower() == 'true':
            config['smtp'] = {
                'enabled': True,
                'host': env_dict.get('OTTO_BGP_SMTP_SERVER', ''),
                'port': int(float(env_dict.get('OTTO_BGP_SMTP_PORT', '587'))),
                'use_tls': env_dict.get('OTTO_BGP_SMTP_USE_TLS', 'true').lower() == 'true',
                'username': env_dict.get('OTTO_BGP_SMTP_USERNAME', ''),
                'password': env_dict.get('OTTO_BGP_SMTP_PASSWORD', ''),
                'from_address': env_dict.get('OTTO_BGP_EMAIL_FROM', ''),
                'to_addresses': normalize_email_addresses(env_dict.get('OTTO_BGP_EMAIL_TO', ''))
            }

        return config
    except Exception:
        return {}


def sync_config_to_otto_env(config: Dict[str, Any]) -> bool:
    """Sync configuration to otto.env file"""
    try:
        otto_env_path = CONFIG_DIR / 'otto.env'
        env_dict: Dict[str, str] = {}
        # Load existing env
        if otto_env_path.exists():
            with open(otto_env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_dict[key.strip()] = value.strip()
        # SSH
        if 'ssh' in config:
            ssh = config['ssh']
            if ssh.get('username'):
                env_dict['SSH_USERNAME'] = ssh['username']
            if ssh.get('password'):
                env_dict['SSH_PASSWORD'] = ssh['password']
            elif ssh.get('key_path'):
                env_dict['SSH_KEY_PATH'] = ssh['key_path']
        # RPKI
        if 'rpki' in config:
            rpki = config['rpki']
            env_dict['OTTO_BGP_RPKI_ENABLED'] = str(rpki.get('enabled', False)).lower()
            if rpki.get('cache_dir'):
                env_dict['OTTO_BGP_RPKI_CACHE_DIR'] = rpki['cache_dir']
            if rpki.get('validator_url'):
                env_dict['OTTO_BGP_RPKI_VALIDATOR_URL'] = rpki['validator_url']
            if 'refresh_interval' in rpki:
                env_dict['OTTO_BGP_RPKI_REFRESH_INTERVAL'] = str(rpki['refresh_interval'])
            if 'strict_validation' in rpki:
                env_dict['OTTO_BGP_RPKI_STRICT'] = str(rpki['strict_validation']).lower()
        # BGPQ4
        if 'bgpq4' in config:
            bgpq4 = config['bgpq4']
            if bgpq4.get('mode'):
                env_dict['OTTO_BGP_BGPQ4_MODE'] = bgpq4['mode']
            if 'timeout' in bgpq4:
                env_dict['OTTO_BGP_BGPQ4_TIMEOUT'] = str(bgpq4['timeout'])
            if bgpq4.get('irr_source'):
                env_dict['OTTO_BGP_IRR_SOURCE'] = bgpq4['irr_source']
            if 'aggregate_prefixes' in bgpq4:
                env_dict['OTTO_BGP_AGGREGATE_PREFIXES'] = str(bgpq4['aggregate_prefixes']).lower()
            if 'ipv4_enabled' in bgpq4:
                env_dict['OTTO_BGP_IPV4_ENABLED'] = str(bgpq4['ipv4_enabled']).lower()
            if 'ipv6_enabled' in bgpq4:
                env_dict['OTTO_BGP_IPV6_ENABLED'] = str(bgpq4['ipv6_enabled']).lower()
        # Guardrails (NEW CANONICAL SCHEMA)
        if 'guardrails' in config:
            gr = config['guardrails']

            # Write enabled guardrails list (comma-separated)
            # Critical guardrails are always enforced at runtime regardless
            if 'enabled_guardrails' in gr and gr['enabled_guardrails']:
                env_dict['OTTO_BGP_GUARDRAILS'] = ','.join(gr['enabled_guardrails'])

            # Write strictness overrides
            if 'strictness' in gr:
                strictness = gr['strictness']
                if 'prefix_count' in strictness:
                    env_dict['OTTO_BGP_PREFIX_STRICTNESS'] = strictness['prefix_count']
                if 'bogon_prefix' in strictness:
                    env_dict['OTTO_BGP_BOGON_STRICTNESS'] = strictness['bogon_prefix']
                if 'rpki_validation' in strictness:
                    env_dict['OTTO_BGP_RPKI_STRICTNESS'] = strictness['rpki_validation']

            # Write prefix count thresholds
            if 'prefix_count_thresholds' in gr:
                thresholds = gr['prefix_count_thresholds']
                if 'max_total_prefixes' in thresholds:
                    env_dict['OTTO_BGP_PREFIX_MAX_TOTAL'] = str(thresholds['max_total_prefixes'])
                if 'max_prefixes_per_as' in thresholds:
                    env_dict['OTTO_BGP_PREFIX_MAX_PER_AS'] = str(thresholds['max_prefixes_per_as'])
                if 'warning_threshold' in thresholds:
                    env_dict['OTTO_BGP_PREFIX_WARNING'] = str(thresholds['warning_threshold'])
                if 'critical_threshold' in thresholds:
                    env_dict['OTTO_BGP_PREFIX_CRITICAL'] = str(thresholds['critical_threshold'])
        # Network Security
        if 'network_security' in config:
            ns = config['network_security']
            if ns.get('ssh_known_hosts'):
                env_dict['OTTO_BGP_SSH_KNOWN_HOSTS'] = ns['ssh_known_hosts']
            if 'ssh_connection_timeout' in ns:
                env_dict['OTTO_BGP_SSH_CONNECTION_TIMEOUT'] = str(ns['ssh_connection_timeout'])
            if 'ssh_max_workers' in ns:
                env_dict['OTTO_BGP_SSH_MAX_WORKERS'] = str(ns['ssh_max_workers'])
            if 'strict_host_verification' in ns:
                env_dict['OTTO_BGP_STRICT_HOST_VERIFICATION'] = str(ns['strict_host_verification']).lower()
            if ns.get('allowed_networks'):
                env_dict['OTTO_BGP_ALLOWED_NETWORKS'] = ','.join(ns['allowed_networks'])
            if ns.get('blocked_networks'):
                env_dict['OTTO_BGP_BLOCKED_NETWORKS'] = ','.join(ns['blocked_networks'])
        # SMTP - DO NOT write to otto.env anymore
        # SMTP configuration is now persisted only in config.json

        # Autonomous Mode alignment (Phase 1a + Phase 4)
        if 'autonomous_mode' in config:
            am = config['autonomous_mode']
            env_dict['OTTO_BGP_AUTONOMOUS_ENABLED'] = str(am.get('enabled', False)).lower()
            if 'auto_apply_threshold' in am:
                env_dict['OTTO_BGP_AUTO_THRESHOLD'] = str(am['auto_apply_threshold'])
            if 'require_confirmation' in am:
                env_dict['OTTO_BGP_REQUIRE_CONFIRMATION'] = str(am['require_confirmation']).lower()

            # Safety overrides (Phase 4)
            if 'safety_overrides' in am:
                so = am['safety_overrides']
                if 'max_session_loss_percent' in so:
                    env_dict['OTTO_BGP_MAX_SESSION_LOSS_PERCENT'] = str(
                        so['max_session_loss_percent'])
                if 'max_route_loss_percent' in so:
                    env_dict['OTTO_BGP_MAX_ROUTE_LOSS_PERCENT'] = str(
                        so['max_route_loss_percent'])
                if 'monitoring_duration_seconds' in so:
                    env_dict['OTTO_BGP_MONITORING_DURATION'] = str(
                        so['monitoring_duration_seconds'])

        # RPKI advanced alignment (Phase 1a)
        if 'rpki' in config:
            rpki = config['rpki']
            if 'fail_closed' in rpki:
                env_dict['OTTO_BGP_RPKI_FAIL_CLOSED'] = str(rpki['fail_closed']).lower()
            if 'max_vrp_age_hours' in rpki:
                env_dict['OTTO_BGP_RPKI_MAX_VRP_AGE'] = str(rpki['max_vrp_age_hours'])
            if rpki.get('vrp_cache_path'):
                env_dict['OTTO_BGP_RPKI_VRP_CACHE'] = rpki['vrp_cache_path']
            if rpki.get('allowlist_path'):
                env_dict['OTTO_BGP_RPKI_ALLOWLIST'] = rpki['allowlist_path']

        # NETCONF alignment (Phase 1a + Phase 6)
        if 'netconf' in config:
            nc = config['netconf']
            if nc.get('username'):
                env_dict['NETCONF_USERNAME'] = nc['username']
            if nc.get('password'):
                env_dict['NETCONF_PASSWORD'] = nc['password']
            if nc.get('ssh_key'):
                env_dict['NETCONF_SSH_KEY'] = nc['ssh_key']
            if 'port' in nc:
                env_dict['NETCONF_PORT'] = str(nc['port'])
            if 'timeout' in nc:
                env_dict['OTTO_BGP_NETCONF_TIMEOUT'] = str(nc['timeout'])
            # Phase 6: Additional NETCONF settings
            if 'default_confirmed_commit' in nc:
                env_dict['OTTO_BGP_NETCONF_CONFIRMED_TIMEOUT'] = str(
                    nc['default_confirmed_commit'])
            if nc.get('commit_comment_prefix'):
                env_dict['OTTO_BGP_NETCONF_COMMIT_PREFIX'] = nc['commit_comment_prefix']

        # Atomic write
        with tempfile.NamedTemporaryFile('w', dir=str(otto_env_path.parent), delete=False) as tmp:
            tmp.write("# Otto BGP Configuration\n")
            tmp.write(f"# Generated by WebUI at {datetime.utcnow().isoformat()}\n")
            tmp.write("# This file is managed by Otto BGP WebUI and consumed by CLI\n\n")

            # Group environment variables by consumer
            tmp.write("# SSH Configuration (CLI collectors)\n")
            for key in ['SSH_USERNAME', 'SSH_PASSWORD', 'SSH_KEY_PATH']:
                if key in env_dict:
                    tmp.write(f"{key}={env_dict[key]}\n")

            tmp.write("\n# Autonomous Mode (CLI appliers)\n")
            for key in ['OTTO_BGP_AUTONOMOUS_ENABLED',
                        'OTTO_BGP_AUTO_THRESHOLD',
                        'OTTO_BGP_REQUIRE_CONFIRMATION',
                        'OTTO_BGP_MAX_SESSION_LOSS_PERCENT',
                        'OTTO_BGP_MAX_ROUTE_LOSS_PERCENT',
                        'OTTO_BGP_MONITORING_DURATION']:
                if key in env_dict:
                    tmp.write(f"{key}={env_dict[key]}\n")

            tmp.write("\n# RPKI Configuration (CLI validators)\n")
            for key in sorted([k for k in env_dict.keys() if k.startswith('OTTO_BGP_RPKI_')]):
                tmp.write(f"{key}={env_dict[key]}\n")

            tmp.write("\n# NETCONF Configuration (CLI appliers)\n")
            for key in ['NETCONF_USERNAME', 'NETCONF_PASSWORD', 'NETCONF_SSH_KEY',
                        'NETCONF_PORT', 'OTTO_BGP_NETCONF_TIMEOUT',
                        'OTTO_BGP_NETCONF_CONFIRMED_TIMEOUT',
                        'OTTO_BGP_NETCONF_COMMIT_PREFIX']:
                if key in env_dict:
                    tmp.write(f"{key}={env_dict[key]}\n")

            tmp.write("\n# BGPq4 Configuration (CLI generators)\n")
            for key in sorted([k for k in env_dict.keys() if 'BGPQ4' in k or 'IRR' in k]):
                tmp.write(f"{key}={env_dict[key]}\n")

            tmp.write("\n# Guardrails (CLI safety)\n")
            for key in sorted([k for k in env_dict.keys() if 'GUARDRAILS' in k or 'AUTO_APPLY' in k or
                              'SESSION_LOSS' in k or 'ROUTE_LOSS' in k or 'BOGON' in k or 'MONITORING' in k]):
                if key not in ['OTTO_BGP_AUTO_THRESHOLD', 'OTTO_BGP_REQUIRE_CONFIRMATION']:  # Already written above
                    tmp.write(f"{key}={env_dict[key]}\n")

            tmp.write("\n# Network Security (CLI security)\n")
            for key in sorted([k for k in env_dict.keys() if 'ALLOWED_NETWORKS' in k or 'BLOCKED_NETWORKS' in k or
                              'STRICT_HOST' in k or 'SSH_CONNECTION' in k or 'SSH_MAX' in k or 'SSH_KNOWN' in k]):
                tmp.write(f"{key}={env_dict[key]}\n")

            tmp.write("\n# Other Settings\n")
            written_keys = set()
            for section in [['SSH_USERNAME', 'SSH_PASSWORD', 'SSH_KEY_PATH'],
                            ['OTTO_BGP_AUTONOMOUS_ENABLED',
                             'OTTO_BGP_AUTO_THRESHOLD',
                             'OTTO_BGP_REQUIRE_CONFIRMATION',
                             'OTTO_BGP_MAX_SESSION_LOSS_PERCENT',
                             'OTTO_BGP_MAX_ROUTE_LOSS_PERCENT',
                             'OTTO_BGP_MONITORING_DURATION'],
                            ['NETCONF_USERNAME', 'NETCONF_PASSWORD', 'NETCONF_SSH_KEY', 'NETCONF_PORT',
                             'OTTO_BGP_NETCONF_TIMEOUT', 'OTTO_BGP_NETCONF_CONFIRMED_TIMEOUT',
                             'OTTO_BGP_NETCONF_COMMIT_PREFIX']]:
                written_keys.update(section)
            for prefix in ['OTTO_BGP_RPKI_', 'BGPQ4', 'IRR', 'GUARDRAILS', 'AUTO_APPLY', 'SESSION_LOSS',
                           'ROUTE_LOSS', 'BOGON', 'MONITORING', 'ALLOWED_NETWORKS', 'BLOCKED_NETWORKS',
                           'STRICT_HOST', 'SSH_CONNECTION', 'SSH_MAX', 'SSH_KNOWN']:
                written_keys.update([k for k in env_dict.keys() if prefix in k])

            for key in sorted(env_dict.keys()):
                if key not in written_keys:
                    tmp.write(f"{key}={env_dict[key]}\n")

            tmp_path = tmp.name
        os.replace(tmp_path, otto_env_path)
        os.chmod(otto_env_path, 0o600)
        return True
    except Exception:
        return False


def load_config() -> Dict[str, Any]:
    """Load configuration from config.json with otto.env fallback"""
    config = {}

    # First try config.json
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                config = json.load(f)
        except Exception:
            pass

    # If no config.json, fall back to otto.env
    if not config:
        config = load_config_from_otto_env()

    # Map nested core email config to flat SMTP for UI
    if 'autonomous_mode' in config and 'notifications' in config['autonomous_mode']:
        if 'email' in config['autonomous_mode']['notifications']:
            email_cfg = config['autonomous_mode']['notifications']['email']
            config['smtp'] = {
                'enabled': email_cfg.get('enabled', False),
                'host': email_cfg.get('smtp_server', ''),
                'port': email_cfg.get('smtp_port', 587),
                'use_tls': email_cfg.get('smtp_use_tls', True),
                'username': email_cfg.get('smtp_username', ''),
                'password': email_cfg.get('smtp_password', ''),
                'from_address': email_cfg.get('from_address', ''),
                'to_addresses': email_cfg.get('to_addresses', [])
            }

    return config


def save_config(config: Dict[str, Any]):
    """Save configuration to config.json and sync non-SMTP settings to otto.env"""
    atomic_write_json(CONFIG_PATH, config, mode=0o600)
    sync_config_to_otto_env(config)
