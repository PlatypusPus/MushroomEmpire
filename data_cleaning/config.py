"""
Cleaning Configuration
Customize PII detection and anonymization strategies
"""

# Anonymization Strategy Definitions
STRATEGIES = {
    'REMOVE': {
        'description': 'Delete entire column',
        'risk_level': 'HIGH',
        'reversible': False,
        'use_cases': ['Credit cards', 'SSN', 'Bank accounts']
    },
    'HASH': {
        'description': 'One-way SHA-256 hash',
        'risk_level': 'MEDIUM',
        'reversible': False,
        'use_cases': ['Emails', 'Phone numbers', 'Names']
    },
    'MASK': {
        'description': 'Replace with asterisks',
        'risk_level': 'LOW',
        'reversible': False,
        'use_cases': ['Partial identifiers', 'Locations']
    },
    'GENERALIZE': {
        'description': 'Reduce precision',
        'risk_level': 'LOW',
        'reversible': False,
        'use_cases': ['Dates', 'Ages', 'ZIP codes']
    },
    'KEEP': {
        'description': 'No changes',
        'risk_level': 'NONE',
        'reversible': True,
        'use_cases': ['Non-sensitive data']
    }
}

# Entity Type to Strategy Mapping
# Customize these based on your compliance requirements
ENTITY_STRATEGY_MAP = {
    # Financial Identifiers - HIGHEST RISK
    'CREDIT_CARD': 'REMOVE',
    'CRYPTO': 'REMOVE',
    'IBAN_CODE': 'REMOVE',
    'US_BANK_NUMBER': 'REMOVE',
    
    # Government IDs - HIGH RISK
    'US_SSN': 'REMOVE',
    'US_DRIVER_LICENSE': 'REMOVE',
    'US_PASSPORT': 'REMOVE',
    'US_ITIN': 'REMOVE',
    'UK_NHS': 'REMOVE',
    'SG_NRIC_FIN': 'REMOVE',
    'IN_PAN': 'REMOVE',
    
    # Nordic National IDs - HIGH RISK (CRITICAL)
    'FI_PERSONAL_ID': 'REMOVE',  # Finnish Henkilötunnus (HETU)
    'SE_PERSONAL_ID': 'REMOVE',  # Swedish Personnummer
    'NO_PERSONAL_ID': 'REMOVE',  # Norwegian Fødselsnummer
    'DK_PERSONAL_ID': 'REMOVE',  # Danish CPR-nummer
    'FI_KELA_ID': 'REMOVE',      # Finnish social security (Kela)
    
    # Health Information - HIGH RISK (GDPR Art. 9)
    'MEDICAL_LICENSE': 'REMOVE',
    
    # Contact Information - MEDIUM RISK
    'EMAIL_ADDRESS': 'HASH',
    'PHONE_NUMBER': 'HASH',
    'URL': 'HASH',
    
    # Personal Identifiers - MEDIUM RISK
    'PERSON': 'HASH',  # Names
    'IP_ADDRESS': 'HASH',
    
    # Nordic Business Identifiers - MEDIUM RISK
    'FI_BUSINESS_ID': 'HASH',  # Finnish Y-tunnus (less sensitive than personal IDs)
    
    # Geographic Information - LOW RISK
    'LOCATION': 'MASK',
    'US_ZIP_CODE': 'GENERALIZE',
    
    # Temporal Information - LOW RISK
    'DATE_TIME': 'GENERALIZE',
    
    # Special Categories - MEDIUM RISK (GDPR Art. 9)
    'NRP': 'HASH',  # Nationality, religious, political views
    
    # Business Identifiers - LOW RISK
    'AU_ABN': 'HASH',
    'AU_ACN': 'HASH',
    'AU_TFN': 'HASH',
}

# Confidence Score Thresholds
CONFIDENCE_THRESHOLDS = {
    'HIGH': 0.85,      # Auto-apply strategy
    'MEDIUM': 0.60,    # Prompt user in interactive mode
    'LOW': 0.40,       # Treat as potential false positive
}

