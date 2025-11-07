"""
Unified Analysis API - Combines TF-IDF and Presidio
Provides fast fallback with TF-IDF and deep analysis with Presidio
"""

import pandas as pd
from typing import Dict, Any, Optional, Literal
import time

from ai_governance.tfidf_analyzer import TFIDFRiskAnalyzer, TFIDFBiasAnalyzer
from ai_governance.risk_analyzer import RiskAnalyzer
from ai_governance.bias_analyzer import BiasAnalyzer


class UnifiedAnalyzer:
    """
    Unified analyzer that combines TF-IDF (fast) with Presidio (accurate)
    Provides intelligent fallback and hybrid analysis modes
    """
    
    def __init__(
        self, 
        mode: Literal['fast', 'accurate', 'hybrid'] = 'hybrid',
        tfidf_model_path: Optional[str] = None
    ):
        """
        Initialize unified analyzer
        
        Args:
            mode: Analysis mode
                - 'fast': TF-IDF only (20x faster)
                - 'accurate': Presidio only (most accurate)
                - 'hybrid': TF-IDF first, Presidio for high-risk (balanced)
            tfidf_model_path: Path to pre-trained TF-IDF model
        """
        self.mode = mode
        
        # Initialize TF-IDF analyzers (always available)
        print(f"\n🔧 Initializing Unified Analyzer (mode: {mode.upper()})...")
        
        self.tfidf_risk = TFIDFRiskAnalyzer(model_path=tfidf_model_path)
        self.tfidf_bias = TFIDFBiasAnalyzer()
        
        # Initialize Presidio analyzers (if needed)
        self.presidio_risk = None
        self.presidio_bias = None
        
        if mode in ['accurate', 'hybrid']:
            try:
                self.presidio_risk = RiskAnalyzer(use_gpu=False)  # CPU for compatibility
                self.presidio_bias = BiasAnalyzer()
                print("✓ Presidio analyzers initialized")
            except Exception as e:
                print(f"⚠️  Presidio not available: {e}")
                print("   Falling back to TF-IDF only mode")
                self.mode = 'fast'
        
        print(f"✓ Unified Analyzer ready ({self.mode} mode)")
    
    def analyze_risk(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze privacy risks using selected mode
        
        Args:
            df: DataFrame to analyze
            
        Returns:
            Risk analysis results with timing info
        """
        start_time = time.time()
        
        if self.mode == 'fast':
            # TF-IDF only (fastest)
            results = self.tfidf_risk.analyze_dataset(df)
            results['analysis_method'] = 'tfidf'
            
        elif self.mode == 'accurate':
            # Presidio only (most accurate)
            results = self.presidio_risk.analyze(df)
            results['analysis_method'] = 'presidio'
            
        else:  # hybrid
            # TF-IDF first for quick screening
            print("\n🔍 Phase 1: TF-IDF quick screening...")
            tfidf_results = self.tfidf_risk.analyze_dataset(df)
            
            # Check if high-risk columns need deep analysis
            high_risk_cols = tfidf_results['overall_risk']['high_risk_columns']
            
            if high_risk_cols:
                print(f"\n🔬 Phase 2: Presidio deep analysis on {len(high_risk_cols)} high-risk columns...")
                presidio_results = self.presidio_risk.analyze(df[high_risk_cols])
                
                # Merge results
                results = self._merge_risk_results(tfidf_results, presidio_results)
                results['analysis_method'] = 'hybrid_tfidf_presidio'
            else:
                results = tfidf_results
                results['analysis_method'] = 'tfidf_only'
        
        elapsed_time = time.time() - start_time
        results['analysis_time_seconds'] = round(elapsed_time, 2)
        
        return results
    
    def analyze_bias(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze bias using selected mode
        
        Args:
            df: DataFrame to analyze
            
        Returns:
            Bias analysis results with timing info
        """
        start_time = time.time()
        
        if self.mode == 'fast':
            # TF-IDF only
            results = self.tfidf_bias.analyze_dataset(df)
            results['analysis_method'] = 'tfidf'
            
        elif self.mode == 'accurate':
            # Presidio-based
            results = self.presidio_bias.analyze(df)
            results['analysis_method'] = 'presidio'
            
        else:  # hybrid
            # Use TF-IDF for pattern matching
            tfidf_results = self.tfidf_bias.analyze_dataset(df)
            
            # Use Presidio for statistical bias
            if self.presidio_bias:
                presidio_results = self.presidio_bias.analyze(df)
                results = self._merge_bias_results(tfidf_results, presidio_results)
                results['analysis_method'] = 'hybrid'
            else:
                results = tfidf_results
                results['analysis_method'] = 'tfidf_only'
        
        elapsed_time = time.time() - start_time
        results['analysis_time_seconds'] = round(elapsed_time, 2)
        
        return results
    
    def analyze_full(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Run complete risk + bias analysis
        
        Args:
            df: DataFrame to analyze
            
        Returns:
            Combined analysis results
        """
        print("\n" + "="*70)
        print("🎯 UNIFIED AI GOVERNANCE ANALYSIS")
        print("="*70)
        
        # Risk analysis
        print("\n📊 PRIVACY RISK ANALYSIS")
        risk_results = self.analyze_risk(df)
        
        # Bias analysis
        print("\n⚖️  FAIRNESS & BIAS ANALYSIS")
        bias_results = self.analyze_bias(df)
        
        # Combined results
        combined = {
            'analysis_mode': self.mode,
            'dataset_info': {
                'rows': len(df),
                'columns': len(df.columns)
            },
            'risk_analysis': risk_results,
            'bias_analysis': bias_results,
            'total_time_seconds': risk_results.get('analysis_time_seconds', 0) + 
                                 bias_results.get('analysis_time_seconds', 0),
            'gdpr_compliance': self._assess_gdpr_compliance(risk_results, bias_results)
        }
        
        print("\n" + "="*70)
        print(f"✅ ANALYSIS COMPLETE in {combined['total_time_seconds']:.2f}s")
        print("="*70)
        
        return combined
    
    def _merge_risk_results(self, tfidf_results: Dict, presidio_results: Dict) -> Dict:
        """Merge TF-IDF and Presidio risk results"""
        merged = tfidf_results.copy()
        
        # Update high-risk columns with Presidio details
        for col in tfidf_results['overall_risk']['high_risk_columns']:
            if col in presidio_results.get('privacy_risks', {}):
                merged['column_analysis'][col]['presidio_details'] = presidio_results['privacy_risks'][col]
        
        return merged
    
    def _merge_bias_results(self, tfidf_results: Dict, presidio_results: Dict) -> Dict:
        """Merge TF-IDF and Presidio bias results"""
        merged = tfidf_results.copy()
        
        # Add statistical bias metrics from Presidio
        if 'bias_metrics' in presidio_results:
            merged['statistical_bias'] = presidio_results['bias_metrics']
        
        return merged
    
    def _assess_gdpr_compliance(self, risk_results: Dict, bias_results: Dict) -> Dict:
        """Assess overall GDPR compliance"""
        compliance = {
            'compliant': True,
            'violations': [],
            'warnings': [],
            'articles_applicable': []
        }
        
        # Check risk results
        if risk_results.get('overall_risk', {}).get('risk_level') in ['HIGH', 'CRITICAL']:
            compliance['compliant'] = False
            compliance['violations'].append("High privacy risk detected (GDPR Art. 5)")
            compliance['articles_applicable'].append("Art. 5 - Data minimization")
        
        direct_ids = len(risk_results.get('privacy_categories', {}).get('direct_identifiers', []))
        if direct_ids > 0:
            compliance['violations'].append(f"{direct_ids} direct identifiers require protection (GDPR Art. 32)")
            compliance['articles_applicable'].append("Art. 32 - Security of processing")
        
        # Check bias results
        article9_violations = bias_results.get('gdpr_compliance', {}).get('article_9_violations', [])
        if article9_violations:
            compliance['compliant'] = False
            compliance['violations'].append(f"{len(article9_violations)} special category violations (GDPR Art. 9)")
            compliance['articles_applicable'].append("Art. 9 - Special categories of personal data")
        
        if compliance['compliant']:
            compliance['status'] = "✅ GDPR Compliant"
        else:
            compliance['status'] = "❌ GDPR Non-Compliant"
        
        return compliance


# Convenience functions for API endpoints
def quick_risk_check(df: pd.DataFrame) -> Dict[str, Any]:
    """Fast risk check using TF-IDF (for API endpoints)"""
    analyzer = UnifiedAnalyzer(mode='fast')
    return analyzer.analyze_risk(df)


def deep_risk_analysis(df: pd.DataFrame) -> Dict[str, Any]:
    """Accurate risk analysis using Presidio (for detailed reports)"""
    analyzer = UnifiedAnalyzer(mode='accurate')
    return analyzer.analyze_risk(df)


def hybrid_analysis(df: pd.DataFrame) -> Dict[str, Any]:
    """Balanced hybrid analysis (recommended)"""
    analyzer = UnifiedAnalyzer(mode='hybrid')
    return analyzer.analyze_full(df)
