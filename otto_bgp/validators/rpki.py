#!/usr/bin/env python3
"""
RPKI/ROA Validation System for Otto BGP

Implements comprehensive RPKI validation with:
- Tri-state validation logic (VALID/INVALID/NOTFOUND)
- VRP JSON processing for rpki-client and routinator formats
- Allowlist exception handling for NOTFOUND prefixes
- Offline validation using cached VRP data
- Fail-closed design for stale VRP data
- Integration with unified safety manager as guardrail 1.5

Security Design:
- All inputs are strictly validated and sanitized
- AS numbers follow RFC validation patterns from processors module
- Fail-closed behavior when VRP data is stale or unavailable
- Comprehensive error handling with structured logging
- Integration with Otto BGP's guardrail architecture
"""

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union, Any
from ipaddress import ip_network, ip_address, AddressValueError, NetmaskValueError

# Otto BGP imports for integration
from ..appliers.guardrails import GuardrailComponent, GuardrailResult, GuardrailConfig


class RPKIState(Enum):
    """RPKI validation states following RFC 6811"""
    VALID = "valid"
    INVALID = "invalid"
    NOTFOUND = "notfound"
    ERROR = "error"  # For validation system errors


@dataclass
class VRPEntry:
    """Validated ROA Payload entry"""
    asn: int
    prefix: str
    max_length: int
    ta: str  # Trust Anchor
    expires: Optional[datetime] = None
    
    def __post_init__(self):
        """Validate VRP entry on creation"""
        if not self._validate_asn(self.asn):
            raise ValueError(f"Invalid AS number: {self.asn}")
        
        if not self._validate_prefix(self.prefix):
            raise ValueError(f"Invalid prefix: {self.prefix}")
            
        prefix_length = int(self.prefix.split('/')[1])
        if not prefix_length <= self.max_length <= 32:
            raise ValueError(f"Invalid max_length {self.max_length} for prefix {self.prefix}")
    
    def _validate_asn(self, asn: int) -> bool:
        """Validate AS number using Otto BGP patterns"""
        return isinstance(asn, int) and 0 <= asn <= 4294967295
    
    def _validate_prefix(self, prefix: str) -> bool:
        """Validate IP prefix format"""
        try:
            ip_network(prefix, strict=True)
            return True
        except (AddressValueError, NetmaskValueError):
            return False


@dataclass
class RPKIValidationResult:
    """Result of RPKI validation for a prefix-AS pair"""
    prefix: str
    asn: int
    state: RPKIState
    reason: str
    covering_vrp: Optional[VRPEntry] = None
    allowlisted: bool = False
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class VRPDataset:
    """Complete VRP dataset with metadata"""
    vrp_entries: List[VRPEntry]
    metadata: Dict[str, Any]
    generated_time: datetime
    expires_time: Optional[datetime] = None
    source_format: str = "unknown"  # rpki-client, routinator, etc.
    
    def is_stale(self, max_age_hours: int = 24) -> bool:
        """Check if VRP data is stale"""
        if self.expires_time:
            return datetime.now() > self.expires_time
        
        age = datetime.now() - self.generated_time
        return age > timedelta(hours=max_age_hours)


