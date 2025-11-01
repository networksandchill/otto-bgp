import logging
from datetime import datetime
from typing import Dict

from fastapi import APIRouter, Depends

from webui.core.audit import audit_log
from webui.core.security import require_role

router = APIRouter()
logger = logging.getLogger('otto_bgp.webui.reports')


def _calculate_matrix_statistics(matrix: Dict) -> Dict:
    """Calculate statistics from matrix data"""
    routers = matrix.get('routers', {})
    as_counts = [len(r['as_numbers']) for r in routers.values()]

    # Find shared AS numbers
    shared_as = []
    for as_num, data in matrix.get('as_numbers', {}).items():
        if len(data['routers']) > 1:
            shared_as.append({
                'as_number': as_num,
                'routers': data['routers']
            })

    # Find most common AS numbers
    as_counter = {}
    for router_data in routers.values():
        for as_num in router_data['as_numbers']:
            as_counter[as_num] = as_counter.get(as_num, 0) + 1

    most_common = sorted(as_counter.items(), key=lambda x: x[1], reverse=True)[:10]
    most_common_list = [{'as_number': asn, 'count': cnt} for asn, cnt in most_common]

    stats = {
        'total_routers': len(routers),
        'total_as_numbers': len(matrix.get('as_numbers', {})),
        'total_bgp_groups': len(matrix.get('bgp_groups', {})),
        'total_policies': sum(as_counts),
        'average_as_per_router': round(sum(as_counts) / len(as_counts), 2) if as_counts else 0,
        'max_as_per_router': max(as_counts) if as_counts else 0,
        'min_as_per_router': min(as_counts) if as_counts else 0,
        'routers_with_no_as': [h for h, r in routers.items() if not r['as_numbers']],
        'most_common_as': most_common_list,
        'shared_as_numbers': shared_as
    }

    return stats


@router.get("/matrix")
async def get_deployment_matrix(user: dict = Depends(require_role("read_only"))):
    from otto_bgp.database.router_mapping import RouterMappingManager

    try:
        mapper = RouterMappingManager()

        # Build matrix from database
        matrix = {
            "_metadata": {
                "generated": datetime.utcnow().isoformat(),
                "version": "0.3.2"
            },
            "routers": {},
            "as_numbers": {},
            "bgp_groups": {},
            "relationships": [],
            "statistics": {}
        }

        # Get all routers
        routers = mapper.get_router_inventory()

        if not routers:
            # Return empty structure consistent with current behavior
            return {
                "routers": {}, "as_distribution": {}, "bgp_groups": {},
                "statistics": {}, "generated_at": datetime.utcnow().isoformat()
            }

        # Build router entries
        for router in routers:
            hostname = router['hostname']

            # Get AS numbers for this router
            as_numbers = mapper.get_as_for_router(hostname)

            # Get BGP groups for this router
            bgp_groups = mapper.get_bgp_groups_for_router(hostname)

            matrix['routers'][hostname] = {
                'ip_address': router.get('ip_address', ''),
                'site': router.get('location', ''),
                'role': router.get('role', ''),
                'as_numbers': as_numbers,
                'as_count': len(as_numbers),
                'bgp_groups': bgp_groups,
                'metadata': {}
            }

        # Build AS number index (reverse mapping)
        all_as_numbers = set()
        for router_data in matrix['routers'].values():
            all_as_numbers.update(router_data['as_numbers'])

        for as_number in all_as_numbers:
            routers_for_as = mapper.get_routers_for_as(as_number)
            bgp_groups_for_as = mapper.get_bgp_groups_for_as(as_number)

            matrix['as_numbers'][as_number] = {
                'routers': routers_for_as,
                'bgp_groups': bgp_groups_for_as
            }

        # Build BGP groups index
        all_bgp_groups = mapper.get_all_bgp_groups()
        for group in all_bgp_groups:
            matrix['bgp_groups'][group['name']] = {
                'routers': group['routers'],
                'as_numbers': group['as_numbers']
            }

        # Calculate statistics
        matrix['_metadata']['total_routers'] = len(matrix['routers'])
        matrix['statistics'] = _calculate_matrix_statistics(matrix)

        audit_log("matrix_viewed", user=user.get('sub'))
        return matrix

    except Exception as e:
        logger.error(f"Failed to generate matrix from DB: {e}")
        return {"error": "Failed to generate matrix from database"}


@router.get("/discovery")
async def get_discovery_mappings(user: dict = Depends(require_role("read_only"))):
    # Call the same matrix generation logic
    return await get_deployment_matrix(user)
