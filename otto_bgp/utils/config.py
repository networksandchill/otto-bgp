#!/usr/bin/env python3
"""
Configuration Management for Otto BGP

Provides centralized configuration handling with:
- Environment variable support
- Configuration file support
- Default values and validation
- Runtime configuration management
"""

import os
import json
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging


@dataclass
class SSHConfig:
    """SSH connection configuration"""

    username: Optional[str] = None
    password: Optional[str] = None
    key_path: Optional[str] = None
    connection_timeout: int = 30
    command_timeout: int = 60

    def __post_init__(self):
        """Load from environment variables if not set"""
        if self.username is None:
            self.username = os.getenv("SSH_USERNAME")
        if self.password is None:
            self.password = os.getenv("SSH_PASSWORD")
        if self.key_path is None:
            self.key_path = os.getenv("SSH_KEY_PATH")


@dataclass
class BGPQ4Config:
    """BGPq4 tool configuration"""

    mode: str = "auto"
    timeout: int = 45
    irr_source: str = "RADB,RIPE,APNIC"
    aggregate_prefixes: bool = True
    ipv4_enabled: bool = True
    ipv6_enabled: bool = False
    max_workers: int = 4
    retry_attempts: int = 2

    def __post_init__(self):
        """Load from environment variables if not set"""
        if os.getenv("OTTO_BGP_BGPQ4_MODE"):
            self.mode = os.getenv("OTTO_BGP_BGPQ4_MODE")
        if os.getenv("OTTO_BGP_BGPQ4_TIMEOUT"):
            try:
                self.timeout = int(os.getenv("OTTO_BGP_BGPQ4_TIMEOUT"))
            except ValueError:
                pass
        if os.getenv("OTTO_BGP_IRR_SOURCE"):
            self.irr_source = os.getenv("OTTO_BGP_IRR_SOURCE")
        if os.getenv("OTTO_BGP_AGGREGATE_PREFIXES"):
            self.aggregate_prefixes = (
                os.getenv("OTTO_BGP_AGGREGATE_PREFIXES").lower() == "true"
            )
        if os.getenv("OTTO_BGP_IPV4_ENABLED"):
            self.ipv4_enabled = os.getenv("OTTO_BGP_IPV4_ENABLED").lower() == "true"
        if os.getenv("OTTO_BGP_IPV6_ENABLED"):
            self.ipv6_enabled = os.getenv("OTTO_BGP_IPV6_ENABLED").lower() == "true"
        if os.getenv("OTTO_BGP_BGPQ4_MAX_WORKERS"):
            try:
                self.max_workers = int(os.getenv("OTTO_BGP_BGPQ4_MAX_WORKERS"))
            except ValueError:
                pass
        if os.getenv("OTTO_BGP_BGPQ4_RETRY_ATTEMPTS"):
            try:
                self.retry_attempts = int(os.getenv("OTTO_BGP_BGPQ4_RETRY_ATTEMPTS"))
            except ValueError:
                pass


@dataclass
class BGPq3Config:
    """BGPq3 tool configuration (legacy)"""

    native_path: Optional[str] = None
    docker_image: str = "mirceaulinic/bgpq3"
    use_docker: bool = False
    use_podman: bool = False
    command_timeout: int = 30

    def __post_init__(self):
        """Load from environment variables if not set"""
        if self.native_path is None:
            self.native_path = os.getenv("BGPQ3_PATH")
        if os.getenv("BGPQ3_DOCKER_IMAGE"):
            self.docker_image = os.getenv("BGPQ3_DOCKER_IMAGE")
        if os.getenv("BGPQ3_USE_DOCKER") in ["1", "true", "yes"]:
            self.use_docker = True
        if os.getenv("BGPQ3_USE_PODMAN") in ["1", "true", "yes"]:
            self.use_podman = True


@dataclass
class ASProcessingConfig:
    """AS number processing configuration"""

    min_as_number: int = 256
    max_as_number: int = 4294967295
    default_pattern: str = "standard"
    remove_substrings: List[str] = None

    def __post_init__(self):
        """Set default remove substrings if not provided"""
        if self.remove_substrings is None:
            self.remove_substrings = ["    peer-as ", ";"]


@dataclass
class OutputConfig:
    """Output file configuration"""

    default_output_dir: str = "output"
    policies_subdir: str = "policies"
    bgp_data_filename: str = "bgp.txt"
    bgp_juniper_filename: str = "bgp-juniper.txt"
    create_timestamps: bool = True

    def __post_init__(self):
        """Load from environment variables if not set"""
        if os.getenv("OTTO_BGP_OUTPUT_DIR"):
            self.default_output_dir = os.getenv("OTTO_BGP_OUTPUT_DIR")


