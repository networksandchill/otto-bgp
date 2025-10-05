"""
Caching Utilities for Otto BGP

Provides intelligent caching for policy generation and discovery results.
"""

import json
import time
import hashlib
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Union
from dataclasses import dataclass, asdict


logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with metadata"""

    data: Any
    timestamp: float
    ttl_seconds: int
    key_hash: str

    @property
    def is_expired(self) -> bool:
        """Check if cache entry has expired"""
        return time.time() - self.timestamp > self.ttl_seconds

    @property
    def age_seconds(self) -> int:
        """Get age of cache entry in seconds"""
        return int(time.time() - self.timestamp)


class PolicyCache:
    """Cache for BGP policy generation results"""

    def __init__(self, cache_dir: Union[str, Path] = None, default_ttl: int = 3600):
        """
        Initialize policy cache

        Args:
            cache_dir: Directory for cache files (default: ~/.otto-bgp/cache)
            default_ttl: Default TTL in seconds (default: 1 hour)
        """
        if cache_dir is None:
            cache_dir = Path.home() / ".otto-bgp" / "cache"

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.default_ttl = default_ttl
        self.logger = logging.getLogger(self.__class__.__name__)

        # In-memory cache for performance
        self._memory_cache: Dict[str, CacheEntry] = {}

        # Load existing cache from disk
        self._load_disk_cache()

    def get_policy(
        self,
        as_number: Optional[int] = None,
        policy_name: str = None,
        *,
        resource: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get cached policy for AS number or IRR object

        Args:
            as_number: AS number (optional)
            policy_name: Policy name (optional)
            resource: IRR object name (optional)

        Returns:
            Cached policy content or None if not found/expired
        """
        cache_key = self._generate_policy_key(as_number, policy_name, resource)

        # Check memory cache first
        if cache_key in self._memory_cache:
            entry = self._memory_cache[cache_key]
            if not entry.is_expired:
                resource_id = resource or f"AS{as_number}" if as_number else "unknown"
                self.logger.debug(
                    f"Policy cache hit for {resource_id} (age: {entry.age_seconds}s)"
                )
                return entry.data
            else:
                # Remove expired entry
                del self._memory_cache[cache_key]
                self._remove_disk_entry(cache_key)

        resource_id = resource or f"AS{as_number}" if as_number else "unknown"
        self.logger.debug(f"Policy cache miss for {resource_id}")
        return None

    def put_policy(
        self,
        as_number: Optional[int] = None,
        policy_content: str = "",
        policy_name: str = None,
        ttl: int = None,
        *,
        resource: Optional[str] = None,
    ) -> None:
        """
        Cache policy for AS number or IRR object

        Args:
            as_number: AS number (optional)
            policy_content: Policy content to cache
            policy_name: Policy name (optional)
            ttl: Time to live in seconds (optional)
            resource: IRR object name (optional)
        """
        if not policy_content.strip():
            return  # Don't cache empty policies

        cache_key = self._generate_policy_key(as_number, policy_name, resource)
        ttl = ttl or self.default_ttl

        entry = CacheEntry(
            data=policy_content,
            timestamp=time.time(),
            ttl_seconds=ttl,
            key_hash=self._hash_key(cache_key),
        )

        # Store in memory
        self._memory_cache[cache_key] = entry

        # Store on disk
        self._save_disk_entry(cache_key, entry)

        resource_id = resource or f"AS{as_number}" if as_number else "unknown"
        self.logger.debug(f"Cached policy for {resource_id} (TTL: {ttl}s)")

    def invalidate_policy(
        self,
        as_number: Optional[int] = None,
        policy_name: str = None,
        *,
        resource: Optional[str] = None,
    ) -> None:
        """
        Invalidate cached policy

        Args:
            as_number: AS number (optional)
            policy_name: Policy name (optional)
            resource: IRR object name (optional)
        """
        cache_key = self._generate_policy_key(as_number, policy_name, resource)

        # Remove from memory
        if cache_key in self._memory_cache:
            del self._memory_cache[cache_key]

        # Remove from disk
        self._remove_disk_entry(cache_key)

        resource_id = resource or f"AS{as_number}" if as_number else "unknown"
        self.logger.debug(f"Invalidated cache for {resource_id}")

    def clear_expired(self) -> int:
        """
        Remove all expired cache entries

        Returns:
            Number of entries removed
        """
        removed = 0
        expired_keys = []

        # Find expired entries
        for key, entry in self._memory_cache.items():
            if entry.is_expired:
                expired_keys.append(key)

        # Remove expired entries
        for key in expired_keys:
            del self._memory_cache[key]
            self._remove_disk_entry(key)
            removed += 1

        if removed > 0:
            self.logger.info(f"Removed {removed} expired cache entries")

        return removed

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics

        Returns:
            Dictionary with cache statistics
        """
        total_entries = len(self._memory_cache)
        expired_entries = sum(
            1 for entry in self._memory_cache.values() if entry.is_expired
        )

        return {
            "total_entries": total_entries,
            "active_entries": total_entries - expired_entries,
            "expired_entries": expired_entries,
            "cache_dir": str(self.cache_dir),
            "default_ttl": self.default_ttl,
        }

    def _generate_policy_key(
        self,
        as_number: Optional[int] = None,
        policy_name: Optional[str] = None,
        resource: Optional[str] = None,
    ) -> str:
        """Generate cache key for policy"""
        # Namespace by type to prevent collisions between ASN and IRR resources
        if resource:
            base = f"irr_{resource}"
        elif as_number is not None:
            base = f"asn_{as_number}"
        else:
            raise ValueError("Either resource or as_number must be provided")
        return f"policy_{base}_{policy_name}" if policy_name else f"policy_{base}"

    def _hash_key(self, key: str) -> str:
        """Generate hash for cache key"""
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def _get_disk_path(self, cache_key: str) -> Path:
        """Get disk path for cache key"""
        key_hash = self._hash_key(cache_key)
        return self.cache_dir / f"{key_hash}.json"

    def _save_disk_entry(self, cache_key: str, entry: CacheEntry) -> None:
        """Save cache entry to disk"""
        try:
            disk_path = self._get_disk_path(cache_key)
            with open(disk_path, "w") as f:
                json.dump({"cache_key": cache_key, "entry": asdict(entry)}, f)
        except Exception as e:
            self.logger.warning(f"Failed to save cache entry to disk: {e}")

    def _remove_disk_entry(self, cache_key: str) -> None:
        """Remove cache entry from disk"""
        try:
            disk_path = self._get_disk_path(cache_key)
            if disk_path.exists():
                disk_path.unlink()
        except Exception as e:
            self.logger.warning(f"Failed to remove cache entry from disk: {e}")

    def _load_disk_cache(self) -> None:
        """Load cache entries from disk"""
        if not self.cache_dir.exists():
            return

        loaded = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)

                cache_key = data["cache_key"]
                entry_data = data["entry"]

                entry = CacheEntry(
                    data=entry_data["data"],
                    timestamp=entry_data["timestamp"],
                    ttl_seconds=entry_data["ttl_seconds"],
                    key_hash=entry_data["key_hash"],
                )

                # Only load if not expired
                if not entry.is_expired:
                    self._memory_cache[cache_key] = entry
                    loaded += 1
                else:
                    # Remove expired file
                    cache_file.unlink()

            except Exception as e:
                self.logger.warning(f"Failed to load cache file {cache_file}: {e}")
                # Remove corrupted file
                try:
                    cache_file.unlink()
                except (OSError, PermissionError):
                    pass

        if loaded > 0:
            self.logger.debug(f"Loaded {loaded} cache entries from disk")


class DiscoveryCache:
    """Cache for router discovery results"""

    def __init__(self, cache_dir: Union[str, Path] = None, default_ttl: int = 1800):
        """
        Initialize discovery cache

        Args:
            cache_dir: Directory for cache files
            default_ttl: Default TTL in seconds (default: 30 minutes)
        """
        if cache_dir is None:
            cache_dir = Path.home() / ".otto-bgp" / "discovery_cache"

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.default_ttl = default_ttl
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_discovery(self, hostname: str) -> Optional[Dict]:
        """
        Get cached discovery result for hostname

        Args:
            hostname: Router hostname

        Returns:
            Cached discovery result or None
        """
        cache_file = self.cache_dir / f"{hostname}.json"

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "r") as f:
                data = json.load(f)

            # Check if expired
            age = time.time() - data["timestamp"]
            if age > data["ttl_seconds"]:
                cache_file.unlink()
                return None

            self.logger.debug(f"Discovery cache hit for {hostname} (age: {int(age)}s)")
            return data["discovery_result"]

        except Exception as e:
            self.logger.warning(f"Failed to load discovery cache for {hostname}: {e}")
            return None

    def put_discovery(
        self, hostname: str, discovery_result: Dict, ttl: int = None
    ) -> None:
        """
        Cache discovery result for hostname

        Args:
            hostname: Router hostname
            discovery_result: Discovery result to cache
            ttl: Time to live in seconds
        """
        ttl = ttl or self.default_ttl
        cache_file = self.cache_dir / f"{hostname}.json"

        data = {
            "hostname": hostname,
            "timestamp": time.time(),
            "ttl_seconds": ttl,
            "discovery_result": discovery_result,
        }

        try:
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2)

            self.logger.debug(f"Cached discovery for {hostname} (TTL: {ttl}s)")

        except Exception as e:
            self.logger.warning(f"Failed to cache discovery for {hostname}: {e}")

    def invalidate_discovery(self, hostname: str) -> None:
        """
        Invalidate cached discovery for hostname

        Args:
            hostname: Router hostname
        """
        cache_file = self.cache_dir / f"{hostname}.json"

        if cache_file.exists():
            cache_file.unlink()
            self.logger.debug(f"Invalidated discovery cache for {hostname}")

    def clear_expired(self) -> int:
        """
        Remove all expired discovery cache entries

        Returns:
            Number of entries removed
        """
        removed = 0
        current_time = time.time()

        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)

                age = current_time - data["timestamp"]
                if age > data["ttl_seconds"]:
                    cache_file.unlink()
                    removed += 1

            except Exception:
                # Remove corrupted files
                cache_file.unlink()
                removed += 1

        if removed > 0:
            self.logger.info(f"Removed {removed} expired discovery cache entries")

        return removed
