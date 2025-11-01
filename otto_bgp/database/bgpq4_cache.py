"""BGPq4 policy cache manager using SQLite backend

This module provides SQLite-based caching for BGP policy generation results,
supporting both AS numbers and IRR objects (AS-SETs) with TTL-based expiration.
"""
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from .core import DatabaseManager

logger = logging.getLogger('otto_bgp.database.bgpq4_cache')


class BGPq4CacheManager:
    """Manages BGP policy cache in SQLite"""

    def __init__(self):
        """Initialize cache manager"""
        self.db = DatabaseManager()

    def _generate_cache_key(
        self,
        as_number: Optional[int] = None,
        policy_name: Optional[str] = None,
        resource: Optional[str] = None
    ) -> str:
        """Generate cache key for policy lookup

        Args:
            as_number: AS number (for AS-based policies)
            policy_name: Policy name suffix
            resource: IRR object name (for AS-SET policies)

        Returns:
            Cache key string

        Raises:
            ValueError: If neither as_number nor resource is provided
        """
        if as_number:
            base = f"AS{as_number}"
        elif resource:
            base = resource.upper()  # Normalize AS-SETs to uppercase
        else:
            raise ValueError("Either as_number or resource required for cache key")

        if policy_name:
            return f"{base}:{policy_name}"
        return f"{base}:default"

    def get_policy(
        self,
        as_number: Optional[int] = None,
        policy_name: Optional[str] = None,
        resource: Optional[str] = None
    ) -> Optional[str]:
        """Get cached policy if available and not expired

        Args:
            as_number: AS number
            policy_name: Policy name
            resource: IRR object name

        Returns:
            Policy content if found and valid, None otherwise
        """
        try:
            cache_key = self._generate_cache_key(
                as_number=as_number,
                policy_name=policy_name,
                resource=resource
            )

            query = '''
                SELECT prefixes, fetched_date, ttl_hours, hits
                FROM bgpq4_cache
                WHERE cache_key = ?
            '''

            row = self.db.fetchone(query, (cache_key,))
            if not row:
                logger.debug(f"Cache miss: {cache_key}")
                return None

            # Check if expired
            fetched = datetime.fromisoformat(row['fetched_date'])
            ttl_hours = row['ttl_hours'] or 24
            expiry = fetched + timedelta(hours=ttl_hours)

            if datetime.utcnow() > expiry:
                logger.debug(f"Cache expired: {cache_key}")
                return None

            # Update hit counter
            update_query = '''
                UPDATE bgpq4_cache
                SET hits = hits + 1, last_hit = ?
                WHERE cache_key = ?
            '''
            try:
                self.db.execute(update_query, (datetime.utcnow(), cache_key))
            except Exception as e:
                logger.warning(f"Failed to update cache hit counter: {e}")

            logger.debug(f"Cache hit: {cache_key} (hits: {row['hits'] + 1})")
            return row['prefixes']

        except Exception as e:
            logger.warning(f"Cache get failed: {e}")
            return None

    def put_policy(
        self,
        policy_content: str,
        as_number: Optional[int] = None,
        policy_name: Optional[str] = None,
        resource: Optional[str] = None,
        ttl: int = 3600
    ) -> None:
        """Store policy in cache with TTL

        Args:
            policy_content: The policy configuration text
            as_number: AS number (for AS-based policies)
            policy_name: Policy name
            resource: IRR object name (for AS-SET policies)
            ttl: Time to live in seconds (default 3600 = 1 hour)
        """
        try:
            cache_key = self._generate_cache_key(
                as_number=as_number,
                policy_name=policy_name,
                resource=resource
            )

            # Convert TTL from seconds to hours
            ttl_hours = max(1, ttl // 3600)

            # Count prefixes in policy
            prefix_count = policy_content.count('route-filter') if policy_content else 0

            # Retry logic for SQLITE_BUSY errors
            max_retries = 3
            retry_delay = 0.1

            for attempt in range(max_retries):
                try:
                    with self.db.transaction() as conn:
                        conn.execute('''
                            INSERT OR REPLACE INTO bgpq4_cache
                            (cache_key, as_number, resource, prefixes,
                             prefix_count, raw_output, ttl_hours)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            cache_key,
                            as_number,
                            resource,
                            policy_content,
                            prefix_count,
                            policy_content,
                            ttl_hours
                        ))
                    logger.debug(f"Cached policy: {cache_key} (prefixes: {prefix_count})")
                    return  # Success

                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e) and attempt < max_retries - 1:
                        time.sleep(retry_delay * (2 ** attempt))
                    else:
                        logger.warning(f"Cache write failed after {attempt + 1} attempts: {e}")
                        return  # Fail silently for cache operations

        except Exception as e:
            logger.warning(f"Cache put failed: {e}")

    def invalidate_policy(
        self,
        as_number: Optional[int] = None,
        policy_name: Optional[str] = None,
        resource: Optional[str] = None
    ) -> None:
        """Invalidate cached policy

        Args:
            as_number: AS number
            policy_name: Policy name
            resource: IRR object name
        """
        try:
            cache_key = self._generate_cache_key(
                as_number=as_number,
                policy_name=policy_name,
                resource=resource
            )

            query = 'DELETE FROM bgpq4_cache WHERE cache_key = ?'
            self.db.execute(query, (cache_key,))
            logger.debug(f"Invalidated cache: {cache_key}")

        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")

    def clear_expired(self) -> int:
        """Remove expired cache entries

        Returns:
            Number of entries removed
        """
        try:
            query = '''
                DELETE FROM bgpq4_cache
                WHERE datetime(fetched_date, '+' || ttl_hours || ' hours') < datetime('now')
            '''

            with self.db.transaction() as conn:
                cursor = conn.execute(query)
                count = cursor.rowcount

            logger.info(f"Cleared {count} expired cache entries")
            return count

        except Exception as e:
            logger.error(f"Failed to clear expired cache: {e}")
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics

        Returns:
            Dictionary with cache statistics
        """
        try:
            stats_query = '''
                SELECT
                    COUNT(*) as total_entries,
                    SUM(hits) as total_hits,
                    SUM(prefix_count) as total_prefixes,
                    COUNT(CASE WHEN as_number IS NOT NULL THEN 1 END) as as_entries,
                    COUNT(CASE WHEN resource IS NOT NULL THEN 1 END) as resource_entries
                FROM bgpq4_cache
            '''

            row = self.db.fetchone(stats_query)
            if not row:
                return {
                    'total_entries': 0,
                    'total_hits': 0,
                    'total_prefixes': 0,
                    'as_entries': 0,
                    'resource_entries': 0
                }

            return {
                'total_entries': row['total_entries'] or 0,
                'total_hits': row['total_hits'] or 0,
                'total_prefixes': row['total_prefixes'] or 0,
                'as_entries': row['as_entries'] or 0,
                'resource_entries': row['resource_entries'] or 0
            }

        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {
                'total_entries': 0,
                'total_hits': 0,
                'total_prefixes': 0,
                'as_entries': 0,
                'resource_entries': 0,
                'error': str(e)
            }