# GDPR Article Mappings
GDPR_COMPLIANCE = {
    'CREDIT_CARD': 'Art. 4(1) - Personal data identifier',
    'US_SSN': 'Art. 4(1) - Personal data identifier',
    'US_BANK_NUMBER': 'Art. 4(1) - Personal data identifier',
    'EMAIL_ADDRESS': 'Art. 4(1) - Personal data identifier',
    'PHONE_NUMBER': 'Art. 4(1) - Personal data identifier',
    'PERSON': 'Art. 4(1) - Personal data (name)',
    'LOCATION': 'Art. 4(1) - Personal data (location)',
    'IP_ADDRESS': 'Art. 4(1) - Online identifier',
    'MEDICAL_LICENSE': 'Art. 9(1) - Special category data (health)',
    'NRP': 'Art. 9(1) - Special category data (political/religious views)',
    'DATE_TIME': 'Art. 4(1) - Personal data (temporal information)',
    
    # Nordic National IDs
    'FI_PERSONAL_ID': 'Art. 4(1) - Personal data identifier + Recital 26',
    'SE_PERSONAL_ID': 'Art. 4(1) - Personal data identifier + Recital 26',
    'NO_PERSONAL_ID': 'Art. 4(1) - Personal data identifier + Recital 26',
    'DK_PERSONAL_ID': 'Art. 4(1) - Personal data identifier + Recital 26',
    'FI_KELA_ID': 'Art. 9(1) - Special category (health/social security)',
    'FI_BUSINESS_ID': 'Art. 4(1) - Organizational identifier (lower risk)',
}

# Presidio Analyzer Settings
PRESIDIO_CONFIG = {
    'language': 'en',
    'score_threshold': 0.6,  # Minimum confidence to report (raised from 0.5 to reduce false positives)
    'entities': None,  # None = detect all, or specify list like ['EMAIL_ADDRESS', 'PHONE_NUMBER']
    'allow_list': ['l1', 'l2', 'L1', 'L2', 'NA', 'N/A', 'null', 'none'],  # Common non-PII values
}

# Column Context Filters - Ignore specific entity types based on column name patterns
# This prevents false positives when column names provide context
COLUMN_CONTEXT_FILTERS = {
    # Column name pattern (regex) -> List of entity types to IGNORE in that column
    r'.*credit.*': ['US_DRIVER_LICENSE', 'US_PASSPORT', 'PERSON'],
    r'.*rating.*': ['US_DRIVER_LICENSE', 'US_PASSPORT'],
    r'.*level.*': ['US_DRIVER_LICENSE', 'US_PASSPORT'],
    r'.*score.*': ['US_DRIVER_LICENSE', 'US_PASSPORT', 'PERSON'],
    r'.*category.*': ['US_DRIVER_LICENSE', 'PERSON'],
    r'.*status.*': ['US_DRIVER_LICENSE', 'PERSON'],
    r'.*type.*': ['US_DRIVER_LICENSE', 'PERSON'],
    r'.*grade.*': ['US_DRIVER_LICENSE', 'PERSON'],
    r'.*class.*': ['US_DRIVER_LICENSE', 'PERSON'],
    r'.*rank.*': ['US_DRIVER_LICENSE', 'PERSON'],
    r'.*tier.*': ['US_DRIVER_LICENSE', 'PERSON'],
    r'.*segment.*': ['US_DRIVER_LICENSE', 'PERSON'],
    r'.*group.*': ['US_DRIVER_LICENSE', 'PERSON'],
    r'.*code.*': ['PERSON'],  # Codes are rarely names
    r'.*id$': ['PERSON'],  # IDs ending in 'id' are rarely names
    r'.*_id$': ['PERSON'],  # Same for underscore_id
}

# Value Pattern Exclusions - Ignore values matching these patterns for specific entity types
# This catches false positives based on the actual detected value format
EXCLUSION_PATTERNS = {
    'US_DRIVER_LICENSE': [
        r'^[a-zA-Z]\d{1,2}$',  # Single letter + 1-2 digits (e.g., l1, l2, A1, B12)
        r'^[a-zA-Z]{1,2}$',    # 1-2 letters only (e.g., A, AB)
        r'^level\s*\d+$',      # "level 1", "level 2", etc.
        r'^tier\s*\d+$',       # "tier 1", "tier 2", etc.
        r'^grade\s*[a-zA-Z]$', # "grade A", "grade B", etc.
    ],
    'US_PASSPORT': [
        r'^[a-zA-Z]\d{1,2}$',  # Single letter + 1-2 digits
        r'^[a-zA-Z]{1,2}$',    # 1-2 letters only
    ],
    'PERSON': [
        r'^(admin|user|guest|system|default|test|demo)$',  # Generic usernames
        r'^[a-zA-Z]\d*$',      # Single letter with optional numbers (A, A1, B2)
        r'^(yes|no|true|false|y|n|t|f)$',  # Boolean values
        r'^(male|female|m|f|other)$',  # Gender categories
        r'^(low|medium|high|good|bad|excellent|poor)$',  # Rating values
    ],
    'EMAIL_ADDRESS': [
        r'^(test|demo|example|sample)@',  # Test emails
        r'@(test|demo|example|sample)\.',  # Test domains
    ],
    'PHONE_NUMBER': [
        r'^(000|111|222|333|444|555|666|777|888|999)[-\s]',  # Fake phone patterns
        r'^1{6,}$',  # All 1s
        r'^0{6,}$',  # All 0s
    ],
}