@dataclass
class IRRProxyConfig:
    """IRR proxy configuration for restricted networks"""

    enabled: bool = False
    method: str = "ssh_tunnel"
    jump_host: str = ""
    jump_user: str = ""
    ssh_key_file: Optional[str] = None
    known_hosts_file: Optional[str] = None
    connection_timeout: int = 10
    health_check_interval: int = 30
    max_retries: int = 3
    tunnels: List[Dict[str, Any]] = None

    def __post_init__(self):
        """Load from environment variables and set defaults"""
        if self.tunnels is None:
            self.tunnels = [
                {
                    "name": "ntt",
                    "local_port": 43001,
                    "remote_host": "rr.ntt.net",
                    "remote_port": 43,
                },
                {
                    "name": "radb",
                    "local_port": 43002,
                    "remote_host": "whois.radb.net",
                    "remote_port": 43,
                },
            ]

        # Load from environment variables
        if os.getenv("OTTO_BGP_PROXY_ENABLED") in ["1", "true", "yes"]:
            self.enabled = True
        if os.getenv("OTTO_BGP_PROXY_JUMP_HOST"):
            self.jump_host = os.getenv("OTTO_BGP_PROXY_JUMP_HOST")
        if os.getenv("OTTO_BGP_PROXY_JUMP_USER"):
            self.jump_user = os.getenv("OTTO_BGP_PROXY_JUMP_USER")
        if os.getenv("OTTO_BGP_PROXY_SSH_KEY"):
            self.ssh_key_file = os.getenv("OTTO_BGP_PROXY_SSH_KEY")
        if os.getenv("OTTO_BGP_PROXY_KNOWN_HOSTS"):
            self.known_hosts_file = os.getenv("OTTO_BGP_PROXY_KNOWN_HOSTS")


@dataclass
class LoggingConfig:
    """Logging configuration"""

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"
    log_to_file: bool = False
    log_file: Optional[str] = None

    def __post_init__(self):
        """Load from environment variables if not set"""
        if os.getenv("OTTO_BGP_LOG_LEVEL"):
            self.level = os.getenv("OTTO_BGP_LOG_LEVEL").upper()
        if os.getenv("OTTO_BGP_LOG_FILE"):
            self.log_file = os.getenv("OTTO_BGP_LOG_FILE")
            self.log_to_file = True


@dataclass
class InstallationModeConfig:
    """Installation mode configuration"""

    type: str = "user"  # user, system
    service_user: str = "otto-bgp"
    systemd_enabled: bool = False
    optimization_level: str = "basic"  # basic, enhanced

    def __post_init__(self):
        """Load from environment variables if not set"""
        if os.getenv("OTTO_BGP_INSTALL_MODE"):
            install_mode = os.getenv("OTTO_BGP_INSTALL_MODE").lower()
            if install_mode in ["user", "system"]:
                self.type = install_mode
        if os.getenv("OTTO_BGP_SERVICE_USER"):
            self.service_user = os.getenv("OTTO_BGP_SERVICE_USER")


@dataclass
class EmailNotificationConfig:
    """Email notification configuration for autonomous mode"""

    enabled: bool = True
    smtp_server: str = "smtp.company.com"
    smtp_port: int = 587
    smtp_use_tls: bool = True
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    from_address: str = "otto-bgp@company.com"
    to_addresses: List[str] = None
    cc_addresses: List[str] = None
    subject_prefix: str = "[Otto BGP Autonomous]"
    send_on_success: bool = True
    send_on_failure: bool = True
    delivery_method: str = "sendmail"  # 'sendmail' | 'smtp'
    sendmail_path: Optional[str] = "/usr/sbin/sendmail"

    def __post_init__(self):
        """Set default values and load from environment"""
        if self.to_addresses is None:
            self.to_addresses = ["network-engineers@company.com"]
        if self.cc_addresses is None:
            self.cc_addresses = []

        # Load from environment variables
        if os.getenv("OTTO_BGP_SMTP_SERVER"):
            self.smtp_server = os.getenv("OTTO_BGP_SMTP_SERVER")
        if os.getenv("OTTO_BGP_SMTP_PORT"):
            try:
                self.smtp_port = int(os.getenv("OTTO_BGP_SMTP_PORT"))
            except ValueError:
                pass
        if os.getenv("OTTO_BGP_SMTP_USERNAME"):
            self.smtp_username = os.getenv("OTTO_BGP_SMTP_USERNAME")
        if os.getenv("OTTO_BGP_SMTP_PASSWORD"):
            self.smtp_password = os.getenv("OTTO_BGP_SMTP_PASSWORD")
        if os.getenv("OTTO_BGP_FROM_ADDRESS"):
            self.from_address = os.getenv("OTTO_BGP_FROM_ADDRESS")
        if os.getenv("OTTO_BGP_EMAIL_DELIVERY_METHOD") in ["sendmail", "smtp"]:
            self.delivery_method = os.getenv("OTTO_BGP_EMAIL_DELIVERY_METHOD")
        if os.getenv("OTTO_BGP_SENDMAIL_PATH"):
            self.sendmail_path = os.getenv("OTTO_BGP_SENDMAIL_PATH")


@dataclass
class NotificationConfig:
    """Notification configuration for autonomous mode"""

    email: EmailNotificationConfig = None
    webhook_url: Optional[str] = None
    alert_on_manual: bool = True
    success_notifications: bool = True

    def __post_init__(self):
        """Initialize email config if not provided"""
        if self.email is None:
            self.email = EmailNotificationConfig()


@dataclass
class SafetyOverridesConfig:
    """Safety override configuration for autonomous mode"""

    max_session_loss_percent: float = 5.0
    max_route_loss_percent: float = 10.0
    monitoring_duration_seconds: int = 300

    def __post_init__(self):
        """Load from environment variables if not set"""
        if os.getenv("OTTO_BGP_MAX_SESSION_LOSS"):
            try:
                self.max_session_loss_percent = float(
                    os.getenv("OTTO_BGP_MAX_SESSION_LOSS")
                )
            except ValueError:
                pass
        if os.getenv("OTTO_BGP_MAX_ROUTE_LOSS"):
            try:
                self.max_route_loss_percent = float(
                    os.getenv("OTTO_BGP_MAX_ROUTE_LOSS")
                )
            except ValueError:
                pass


