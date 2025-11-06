"""
Report Generator Module
Generates comprehensive JSON reports
"""

import json
import numpy as np
from datetime import datetime

class NumpyEncoder(json.JSONEncoder):
    """Custom JSON encoder for numpy types"""
    def default(self, obj):
        if isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        elif isinstance(obj, (np.ndarray,)):
            return obj.tolist()
        elif isinstance(obj, (np.bool_,)):
            return bool(obj)
        return super(NumpyEncoder, self).default(obj)

class ReportGenerator:
    """Generate comprehensive analysis reports"""
    
    def __init__(self, model_results, bias_results, risk_results, df):
        self.model_results = model_results
        self.bias_results = bias_results
        self.risk_results = risk_results
        self.df = df
    
    def generate_report(self):
        """Generate comprehensive JSON report"""
        report = {
            'metadata': self._generate_metadata(),
            'summary': self._generate_summary(),
            'model_performance': self._format_model_results(),
            'bias_analysis': self._format_bias_results(),
            'risk_assessment': self._format_risk_results(),
            'key_findings': self._extract_key_findings(),
            'recommendations': self._compile_recommendations(),
            'detailed_metrics': self._compile_detailed_metrics()
        }
        
        return report
    
    def _generate_metadata(self):
        """Generate report metadata"""
        return {
            'report_id': f"AIGov_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            'generated_at': datetime.now().isoformat(),
            'report_version': '1.0',
            'dataset_info': {
                'total_records': len(self.df),
                'total_features': len(self.df.columns),
                'columns': list(self.df.columns)
            }
        }
    
    def _generate_summary(self):
        """Generate executive summary"""
        model_metrics = self.model_results.get('metrics', {})
        
        return {
            'overall_bias_score': self.bias_results.get('overall_bias_score', 0.0),
            'overall_risk_score': self.risk_results.get('overall_risk_score', 0.0),
            'risk_level': self.risk_results.get('risk_level', 'UNKNOWN'),
            'model_accuracy': model_metrics.get('accuracy', 0.0),
            'fairness_violations_count': len(self.bias_results.get('fairness_violations', [])),
            'passes_fairness_threshold': self.bias_results.get('fairness_assessment', {}).get('passes_fairness_threshold', False)
        }
    
    def _format_model_results(self):
        """Format model performance results"""
        return {
            'model_type': self.model_results.get('model_type', 'Unknown'),
            'metrics': self.model_results.get('metrics', {}),
            'confusion_matrix': self.model_results.get('confusion_matrix', []),
            'top_features': dict(list(self.model_results.get('feature_importance', {}).items())[:10])
        }
    
    def _format_bias_results(self):
        """Format bias analysis results"""
        return {
            'overall_bias_score': self.bias_results.get('overall_bias_score', 0.0),
            'fairness_metrics': self.bias_results.get('fairness_metrics', {}),
            'fairness_violations': self.bias_results.get('fairness_violations', []),
            'fairness_assessment': self.bias_results.get('fairness_assessment', {}),
            'demographic_bias_summary': self._summarize_demographic_bias()
        }
    
    def _format_risk_results(self):
        """Format risk assessment results"""
        return {
            'overall_risk_score': self.risk_results.get('overall_risk_score', 0.0),
            'risk_level': self.risk_results.get('risk_level', 'UNKNOWN'),
            'risk_categories': self.risk_results.get('risk_categories', {}),
            'privacy_risks': self._summarize_privacy_risks(),
            'ethical_risks': self._summarize_ethical_risks()
        }
    
    def _summarize_demographic_bias(self):
        """Summarize demographic bias"""
        demo_bias = self.bias_results.get('demographic_bias', {})
        summary = {}
        
        for attr, data in demo_bias.items():
            summary[attr] = {
                'max_disparity': data.get('max_disparity', 0),
                'groups_analyzed': len(data.get('approval_rates', {}))
            }
        
        return summary
    
    def _summarize_privacy_risks(self):
        """Summarize privacy risks"""
        privacy = self.risk_results.get('privacy_risks', {})
        
        return {
            'pii_count': len(privacy.get('pii_detected', [])),
            'anonymization_level': privacy.get('anonymization_level', 'UNKNOWN'),
            'exposure_risk_count': len(privacy.get('exposure_risks', [])),
            'gdpr_compliance_score': privacy.get('gdpr_compliance', {}).get('compliance_score', 0)
        }
    
    def _summarize_ethical_risks(self):
        """Summarize ethical risks"""
        ethical = self.risk_results.get('ethical_risks', {})
        
        return {
            'fairness_issues_count': len(ethical.get('fairness_issues', [])),
            'transparency_score': ethical.get('transparency_score', 0),
            'bias_amplification_risk': ethical.get('bias_amplification_risk', 'UNKNOWN'),
            'social_impact': ethical.get('social_impact_assessment', {})
        }
    
    def _extract_key_findings(self):
        """Extract key findings from analysis"""
        findings = []
        
        # Model performance findings
        accuracy = self.model_results.get('metrics', {}).get('accuracy', 0)
        if accuracy >= 0.8:
            findings.append(f"✓ Model achieves good accuracy ({accuracy:.2%})")
        else:
            findings.append(f"⚠ Model accuracy is below optimal ({accuracy:.2%})")
        
        # Bias findings
        bias_score = self.bias_results.get('overall_bias_score', 0)
        if bias_score < 0.3:
            findings.append("✓ Low bias detected across protected attributes")
        elif bias_score < 0.5:
            findings.append("⚠ Moderate bias detected - monitoring recommended")
        else:
            findings.append("❌ High bias detected - immediate action required")
        
        # Fairness violations
        violations = self.bias_results.get('fairness_violations', [])
        if violations:
            high_sev = sum(1 for v in violations if v['severity'] == 'HIGH')
            findings.append(f"❌ {len(violations)} fairness violations detected ({high_sev} high severity)")
        else:
            findings.append("✓ No fairness violations detected")
        
        # Privacy findings
        privacy = self.risk_results.get('privacy_risks', {})
        pii_count = len(privacy.get('pii_detected', []))
        if pii_count > 0:
            findings.append(f"⚠ {pii_count} columns contain potential PII")
        else:
            findings.append("✓ No obvious PII detected in dataset")
        
        # Risk level
        risk_level = self.risk_results.get('risk_level', 'UNKNOWN')
        findings.append(f"Overall Risk Level: {risk_level}")
        
        return findings
    
    def _compile_recommendations(self):
        """Compile all recommendations"""
        recommendations = []
        
        # Get recommendations from each component
        privacy_recs = self.risk_results.get('privacy_risks', {}).get('recommendations', [])
        ethical_recs = self.risk_results.get('ethical_risks', {}).get('recommendations', [])
        performance_recs = self.risk_results.get('model_performance_risks', {}).get('recommendations', [])
        compliance_recs = self.risk_results.get('compliance_risks', {}).get('recommendations', [])
        
        # Prioritize recommendations
        all_recs = []
        
        # High priority (from violations and high risks)
        violations = self.bias_results.get('fairness_violations', [])
        if violations:
            all_recs.append({
                'priority': 'HIGH',
                'category': 'Fairness',
                'recommendation': 'Address fairness violations in protected attributes'
            })
        
        if len(privacy_recs) > 0:
            all_recs.append({
                'priority': 'HIGH',
                'category': 'Privacy',
                'recommendation': privacy_recs[0]
            })
        
        # Medium priority
        for rec in ethical_recs[:2]:
            all_recs.append({
                'priority': 'MEDIUM',
                'category': 'Ethics',
                'recommendation': rec
            })
        
        # Lower priority
        for rec in performance_recs[:2]:
            all_recs.append({
                'priority': 'MEDIUM',
                'category': 'Performance',
                'recommendation': rec
            })
        
        for rec in compliance_recs[:2]:
            all_recs.append({
                'priority': 'MEDIUM',
                'category': 'Compliance',
                'recommendation': rec
            })
        
        # Convert to simple list with formatting
        recommendations = [
            f"[{r['priority']}] {r['category']}: {r['recommendation']}"
            for r in all_recs[:10]  # Limit to top 10
        ]
        
        return recommendations
    
    def _compile_detailed_metrics(self):
        """Compile detailed metrics for analysis"""
        return {
            'bias_metrics': {
                'by_attribute': self.bias_results.get('fairness_metrics', {}),
                'demographic_analysis': self.bias_results.get('demographic_bias', {})
            },
            'risk_breakdown': {
                'privacy': self.risk_results.get('privacy_risks', {}),
                'ethical': self.risk_results.get('ethical_risks', {}),
                'compliance': self.risk_results.get('compliance_risks', {}),
                'data_quality': self.risk_results.get('data_quality_risks', {})
            },
            'model_details': {
                'classification_report': self.model_results.get('classification_report', {}),
                'feature_importance': self.model_results.get('feature_importance', {})
            }
        }
    
    def save_report(self, filepath):
        """Save report to JSON file"""
        report = self.generate_report()
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2, cls=NumpyEncoder)
        return filepath
