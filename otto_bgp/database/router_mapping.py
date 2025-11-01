"""Router mapping database manager for discovery data persistence

This module manages persistent storage of discovered network topology including:
- Router inventory (devices and their properties)
- BGP groups and their relationships
- Router-to-AS number mappings

Note: This module handles discovery data persistence and is separate from
multi_router.py which manages temporary rollout orchestration state.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .core import DatabaseManager

logger = logging.getLogger('otto_bgp.database.router_mapping')


class RouterMappingManager:
    """Manages router inventory and AS mappings in SQLite"""

    def __init__(self):
        """Initialize router mapping manager"""
        self.db = DatabaseManager()

    def update_router_inventory(
        self,
        hostname: str,
        ip_address: str,
        platform: Optional[str] = None,
        model: Optional[str] = None,
        software_version: Optional[str] = None,
        serial_number: Optional[str] = None,
        location: Optional[str] = None,
        role: Optional[str] = None,
        collection_success: Optional[bool] = None
    ) -> None:
        """Update or create router inventory entry

        Args:
            hostname: Router hostname (primary key)
            ip_address: Router IP address
            platform: Device platform (e.g., 'junos')
            model: Device model
            software_version: Software version
            serial_number: Device serial number
            location: Physical location or site
            role: Router role (e.g., 'edge', 'core')
            collection_success: Whether last collection succeeded
        """
        query = '''
            INSERT INTO router_inventory (
                hostname, ip_address, platform, model,
                software_version, serial_number, location, role,
                last_seen, last_collection_success, last_collection_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(hostname) DO UPDATE SET
                ip_address = excluded.ip_address,
                platform = excluded.platform,
                model = excluded.model,
                software_version = excluded.software_version,
                serial_number = excluded.serial_number,
                location = excluded.location,
                role = excluded.role,
                last_seen = excluded.last_seen,
                last_collection_success = excluded.last_collection_success,
                last_collection_date = excluded.last_collection_date
        '''

        now = datetime.utcnow()
        params = (
            hostname, ip_address, platform, model,
            software_version, serial_number, location, role,
            now, collection_success, now
        )

        try:
            self.db.execute(query, params)
            logger.debug(f"Updated router inventory for {hostname}")
        except Exception as e:
            logger.error(f"Failed to update router inventory for {hostname}: {e}")
            raise

    def save_bgp_group(
        self,
        router_hostname: str,
        group_name: str,
        group_type: Optional[str] = None,
        import_policy: Optional[str] = None,
        export_policy: Optional[str] = None,
        peer_count: Optional[int] = None
    ) -> None:
        """Save or update BGP group information

        Args:
            router_hostname: Router hostname
            group_name: BGP group name
            group_type: Group type (e.g., 'external', 'internal')
            import_policy: Import policy name
            export_policy: Export policy name
            peer_count: Number of peers in group
        """
        query = '''
            INSERT INTO bgp_groups (
                router_hostname, group_name, group_type,
                import_policy, export_policy, peer_count
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(router_hostname, group_name) DO UPDATE SET
                group_type = excluded.group_type,
                import_policy = excluded.import_policy,
                export_policy = excluded.export_policy,
                peer_count = excluded.peer_count,
                discovered_date = CURRENT_TIMESTAMP
        '''

        params = (
            router_hostname, group_name, group_type,
            import_policy, export_policy, peer_count
        )

        try:
            self.db.execute(query, params)
            logger.debug(f"Saved BGP group {group_name} for {router_hostname}")
        except Exception as e:
            logger.error(f"Failed to save BGP group {group_name} for {router_hostname}: {e}")
            raise

    def update_router_as_mapping(
        self,
        router_hostname: str,
        as_number: int,
        bgp_group: str,
        peer_info: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update router-to-AS number mapping

        Args:
            router_hostname: Router hostname
            as_number: AS number
            bgp_group: BGP group containing this AS
            peer_info: Optional peer information dict with keys:
                - peer_address: Peer IP address
                - peer_description: Peer description
        """
        peer_info = peer_info or {}

        query = '''
            INSERT INTO router_as_mapping (
                router_hostname, as_number, bgp_group,
                peer_address, peer_description, last_confirmed, active
            ) VALUES (?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(router_hostname, as_number, bgp_group) DO UPDATE SET
                peer_address = excluded.peer_address,
                peer_description = excluded.peer_description,
                last_confirmed = excluded.last_confirmed,
                active = 1
        '''

        now = datetime.utcnow()
        params = (
            router_hostname, as_number, bgp_group,
            peer_info.get('peer_address'),
            peer_info.get('peer_description'),
            now
        )

        try:
            self.db.execute(query, params)
            logger.debug(f"Updated AS{as_number} mapping for {router_hostname} in {bgp_group}")
        except Exception as e:
            logger.error(f"Failed to update AS mapping for {router_hostname}: {e}")
            raise

    def get_router_inventory(self) -> List[Dict[str, Any]]:
        """Get all routers in inventory

        Returns:
            List of router inventory dictionaries
        """
        query = '''
            SELECT hostname, ip_address, platform, model,
                   software_version, serial_number, location, role,
                   first_seen, last_seen, last_collection_success,
                   last_collection_date, notes
            FROM router_inventory
            ORDER BY hostname
        '''

        try:
            rows = self.db.fetchall(query)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get router inventory: {e}")
            return []

    def get_as_for_router(self, router_hostname: str) -> List[int]:
        """Get all AS numbers for a specific router

        Args:
            router_hostname: Router hostname

        Returns:
            List of AS numbers
        """
        query = '''
            SELECT DISTINCT as_number
            FROM router_as_mapping
            WHERE router_hostname = ? AND active = 1
            ORDER BY as_number
        '''

        try:
            rows = self.db.fetchall(query, (router_hostname,))
            return [row['as_number'] for row in rows]
        except Exception as e:
            logger.error(f"Failed to get AS numbers for {router_hostname}: {e}")
            return []

    def get_routers_for_as(self, as_number: int) -> List[str]:
        """Get all routers that handle a specific AS number

        Args:
            as_number: AS number

        Returns:
            List of router hostnames
        """
        query = '''
            SELECT DISTINCT router_hostname
            FROM router_as_mapping
            WHERE as_number = ? AND active = 1
            ORDER BY router_hostname
        '''

        try:
            rows = self.db.fetchall(query, (as_number,))
            return [row['router_hostname'] for row in rows]
        except Exception as e:
            logger.error(f"Failed to get routers for AS{as_number}: {e}")
            return []

    def get_bgp_groups_for_router(self, hostname: str) -> Dict[str, List[int]]:
        """Get BGP groups and their AS numbers for a router

        Args:
            hostname: Router hostname

        Returns:
            Dict mapping group_name -> list of AS numbers
        """
        query = '''
            SELECT bg.group_name,
                   GROUP_CONCAT(ram.as_number) as as_numbers
            FROM bgp_groups bg
            LEFT JOIN router_as_mapping ram
                ON bg.router_hostname = ram.router_hostname
                AND bg.group_name = ram.bgp_group
            WHERE bg.router_hostname = ?
            GROUP BY bg.group_name
        '''

        try:
            groups = {}
            for row in self.db.fetchall(query, (hostname,)):
                as_list = []
                if row['as_numbers']:
                    as_list = [int(x) for x in row['as_numbers'].split(',')]
                groups[row['group_name']] = as_list
            return groups
        except Exception as e:
            logger.error(f"Failed to get BGP groups for {hostname}: {e}")
            return {}

    def get_bgp_groups_for_as(self, as_number: int) -> List[str]:
        """Get all BGP groups containing an AS number

        Args:
            as_number: AS number

        Returns:
            List of BGP group names
        """
        query = '''
            SELECT DISTINCT bgp_group
            FROM router_as_mapping
            WHERE as_number = ? AND active = 1
        '''

        try:
            rows = self.db.fetchall(query, (as_number,))
            return [row['bgp_group'] for row in rows if row['bgp_group']]
        except Exception as e:
            logger.error(f"Failed to get BGP groups for AS{as_number}: {e}")
            return []

    def get_all_bgp_groups(self) -> List[Dict[str, Any]]:
        """Get all BGP groups with their routers and AS numbers

        Returns:
            List of dicts with 'name', 'routers', and 'as_numbers' keys
        """
        query = '''
            SELECT
                bg.group_name,
                GROUP_CONCAT(DISTINCT bg.router_hostname) as routers,
                GROUP_CONCAT(DISTINCT ram.as_number) as as_numbers
            FROM bgp_groups bg
            LEFT JOIN router_as_mapping ram
                ON bg.router_hostname = ram.router_hostname
                AND bg.group_name = ram.bgp_group
            WHERE ram.active = 1 OR ram.active IS NULL
            GROUP BY bg.group_name
        '''

        try:
            groups = []
            for row in self.db.fetchall(query):
                router_list = row['routers'].split(',') if row['routers'] else []
                as_list = []
                if row['as_numbers']:
                    as_list = [int(x) for x in row['as_numbers'].split(',')]

                groups.append({
                    'name': row['group_name'],
                    'routers': router_list,
                    'as_numbers': as_list
                })
            return groups
        except Exception as e:
            logger.error(f"Failed to get all BGP groups: {e}")
            return []