@dataclass
class AutonomousModeConfig:
    """Autonomous mode configuration"""

    enabled: bool = False  # Default to safe (manual mode)
    auto_apply_threshold: int = 100  # Informational threshold for notifications
    require_confirmation: bool = True  # Use confirmed commits
    safety_overrides: SafetyOverridesConfig = None
    notifications: NotificationConfig = None

    def __post_init__(self):
        """Initialize subconfigs and load from environment"""
        if self.safety_overrides is None:
            self.safety_overrides = SafetyOverridesConfig()
        if self.notifications is None:
            self.notifications = NotificationConfig()

        # Load from environment variables
        if os.getenv("OTTO_BGP_AUTONOMOUS_ENABLED") in ["1", "true", "yes"]:
            self.enabled = True
        if os.getenv("OTTO_BGP_AUTO_THRESHOLD"):
            try:
                self.auto_apply_threshold = int(os.getenv("OTTO_BGP_AUTO_THRESHOLD"))
            except ValueError:
                pass


@dataclass
class RPKIConfig:
    """RPKI/ROA validation configuration"""

    enabled: bool = True  # RPKI validation enabled by default
    fail_closed: bool = True  # Fail closed when VRP data stale/unavailable
    max_vrp_age_hours: int = 24  # Maximum age for VRP data before stale
    vrp_cache_path: Optional[str] = None  # Path to VRP cache file
    allowlist_path: Optional[str] = None  # Path to NOTFOUND allowlist file

    # Validation thresholds
    max_invalid_percent: float = 0.0  # Maximum percentage of invalid prefixes allowed
    max_notfound_percent: float = (
        25.0  # Maximum percentage of non-allowlisted NOTFOUND prefixes
    )
    require_vrp_data: bool = True  # Require fresh VRP data for validation
    allow_allowlisted_notfound: bool = True  # Allow allowlisted NOTFOUND prefixes

    # VRP data sources configuration
    vrp_sources: List[str] = None  # List of VRP data sources to check
    auto_update_vrp: bool = False  # Automatically update VRP data
    vrp_update_interval_hours: int = 6  # VRP data update interval

    def __post_init__(self):
        """Set defaults and load from environment"""
        if self.vrp_cache_path is None:
            self.vrp_cache_path = "/var/lib/otto-bgp/rpki/vrp_cache.json"
        if self.allowlist_path is None:
            self.allowlist_path = "/var/lib/otto-bgp/rpki/allowlist.json"
        if self.vrp_sources is None:
            self.vrp_sources = []

        # Load from environment variables
        if os.getenv("OTTO_BGP_RPKI_ENABLED") in ["0", "false", "no"]:
            self.enabled = False
        if os.getenv("OTTO_BGP_RPKI_FAIL_CLOSED") in ["0", "false", "no"]:
            self.fail_closed = False
        if os.getenv("OTTO_BGP_RPKI_VRP_CACHE"):
            self.vrp_cache_path = os.getenv("OTTO_BGP_RPKI_VRP_CACHE")
        if os.getenv("OTTO_BGP_RPKI_ALLOWLIST"):
            self.allowlist_path = os.getenv("OTTO_BGP_RPKI_ALLOWLIST")
        if os.getenv("OTTO_BGP_RPKI_MAX_VRP_AGE"):
            try:
                self.max_vrp_age_hours = int(os.getenv("OTTO_BGP_RPKI_MAX_VRP_AGE"))
            except ValueError:
                pass


# Configuration validation schemas
INSTALLATION_MODE_SCHEMA = {
    "type": {"valid_values": ["user", "system"], "required": True},
    "service_user": {"type": str, "default": "otto-bgp"},
    "systemd_enabled": {"type": bool, "default": False},
    "optimization_level": {"valid_values": ["basic", "enhanced"], "default": "basic"},
}

AUTONOMOUS_MODE_SCHEMA = {
    "enabled": {"type": bool, "default": False},
    "auto_apply_threshold": {"type": int, "min": 1, "max": 10000, "default": 100},
    "require_confirmation": {"type": bool, "default": True},
    "safety_overrides": {
        "max_session_loss_percent": {
            "type": float,
            "min": 0.0,
            "max": 100.0,
            "default": 5.0,
        },
        "max_route_loss_percent": {
            "type": float,
            "min": 0.0,
            "max": 100.0,
            "default": 10.0,
        },
        "monitoring_duration_seconds": {
            "type": int,
            "min": 30,
            "max": 3600,
            "default": 300,
        },
    },
    "notifications": {
        "email": {
            "enabled": {"type": bool, "default": True},
            "delivery_method": {
                "valid_values": ["sendmail", "smtp"],
                "default": "sendmail",
            },
            "sendmail_path": {"type": str, "default": "/usr/sbin/sendmail"},
            "smtp_server": {"type": str},
            "smtp_port": {"type": int, "min": 1, "max": 65535, "default": 587},
            "smtp_use_tls": {"type": bool, "default": True},
            "from_address": {"type": str, "required": True},
            "to_addresses": {"type": list, "required": True},
            "subject_prefix": {"type": str, "default": "[Otto BGP Autonomous]"},
        }
    },
}