# Custom Recognizers (domain-specific patterns)
# Add patterns specific to your industry/use case
CUSTOM_PATTERNS = {
    'LOAN_ID': {
        'pattern': r'LN\d{8}',
        'score': 0.9,
        'strategy': 'HASH'
    },
    'EMPLOYEE_ID': {
        'pattern': r'EMP\d{6}',
        'score': 0.9,
        'strategy': 'HASH'
    },
    'ACCOUNT_NUMBER': {
        'pattern': r'ACC\d{10}',
        'score': 0.95,
        'strategy': 'REMOVE'
    }
}

# Column Name Heuristics
# Auto-flag columns based on name patterns
RISKY_COLUMN_PATTERNS = [
    r'.*email.*',
    r'.*phone.*',
    r'.*ssn.*',
    r'.*social.*security.*',
    r'.*credit.*card.*',
    r'.*passport.*',
    r'.*license.*',
    r'.*address.*',
    r'.*ip.*addr.*',
]

# Protected Attributes Configuration
# These are needed for bias analysis but may contain PII
PROTECTED_ATTRIBUTES_HANDLING = {
    'default_strategy': 'KEEP',  # Keep for bias analysis
    'warn_user': True,  # Warn about privacy implications
    'alternative': 'Use generalization (e.g., age_group instead of exact age)'
}

# Audit Report Settings
AUDIT_CONFIG = {
    'include_examples': True,
    'max_examples_per_column': 3,
    'truncate_values': 50,  # Max characters to show in examples
    'include_presidio_metrics': True,
    'include_gdpr_references': True,
    'include_recommendations': True
}

# Performance Settings
PERFORMANCE_CONFIG = {
    'sample_size_for_detection': 1000,  # Max rows to analyze per column
    'batch_size': 100,  # Rows to process per batch
    'enable_parallel': False,  # Future: parallel column processing
}

# Output Settings
OUTPUT_CONFIG = {
    'cleaned_suffix': '_cleaned',
    'audit_suffix': '_audit',
    'format': 'csv',  # Future: support parquet, json
    'compression': None,  # Future: gzip, bz2
}


def get_strategy_for_entity(entity_type: str) -> str:
    """
    Get anonymization strategy for an entity type
    
    Args:
        entity_type: Presidio entity type (e.g., 'EMAIL_ADDRESS')
        
    Returns:
        Strategy name (e.g., 'HASH')
    """
    return ENTITY_STRATEGY_MAP.get(entity_type, 'HASH')  # Default to HASH if unknown


def get_risk_level(strategy: str) -> str:
    """
    Get risk level for a strategy
    
    Args:
        strategy: Strategy name (e.g., 'HASH')
        
    Returns:
        Risk level (e.g., 'MEDIUM')
    """
    return STRATEGIES.get(strategy, {}).get('risk_level', 'UNKNOWN')


def is_high_confidence(score: float) -> bool:
    """Check if confidence score is high enough for auto-processing"""
    return score >= CONFIDENCE_THRESHOLDS['HIGH']


def is_medium_confidence(score: float) -> bool:
    """Check if confidence score requires user confirmation"""
    return CONFIDENCE_THRESHOLDS['MEDIUM'] <= score < CONFIDENCE_THRESHOLDS['HIGH']


def is_low_confidence(score: float) -> bool:
    """Check if confidence score might be false positive"""
    return score < CONFIDENCE_THRESHOLDS['MEDIUM']


# Example usage in cleaning.py:
# from cleaning_config import ENTITY_STRATEGY_MAP, get_strategy_for_entity
# strategy = get_strategy_for_entity('EMAIL_ADDRESS')  # Returns 'HASH'
