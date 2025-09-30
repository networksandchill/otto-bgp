"""RPKI override management operations with atomic transactions and caching"""
import logging
import time
from typing import List, Dict, Optional, Set
from threading import Lock

from .core import get_db
from .exceptions import OverrideError

logger = logging.getLogger('otto_bgp.database.rpki_overrides')

# Cache for disabled ASNs with TTL
_cache_lock = Lock()
_disabled_cache: Optional[Set[int]] = None
_cache_timestamp: float = 0
CACHE_TTL = 60  # 60 seconds


class RPKIOverrideManager:
    """Manages RPKI override operations with atomic transactions"""

    def __init__(self):
        self.db = get_db()

    def _validate_as_number(self, as_number: int) -> None:
        """Validate AS number is in valid range"""
        if (not isinstance(as_number, int) or
                as_number < 0 or as_number > 4294967295):
            raise ValueError(f"Invalid AS number: {as_number}")

    def _validate_input(
            self, text: str, max_length: int, field_name: str
    ) -> str:
        """Validate and truncate input text"""
        if text is None:
            return None
        text = str(text)[:max_length]
        return text

    def _invalidate_cache(self):
        """Invalidate the disabled ASN cache"""
        global _disabled_cache, _cache_timestamp
        with _cache_lock:
            _disabled_cache = None
            _cache_timestamp = 0

    def _get_disabled_cache(self) -> Set[int]:
        """Get cached set of disabled ASNs"""
        global _disabled_cache, _cache_timestamp

        with _cache_lock:
            cache_expired = (
                _disabled_cache is None or
                (time.time() - _cache_timestamp) > CACHE_TTL
            )
            if cache_expired:
                rows = self.db.fetchall(
                    "SELECT as_number FROM rpki_overrides "
                    "WHERE rpki_enabled = 0"
                )
                _disabled_cache = {row['as_number'] for row in rows}
                _cache_timestamp = time.time()
                count = len(_disabled_cache)
                logger.debug(
                    f"Refreshed disabled ASN cache: {count} entries"
                )

            return _disabled_cache.copy()

    def is_rpki_disabled(self, as_number: int) -> bool:
        """Check if RPKI is disabled for an AS (with caching)"""
        try:
            self._validate_as_number(as_number)
        except ValueError:
            return False

        # Use cache for performance
        disabled_set = self._get_disabled_cache()
        return as_number in disabled_set

    def disable_rpki(
            self, as_number: int, reason: str, user: str,
            ip_address: Optional[str] = None
    ) -> bool:
        """Disable RPKI validation for an AS (atomic operation)"""
        try:
            self._validate_as_number(as_number)
            reason = self._validate_input(reason, 500, 'reason')
            user = self._validate_input(user, 100, 'user')
            ip_address = self._validate_input(ip_address, 45, 'ip_address')

            # Atomic transaction for both tables
            with self.db.transaction() as conn:
                # Update or insert override
                conn.execute(
                    """INSERT OR REPLACE INTO rpki_overrides
                       (as_number, rpki_enabled, reason,
                        modified_date, modified_by)
                       VALUES (?, 0, ?, CURRENT_TIMESTAMP, ?)""",
                    (as_number, reason, user)
                )

                # Log to history
                conn.execute(
                    """INSERT INTO rpki_override_history
                       (as_number, action, reason, user, ip_address)
                       VALUES (?, 'disable', ?, ?, ?)""",
                    (as_number, reason, user, ip_address)
                )

            self._invalidate_cache()
            logger.info(f"RPKI disabled for AS{as_number} by {user}")
            return True

        except ValueError as e:
            raise OverrideError(f"Invalid input: {e}")
        except Exception as e:
            logger.error(f"Failed to disable RPKI for AS{as_number}: {e}")
            raise OverrideError(f"Failed to disable RPKI: {e}")

    def enable_rpki(
            self, as_number: int, reason: str, user: str,
            ip_address: Optional[str] = None
    ) -> bool:
        """Enable RPKI validation for an AS (atomic operation)"""
        try:
            self._validate_as_number(as_number)
            reason = self._validate_input(reason, 500, 'reason')
            user = self._validate_input(user, 100, 'user')
            ip_address = self._validate_input(ip_address, 45, 'ip_address')

            # Atomic transaction for both tables
            with self.db.transaction() as conn:
                # Update or insert override
                conn.execute(
                    """INSERT OR REPLACE INTO rpki_overrides
                       (as_number, rpki_enabled, reason,
                        modified_date, modified_by)
                       VALUES (?, 1, ?, CURRENT_TIMESTAMP, ?)""",
                    (as_number, reason, user)
                )

                # Log to history
                conn.execute(
                    """INSERT INTO rpki_override_history
                       (as_number, action, reason, user, ip_address)
                       VALUES (?, 'enable', ?, ?, ?)""",
                    (as_number, reason, user, ip_address)
                )

            self._invalidate_cache()
            logger.info(f"RPKI enabled for AS{as_number} by {user}")
            return True

        except ValueError as e:
            raise OverrideError(f"Invalid input: {e}")
        except Exception as e:
            logger.error(f"Failed to enable RPKI for AS{as_number}: {e}")
            raise OverrideError(f"Failed to enable RPKI: {e}")

    def get_all_overrides(self) -> List[Dict]:
        """Get all RPKI overrides"""
        rows = self.db.fetchall(
            """SELECT as_number, rpki_enabled, reason,
                      modified_date, modified_by
               FROM rpki_overrides
               ORDER BY as_number"""
        )
        return [dict(row) for row in rows]

    def get_disabled_asns(self) -> List[int]:
        """Get list of AS numbers with RPKI disabled"""
        rows = self.db.fetchall(
            "SELECT as_number FROM rpki_overrides "
            "WHERE rpki_enabled = 0"
        )
        return [row['as_number'] for row in rows]

    def get_override_history(
            self, as_number: Optional[int] = None,
            limit: int = 100
    ) -> List[Dict]:
        """Get override history"""
        if as_number:
            rows = self.db.fetchall(
                """SELECT * FROM rpki_override_history
                   WHERE as_number = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (as_number, limit)
            )
        else:
            rows = self.db.fetchall(
                """SELECT * FROM rpki_override_history
                   ORDER BY timestamp DESC LIMIT ?""",
                (limit,)
            )
        return [dict(row) for row in rows]

    def bulk_update(self, operations: List[Dict], user: str) -> Dict:
        """Perform bulk override updates"""
        success_count = 0
        failed = []

        for op in operations:
            try:
                as_number = op['as_number']
                if op['action'] == 'disable':
                    self.disable_rpki(
                        as_number,
                        op.get('reason', 'Bulk update'),
                        user
                    )
                elif op['action'] == 'enable':
                    self.enable_rpki(
                        as_number,
                        op.get('reason', 'Bulk update'),
                        user
                    )
                success_count += 1
            except Exception as e:
                failed.append({'as_number': as_number, 'error': str(e)})

        return {
            'success_count': success_count,
            'failed': failed,
            'total': len(operations)
        }