@dataclass
class BGPToolkitConfig:
    """Main configuration container"""

    ssh: SSHConfig = None
    bgpq4: BGPQ4Config = None
    bgpq3: BGPq3Config = None
    as_processing: ASProcessingConfig = None
    output: OutputConfig = None
    logging: LoggingConfig = None
    irr_proxy: IRRProxyConfig = None
    installation_mode: InstallationModeConfig = None
    autonomous_mode: AutonomousModeConfig = None
    rpki: RPKIConfig = None

    def __post_init__(self):
        """Initialize subconfigs if not provided"""
        if self.ssh is None:
            self.ssh = SSHConfig()
        if self.bgpq4 is None:
            self.bgpq4 = BGPQ4Config()
        if self.bgpq3 is None:
            self.bgpq3 = BGPq3Config()
        if self.as_processing is None:
            self.as_processing = ASProcessingConfig()
        if self.output is None:
            self.output = OutputConfig()
        if self.logging is None:
            self.logging = LoggingConfig()
        if self.irr_proxy is None:
            self.irr_proxy = IRRProxyConfig()
        if self.installation_mode is None:
            self.installation_mode = InstallationModeConfig()
        if self.autonomous_mode is None:
            self.autonomous_mode = AutonomousModeConfig()
        if self.rpki is None:
            self.rpki = RPKIConfig()