class RPKIValidator:
    """
    Comprehensive RPKI/ROA validator with tri-state logic
    
    Implements RFC 6811 origin validation with enhancements:
    - Support for multiple VRP data sources
    - Allowlist for NOTFOUND exceptions
    - Fail-closed behavior for stale data
    - AS number validation following Otto BGP patterns
    """
    
    def __init__(self, 
                 vrp_cache_path: Optional[Path] = None,
                 allowlist_path: Optional[Path] = None,
                 fail_closed: bool = True,
                 max_vrp_age_hours: int = 24,
                 logger: Optional[logging.Logger] = None):
        """
        Initialize RPKI validator
        
        Args:
            vrp_cache_path: Path to cached VRP data file
            allowlist_path: Path to NOTFOUND allowlist file
            fail_closed: Fail closed when VRP data is stale (default True)
            max_vrp_age_hours: Maximum age for VRP data before considered stale
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.vrp_cache_path = vrp_cache_path or Path("/var/lib/otto-bgp/rpki/vrp_cache.json")
        self.allowlist_path = allowlist_path or Path("/var/lib/otto-bgp/rpki/allowlist.json")
        self.fail_closed = fail_closed
        self.max_vrp_age_hours = max_vrp_age_hours
        
        # VRP data and allowlist
        self._vrp_dataset: Optional[VRPDataset] = None
        self._allowlist: Set[Tuple[str, int]] = set()  # (prefix, asn) tuples
        
        # Performance optimization: prefix tree lookup
        self._vrp_index: Dict[str, List[VRPEntry]] = {}
        
        # Load initial data
        self._load_vrp_data()
        self._load_allowlist()
        
        self.logger.info(f"RPKI validator initialized - VRP entries: {len(self._vrp_dataset.vrp_entries) if self._vrp_dataset else 0}, "
                        f"Allowlist entries: {len(self._allowlist)}, Fail-closed: {fail_closed}")
    
    def validate_prefix_origin(self, prefix: str, asn: int) -> RPKIValidationResult:
        """
        Validate a prefix-origin pair using RPKI/ROA data
        
        Args:
            prefix: IP prefix in CIDR notation (e.g., "192.0.2.0/24")
            asn: AS number as integer
            
        Returns:
            RPKIValidationResult with validation outcome
        """
        try:
            # Input validation and sanitization
            sanitized_prefix = self._sanitize_prefix(prefix)
            sanitized_asn = self._sanitize_asn(asn)
            
            # Check if VRP data is available and fresh
            if not self._vrp_dataset:
                if self.fail_closed:
                    return RPKIValidationResult(
                        prefix=sanitized_prefix,
                        asn=sanitized_asn,
                        state=RPKIState.ERROR,
                        reason="No VRP data available - failing closed for security"
                    )
                else:
                    return RPKIValidationResult(
                        prefix=sanitized_prefix,
                        asn=sanitized_asn,
                        state=RPKIState.NOTFOUND,
                        reason="No VRP data available - proceeding with warning"
                    )
            
            # Check for stale VRP data
            if self._vrp_dataset.is_stale(self.max_vrp_age_hours):
                if self.fail_closed:
                    return RPKIValidationResult(
                        prefix=sanitized_prefix,
                        asn=sanitized_asn,
                        state=RPKIState.ERROR,
                        reason=f"VRP data is stale (age: {datetime.now() - self._vrp_dataset.generated_time}) - failing closed"
                    )
                else:
                    self.logger.warning("VRP data is stale but proceeding due to fail-open configuration")
            
            # Perform RPKI validation
            validation_result = self._perform_rpki_validation(sanitized_prefix, sanitized_asn)
            
            # Check allowlist for NOTFOUND results
            if validation_result.state == RPKIState.NOTFOUND:
                if (sanitized_prefix, sanitized_asn) in self._allowlist:
                    validation_result.allowlisted = True
                    validation_result.reason += " - allowlisted exception"
            
            self.logger.debug(f"RPKI validation: {sanitized_prefix} AS{sanitized_asn} -> {validation_result.state.value} ({validation_result.reason})")
            return validation_result
            
        except Exception as e:
            self.logger.error(f"RPKI validation error for {prefix} AS{asn}: {e}")
            return RPKIValidationResult(
                prefix=prefix,
                asn=asn,
                state=RPKIState.ERROR,
                reason=f"Validation system error: {str(e)}"
            )
    
    def validate_policy_prefixes(self, policy: Dict[str, Any]) -> List[RPKIValidationResult]:
        """
        Validate all prefixes in a BGP policy
        
        Args:
            policy: Policy dictionary with 'content' and 'as_number' keys
            
        Returns:
            List of RPKIValidationResult for each prefix found
        """
        results = []
        
        try:
            as_number = policy.get('as_number')
            content = policy.get('content', '')
            
            if not as_number:
                self.logger.warning("Policy missing AS number - skipping RPKI validation")
                return results
            
            # Extract all prefixes from policy content
            prefixes = self._extract_prefixes_from_policy(content)
            
            # Validate each prefix
            for prefix in prefixes:
                result = self.validate_prefix_origin(prefix, as_number)
                results.append(result)
                
        except Exception as e:
            self.logger.error(f"Error validating policy prefixes: {e}")
            # Return error result for the AS
            results.append(RPKIValidationResult(
                prefix="0.0.0.0/0",
                asn=policy.get('as_number', 0),
                state=RPKIState.ERROR,
                reason=f"Policy validation error: {str(e)}"
            ))
        
        return results
    
    def load_vrp_data(self, vrp_file_path: Path, source_format: str = "auto") -> bool:
        """
        Load VRP data from file
        
        Args:
            vrp_file_path: Path to VRP data file
            source_format: Format hint ("rpki-client", "routinator", "auto")
            
        Returns:
            True if loaded successfully
        """
        try:
            if not vrp_file_path.exists():
                self.logger.error(f"VRP file not found: {vrp_file_path}")
                return False
            
            with open(vrp_file_path, 'r') as f:
                vrp_data = json.load(f)
            
            # Auto-detect format if needed
            if source_format == "auto":
                source_format = self._detect_vrp_format(vrp_data)
            
            # Parse VRP data based on format
            if source_format == "rpki-client":
                dataset = self._parse_rpki_client_format(vrp_data)
            elif source_format == "routinator":
                dataset = self._parse_routinator_format(vrp_data)
            else:
                self.logger.error(f"Unsupported VRP format: {source_format}")
                return False
            
            # Update dataset and rebuild index
            self._vrp_dataset = dataset
            self._build_vrp_index()
            
            # Cache the data
            self._cache_vrp_data()
            
            self.logger.info(f"Loaded {len(dataset.vrp_entries)} VRP entries from {source_format} format")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load VRP data from {vrp_file_path}: {e}")
            return False
    
    def update_allowlist(self, prefix: str, asn: int, add: bool = True) -> bool:
        """
        Update allowlist for NOTFOUND exceptions
        
        Args:
            prefix: IP prefix in CIDR notation
            asn: AS number
            add: True to add, False to remove
            
        Returns:
            True if updated successfully
        """
        try:
            sanitized_prefix = self._sanitize_prefix(prefix)
            sanitized_asn = self._sanitize_asn(asn)
            
            entry = (sanitized_prefix, sanitized_asn)
            
            if add:
                self._allowlist.add(entry)
                action = "added"
            else:
                self._allowlist.discard(entry)
                action = "removed"
            
            # Save updated allowlist
            self._save_allowlist()
            
            self.logger.info(f"Allowlist {action}: {sanitized_prefix} AS{sanitized_asn}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update allowlist: {e}")
            return False
    
    def get_validation_stats(self) -> Dict[str, Any]:
        """Get validation statistics"""
        stats = {
            'vrp_entries': len(self._vrp_dataset.vrp_entries) if self._vrp_dataset else 0,
            'allowlist_entries': len(self._allowlist),
            'vrp_data_age': None,
            'vrp_data_stale': None
        }
        
        if self._vrp_dataset:
            age = datetime.now() - self._vrp_dataset.generated_time
            stats['vrp_data_age'] = str(age)
            stats['vrp_data_stale'] = self._vrp_dataset.is_stale(self.max_vrp_age_hours)
        
        return stats
    
    def _sanitize_prefix(self, prefix: str) -> str:
        """Sanitize and validate IP prefix"""
        if not isinstance(prefix, str):
            raise ValueError(f"Prefix must be string, got {type(prefix).__name__}")
        
        # Remove whitespace and validate format
        prefix = prefix.strip()
        
        try:
            # Validate using ipaddress module
            network = ip_network(prefix, strict=True)
            return str(network)
        except (AddressValueError, NetmaskValueError) as e:
            raise ValueError(f"Invalid prefix format '{prefix}': {e}")
    
    def _sanitize_asn(self, asn: Union[int, str]) -> int:
        """Sanitize and validate AS number following Otto BGP patterns"""
        if isinstance(asn, str):
            # Handle AS prefix format
            asn = asn.strip()
            if asn.upper().startswith('AS'):
                asn = asn[2:]
            
            try:
                asn = int(asn)
            except ValueError:
                raise ValueError(f"Invalid AS number format: {asn}")
        
        if not isinstance(asn, int):
            raise ValueError(f"AS number must be integer, got {type(asn).__name__}")
        
        # RFC-compliant AS number validation (from processors module)
        if not 0 <= asn <= 4294967295:
            raise ValueError(f"AS number out of valid range (0-4294967295): {asn}")
        
        return asn
    
    def _extract_prefixes_from_policy(self, content: str) -> Set[str]:
        """Extract IP prefixes from policy content"""
        prefixes = set()
        
        # IPv4 prefix pattern
        ipv4_pattern = r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)/(?:[0-9]|[1-2][0-9]|3[0-2])\b'
        
        for match in re.finditer(ipv4_pattern, content):
            prefix = match.group(0)
            try:
                # Validate prefix
                validated_prefix = self._sanitize_prefix(prefix)
                prefixes.add(validated_prefix)
            except ValueError:
                self.logger.debug(f"Skipping invalid prefix: {prefix}")
        
        return prefixes
    
    def _perform_rpki_validation(self, prefix: str, asn: int) -> RPKIValidationResult:
        """Perform core RPKI validation logic"""
        try:
            target_network = ip_network(prefix)
        except (AddressValueError, NetmaskValueError):
            return RPKIValidationResult(
                prefix=prefix,
                asn=asn,
                state=RPKIState.ERROR,
                reason="Invalid prefix format"
            )
        
        # Find all VRPs that have a topological relationship with the target prefix
        matching_vrps = []
        invalid_length_vrps = []
        
        for vrp in self._vrp_dataset.vrp_entries:
            try:
                vrp_network = ip_network(vrp.prefix)
                
                # Check if VRP prefix covers the target prefix (target is subnet of VRP or equal)
                if (target_network.subnet_of(vrp_network) or target_network == vrp_network):
                    # Check max_length constraint
                    if target_network.prefixlen <= vrp.max_length:
                        # VRP covers and length is valid
                        matching_vrps.append(vrp)
                    else:
                        # VRP covers but length exceeds max_length - this is INVALID
                        invalid_length_vrps.append(vrp)
            except Exception:
                continue
        
        # RFC 6811 validation logic:
        # 1. If prefix exceeds max-length of any covering VRP, it's INVALID
        if invalid_length_vrps:
            return RPKIValidationResult(
                prefix=prefix,
                asn=asn,
                state=RPKIState.INVALID,
                reason=f"Invalid: prefix length {target_network.prefixlen} exceeds max-length {invalid_length_vrps[0].max_length} of covering VRP {invalid_length_vrps[0].prefix}",
                covering_vrp=invalid_length_vrps[0]
            )
        
        # 2. If no covering VRPs at all, it's NOTFOUND
        if not matching_vrps:
            return RPKIValidationResult(
                prefix=prefix,
                asn=asn,
                state=RPKIState.NOTFOUND,
                reason="No covering VRP found"
            )
        
        # 3. Check if any matching VRP has the same origin AS
        for vrp in matching_vrps:
            if vrp.asn == asn:
                return RPKIValidationResult(
                    prefix=prefix,
                    asn=asn,
                    state=RPKIState.VALID,
                    reason=f"Valid ROA found: {vrp.prefix} max-length {vrp.max_length}",
                    covering_vrp=vrp
                )
        
        # 4. Covering VRPs exist with valid length but none match the origin AS - INVALID
        return RPKIValidationResult(
            prefix=prefix,
            asn=asn,
            state=RPKIState.INVALID,
            reason=f"Invalid: covered by VRP(s) for different AS(s): {', '.join(f'AS{vrp.asn}' for vrp in matching_vrps)}",
            covering_vrp=matching_vrps[0]  # Include first covering VRP for reference
        )
    
    def _load_vrp_data(self):
        """Load VRP data from cache"""
        try:
            if not self.vrp_cache_path.exists():
                self.logger.warning(f"VRP cache file not found: {self.vrp_cache_path}")
                return
            
            with open(self.vrp_cache_path, 'r') as f:
                cache_data = json.load(f)
            
            # Parse cached VRP data
            vrp_entries = []
            for entry_data in cache_data.get('vrp_entries', []):
                try:
                    vrp_entry = VRPEntry(
                        asn=entry_data['asn'],
                        prefix=entry_data['prefix'],
                        max_length=entry_data['max_length'],
                        ta=entry_data.get('ta', 'unknown')
                    )
                    vrp_entries.append(vrp_entry)
                except Exception as e:
                    self.logger.debug(f"Skipping invalid VRP entry: {e}")
            
            # Create dataset
            metadata = cache_data.get('metadata', {})
            generated_time = datetime.fromisoformat(cache_data.get('generated_time', datetime.now().isoformat()))
            
            self._vrp_dataset = VRPDataset(
                vrp_entries=vrp_entries,
                metadata=metadata,
                generated_time=generated_time,
                source_format=cache_data.get('source_format', 'cached')
            )
            
            # Build lookup index
            self._build_vrp_index()
            
            self.logger.info(f"Loaded {len(vrp_entries)} VRP entries from cache")
            
        except Exception as e:
            self.logger.error(f"Failed to load VRP cache: {e}")
    
    def _load_allowlist(self):
        """Load allowlist from file"""
        try:
            if not self.allowlist_path.exists():
                self.logger.info("No allowlist file found - starting with empty allowlist")
                return
            
            with open(self.allowlist_path, 'r') as f:
                allowlist_data = json.load(f)
            
            for entry in allowlist_data.get('entries', []):
                try:
                    prefix = self._sanitize_prefix(entry['prefix'])
                    asn = self._sanitize_asn(entry['asn'])
                    self._allowlist.add((prefix, asn))
                except Exception as e:
                    self.logger.warning(f"Skipping invalid allowlist entry: {e}")
            
            self.logger.info(f"Loaded {len(self._allowlist)} allowlist entries")
            
        except Exception as e:
            self.logger.error(f"Failed to load allowlist: {e}")
    
    def _save_allowlist(self):
        """Save allowlist to file"""
        try:
            # Create directory if needed
            self.allowlist_path.parent.mkdir(parents=True, exist_ok=True)
            
            allowlist_data = {
                'entries': [
                    {'prefix': prefix, 'asn': asn}
                    for prefix, asn in self._allowlist
                ],
                'generated_time': datetime.now().isoformat()
            }
            
            with open(self.allowlist_path, 'w') as f:
                json.dump(allowlist_data, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Failed to save allowlist: {e}")
    
    def _cache_vrp_data(self):
        """Cache VRP data to file"""
        try:
            if not self._vrp_dataset:
                return
            
            # Create directory if needed
            self.vrp_cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            cache_data = {
                'vrp_entries': [
                    {
                        'asn': vrp.asn,
                        'prefix': vrp.prefix,
                        'max_length': vrp.max_length,
                        'ta': vrp.ta
                    }
                    for vrp in self._vrp_dataset.vrp_entries
                ],
                'metadata': self._vrp_dataset.metadata,
                'generated_time': self._vrp_dataset.generated_time.isoformat(),
                'source_format': self._vrp_dataset.source_format
            }
            
            with open(self.vrp_cache_path, 'w') as f:
                json.dump(cache_data, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Failed to cache VRP data: {e}")
    
    def _build_vrp_index(self):
        """Build index for fast VRP lookups"""
        self._vrp_index = {}
        
        if not self._vrp_dataset:
            return
        
        for vrp in self._vrp_dataset.vrp_entries:
            # Index by network address for faster lookups
            try:
                network = ip_network(vrp.prefix)
                network_addr = str(network.network_address)
                
                if network_addr not in self._vrp_index:
                    self._vrp_index[network_addr] = []
                self._vrp_index[network_addr].append(vrp)
                
            except Exception:
                continue
    
    def _detect_vrp_format(self, vrp_data: Dict[str, Any]) -> str:
        """Auto-detect VRP data format"""
        if 'roas' in vrp_data:
            return "rpki-client"
        elif 'roa-count' in vrp_data or 'version' in vrp_data:
            return "routinator"
        else:
            return "generic"
    
    def _parse_rpki_client_format(self, vrp_data: Dict[str, Any]) -> VRPDataset:
        """Parse rpki-client VRP format"""
        vrp_entries = []
        
        for roa in vrp_data.get('roas', []):
            try:
                vrp_entry = VRPEntry(
                    asn=roa['asn'],
                    prefix=roa['prefix'],
                    max_length=roa.get('maxLength', int(roa['prefix'].split('/')[1])),
                    ta=roa.get('ta', 'unknown')
                )
                vrp_entries.append(vrp_entry)
            except Exception as e:
                self.logger.debug(f"Skipping invalid ROA entry: {e}")
        
        return VRPDataset(
            vrp_entries=vrp_entries,
            metadata=vrp_data.get('metadata', {}),
            generated_time=datetime.now(),  # rpki-client doesn't provide timestamp
            source_format="rpki-client"
        )
    
    def _parse_routinator_format(self, vrp_data: Dict[str, Any]) -> VRPDataset:
        """Parse routinator VRP format"""
        vrp_entries = []
        
        for vrp in vrp_data.get('validated-roa-payloads', []):
            try:
                vrp_entry = VRPEntry(
                    asn=vrp['asn'],
                    prefix=vrp['prefix'],
                    max_length=vrp.get('max-length', int(vrp['prefix'].split('/')[1])),
                    ta=vrp.get('ta', 'unknown')
                )
                vrp_entries.append(vrp_entry)
            except Exception as e:
                self.logger.debug(f"Skipping invalid VRP entry: {e}")
        
        return VRPDataset(
            vrp_entries=vrp_entries,
            metadata=vrp_data.get('metadata', {}),
            generated_time=datetime.now(),  # Parse from metadata if available
            source_format="routinator"
        )


class RPKIGuardrail(GuardrailComponent):
    """
    RPKI validation guardrail component for integration with unified safety manager
    
    Provides RPKI validation as guardrail 1.5 in Otto BGP's safety architecture.
    Validates all BGP prefixes against RPKI/ROA data before policy application.
    """
    
    def __init__(self, 
                 rpki_validator: Optional[RPKIValidator] = None,
                 config: Optional[GuardrailConfig] = None,
                 logger: Optional[logging.Logger] = None):
        """
        Initialize RPKI guardrail
        
        Args:
            rpki_validator: RPKI validator instance
            config: Guardrail configuration
            logger: Logger instance
        """
        super().__init__("rpki_validation", config, logger)
        
        # Initialize RPKI validator
        if rpki_validator:
            self.rpki_validator = rpki_validator
        else:
            self.rpki_validator = RPKIValidator(logger=self.logger)
        
        # RPKI-specific thresholds
        self.default_thresholds = {
            'max_invalid_percent': 0.0,  # No invalid prefixes allowed by default
            'max_notfound_percent': 25.0,  # Allow 25% NOTFOUND (conservative)
            'require_vrp_data': True,  # Require fresh VRP data
            'allow_allowlisted_notfound': True  # Allow allowlisted NOTFOUND prefixes
        }
    
    def check(self, context: Dict[str, Any]) -> GuardrailResult:
        """
        Perform RPKI validation check on policies
        
        Args:
            context: Must contain 'policies' key with policy list
            
        Returns:
            GuardrailResult with RPKI validation results
        """
        self._check_count += 1
        self._last_check_time = datetime.now()
        
        policies = context.get('policies', [])
        if not policies:
            return GuardrailResult(
                passed=True,
                guardrail_name=self.name,
                risk_level="low",
                message="No policies to validate",
                details={},
                recommended_action="Safe to proceed - no RPKI validation needed",
                timestamp=self._last_check_time
            )
        
        # Get thresholds
        thresholds = dict(self.default_thresholds)
        if self.config.custom_thresholds:
            thresholds.update(self.config.custom_thresholds)
        
        # Validate all policies
        all_results = []
        policy_summaries = []
        
        for policy in policies:
            validation_results = self.rpki_validator.validate_policy_prefixes(policy)
            all_results.extend(validation_results)
            
            # Summarize results per policy
            as_number = policy.get('as_number', '?')
            valid_count = sum(1 for r in validation_results if r.state == RPKIState.VALID)
            invalid_count = sum(1 for r in validation_results if r.state == RPKIState.INVALID)
            notfound_count = sum(1 for r in validation_results if r.state == RPKIState.NOTFOUND)
            error_count = sum(1 for r in validation_results if r.state == RPKIState.ERROR)
            allowlisted_count = sum(1 for r in validation_results if r.allowlisted)
            
            policy_summaries.append({
                'as_number': as_number,
                'total_prefixes': len(validation_results),
                'valid': valid_count,
                'invalid': invalid_count,
                'notfound': notfound_count,
                'error': error_count,
                'allowlisted': allowlisted_count
            })
        
        # Analyze results
        total_prefixes = len(all_results)
        if total_prefixes == 0:
            return GuardrailResult(
                passed=True,
                guardrail_name=self.name,
                risk_level="low",
                message="No prefixes found in policies",
                details={'policy_summaries': policy_summaries},
                recommended_action="Safe to proceed - no prefixes to validate",
                timestamp=self._last_check_time
            )
        
        # Count validation states
        valid_count = sum(1 for r in all_results if r.state == RPKIState.VALID)
        invalid_count = sum(1 for r in all_results if r.state == RPKIState.INVALID)
        notfound_count = sum(1 for r in all_results if r.state == RPKIState.NOTFOUND)
        error_count = sum(1 for r in all_results if r.state == RPKIState.ERROR)
        allowlisted_count = sum(1 for r in all_results if r.allowlisted)
        
        # Calculate percentages
        invalid_percent = (invalid_count / total_prefixes) * 100
        notfound_percent = (notfound_count / total_prefixes) * 100
        error_percent = (error_count / total_prefixes) * 100
        
        # Determine pass/fail and risk level
        issues = []
        risk_level = "low"
        
        # Check for validation errors
        if error_count > 0:
            issues.append(f"{error_count} validation errors ({error_percent:.1f}%)")
            risk_level = "high"
        
        # Check invalid threshold
        if invalid_percent > thresholds['max_invalid_percent']:
            issues.append(f"{invalid_count} invalid prefixes ({invalid_percent:.1f}% > {thresholds['max_invalid_percent']}%)")
            risk_level = "critical"
        
        # Check NOTFOUND threshold (excluding allowlisted)
        effective_notfound = notfound_count - allowlisted_count
        effective_notfound_percent = (effective_notfound / total_prefixes) * 100 if total_prefixes > 0 else 0
        
        if effective_notfound_percent > thresholds['max_notfound_percent']:
            issues.append(f"{effective_notfound} non-allowlisted NOTFOUND prefixes ({effective_notfound_percent:.1f}% > {thresholds['max_notfound_percent']}%)")
            if risk_level == "low":
                risk_level = "medium"
        
        # Check VRP data availability
        stats = self.rpki_validator.get_validation_stats()
        if thresholds['require_vrp_data'] and (stats['vrp_entries'] == 0 or stats.get('vrp_data_stale', True)):
            issues.append("VRP data unavailable or stale")
            risk_level = "high"
        
        # Determine overall result
        passed = len(issues) == 0 or (risk_level == "medium" and self.config.strictness_level == "low")
        
        if passed:
            message = f"RPKI validation passed: {valid_count} valid, {notfound_count} not found ({allowlisted_count} allowlisted)"
        else:
            message = f"RPKI validation issues: {'; '.join(issues)}"
        
        recommended_action = self._get_rpki_action(passed, risk_level, issues)
        
        return GuardrailResult(
            passed=passed,
            guardrail_name=self.name,
            risk_level=risk_level,
            message=message,
            details={
                'total_prefixes': total_prefixes,
                'valid_count': valid_count,
                'invalid_count': invalid_count,
                'notfound_count': notfound_count,
                'error_count': error_count,
                'allowlisted_count': allowlisted_count,
                'invalid_percent': invalid_percent,
                'notfound_percent': notfound_percent,
                'effective_notfound_percent': effective_notfound_percent,
                'policy_summaries': policy_summaries,
                'thresholds': thresholds,
                'vrp_stats': stats,
                'issues': issues
            },
            recommended_action=recommended_action,
            timestamp=self._last_check_time
        )
    
    def _get_rpki_action(self, passed: bool, risk_level: str, issues: List[str]) -> str:
        """Get recommended action for RPKI validation results"""
        if passed:
            return "Safe to proceed - RPKI validation passed"
        elif risk_level == "critical":
            return "DO NOT PROCEED - Invalid RPKI prefixes detected"
        elif risk_level == "high":
            return "Review RPKI issues carefully before proceeding"
        else:
            return "Monitor RPKI validation results during application"