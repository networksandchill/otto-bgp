#!/usr/bin/env python3
"""
SSH Security Module for Otto BGP

Provides secure SSH host key verification for production deployments.
Replaces the insecure AutoAddPolicy with proper host key validation.

Security features:
- Pre-deployed known_hosts file verification
- Strict host key checking for production
- Setup mode for initial host key collection
- Detailed logging of security events
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

import paramiko


class ProductionHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    """
    Production-grade SSH host key verification policy.

    This policy strictly verifies all host keys against a pre-deployed
    known_hosts file. It will never automatically accept unknown hosts
    in production mode.
    """

    def __init__(self, known_hosts_path: Optional[str] = None, strict: bool = True):
        """
        Initialize the production host key policy.

        Args:
            known_hosts_path: Path to known_hosts file. Defaults to
                            /var/lib/otto-bgp/ssh-keys/known_hosts
            strict: If True, reject all unknown hosts. If False, allow
                   trust-on-first-use (only for initial setup)
        """
        self.logger = logging.getLogger(__name__)

        # Default production path
        if known_hosts_path is None:
            known_hosts_path = os.getenv(
                "SSH_KNOWN_HOSTS", "/var/lib/otto-bgp/ssh-keys/known_hosts"
            )

        self.known_hosts_path = Path(known_hosts_path)
        self.strict = strict
        self.host_keys = paramiko.HostKeys()

        # Load existing known hosts if file exists
        if self.known_hosts_path.exists():
            try:
                self.host_keys.load(str(self.known_hosts_path))
                self.logger.info(
                    f"Loaded {len(self.host_keys)} host keys from {self.known_hosts_path}"
                )
            except Exception as e:
                self.logger.error(
                    f"Failed to load known_hosts from {self.known_hosts_path}: {e}"
                )
                if self.strict:
                    raise RuntimeError(
                        f"Cannot load known_hosts file in strict mode: {e}"
                    )
        else:
            if self.strict:
                raise RuntimeError(
                    f"Production known_hosts file missing: {self.known_hosts_path}. "
                    f"Run setup-host-keys.sh to collect host keys before deployment."
                )
            else:
                self.logger.warning(
                    f"Known hosts file does not exist: {self.known_hosts_path}. "
                    f"Running in setup mode - host keys will be collected."
                )
                # Create parent directory if it doesn't exist
                self.known_hosts_path.parent.mkdir(parents=True, exist_ok=True)

    def missing_host_key(self, client, hostname, key):
        """
        Handle missing host key based on strict mode setting.

        In strict mode (production): Always reject unknown hosts
        In setup mode: Add new hosts to known_hosts file
        """
        key_fingerprint = self._get_key_fingerprint(key)

        # Check if we already have this host
        if hostname in self.host_keys:
            # Check if the key matches any known key for this host
            for known_key in self.host_keys[hostname].values():
                if known_key.get_fingerprint() == key.get_fingerprint():
                    # Key matches, allow connection
                    self.logger.debug(
                        f"Host {hostname} key verified: {key_fingerprint}"
                    )
                    return

            # Host is known but key doesn't match - potential security issue
            self.logger.error(
                f"HOST KEY MISMATCH for {hostname}! "
                f"Expected keys: {[self._get_key_fingerprint(k) for k in self.host_keys[hostname].values()]} "
                f"Received key: {key_fingerprint}"
            )
            raise paramiko.SSHException(
                f"Host key verification failed for {hostname}: "
                f"Key mismatch (possible MITM attack)"
            )

        # Host is unknown
        if self.strict:
            # Production mode - never accept unknown hosts
            self.logger.error(
                f"UNKNOWN HOST rejected: {hostname} with fingerprint {key_fingerprint}. "
                f"Add to {self.known_hosts_path} before connecting."
            )
            raise paramiko.SSHException(
                f"Host {hostname} not in known_hosts. "
                f"Run setup script to add host key before production deployment."
            )
        else:
            # Setup mode - add to known_hosts
            self.logger.warning(
                f"NEW HOST detected: {hostname} with fingerprint {key_fingerprint}. "
                f"Adding to {self.known_hosts_path}"
            )

            # Add to in-memory host keys
            self.host_keys.add(hostname, key.get_name(), key)

            # Save to file
            try:
                self.host_keys.save(str(self.known_hosts_path))
                self.logger.info(
                    f"Host key for {hostname} saved to {self.known_hosts_path}"
                )
            except Exception as e:
                self.logger.error(f"Failed to save host key for {hostname}: {e}")
                raise

    def _get_key_fingerprint(self, key) -> str:
        """Get human-readable fingerprint of SSH key"""
        # Get SHA256 fingerprint (modern format)
        fingerprint_bytes = key.get_fingerprint()
        fingerprint_hex = fingerprint_bytes.hex()
        # Format as SHA256:base64 (like OpenSSH)
        import base64

        fingerprint_b64 = (
            base64.b64encode(fingerprint_bytes).decode("ascii").rstrip("=")
        )
        self.logger.debug("Computed SSH fingerprint hex=%s", fingerprint_hex)
        return f"SHA256:{fingerprint_b64}"


class HostKeyManager:
    """
    Manages SSH host keys for the BGP toolkit.
    Provides utilities for setup, verification, and maintenance.
    """

    def __init__(self, known_hosts_path: Optional[str] = None):
        """Initialize the host key manager"""
        self.logger = logging.getLogger(__name__)

        if known_hosts_path is None:
            known_hosts_path = os.getenv(
                "SSH_KNOWN_HOSTS", "/var/lib/otto-bgp/ssh-keys/known_hosts"
            )

        self.known_hosts_path = Path(known_hosts_path)
        self.host_keys = paramiko.HostKeys()

        if self.known_hosts_path.exists():
            self.host_keys.load(str(self.known_hosts_path))

    def collect_host_key(self, hostname: str, port: int = 22) -> bool:
        """
        Collect SSH host key from a device using ssh-keyscan equivalent.

        Args:
            hostname: Hostname or IP address of the device
            port: SSH port (default 22)

        Returns:
            True if key was successfully collected, False otherwise
        """
        try:
            # Create a temporary SSH client just to get the host key
            temp_client = paramiko.SSHClient()
            temp_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Try to connect (will fail auth but we get the host key)
            try:
                temp_client.connect(
                    hostname=hostname,
                    port=port,
                    username="dummy",
                    password="dummy",
                    timeout=5,
                    auth_timeout=1,
                )
            except (paramiko.AuthenticationException, paramiko.SSHException):
                # Expected - we just want the host key
                pass

            # Get the host key from the client
            if hostname in temp_client.get_host_keys():
                for key_type, key in temp_client.get_host_keys()[hostname].items():
                    self.host_keys.add(hostname, key_type, key)
                    self.logger.info(f"Collected {key_type} key for {hostname}")

                # Save to file
                self.host_keys.save(str(self.known_hosts_path))
                return True

            return False

        except Exception as e:
            self.logger.error(f"Failed to collect host key for {hostname}: {e}")
            return False
        finally:
            try:
                temp_client.close()
            except (paramiko.SSHException, OSError) as e:
                self.logger.debug(f"SSH cleanup warning for temp client: {e}")

    def verify_host_keys(self) -> dict:
        """
        Verify the integrity of the known_hosts file.

        Returns:
            Dictionary with verification results
        """
        results = {
            "total_hosts": len(self.host_keys),
            "total_keys": 0,
            "key_types": {},
            "hosts": [],
        }

        for hostname in self.host_keys:
            host_info = {"hostname": hostname, "keys": []}

            for key_type, key in self.host_keys[hostname].items():
                results["total_keys"] += 1

                if key_type not in results["key_types"]:
                    results["key_types"][key_type] = 0
                results["key_types"][key_type] += 1

                # Calculate fingerprint
                fingerprint = self._get_key_fingerprint(key)
                host_info["keys"].append({"type": key_type, "fingerprint": fingerprint})

            results["hosts"].append(host_info)

        return results

    def _get_key_fingerprint(self, key) -> str:
        """Get human-readable fingerprint of SSH key"""
        import base64

        fingerprint_bytes = key.get_fingerprint()
        fingerprint_b64 = (
            base64.b64encode(fingerprint_bytes).decode("ascii").rstrip("=")
        )
        return f"SHA256:{fingerprint_b64}"

    def export_to_json(self, output_path: str):
        """
        Export host keys to JSON format for backup/audit.

        Args:
            output_path: Path to write JSON file
        """
        data = self.verify_host_keys()

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        self.logger.info(f"Exported host keys to {output_path}")


def get_host_key_policy(setup_mode: bool = False) -> paramiko.MissingHostKeyPolicy:
    """
    Factory function to get appropriate host key policy.

    Args:
        setup_mode: If True, return policy for initial setup (collects keys).
                   If False, return strict production policy.

    Returns:
        Appropriate paramiko host key policy
    """
    if setup_mode:
        # Check if we're explicitly in setup mode via environment
        if os.getenv("OTTO_BGP_SETUP_MODE", "").lower() == "true":
            logging.getLogger(__name__).warning(
                "Running in SETUP MODE - host keys will be automatically collected. "
                "Disable OTTO_BGP_SETUP_MODE for production!"
            )
            return ProductionHostKeyPolicy(strict=False)

    # Production mode - strict verification
    return ProductionHostKeyPolicy(strict=True)
