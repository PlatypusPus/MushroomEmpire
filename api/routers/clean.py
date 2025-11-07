"""
Data Cleaning Router
Handles PII detection and anonymization endpoints
"""

from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse
import pandas as pd
import numpy as np
import io
import os
import json
from datetime import datetime
from typing import Dict, Any, Optional

# Import cleaning module
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from data_cleaning import DataCleaner

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


@router.post("/clean")
async def clean_dataset(
    file: UploadFile = File(...),
    custom_strategies: Optional[str] = Form(None)
):
    """
    Clean uploaded dataset - detect and anonymize PII
    
    - **file**: CSV file to clean
    - **custom_strategies**: Optional JSON string mapping column names to strategy choices
      Format: {"column_name": {"enabled": true, "strategy": "HASHING"}}
    
    Returns:
        - Cleaned dataset statistics
        - PII detections and anonymization actions
        - Report file path for download
        - Cleaned CSV file path for download
    """
    
    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    
    # Parse custom strategies if provided
    strategy_map = None
    if custom_strategies:
        try:
            strategy_map = json.loads(custom_strategies)
            print(f"Using custom strategies for {len(strategy_map)} columns")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid custom_strategies JSON format")
    
    try:
        # Read uploaded file
        contents = await file.read()
        df = pd.read_csv(io.BytesIO(contents))
        
        if df.empty:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        
        # Initialize Data Cleaner (with GPU if available)
        print(f"Cleaning dataset: {file.filename} ({len(df)} rows, {len(df.columns)} columns)")
        cleaner = DataCleaner(df, use_gpu=True)
        
        # If custom strategies provided, filter and apply only enabled columns
        risky_features_to_clean = None
        if strategy_map:
            # Only clean columns that are enabled in the strategy map
            enabled_columns = [col for col, config in strategy_map.items() if config.get('enabled', True)]
            risky_features_to_clean = enabled_columns
            print(f"  Using custom strategies for {len(enabled_columns)} enabled columns")
            
            # Store the strategy choices for the cleaner to use
            cleaner.custom_strategy_map = {
                col: config['strategy'] 
                for col, config in strategy_map.items() 
                if config.get('enabled', True)
            }
        
        # Run cleaning (non-interactive mode for API)
        cleaned_df, audit_report = cleaner.clean(
            risky_features=risky_features_to_clean,  # Use custom list if provided, otherwise auto-detect
            interactive=False,    # No user prompts in API mode
            scan_all_cells=True
        )
        
        # Generate filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = file.filename.replace('.csv', '')
        
        # Save cleaned CSV
        cleaned_csv_filename = f"cleaned_{safe_filename}_{timestamp}.csv"
        cleaned_csv_path = os.path.join("reports", cleaned_csv_filename)
        full_cleaned_csv_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            cleaned_csv_path
        )
        cleaner.save_cleaned_data(cleaned_df, full_cleaned_csv_path)
        
        # Save audit report
        audit_report_filename = f"cleaning_audit_{safe_filename}_{timestamp}.json"
        audit_report_path = os.path.join("reports", audit_report_filename)
        full_audit_report_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            audit_report_path
        )
        cleaner.save_audit_report(audit_report, full_audit_report_path)
        
        # Prepare response
        response_data = {
            "status": "success",
            "filename": file.filename,
            "dataset_info": {
                "original_rows": int(audit_report["metadata"]["original_rows"]),
                "original_columns": int(audit_report["metadata"]["original_columns"]),
                "cleaned_rows": int(audit_report["metadata"]["cleaned_rows"]),
                "cleaned_columns": int(audit_report["metadata"]["cleaned_columns"])
            },
            "gpu_acceleration": audit_report["metadata"].get("gpu_acceleration", {
                "enabled": False,
                "device": "CPU"
            }),
            "summary": {
                "columns_removed": audit_report["summary"]["columns_removed"],
                "columns_anonymized": audit_report["summary"]["columns_anonymized"],
                "total_cells_affected": int(audit_report["summary"]["total_cells_affected"])
            },
            "pii_detections": {
                col: {
                    "action": details["action"],
                    "entity_types": details["entity_types_found"],
                    "num_affected_rows": int(details.get("num_affected_rows", 0)),
                    "examples": details.get("examples", [])[:2]  # Show 2 examples
                }
                for col, details in audit_report["details"].items()
            },
            "gdpr_compliance": audit_report["compliance"]["gdpr_articles_applied"],
            "files": {
                "cleaned_csv": f"/{cleaned_csv_path}",
                "audit_report": f"/{audit_report_path}"
            },
            "timestamp": datetime.now().isoformat()
        }
        
        # Convert all numpy/pandas types to native Python types
        response_data = convert_to_serializable(response_data)
        
        return JSONResponse(content=response_data)
        
    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="File is empty or invalid CSV format")
    except Exception as e:
        print(f"Error during cleaning: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Cleaning failed: {str(e)}")
