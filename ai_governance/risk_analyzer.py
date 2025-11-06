"""
Risk Analyzer Module
Assesses privacy and ethical risks in AI models
"""

import pandas as pd
import numpy as np
import re
from datetime import datetime

class RiskAnalyzer:
    """Analyze privacy and ethical risks"""
    
    def __init__(self, df, model_results, bias_results, protected_attributes, target_column):
        self.df = df
        self.model_results = model_results
        self.bias_results = bias_results
        self.protected_attributes = protected_attributes
        self.target_column = target_column
        self.results = {}
    
    def analyze(self):
        """Perform comprehensive risk analysis"""
        self.results = {
            'privacy_risks': self._analyze_privacy_risks(),
            'ethical_risks': self._analyze_ethical_risks(),
            'model_performance_risks': self._analyze_model_performance_risks(),
            'compliance_risks': self._analyze_compliance_risks(),
            'data_quality_risks': self._analyze_data_quality_risks(),
            'risk_categories': {},
            'overall_risk_score': 0.0,
            'risk_level': 'UNKNOWN'
        }
        
        # Aggregate risk categories
        self.results['risk_categories'] = self._aggregate_risk_categories()
        
        # Calculate overall risk score
        self.results['overall_risk_score'] = self._calculate_overall_risk_score()
        
        # Determine risk level
        self.results['risk_level'] = self._determine_risk_level()
        
        return self.results
    
    def _analyze_privacy_risks(self):
        """Analyze privacy-related risks"""
        privacy_risks = {
            'pii_detected': [],
            'sensitive_attributes': self.protected_attributes,
            'data_minimization_score': 0.0,
            'anonymization_level': 'NONE',
            'exposure_risks': [],
            'gdpr_compliance': {},
            'recommendations': []
        }
        
        # Detect PII columns
        pii_patterns = {
            'email': r'^.*email.*$',
            'phone': r'^.*(phone|mobile|tel).*$',
            'address': r'^.*(address|street|city|zip|postal).*$',
            'name': r'^.*(name|firstname|lastname).*$',
            'ssn': r'^.*(ssn|social.*security).*$',
            'id': r'^.*(id|identifier|passport|license).*$',
            'dob': r'^.*(dob|birth|birthday).*$',
            'age': r'^.*age.*$',
            'gender': r'^.*gender.*$'
        }
        
        for col in self.df.columns:
            col_lower = col.lower()
            for pii_type, pattern in pii_patterns.items():
                if re.match(pattern, col_lower):
                    privacy_risks['pii_detected'].append({
                        'column': col,
                        'type': pii_type,
                        'severity': 'HIGH' if pii_type in ['ssn', 'email', 'phone'] else 'MEDIUM'
                    })
                    break
        
        # Check data minimization
        total_cols = len(self.df.columns)
        essential_cols = len([col for col in self.df.columns if col != self.target_column])
        privacy_risks['data_minimization_score'] = 1.0 - (essential_cols / total_cols) if total_cols > 0 else 0.0
        
        # Assess anonymization level
        if len(privacy_risks['pii_detected']) > 5:
            privacy_risks['anonymization_level'] = 'NONE'
            privacy_risks['exposure_risks'].append("High number of PII columns detected without anonymization")
        elif len(privacy_risks['pii_detected']) > 0:
            privacy_risks['anonymization_level'] = 'PARTIAL'
            privacy_risks['exposure_risks'].append("Some PII columns detected - consider anonymization")
        else:
            privacy_risks['anonymization_level'] = 'FULL'
        
        # GDPR compliance checks
        privacy_risks['gdpr_compliance'] = {
            'has_consent_mechanism': False,  # Cannot determine from data alone
            'data_portability': True,  # CSV format allows export
            'right_to_erasure': False,  # Cannot determine from data alone
            'data_protection_by_design': len(privacy_risks['pii_detected']) == 0,
            'compliance_score': 0.25
        }
        
        # Recommendations
        if len(privacy_risks['pii_detected']) > 0:
            privacy_risks['recommendations'].append("Implement data anonymization techniques (hashing, tokenization)")
            privacy_risks['recommendations'].append("Remove unnecessary PII columns")
            privacy_risks['recommendations'].append("Implement access controls for sensitive data")
        
        privacy_risks['recommendations'].append("Implement data encryption at rest and in transit")
        privacy_risks['recommendations'].append("Establish data retention and deletion policies")
        privacy_risks['recommendations'].append("Conduct regular privacy impact assessments")
        
        return privacy_risks
    
    def _analyze_ethical_risks(self):
        """Analyze ethical risks"""
        ethical_risks = {
            'fairness_issues': [],
            'transparency_score': 0.0,
            'transparency_notes': '',
            'accountability_measures': [],
            'social_impact_assessment': {},
            'bias_amplification_risk': 'UNKNOWN',
            'recommendations': []
        }
        
        # Fairness issues from bias analysis
        violations = self.bias_results.get('fairness_violations', [])
        for violation in violations:
            ethical_risks['fairness_issues'].append(
                f"{violation['attribute']}: {violation['message']} (Severity: {violation['severity']})"
            )
        
        # Transparency score based on model complexity
        model_type = self.model_results.get('model_type', 'Unknown')
        if model_type in ['LogisticRegression', 'DecisionTreeClassifier']:
            ethical_risks['transparency_score'] = 0.9
            ethical_risks['transparency_notes'] = "Model is highly interpretable"
        elif model_type in ['RandomForestClassifier', 'GradientBoostingClassifier']:
            ethical_risks['transparency_score'] = 0.6
            ethical_risks['transparency_notes'] = "Model has moderate interpretability - feature importance available"
        else:
            ethical_risks['transparency_score'] = 0.3
            ethical_risks['transparency_notes'] = "Model has low interpretability - consider using SHAP/LIME"
        
        # Accountability measures
        ethical_risks['accountability_measures'] = [
            "Model versioning and tracking",
            "Prediction logging for audit trail",
            "Regular bias monitoring",
            "Human review for high-stakes decisions"
        ]
        
        # Social impact assessment
        ethical_risks['social_impact_assessment'] = {
            'affected_groups': self.protected_attributes,
            'potential_harms': [
                "Unfair denial of opportunities for protected groups",
                "Reinforcement of historical biases",
                "Lack of recourse for affected individuals"
            ],
            'mitigation_strategies': [
                "Regular fairness audits",
                "Diverse dataset collection",
                "Stakeholder engagement",
                "Appeal and review mechanisms"
            ]
        }
        
        # Bias amplification risk
        overall_bias = self.bias_results.get('overall_bias_score', 0)
        if overall_bias > 0.5:
            ethical_risks['bias_amplification_risk'] = 'HIGH'
        elif overall_bias > 0.3:
            ethical_risks['bias_amplification_risk'] = 'MEDIUM'
        else:
            ethical_risks['bias_amplification_risk'] = 'LOW'
        
        # Recommendations
        ethical_risks['recommendations'] = [
            "Implement regular fairness audits and monitoring",
            "Use explainable AI techniques (SHAP, LIME) for transparency",
            "Establish ethics review board for model deployment",
            "Create feedback mechanisms for affected individuals",
            "Document decision-making processes and limitations",
            "Provide clear communication about model capabilities and limitations"
        ]
        
        return ethical_risks
    
    def _analyze_model_performance_risks(self):
        """Analyze risks related to model performance"""
        risks = {
            'performance_gaps': [],
            'overfitting_risk': 'UNKNOWN',
            'underfitting_risk': 'UNKNOWN',
            'reliability_score': 0.0,
            'recommendations': []
        }
        
        metrics = self.model_results.get('metrics', {})
        accuracy = metrics.get('accuracy', 0)
        precision = metrics.get('precision', 0)
        recall = metrics.get('recall', 0)
        
        # Check for performance issues
        if accuracy < 0.7:
            risks['performance_gaps'].append("Low overall accuracy - model may not be reliable")
            risks['underfitting_risk'] = 'HIGH'
        
        if precision < 0.6:
            risks['performance_gaps'].append("Low precision - high false positive rate")
        
        if recall < 0.6:
            risks['performance_gaps'].append("Low recall - missing many positive cases")
        
        # Calculate reliability score
        risks['reliability_score'] = (accuracy + precision + recall) / 3
        
        # Recommendations
        if accuracy < 0.7:
            risks['recommendations'].append("Consider more complex models or feature engineering")
            risks['recommendations'].append("Collect more training data")
        
        if precision < 0.6 or recall < 0.6:
            risks['recommendations'].append("Adjust classification threshold")
            risks['recommendations'].append("Address class imbalance")
        
        risks['recommendations'].append("Implement continuous monitoring of model performance")
        risks['recommendations'].append("Set up alerts for performance degradation")
        
        return risks
    
    def _analyze_compliance_risks(self):
        """Analyze regulatory compliance risks"""
        risks = {
            'regulatory_frameworks': [],
            'compliance_gaps': [],
            'audit_readiness': 'LOW',
            'documentation_completeness': 0.0,
            'recommendations': []
        }
        
        # Identify applicable frameworks
        risks['regulatory_frameworks'] = [
            'GDPR (General Data Protection Regulation)',
            'CCPA (California Consumer Privacy Act)',
            'AI Act (EU)',
            'Fair Credit Reporting Act (if applicable)'
        ]
        
        # Identify compliance gaps
        privacy_risks = self.results.get('privacy_risks', {}) if 'privacy_risks' in self.results else {}
        
        if len(privacy_risks.get('pii_detected', [])) > 0:
            risks['compliance_gaps'].append("Unprotected PII may violate GDPR/CCPA requirements")
        
        if len(self.bias_results.get('fairness_violations', [])) > 0:
            risks['compliance_gaps'].append("Fairness violations may violate anti-discrimination laws")
        
        if not privacy_risks.get('gdpr_compliance', {}).get('data_protection_by_design', False):
            risks['compliance_gaps'].append("Lack of privacy by design principles")
        
        # Assess audit readiness
        if len(risks['compliance_gaps']) == 0:
            risks['audit_readiness'] = 'HIGH'
        elif len(risks['compliance_gaps']) <= 2:
            risks['audit_readiness'] = 'MEDIUM'
        else:
            risks['audit_readiness'] = 'LOW'
        
        # Documentation completeness (placeholder - would need more info)
        risks['documentation_completeness'] = 0.4
        
        # Recommendations
        risks['recommendations'] = [
            "Conduct comprehensive privacy impact assessment",
            "Document data lineage and processing activities",
            "Implement data subject rights (access, deletion, portability)",
            "Establish regular compliance audits",
            "Create model cards documenting intended use and limitations",
            "Implement model monitoring and incident response procedures"
        ]
        
        return risks
    
    def _analyze_data_quality_risks(self):
        """Analyze data quality risks"""
        risks = {
            'missing_data': {},
            'data_imbalance': {},
            'outlier_risk': 'UNKNOWN',
            'data_quality_score': 0.0,
            'recommendations': []
        }
        
        # Missing data analysis
        missing_counts = self.df.isnull().sum()
        missing_pct = (missing_counts / len(self.df)) * 100
        
        for col in self.df.columns:
            if missing_pct[col] > 5:
                risks['missing_data'][col] = {
                    'count': int(missing_counts[col]),
                    'percentage': float(missing_pct[col])
                }
        
        # Class imbalance
        if self.target_column in self.df.columns:
            target_dist = self.df[self.target_column].value_counts()
            imbalance_ratio = target_dist.max() / target_dist.min() if len(target_dist) > 1 else 1.0
            
            risks['data_imbalance'] = {
                'ratio': float(imbalance_ratio),
                'distribution': target_dist.to_dict(),
                'severe': imbalance_ratio > 5
            }
        
        # Calculate data quality score
        missing_score = 1.0 - (len(risks['missing_data']) / len(self.df.columns))
        imbalance_score = 1.0 / (1.0 + np.log1p(risks['data_imbalance'].get('ratio', 1) - 1))
        risks['data_quality_score'] = (missing_score + imbalance_score) / 2
        
        # Recommendations
        if len(risks['missing_data']) > 0:
            risks['recommendations'].append("Address missing data through imputation or removal")
        
        if risks['data_imbalance'].get('severe', False):
            risks['recommendations'].append("Use resampling techniques (SMOTE) to address class imbalance")
            risks['recommendations'].append("Consider adjusting class weights in model training")
        
        risks['recommendations'].append("Implement data validation pipelines")
        risks['recommendations'].append("Monitor data drift over time")
        
        return risks
    
    def _aggregate_risk_categories(self):
        """Aggregate risks into categories with scores"""
        categories = {}
        
        # Privacy risks
        privacy = self.results.get('privacy_risks', {})
        privacy_score = self._calculate_privacy_risk_score(privacy)
        categories['privacy_risks'] = {
            'score': privacy_score,
            'level': self._score_to_level(privacy_score),
            'issues': [
                f"{len(privacy['pii_detected'])} PII columns detected",
                f"Anonymization level: {privacy['anonymization_level']}"
            ],
            'recommendations': privacy['recommendations'][:3]
        }
        
        # Ethical risks
        ethical = self.results.get('ethical_risks', {})
        ethical_score = self._calculate_ethical_risk_score(ethical)
        categories['ethical_risks'] = {
            'score': ethical_score,
            'level': self._score_to_level(ethical_score),
            'issues': ethical['fairness_issues'][:3],
            'recommendations': ethical['recommendations'][:3]
        }
        
        # Model performance risks
        performance = self.results.get('model_performance_risks', {})
        performance_score = 1.0 - performance.get('reliability_score', 0.5)
        categories['model_performance_risks'] = {
            'score': performance_score,
            'level': self._score_to_level(performance_score),
            'issues': performance['performance_gaps'],
            'recommendations': performance['recommendations'][:3]
        }
        
        # Compliance risks
        compliance = self.results.get('compliance_risks', {})
        compliance_score = len(compliance['compliance_gaps']) / 10.0
        categories['compliance_risks'] = {
            'score': min(compliance_score, 1.0),
            'level': self._score_to_level(min(compliance_score, 1.0)),
            'issues': compliance['compliance_gaps'],
            'recommendations': compliance['recommendations'][:3]
        }
        
        # Data quality risks
        data_quality = self.results.get('data_quality_risks', {})
        data_quality_score = 1.0 - data_quality.get('data_quality_score', 0.5)
        categories['data_quality_risks'] = {
            'score': data_quality_score,
            'level': self._score_to_level(data_quality_score),
            'issues': [
                f"{len(data_quality['missing_data'])} columns with missing data",
                f"Class imbalance ratio: {data_quality['data_imbalance'].get('ratio', 1):.2f}"
            ],
            'recommendations': data_quality['recommendations'][:3]
        }
        
        return categories
    
    def _calculate_privacy_risk_score(self, privacy_risks):
        """Calculate privacy risk score (0-1, higher is worse)"""
        pii_count = len(privacy_risks.get('pii_detected', []))
        pii_score = min(pii_count / 10, 1.0)
        
        anon_level = privacy_risks.get('anonymization_level', 'NONE')
        anon_score = {'FULL': 0.0, 'PARTIAL': 0.5, 'NONE': 1.0}.get(anon_level, 0.5)
        
        gdpr_score = 1.0 - privacy_risks.get('gdpr_compliance', {}).get('compliance_score', 0)
        
        return (pii_score * 0.4 + anon_score * 0.3 + gdpr_score * 0.3)
    
    def _calculate_ethical_risk_score(self, ethical_risks):
        """Calculate ethical risk score (0-1, higher is worse)"""
        fairness_score = len(ethical_risks.get('fairness_issues', [])) / 10
        transparency_score = 1.0 - ethical_risks.get('transparency_score', 0.5)
        bias_amp = ethical_risks.get('bias_amplification_risk', 'MEDIUM')
        bias_score = {'LOW': 0.2, 'MEDIUM': 0.5, 'HIGH': 0.9}.get(bias_amp, 0.5)
        
        return (fairness_score * 0.4 + transparency_score * 0.3 + bias_score * 0.3)
    
    def _calculate_overall_risk_score(self):
        """Calculate overall risk score"""
        category_scores = []
        
        for category, details in self.results.get('risk_categories', {}).items():
            category_scores.append(details['score'])
        
        overall = np.mean(category_scores) if category_scores else 0.5
        return float(min(overall, 1.0))
    
    def _determine_risk_level(self):
        """Determine overall risk level"""
        score = self.results.get('overall_risk_score', 0.5)
        return self._score_to_level(score)
    
    def _score_to_level(self, score):
        """Convert score to risk level"""
        if score >= 0.7:
            return 'HIGH'
        elif score >= 0.4:
            return 'MEDIUM'
        else:
            return 'LOW'
