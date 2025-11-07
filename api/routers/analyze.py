"""
AI Governance Analysis Router
Handles bias detection and risk analysis endpoints
"""

from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import pandas as pd
import numpy as np
import io
import os
import json
from datetime import datetime
from typing import Dict, Any

# Import AI Governance modules
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from ai_governance import AIGovernanceAnalyzer

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

@router.post("/analyze")
async def analyze_dataset(file: UploadFile = File(...)):
    """
    Analyze uploaded dataset for bias and risk
    
    - **file**: CSV file to analyze
    
    Returns:
        - Analysis results (bias metrics, risk assessment)
        - Report file path for download
    """
    
    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    
    try:
        # Read uploaded file
        contents = await file.read()
        df = pd.read_csv(io.BytesIO(contents))
        
        if df.empty:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        
        # Initialize AI Governance Analyzer
        analyzer = AIGovernanceAnalyzer()
        
        # Auto-detect target column and protected attributes
        # Target: Last column (common convention) or first binary/categorical column
        target_column = df.columns[-1]
        
        # Protected attributes: Common sensitive columns
        protected_keywords = ['gender', 'age', 'race', 'sex', 'ethnicity', 'religion', 'nationality']
        protected_attributes = [col for col in df.columns 
                              if any(keyword in col.lower() for keyword in protected_keywords)]
        
        # If no protected attributes found, use first few categorical columns
        if not protected_attributes:
            categorical_cols = df.select_dtypes(include=['object', 'category']).columns
            protected_attributes = [col for col in categorical_cols if col != target_column][:3]
        
        print(f"Analyzing dataset: {file.filename} ({len(df)} rows, {len(df.columns)} columns)")
        print(f"Target column: {target_column}")
        print(f"Protected attributes: {protected_attributes}")
        
        # Run analysis
        report = analyzer.analyze_dataframe(df, target_column, protected_attributes)
        
        # Generate report filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = (file.filename or "dataset").replace('.csv', '')
        report_filename = f"governance_report_{safe_filename}_{timestamp}.json"
        report_path = os.path.join("reports", report_filename)
        
        # Save full report to disk
        full_report_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            report_path
        )
        analyzer.save_report(report, full_report_path)
        
        # Prepare response with summary
        bias_analysis = report.get("bias_analysis", {})
        model_metrics = report.get("model_performance", {}).get("metrics", {})
        risk_assessment = report.get("risk_assessment", {})
        
        response_data = {
            "status": "success",
            "filename": file.filename,
            "dataset_info": {
                "rows": len(df),
                "columns": len(df.columns),
                "features": list(df.columns)
            },
            "model_performance": {
                "accuracy": model_metrics.get("accuracy", 0),
                "precision": model_metrics.get("precision", 0),
                "recall": model_metrics.get("recall", 0),
                "f1_score": model_metrics.get("f1_score", 0)
            },
            "bias_metrics": {
                "overall_bias_score": bias_analysis.get("overall_bias_score", 0),
                "disparate_impact": bias_analysis.get("fairness_metrics", {}),
                "statistical_parity": bias_analysis.get("fairness_metrics", {}),
                "violations_detected": bias_analysis.get("fairness_violations", [])
            },
            "risk_assessment": {
                "overall_risk_score": risk_assessment.get("overall_risk_score", 0),
                "risk_level": risk_assessment.get("risk_level", "LOW"),
                "presidio_enabled": risk_assessment.get("presidio_enabled", False),
                "privacy_risks": risk_assessment.get("privacy_risks", {}),
                "ethical_risks": risk_assessment.get("ethical_risks", {}),
                "compliance_risks": risk_assessment.get("compliance_risks", {}),
                "risk_categories": risk_assessment.get("risk_categories", {}),
                "violations": risk_assessment.get("violations", []),
                "insights": risk_assessment.get("insights", [])
            },
            "recommendations": report.get("recommendations", []),
            "report_file": f"/{report_path}",
            "timestamp": datetime.now().isoformat()
        }
        
        # Debug: Print bias metrics being sent to frontend
        print(f"\n📊 Sending bias metrics to frontend:")
        print(f"  Overall Bias Score: {response_data['bias_metrics']['overall_bias_score']:.3f}")
        print(f"  Violations: {len(response_data['bias_metrics']['violations_detected'])}")
        print(f"  Fairness Metrics: {len(response_data['bias_metrics']['disparate_impact'])} attributes")
        
        # Convert all numpy/pandas types to native Python types
        response_data = convert_to_serializable(response_data)
        
        return JSONResponse(content=response_data)
        
    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="File is empty or invalid CSV format")
    except Exception as e:
        print(f"Error during analysis: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
