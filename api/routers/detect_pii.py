"""
PII Detection Router
Detects risky features WITHOUT anonymizing them
Returns risk classification for user review
"""

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import pandas as pd
import numpy as np
import io
import os
import sys
from typing import Dict, Any, List

# Import cleaning module
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from data_cleaning.cleaner import DataCleaner
from data_cleaning.config import (
    ENTITY_STRATEGY_MAP, 
    STRATEGIES, 
    GDPR_COMPLIANCE,
    COLUMN_CONTEXT_FILTERS,
    EXCLUSION_PATTERNS,
    get_strategy_for_entity,
    get_risk_level
)

router = APIRouter()


def convert_to_serializable(obj):
    """Convert numpy/pandas types to native Python types for JSON serialization"""
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_to_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_serializable(item) for item in obj]
    return obj


@router.post("/detect-pii")
async def detect_pii(file: UploadFile = File(...)):
    """
    Detect PII in uploaded file WITHOUT anonymizing
    
    - **file**: CSV, JSON, or TXT file to analyze for PII
    
    Returns:
        - List of risky features with severity and recommended strategies
        - Detection confidence scores
        - GDPR article references
        - Example values for review
    """
    
    try:
        # Read uploaded file
        contents = await file.read()
        file_extension = os.path.splitext(file.filename)[1].lower()
        
        # Determine file type and parse accordingly
        if file_extension == '.csv':
            df = pd.read_csv(io.BytesIO(contents))
            file_type = 'csv'
        elif file_extension == '.json':
            df = pd.read_json(io.BytesIO(contents))
            file_type = 'json'
        elif file_extension in ['.txt', '.text']:
            # For plain text, create a single-column dataframe
            text_content = contents.decode('utf-8', errors='ignore')
            # Split into lines for better granularity
            lines = [line.strip() for line in text_content.split('\n') if line.strip()]
            df = pd.DataFrame({'text_content': lines})
            file_type = 'text'
        else:
            # Try to auto-detect format
            try:
                # Try CSV first
                df = pd.read_csv(io.BytesIO(contents))
                file_type = 'csv'
            except:
                try:
                    # Try JSON
                    df = pd.read_json(io.BytesIO(contents))
                    file_type = 'json'
                except:
                    # Fall back to plain text
                    text_content = contents.decode('utf-8', errors='ignore')
                    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
                    df = pd.DataFrame({'text_content': lines})
                    file_type = 'text'
        
        if df.empty:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        
        print(f"Detecting PII in: {file.filename} ({file_type} format, {len(df)} rows, {len(df.columns)} columns)")
        
        # Initialize Data Cleaner (with GPU if available)
        cleaner = DataCleaner(df, use_gpu=True)
        
        # Detect PII without cleaning
        pii_detections = cleaner._detect_pii(
            df=df,
            risky_columns=None,  # Scan all columns
            scan_all_cells=True
        )
        
        # Classify by risk level
        risk_classification = cleaner._classify_risk(pii_detections)
        
        # Build response with detailed feature information
        risky_features = []
        
        for risk_level in ['HIGH', 'MEDIUM', 'LOW', 'UNKNOWN']:
            detections = risk_classification[risk_level]
            
            for column, entities in detections.items():
                for entity_info in entities:
                    entity_type = entity_info['entity_type']
                    strategy = entity_info['strategy']
                    
                    # Get example values from the column (first 3 non-null)
                    sample_values = df[column].dropna().head(5).astype(str).tolist()
                    
                    # Get GDPR article
                    gdpr_article = GDPR_COMPLIANCE.get(entity_type, 'Not classified')
                    
                    # Get strategy details
                    strategy_details = STRATEGIES.get(strategy, {})
                    
                    risky_features.append({
                        'column': column,
                        'entity_type': entity_type,
                        'risk_level': risk_level,
                        'confidence': float(entity_info['confidence']),
                        'detection_count': int(entity_info['count']),
                        'recommended_strategy': strategy,
                        'strategy_description': strategy_details.get('description', ''),
                        'reversible': strategy_details.get('reversible', False),
                        'use_cases': strategy_details.get('use_cases', []),
                        'gdpr_article': gdpr_article,
                        'sample_values': sample_values[:3],  # Show 3 examples
                        'explanation': _generate_risk_explanation(entity_type, risk_level, strategy)
                    })
        
        # Sort by risk level (HIGH -> MEDIUM -> LOW)
        risk_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2, 'UNKNOWN': 3}
        risky_features.sort(key=lambda x: (risk_order[x['risk_level']], x['column']))
        
        # Prepare summary statistics
        summary = {
            'total_columns_scanned': len(df.columns),
            'risky_columns_found': len(set(f['column'] for f in risky_features)),
            'high_risk_count': sum(1 for f in risky_features if f['risk_level'] == 'HIGH'),
            'medium_risk_count': sum(1 for f in risky_features if f['risk_level'] == 'MEDIUM'),
            'low_risk_count': sum(1 for f in risky_features if f['risk_level'] == 'LOW'),
            'unique_entity_types': len(set(f['entity_type'] for f in risky_features))
        }
        
        response_data = {
            'status': 'success',
            'filename': file.filename,
            'file_type': file_type,
            'dataset_info': {
                'rows': len(df),
                'columns': len(df.columns),
                'column_names': df.columns.tolist()
            },
            'summary': summary,
            'risky_features': risky_features,
            'available_strategies': STRATEGIES,
            'message': f"Found {summary['risky_columns_found']} columns with PII ({summary['high_risk_count']} HIGH risk, {summary['medium_risk_count']} MEDIUM risk, {summary['low_risk_count']} LOW risk)"
        }
        
        # Convert all numpy/pandas types to native Python types
        response_data = convert_to_serializable(response_data)
        
        return JSONResponse(content=response_data)
        
    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="File is empty or invalid CSV format")
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Presidio not installed. Please install: pip install presidio-analyzer presidio-anonymizer")
    except Exception as e:
        print(f"Error during PII detection: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"PII detection failed: {str(e)}")


def _generate_risk_explanation(entity_type: str, risk_level: str, strategy: str) -> str:
    """Generate human-readable explanation for why a feature is risky"""
    
    explanations = {
        'CREDIT_CARD': "Credit card numbers are highly sensitive financial identifiers protected under GDPR Art. 4(1) and PCI-DSS regulations. Unauthorized disclosure can lead to fraud and identity theft.",
        'US_SSN': "Social Security Numbers are government-issued identifiers that can be used for identity theft. They are strictly protected under US federal law and GDPR Art. 4(1).",
        'EMAIL_ADDRESS': "Email addresses are personal identifiers under GDPR Art. 4(1) that can be used to re-identify individuals and track behavior across services.",
        'PHONE_NUMBER': "Phone numbers are direct personal identifiers under GDPR Art. 4(1) that enable contact and can be used to track individuals.",
        'PERSON': "Personal names are explicit identifiers under GDPR Art. 4(1) that directly identify individuals and must be protected in datasets.",
        'LOCATION': "Location data reveals personal information about individuals' movements and residence, protected under GDPR Art. 4(1) as personal data.",
        'IP_ADDRESS': "IP addresses are online identifiers under GDPR Art. 4(1) that can be used to track individuals across the internet.",
        'DATE_TIME': "Temporal data can be used to re-identify individuals when combined with other data points, especially for rare events.",
        'MEDICAL_LICENSE': "Medical information is special category data under GDPR Art. 9(1) requiring heightened protection due to health privacy concerns.",
        'NRP': "Nationality, religious, or political views are special category data under GDPR Art. 9(1) that can lead to discrimination.",
        'US_BANK_NUMBER': "Bank account numbers are financial identifiers that enable unauthorized access to accounts and are protected under GDPR Art. 4(1).",
        'CRYPTO': "Cryptocurrency addresses are financial identifiers that can reveal transaction history and wealth, requiring protection.",
        'FI_PERSONAL_ID': "Finnish personal identity numbers (HETU) are highly sensitive national identifiers under GDPR Art. 4(1) + Recital 26, granting access to government services.",
        'SE_PERSONAL_ID': "Swedish Personnummer are national identifiers protected under GDPR Art. 4(1) + Recital 26, used across all government and private services.",
        'NO_PERSONAL_ID': "Norwegian Fødselsnummer are national ID numbers under GDPR Art. 4(1) + Recital 26, used for all official identification.",
        'DK_PERSONAL_ID': "Danish CPR numbers are national identifiers protected under GDPR Art. 4(1) + Recital 26, critical for government services.",
        'FI_BUSINESS_ID': "Finnish business IDs (Y-tunnus) are organizational identifiers with lower risk than personal IDs, but still require protection for business privacy.",
    }
    
    base_explanation = explanations.get(entity_type, 
        f"{entity_type} detected as {risk_level} risk personal data under GDPR regulations requiring appropriate protection measures.")
    
    strategy_note = f" Recommended action: {strategy} - this {'permanently removes' if strategy == 'REMOVE' else 'anonymizes'} the data to ensure compliance."
    
    return base_explanation + strategy_note
