import json
import os
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

        # Guardrails settings
        config['guardrails'] = {
            'enabled': env_dict.get('OTTO_BGP_GUARDRAILS_ENABLED', 'true').lower() == 'true',
            'max_prefix_threshold': int(env_dict.get('OTTO_BGP_AUTO_APPLY_THRESHOLD', '100')),
            'max_session_loss_percent': int(env_dict.get('OTTO_BGP_MAX_SESSION_LOSS_PERCENT', '10')),
            'max_route_loss_percent': int(env_dict.get('OTTO_BGP_MAX_ROUTE_LOSS_PERCENT', '20')),
            'monitoring_duration': int(env_dict.get('OTTO_BGP_MONITORING_DURATION_SECONDS', '300')),
            'bogon_check_enabled': env_dict.get('OTTO_BGP_BOGON_CHECK_ENABLED', 'true').lower() == 'true',
            'require_confirmation': env_dict.get('OTTO_BGP_REQUIRE_CONFIRMATION', 'false').lower() == 'true'
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

        # SMTP settings
        if env_dict.get('OTTO_BGP_EMAIL_ENABLED', 'false').lower() == 'true':
            config['smtp'] = {
                'enabled': True,
                'host': env_dict.get('OTTO_BGP_SMTP_SERVER', ''),
                'port': int(float(env_dict.get('OTTO_BGP_SMTP_PORT', '587'))),
                'use_tls': env_dict.get('OTTO_BGP_SMTP_USE_TLS', 'true').lower() == 'true',
                'username': env_dict.get('OTTO_BGP_SMTP_USERNAME', ''),
                'password': env_dict.get('OTTO_BGP_SMTP_PASSWORD', ''),
                'from_address': env_dict.get('OTTO_BGP_EMAIL_FROM', ''),
                'to_addresses': env_dict.get('OTTO_BGP_EMAIL_TO', '').split(',') if env_dict.get('OTTO_BGP_EMAIL_TO') else []
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
        # Guardrails
        if 'guardrails' in config:
            gr = config['guardrails']
            env_dict['OTTO_BGP_GUARDRAILS_ENABLED'] = str(gr.get('enabled', True)).lower()
            if 'max_prefix_threshold' in gr:
                env_dict['OTTO_BGP_AUTO_APPLY_THRESHOLD'] = str(gr['max_prefix_threshold'])
            if 'max_session_loss_percent' in gr:
                env_dict['OTTO_BGP_MAX_SESSION_LOSS_PERCENT'] = str(gr['max_session_loss_percent'])
            if 'max_route_loss_percent' in gr:
                env_dict['OTTO_BGP_MAX_ROUTE_LOSS_PERCENT'] = str(gr['max_route_loss_percent'])
            if 'bogon_check_enabled' in gr:
                env_dict['OTTO_BGP_BOGON_CHECK_ENABLED'] = str(gr['bogon_check_enabled']).lower()
            if 'require_confirmation' in gr:
                env_dict['OTTO_BGP_REQUIRE_CONFIRMATION'] = str(gr['require_confirmation']).lower()
            if 'monitoring_duration' in gr:
                env_dict['OTTO_BGP_MONITORING_DURATION_SECONDS'] = str(gr['monitoring_duration'])
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
        # SMTP
        if 'smtp' in config and config['smtp'].get('enabled'):
            smtp = config['smtp']
            env_dict['OTTO_BGP_EMAIL_ENABLED'] = 'true'
            if smtp.get('host'):
                env_dict['OTTO_BGP_SMTP_SERVER'] = smtp['host']
            if smtp.get('port'):
                env_dict['OTTO_BGP_SMTP_PORT'] = str(smtp['port'])
            if 'use_tls' in smtp:
                env_dict['OTTO_BGP_SMTP_USE_TLS'] = str(smtp['use_tls']).lower()
            if smtp.get('username'):
                env_dict['OTTO_BGP_SMTP_USERNAME'] = smtp['username']
            if smtp.get('password'):
                env_dict['OTTO_BGP_SMTP_PASSWORD'] = smtp['password']
            if smtp.get('from_address'):
                env_dict['OTTO_BGP_EMAIL_FROM'] = smtp['from_address']
            if smtp.get('to_addresses'):
                env_dict['OTTO_BGP_EMAIL_TO'] = ','.join(smtp['to_addresses'])
        else:
            env_dict['OTTO_BGP_EMAIL_ENABLED'] = 'false'

        # Atomic write
        with tempfile.NamedTemporaryFile('w', dir=str(otto_env_path.parent), delete=False) as tmp:
            tmp.write("# Otto BGP Configuration\n")
            tmp.write(f"# Generated by WebUI at {datetime.utcnow().isoformat()}\n\n")
            for key in sorted(env_dict.keys()):
                tmp.write(f"{key}={env_dict[key]}\n")
            tmp_path = tmp.name
        os.replace(tmp_path, otto_env_path)
        os.chmod(otto_env_path, 0o600)
        return True
    except Exception:
        return False


def load_config() -> Dict[str, Any]:
    """Load configuration from config.json with otto.env fallback"""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return load_config_from_otto_env()


def save_config(config: Dict[str, Any]):
    """Save configuration to both config.json and otto.env"""
    atomic_write_json(CONFIG_PATH, config, mode=0o600)
    sync_config_to_otto_env(config)
