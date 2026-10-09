"""
Authoritative single source of truth for Traffic Classes, DSCP mappings,
and Linux CAKE diffserv tin steering.
"""
from typing import Dict, Any, Optional

CANONICAL_CLASSES = {
    "video_conference",
    "gaming",
    "bulk_download",
    "unclassified",
    "default"
}

CLASS_ALIASES = {
    "video": "video_conference",
    "meeting": "video_conference",
    "zoom": "video_conference",
    "teams": "video_conference",
    "game": "gaming",
    "voice": "gaming",  # EF Tin 3
    "interactive": "gaming",
    "bulk": "bulk_download",
    "download": "bulk_download",
    "backup": "bulk_download",
    "torrent": "bulk_download",
    "best_effort": "default",
    "normal": "default",
    "other": "default"
}

# DiffServ mappings aligned with Linux CAKE diffserv4 tin steering:
# Tin 0 (bulk):       CS1 (0x08)
# Tin 1 (besteffort): CS0 (0x00)
# Tin 2 (video):      AF41 (0x22), AF42, AF43, CS4, CS5
# Tin 3 (voice/inter):EF (0x2E), CS6, CS7
CLASS_SPECS: Dict[str, Dict[str, Any]] = {
    "gaming": {
        "canonical_name": "gaming",
        "dscp_name": "EF",
        "dscp_hex": "0x2e",
        "dscp_dec": 46,
        "cake_tin": "voice",
        "cake_tin_index": 3,
        "priority_level": 1,  # Lowest queuing delay
        "description": "Interactive low-latency gaming & voice traffic"
    },
    "video_conference": {
        "canonical_name": "video_conference",
        "dscp_name": "AF41",
        "dscp_hex": "0x22",
        "dscp_dec": 34,
        "cake_tin": "video",
        "cake_tin_index": 2,
        "priority_level": 2,  # Protected bandwidth & jitter
        "description": "Two-way interactive video and conferencing streams"
    },
    "bulk_download": {
        "canonical_name": "bulk_download",
        "dscp_name": "CS1",
        "dscp_hex": "0x08",
        "dscp_dec": 8,
        "cake_tin": "bulk",
        "cake_tin_index": 0,
        "priority_level": 4,  # Background scavenger tin
        "description": "Throughput-oriented bulk transfers, downloads and backups"
    },
    "default": {
        "canonical_name": "default",
        "dscp_name": "CS0",
        "dscp_hex": "0x00",
        "dscp_dec": 0,
        "cake_tin": "besteffort",
        "cake_tin_index": 1,
        "priority_level": 3,  # Standard Best Effort
        "description": "Standard unclassified web and generic application traffic"
    },
    "unclassified": {
        "canonical_name": "unclassified",
        "dscp_name": "CS0",
        "dscp_hex": "0x00",
        "dscp_dec": 0,
        "cake_tin": "besteffort",
        "cake_tin_index": 1,
        "priority_level": 3,
        "description": "Newly observed flows pending feature aggregation"
    }
}


def normalize_class_name(name: Optional[str]) -> str:
    """Normalize user or parser input to canonical class name."""
    if not name:
        return "default"
    cleaned = str(name).strip().lower()
    if cleaned in CANONICAL_CLASSES:
        return cleaned
    if cleaned in CLASS_ALIASES:
        return CLASS_ALIASES[cleaned]
    raise ValueError(f"Unsupported traffic class '{name}'. Supported: {sorted(list(CANONICAL_CLASSES))}")


def get_class_spec(name: Optional[str]) -> Dict[str, Any]:
    """Retrieve full QoS specification for a class."""
    canonical = normalize_class_name(name)
    return CLASS_SPECS.get(canonical, CLASS_SPECS["default"])


def get_dscp_for_class(name: Optional[str]) -> Dict[str, str]:
    """Return {'name': DSCP_NAME, 'val': DSCP_HEX}."""
    spec = get_class_spec(name)
    return {"name": spec["dscp_name"], "val": spec["dscp_hex"]}


def get_expected_cake_tin(name: Optional[str], diffserv_mode: str = "diffserv4") -> str:
    """Return expected CAKE tin for this class."""
    spec = get_class_spec(name)
    return spec["cake_tin"]


def validate_intent_class(name: Optional[str]) -> str:
    """Strict validation for operator intent classes."""
    if not name:
        raise ValueError("Intent must specify a valid traffic class")
    return normalize_class_name(name)
