"""Shared validation and helper functions."""

import re


# Valid tracking ID pattern: TGMA-WT-F-0037
TRACKING_ID_PATTERN = re.compile(r'^TGMA-(WT|ST|DL)-(M|F)-(\d{4})$')

# Sample ID suffixes
SAMPLE_SUFFIXES = {
    'stool': 'STL',
    'blood': 'BLD',
    'saliva_1': 'SLV1',
    'saliva_2': 'SLV2',
    'saliva_3': 'SLV3',
    'saliva_4': 'SLV4',
    'dna_extract': 'DNA',
    'serum': 'SRM',
}

DISTRICT_CODES = {'WT': 'West Tripura', 'ST': 'South Tripura', 'DL': 'Dhalai'}


def validate_tracking_id(tracking_id):
    """Validate a tracking ID format. Returns True if valid."""
    return bool(TRACKING_ID_PATTERN.match(tracking_id))


def generate_tracking_id(district, gender, sequence):
    """Generate a tracking ID from components."""
    return f"TGMA-{district}-{gender}-{sequence:04d}"


def generate_sample_id(tracking_id, sample_type):
    """Generate a sample ID from tracking ID and sample type."""
    suffix = SAMPLE_SUFFIXES.get(sample_type)
    if not suffix:
        raise ValueError(f"Unknown sample type: {sample_type}")
    return f"{tracking_id}-{suffix}"


def validate_gps(lat, lon):
    """Validate GPS coordinates are within Tripura bounds."""
    if lat is None or lon is None:
        return True  # nullable
    return (22.9 <= float(lat) <= 24.5) and (91.1 <= float(lon) <= 92.3)


def validate_age(age):
    """Validate age is within study range (12-18)."""
    if age is None:
        return True
    return 12 <= int(age) <= 18