class ConfigManager:
    """Configuration management for Otto BGP"""

    DEFAULT_CONFIG_PATHS = [
        Path.home() / ".config/otto-bgp/config.json",
        Path("/etc/otto-bgp/config.json"),
        Path("./config.json"),
    ]

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration manager

        Args:
            config_path: Optional path to configuration file
        """
        self.logger = logging.getLogger(__name__)
        self.config_path = config_path
        self.config = BGPToolkitConfig()

        # Load configuration
        self._load_config()

    def _load_config(self):
        """Load configuration from file and environment"""
        # Try to load from file
        config_file = self._find_config_file()
        if config_file:
            try:
                self._load_from_file(config_file)
                self.logger.info(f"Loaded configuration from {config_file}")
            except Exception as e:
                self.logger.warning(f"Failed to load config file {config_file}: {e}")

        # NEW: Load guardrail environment overrides
        self._load_guardrail_env()

        # Environment variables are loaded in __post_init__ methods
        self.logger.debug("Configuration loaded with environment variable overrides")

    def _find_config_file(self) -> Optional[Path]:
        """Find configuration file in default locations"""
        if self.config_path and self.config_path.exists():
            return self.config_path

        for path in self.DEFAULT_CONFIG_PATHS:
            if path.exists():
                return path

        return None

    def _load_from_file(self, config_path: Path):
        """Load configuration from JSON file"""
        with open(config_path, "r") as f:
            data = json.load(f)
        self._load_from_dict(data)

    def _load_from_dict(self, data: dict):
        """Load configuration from dictionary (side-effect-free)"""
        # Update configuration sections
        if "ssh" in data:
            ssh_data = data["ssh"]
            self.config.ssh = SSHConfig(**ssh_data)

        if "bgpq3" in data:
            bgpq3_data = data["bgpq3"]
            self.config.bgpq3 = BGPq3Config(**bgpq3_data)

        if "bgpq4" in data:
            bgpq4_data = data["bgpq4"]
            self.config.bgpq4 = BGPQ4Config(**bgpq4_data)

        if "as_processing" in data:
            as_data = data["as_processing"]
            self.config.as_processing = ASProcessingConfig(**as_data)

        if "output" in data:
            output_data = data["output"]
            self.config.output = OutputConfig(**output_data)

        if "logging" in data:
            logging_data = data["logging"]
            self.config.logging = LoggingConfig(**logging_data)

        if "irr_proxy" in data:
            proxy_data = data["irr_proxy"]
            self.config.irr_proxy = IRRProxyConfig(**proxy_data)

        # Handle installation mode configuration
        if "installation_mode" in data:
            install_data = data["installation_mode"]
            self.config.installation_mode = InstallationModeConfig(**install_data)

        # Handle autonomous mode configuration with nested objects
        if "autonomous_mode" in data:
            autonomous_data = data["autonomous_mode"]

            # Handle nested safety_overrides
            if "safety_overrides" in autonomous_data:
                safety_data = autonomous_data.pop("safety_overrides")
                safety_overrides = SafetyOverridesConfig(**safety_data)
            else:
                safety_overrides = SafetyOverridesConfig()

            # Handle nested notifications
            if "notifications" in autonomous_data:
                notifications_data = autonomous_data.pop("notifications")

                # Handle nested email configuration
                if "email" in notifications_data:
                    email_data = notifications_data.pop("email")
                    email_config = EmailNotificationConfig(**email_data)
                else:
                    email_config = EmailNotificationConfig()

                notifications = NotificationConfig(
                    email=email_config, **notifications_data
                )
            else:
                notifications = NotificationConfig()

            # Create autonomous mode config with nested objects
            self.config.autonomous_mode = AutonomousModeConfig(
                safety_overrides=safety_overrides,
                notifications=notifications,
                **autonomous_data,
            )

        # Handle RPKI configuration
        if "rpki" in data:
            rpki_data = data["rpki"]
            self.config.rpki = RPKIConfig(**rpki_data)

    def _load_guardrail_env(self):
        """Load guardrail enablement and prefix thresholds from environment"""
        enabled = []
        if os.getenv("OTTO_BGP_GUARDRAILS"):
            enabled = [
                g.strip()
                for g in os.getenv("OTTO_BGP_GUARDRAILS").split(",")
                if g.strip()
            ]

        # PrefixCountGuardrail overrides
        prefix_overrides = {}
        if os.getenv("OTTO_BGP_PREFIX_MAX_TOTAL"):
            prefix_overrides["max_total_prefixes"] = int(
                os.getenv("OTTO_BGP_PREFIX_MAX_TOTAL")
            )
        if os.getenv("OTTO_BGP_PREFIX_MAX_PER_AS"):
            prefix_overrides["max_prefixes_per_as"] = int(
                os.getenv("OTTO_BGP_PREFIX_MAX_PER_AS")
            )
        if os.getenv("OTTO_BGP_PREFIX_WARNING"):
            prefix_overrides["warning_threshold"] = float(
                os.getenv("OTTO_BGP_PREFIX_WARNING")
            )
        if os.getenv("OTTO_BGP_PREFIX_CRITICAL"):
            prefix_overrides["critical_threshold"] = float(
                os.getenv("OTTO_BGP_PREFIX_CRITICAL")
            )

        strictness = os.getenv("OTTO_BGP_PREFIX_STRICTNESS")
        if strictness and strictness not in ["low", "medium", "high", "strict"]:
            self.logger.warning(
                f"Invalid OTTO_BGP_PREFIX_STRICTNESS: {strictness} (ignored)"
            )
            strictness = None

        # Tight range validation: numeric sanity checks for safety
        # These do not raise here; startup validation in UnifiedSafetyManager will fail if invalid
        def _is_pos_int(v):
            try:
                return isinstance(v, int) and v > 0
            except Exception:
                return False

        def _is_ratio(v):
            try:
                return isinstance(v, float) and 0.0 < v <= 1.0
            except Exception:
                return False

        if "warning_threshold" in prefix_overrides and not _is_ratio(
            prefix_overrides["warning_threshold"]
        ):
            self.logger.error("OTTO_BGP_PREFIX_WARNING must be a float in (0.0, 1.0]")
        if "critical_threshold" in prefix_overrides and not _is_ratio(
            prefix_overrides["critical_threshold"]
        ):
            self.logger.error("OTTO_BGP_PREFIX_CRITICAL must be a float in (0.0, 1.0]")
        if "max_total_prefixes" in prefix_overrides and not _is_pos_int(
            prefix_overrides["max_total_prefixes"]
        ):
            self.logger.error("OTTO_BGP_PREFIX_MAX_TOTAL must be a positive integer")
        if "max_prefixes_per_as" in prefix_overrides and not _is_pos_int(
            prefix_overrides["max_prefixes_per_as"]
        ):
            self.logger.error("OTTO_BGP_PREFIX_MAX_PER_AS must be a positive integer")

        self.guardrail_env = {
            "enabled": enabled,
            "prefix_count": {
                "custom_thresholds": prefix_overrides,
                "strictness_level": strictness,
            },
        }
        if enabled:
            self.logger.info(f"Guardrail env override: {len(enabled)} names")

    def save_config(self, config_path: Optional[Path] = None) -> Path:
        """
        Save current configuration to file

        Args:
            config_path: Path to save configuration (default: first default path)

        Returns:
            Path where configuration was saved
        """
        if config_path is None:
            config_path = self.DEFAULT_CONFIG_PATHS[0]

        # Create directory if needed
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dictionary
        config_dict = {
            "ssh": asdict(self.config.ssh),
            "bgpq3": asdict(self.config.bgpq3),
            "as_processing": asdict(self.config.as_processing),
            "output": asdict(self.config.output),
            "logging": asdict(self.config.logging),
            "irr_proxy": asdict(self.config.irr_proxy),
            "installation_mode": asdict(self.config.installation_mode),
            "autonomous_mode": asdict(self.config.autonomous_mode),
            "rpki": asdict(self.config.rpki),
        }

        # Write to file
        with open(config_path, "w") as f:
            json.dump(config_dict, f, indent=2)

        self.logger.info(f"Configuration saved to {config_path}")
        return config_path

    def get_config(self) -> BGPToolkitConfig:
        """Get current configuration with timeout validation"""
        # Validate timeouts on first config load
        if not hasattr(self, "_timeouts_validated"):
            from otto_bgp.utils.timeout_config import validate_timeouts

            timeout_results = validate_timeouts()

            # Log timeout validation summary
            logger = logging.getLogger("otto-bgp.config")
            total_count = len(timeout_results.get("timeouts", {}))
            valid = timeout_results.get("valid", False)
            status = 'valid' if valid else 'issues found'
            logger.info(
                f"Timeout validation completed: {status} ({total_count} configurations checked)"
            )

            # Log any timeout issues
            for warning in timeout_results.get("warnings", []):
                logger.warning(f"Timeout configuration warning: {warning}")
            for error in timeout_results.get("errors", []):
                logger.error(f"Timeout configuration error: {error}")

            self._timeouts_validated = True

        return self.config

    def update_ssh_config(self, **kwargs):
        """Update SSH configuration"""
        for key, value in kwargs.items():
            if hasattr(self.config.ssh, key):
                setattr(self.config.ssh, key, value)

    def update_bgpq3_config(self, **kwargs):
        """Update BGPq3 configuration"""
        for key, value in kwargs.items():
            if hasattr(self.config.bgpq3, key):
                setattr(self.config.bgpq3, key, value)

    def update_proxy_config(self, **kwargs):
        """Update IRR proxy configuration"""
        for key, value in kwargs.items():
            if hasattr(self.config.irr_proxy, key):
                setattr(self.config.irr_proxy, key, value)

    def update_installation_config(self, **kwargs):
        """Update installation mode configuration"""
        for key, value in kwargs.items():
            if hasattr(self.config.installation_mode, key):
                setattr(self.config.installation_mode, key, value)

    def update_autonomous_config(self, **kwargs):
        """Update autonomous mode configuration"""
        for key, value in kwargs.items():
            if hasattr(self.config.autonomous_mode, key):
                setattr(self.config.autonomous_mode, key, value)

    def update_email_config(self, **kwargs):
        """Update email notification configuration"""
        for key, value in kwargs.items():
            if hasattr(self.config.autonomous_mode.notifications.email, key):
                setattr(self.config.autonomous_mode.notifications.email, key, value)

    def update_rpki_config(self, **kwargs):
        """Update RPKI configuration"""
        for key, value in kwargs.items():
            if hasattr(self.config.rpki, key):
                setattr(self.config.rpki, key, value)

    @classmethod
    def validate_object(cls, data: dict) -> List[str]:
        """
        Validate configuration from dictionary without side effects

        Args:
            data: Configuration dictionary to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        # Create temporary instance without loading from file
        temp_manager = cls.__new__(cls)
        temp_manager.logger = logging.getLogger(__name__)
        temp_manager.config_path = None
        temp_manager.config = BGPToolkitConfig()

        # Load from dict (side-effect-free)
        try:
            temp_manager._load_from_dict(data)
        except Exception as e:
            return [f"Failed to load configuration: {e}"]

        # Validate loaded configuration
        return temp_manager.validate_config()

    def validate_config(self) -> List[str]:
        """
        Validate configuration and return list of issues

        Returns:
            List of validation error messages
        """
        issues = []

        # SSH validation (only if SSH will be used)
        ssh_required = True  # Can be made conditional based on pipeline mode
        if ssh_required:
            if not self.config.ssh.username:
                issues.append("SSH username not configured (set SSH_USERNAME env var)")

            if not self.config.ssh.password and not self.config.ssh.key_path:
                issues.append(
                    "SSH authentication not configured (set SSH_PASSWORD or SSH_KEY_PATH env var)"
                )

        # AS processing validation
        if (
            self.config.as_processing.min_as_number
            >= self.config.as_processing.max_as_number
        ):
            issues.append("Invalid AS number range: min >= max")

        # Output validation (side-effect-free)
        output_dir = Path(self.config.output.default_output_dir)
        if output_dir.exists():
            if not output_dir.is_dir():
                issues.append(f"Output path exists but is not a directory: {output_dir}")
            elif not os.access(output_dir, os.W_OK):
                issues.append(f"Output directory is not writable: {output_dir}")
        else:
            # Check if parent directory exists and is writable
            parent_dir = output_dir.parent
            if not parent_dir.exists():
                issues.append(f"Output parent directory does not exist: {parent_dir}")
            elif not os.access(parent_dir, os.W_OK):
                issues.append(f"Output parent directory is not writable: {parent_dir}")

        # IRR proxy validation (only if enabled)
        if self.config.irr_proxy.enabled:
            if not self.config.irr_proxy.jump_host:
                issues.append("IRR proxy enabled but jump_host not configured")

            if not self.config.irr_proxy.jump_user:
                issues.append("IRR proxy enabled but jump_user not configured")

            # Validate SSH key if specified
            if self.config.irr_proxy.ssh_key_file:
                key_path = Path(self.config.irr_proxy.ssh_key_file)
                if not key_path.exists():
                    issues.append(f"IRR proxy SSH key not found: {key_path}")

            # Validate known_hosts if specified
            if self.config.irr_proxy.known_hosts_file:
                known_hosts_path = Path(self.config.irr_proxy.known_hosts_file)
                if not known_hosts_path.exists():
                    issues.append(
                        f"IRR proxy known_hosts file not found: {known_hosts_path}"
                    )

            # Validate tunnel configurations
            if not self.config.irr_proxy.tunnels:
                issues.append("IRR proxy enabled but no tunnels configured")
            else:
                for i, tunnel in enumerate(self.config.irr_proxy.tunnels):
                    if "local_port" not in tunnel or "remote_host" not in tunnel:
                        issues.append(f"IRR proxy tunnel {i} missing required fields")

        # Installation mode validation
        if self.config.installation_mode:
            install_mode = self.config.installation_mode.type
            if install_mode not in ["user", "system"]:
                issues.append(
                    f"Invalid installation mode: {install_mode}. Must be 'user' or 'system'"
                )

            optimization_level = self.config.installation_mode.optimization_level
            if optimization_level not in ["basic", "enhanced"]:
                issues.append(
                    f"Invalid optimization level: {optimization_level}. Must be 'basic' or 'enhanced'"
                )

        # Autonomous mode validation (only if enabled)
        if self.config.autonomous_mode and self.config.autonomous_mode.enabled:
            autonomous = self.config.autonomous_mode

            # Validate auto_apply_threshold
            threshold = autonomous.auto_apply_threshold
            if not isinstance(threshold, int) or threshold < 1:
                issues.append("auto_apply_threshold must be positive integer")
            elif threshold > 10000:
                issues.append(
                    f"auto_apply_threshold very high: {threshold} (consider reducing for safety)"
                )

            # Validate safety overrides
            if autonomous.safety_overrides:
                safety = autonomous.safety_overrides

                if not 0.0 <= safety.max_session_loss_percent <= 100.0:
                    issues.append(
                        "max_session_loss_percent must be between 0.0 and 100.0"
                    )

                if not 0.0 <= safety.max_route_loss_percent <= 100.0:
                    issues.append(
                        "max_route_loss_percent must be between 0.0 and 100.0"
                    )

                if not 30 <= safety.monitoring_duration_seconds <= 3600:
                    issues.append(
                        "monitoring_duration_seconds must be between 30 and 3600"
                    )

            # Validate email notification configuration
            if (
                autonomous.notifications
                and autonomous.notifications.email
                and autonomous.notifications.email.enabled
            ):
                email = autonomous.notifications.email
                method = getattr(email, "delivery_method", "sendmail")

                # Common requirements
                if not email.from_address:
                    issues.append(
                        "Email notifications enabled but from_address not configured"
                    )

                if not email.to_addresses:
                    issues.append(
                        "Email notifications enabled but to_addresses not configured"
                    )

                # Validate email addresses format (basic validation)
                import re

                email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

                if not re.match(email_pattern, email.from_address):
                    issues.append(f"Invalid from_address format: {email.from_address}")

                for addr in email.to_addresses:
                    if not re.match(email_pattern, addr):
                        issues.append(f"Invalid to_address format: {addr}")

                # Method-specific validation
                if method == "smtp":
                    if not email.smtp_server:
                        issues.append("SMTP selected but smtp_server not configured")
                    if not 1 <= email.smtp_port <= 65535:
                        issues.append(f"Invalid SMTP port: {email.smtp_port}")
                elif method == "sendmail":
                    if not email.sendmail_path:
                        issues.append(
                            "sendmail selected but sendmail_path not configured"
                        )
                    elif not Path(email.sendmail_path).is_absolute():
                        issues.append(
                            f"sendmail_path must be absolute: {email.sendmail_path}"
                        )
                    elif not Path(email.sendmail_path).is_file():
                        issues.append(
                            f"sendmail_path does not exist: {email.sendmail_path}"
                        )
                    elif not os.access(email.sendmail_path, os.X_OK):
                        issues.append(
                            f"sendmail_path is not executable: {email.sendmail_path}"
                        )

        # Validate installation and autonomous mode compatibility
        if (
            self.config.autonomous_mode
            and self.config.autonomous_mode.enabled
            and self.config.installation_mode
            and self.config.installation_mode.type == "user"
        ):
            issues.append(
                "Autonomous mode recommended with system installation for production use"
            )

        # RPKI configuration validation (only if enabled)
        if self.config.rpki and self.config.rpki.enabled:
            rpki = self.config.rpki

            # Validate VRP cache path (side-effect-free)
            if rpki.vrp_cache_path:
                vrp_cache_path = Path(rpki.vrp_cache_path)
                vrp_cache_dir = vrp_cache_path.parent
                if vrp_cache_dir.exists():
                    if not vrp_cache_dir.is_dir():
                        issues.append(f"VRP cache parent path exists but is not a directory: {vrp_cache_dir}")
                    elif not os.access(vrp_cache_dir, os.W_OK):
                        issues.append(f"VRP cache directory is not writable: {vrp_cache_dir}")
                else:
                    # Check if parent's parent exists and is writable
                    grandparent = vrp_cache_dir.parent
                    if grandparent.exists() and not os.access(grandparent, os.W_OK):
                        issues.append(f"Cannot create VRP cache directory (parent not writable): {vrp_cache_dir}")

            # Validate allowlist path (side-effect-free)
            if rpki.allowlist_path:
                allowlist_path = Path(rpki.allowlist_path)
                allowlist_dir = allowlist_path.parent
                if allowlist_dir.exists():
                    if not allowlist_dir.is_dir():
                        issues.append(f"Allowlist parent path exists but is not a directory: {allowlist_dir}")
                    elif not os.access(allowlist_dir, os.W_OK):
                        issues.append(f"Allowlist directory is not writable: {allowlist_dir}")
                else:
                    # Check if parent's parent exists and is writable
                    grandparent = allowlist_dir.parent
                    if grandparent.exists() and not os.access(grandparent, os.W_OK):
                        issues.append(f"Cannot create allowlist directory (parent not writable): {allowlist_dir}")

            # Validate thresholds
            if not 0.0 <= rpki.max_invalid_percent <= 100.0:
                issues.append("RPKI max_invalid_percent must be between 0.0 and 100.0")

            if not 0.0 <= rpki.max_notfound_percent <= 100.0:
                issues.append("RPKI max_notfound_percent must be between 0.0 and 100.0")

            # Validate age settings
            if not 1 <= rpki.max_vrp_age_hours <= 168:  # 1 hour to 1 week
                issues.append(
                    "RPKI max_vrp_age_hours must be between 1 and 168 (1 week)"
                )

            if rpki.auto_update_vrp and not 1 <= rpki.vrp_update_interval_hours <= 24:
                issues.append("RPKI vrp_update_interval_hours must be between 1 and 24")

            # Validate fail-closed with autonomous mode
            if (
                self.config.autonomous_mode
                and self.config.autonomous_mode.enabled
                and not rpki.fail_closed
            ):
                issues.append(
                    "RPKI fail-closed recommended with autonomous mode for security"
                )

        return issues

    def print_config(self):
        """Print current configuration (sanitized)"""
        print("Otto BGP Configuration:")
        print("  SSH:")
        print(f"    Username: {self.config.ssh.username or 'Not set'}")
        print(f"    Key path: {self.config.ssh.key_path or 'Not set'}")
        print(f"    Password: {'Set' if self.config.ssh.password else 'Not set'}")
        print(f"    Connection timeout: {self.config.ssh.connection_timeout}s")
        print(f"    Command timeout: {self.config.ssh.command_timeout}s")

        print("  BGPq3:")
        print(f"    Native path: {self.config.bgpq3.native_path or 'Auto-detect'}")
        print(f"    Docker image: {self.config.bgpq3.docker_image}")
        print(f"    Use Docker: {self.config.bgpq3.use_docker}")
        print(f"    Use Podman: {self.config.bgpq3.use_podman}")
        print(f"    Command timeout: {self.config.bgpq3.command_timeout}s")

        print("  AS Processing:")
        print(
            f"    AS range: {self.config.as_processing.min_as_number}-{self.config.as_processing.max_as_number}"
        )
        print(f"    Default pattern: {self.config.as_processing.default_pattern}")

        print("  Output:")
        print(f"    Default directory: {self.config.output.default_output_dir}")
        print(f"    Policies subdirectory: {self.config.output.policies_subdir}")

        print("  Logging:")
        print(f"    Level: {self.config.logging.level}")
        print(f"    Log to file: {self.config.logging.log_to_file}")
        if self.config.logging.log_file:
            print(f"    Log file: {self.config.logging.log_file}")

        print("  IRR Proxy:")
        print(f"    Enabled: {self.config.irr_proxy.enabled}")
        if self.config.irr_proxy.enabled:
            print(f"    Jump host: {self.config.irr_proxy.jump_host}")
            print(f"    Jump user: {self.config.irr_proxy.jump_user}")
            print(f"    SSH key: {self.config.irr_proxy.ssh_key_file or 'Not set'}")
            print(
                f"    Known hosts: {self.config.irr_proxy.known_hosts_file or 'Not set'}"
            )
            print(f"    Tunnels configured: {len(self.config.irr_proxy.tunnels)}")
            for tunnel in self.config.irr_proxy.tunnels:
                tunnel_name = tunnel.get("name", "unnamed")
                remote_host = tunnel.get("remote_host")
                remote_port = tunnel.get("remote_port")
                local_port = tunnel.get("local_port")
                print(
                    f"      {tunnel_name}: {remote_host}:{remote_port} -> :{local_port}"
                )

        print("  Installation Mode:")
        print(f"    Type: {self.config.installation_mode.type}")
        print(f"    Service user: {self.config.installation_mode.service_user}")
        print(f"    SystemD enabled: {self.config.installation_mode.systemd_enabled}")
        print(
            f"    Optimization level: {self.config.installation_mode.optimization_level}"
        )

        print("  Autonomous Mode:")
        print(f"    Enabled: {self.config.autonomous_mode.enabled}")
        if self.config.autonomous_mode.enabled:
            print(
                f"    Auto-apply threshold: {self.config.autonomous_mode.auto_apply_threshold} (informational)"
            )
            print(
                f"    Require confirmation: {self.config.autonomous_mode.require_confirmation}"
            )
            print("    Safety overrides:")
            print(
                f"      Max session loss: {self.config.autonomous_mode.safety_overrides.max_session_loss_percent}%"
            )
            print(
                f"      Max route loss: {self.config.autonomous_mode.safety_overrides.max_route_loss_percent}%"
            )
            monitoring_duration = self.config.autonomous_mode.safety_overrides.monitoring_duration_seconds
            print(f"      Monitoring duration: {monitoring_duration}s")
            print("    Email notifications:")
            email = self.config.autonomous_mode.notifications.email
            print(f"      Enabled: {email.enabled}")
            if email.enabled:
                print(f"      SMTP server: {email.smtp_server}:{email.smtp_port}")
                print(f"      From address: {email.from_address}")
                print(f"      To addresses: {', '.join(email.to_addresses)}")
                print(f"      Subject prefix: {email.subject_prefix}")
                print(f"      Send on success: {email.send_on_success}")
                print(f"      Send on failure: {email.send_on_failure}")
        else:
            print("    Manual policy application mode")

        print("  RPKI/ROA Validation:")
        print(f"    Enabled: {self.config.rpki.enabled}")
        if self.config.rpki.enabled:
            print(f"    Fail-closed: {self.config.rpki.fail_closed}")
            print(f"    Max VRP age: {self.config.rpki.max_vrp_age_hours} hours")
            print(f"    VRP cache path: {self.config.rpki.vrp_cache_path}")
            print(f"    Allowlist path: {self.config.rpki.allowlist_path}")
            print("    Thresholds:")
            print(
                f"      Max invalid prefixes: {self.config.rpki.max_invalid_percent}%"
            )
            print(
                f"      Max NOTFOUND prefixes: {self.config.rpki.max_notfound_percent}%"
            )
            print(f"      Require VRP data: {self.config.rpki.require_vrp_data}")
            print("    Auto-update:")
            print(f"      Enabled: {self.config.rpki.auto_update_vrp}")
            if self.config.rpki.auto_update_vrp:
                print(
                    f"      Update interval: {self.config.rpki.vrp_update_interval_hours} hours"
                )
        else:
            print("    RPKI validation disabled")


# Global configuration instance with thread-safe singleton pattern
_config_manager = None
_config_manager_lock = threading.RLock()


def get_config_manager(config_path: Optional[Path] = None) -> ConfigManager:
    """
    Get global configuration manager instance using thread-safe double-checked locking.

    Fixes race condition where multiple threads could create multiple instances
    during concurrent initialization. Uses double-checked locking pattern for
    optimal performance - fast path avoids lock acquisition after initialization.

    Performance: First check is lockless, lock only acquired during initialization.
    """
    global _config_manager

    # Fast path - avoid lock if already initialized (lockless read)
    if _config_manager is not None:
        return _config_manager

    # Slow path - thread-safe initialization with double-checked locking
    with _config_manager_lock:
        # Check again inside lock in case another thread initialized it
        if _config_manager is None:
            # Log thread info for race condition debugging
            thread_id = threading.current_thread().ident
            logger = logging.getLogger(__name__)
            logger.debug(f"Initializing ConfigManager singleton in thread {thread_id}")

            _config_manager = ConfigManager(config_path)

        return _config_manager


def get_config() -> BGPToolkitConfig:
    """Get current configuration"""
    return get_config_manager().get_config()
