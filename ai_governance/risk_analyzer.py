"""
Enhanced Risk Analyzer Module - Presidio-Powered
Comprehensive privacy, security, and ethical risk assessment
"""

import pandas as pd
import numpy as np
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import defaultdict

# Presidio imports
try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    PRESIDIO_AVAILABLE = True
except ImportError:
    PRESIDIO_AVAILABLE = False
    print("⚠️  Presidio not available. Install with: pip install presidio-analyzer")


class RiskAnalyzer:
    """Comprehensive risk analysis with Presidio-enhanced PII detection"""
    
    # Class-level cache for Presidio analyzer
    _presidio_analyzer = None
    _presidio_initialized = False
    _presidio_init_failed = False
    
    def __init__(self, df, model_results, bias_results, protected_attributes, target_column, use_presidio=False):
        self.df = df
        self.model_results = model_results
        self.bias_results = bias_results
        self.protected_attributes = protected_attributes
        self.target_column = target_column
        self.results = {}
        self.use_presidio = use_presidio
        
        # Initialize Presidio only if requested and not already failed
        if self.use_presidio and PRESIDIO_AVAILABLE and not RiskAnalyzer._presidio_init_failed:
            if not RiskAnalyzer._presidio_initialized:
                self._init_presidio()
            self.analyzer = RiskAnalyzer._presidio_analyzer
        else:
            self.analyzer = None
    
    def _init_presidio(self):
        """Initialize Presidio analyzer (cached at class level)"""
        try:
            print("⏳ Initializing Presidio for risk analysis...")
            
            # Check if spaCy and model are available
            try:
                import spacy
                
                # Check if model exists WITHOUT loading it
                model_name = "en_core_web_sm"
                if not spacy.util.is_package(model_name):
                    print(f"⚠️  spaCy model '{model_name}' not found.")
                    print(f"   To enable Presidio, install the model with:")
                    print(f"   python -m spacy download {model_name}")
                    print("   Continuing with regex-only PII detection...")
                    RiskAnalyzer._presidio_init_failed = True
                    return
                
                # Model exists, now load it
                print(f"✓ spaCy model '{model_name}' found, loading...")
                nlp = spacy.load(model_name)
                
            except ImportError:
                print("⚠️  spaCy not installed. Continuing with regex-only detection...")
                print("   Install spaCy with: pip install spacy")
                RiskAnalyzer._presidio_init_failed = True
                return
            except Exception as e:
                print(f"⚠️  Error loading spaCy model: {e}")
                print("   Continuing with regex-only PII detection...")
                RiskAnalyzer._presidio_init_failed = True
                return
            
            # Create NLP engine configuration (prevent auto-download)
            from presidio_analyzer.nlp_engine import NlpEngineProvider
            
            configuration = {
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": model_name}],
            }
            
            provider = NlpEngineProvider(nlp_configuration=configuration)
            nlp_engine = provider.create_engine()
            
            # Initialize analyzer
            RiskAnalyzer._presidio_analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
            RiskAnalyzer._presidio_initialized = True
            print("✓ Presidio initialized for risk analysis")
            
        except Exception as e:
            print(f"⚠️  Could not initialize Presidio: {e}")
            print("   Continuing with regex-only PII detection...")
            RiskAnalyzer._presidio_init_failed = True
            RiskAnalyzer._presidio_analyzer = None
    
    # Enhanced PII patterns for fallback regex detection
    PII_PATTERNS = {
        'EMAIL': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'PHONE_US': r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b',
        'PHONE_INTERNATIONAL': r'\+\d{1,3}[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}',
        'SSN': r'\b\d{3}-\d{2}-\d{4}\b',
        'CREDIT_CARD': r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
        'IP_ADDRESS': r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        'MAC_ADDRESS': r'\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b',
        'US_ADDRESS': r'\b\d{1,5}\s+[\w\s]+(?:street|st|avenue|ave|road|rd|highway|hwy)\b',
        'ZIP_CODE': r'\b\d{5}(?:-\d{4})?\b',
        'DATE_OF_BIRTH': r'\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b',
        'PASSPORT': r'\b[A-Z]{1,2}\d{6,9}\b',
        'DRIVERS_LICENSE': r'\b[A-Z]{1,2}\d{6,8}\b',
        'BANK_ACCOUNT': r'\b\d{8,17}\b',
        'ROUTING_NUMBER': r'\b[0-9]{9}\b',
        'MEDICAL_RECORD': r'\b(?:MRN|MR#)[\s:]*[A-Z0-9]{6,12}\b',
    }
    
    # Presidio entity types to detect
    PRESIDIO_ENTITIES = [
        'CREDIT_CARD', 'CRYPTO', 'EMAIL_ADDRESS', 'IBAN_CODE', 
        'IP_ADDRESS', 'LOCATION', 'PERSON', 'PHONE_NUMBER',
        'MEDICAL_LICENSE', 'US_BANK_NUMBER', 'US_DRIVER_LICENSE',
        'US_ITIN', 'US_PASSPORT', 'US_SSN', 'UK_NHS',
        'SG_NRIC_FIN', 'AU_ABN', 'AU_ACN', 'AU_TFN', 'AU_MEDICARE'
    ]
    
    def analyze(self):
        """Perform comprehensive risk analysis with Presidio integration"""
        print("\n" + "=" * 70)
        print("COMPREHENSIVE RISK ANALYSIS WITH PRESIDIO")
        print("=" * 70)
        
        # Enhanced risk analysis
        privacy_risks = self._analyze_privacy_risks_enhanced()
        ethical_risks = self._analyze_ethical_risks_enhanced()
        compliance_risks = self._analyze_compliance_risks_enhanced()
        security_risks = self._analyze_security_risks()
        operational_risks = self._analyze_operational_risks()
        data_quality_risks = self._analyze_data_quality_risks_enhanced()
        
        # Calculate category scores
        category_scores = {
            'privacy': privacy_risks.get('risk_score', 0.0),
            'ethical': ethical_risks.get('risk_score', 0.0),
            'compliance': compliance_risks.get('risk_score', 0.0),
            'security': security_risks.get('risk_score', 0.0),
            'operational': operational_risks.get('risk_score', 0.0),
            'data_quality': data_quality_risks.get('risk_score', 0.0)
        }
        
        # Calculate weighted overall risk
        overall_risk_score = self._calculate_weighted_risk_score(category_scores)
        risk_level = self._classify_risk_level(overall_risk_score)
        
        # Detect violations
        violations = self._detect_all_violations(
            privacy_risks, ethical_risks, compliance_risks,
            security_risks, operational_risks, data_quality_risks
        )
        
        # Generate insights
        insights = self._generate_risk_insights(
            category_scores, violations, privacy_risks, ethical_risks
        )
        
        self.results = {
            'privacy_risks': privacy_risks,
            'ethical_risks': ethical_risks,
            'model_performance_risks': self._analyze_model_performance_risks(),
            'compliance_risks': compliance_risks,
            'data_quality_risks': data_quality_risks,
            'security_risks': security_risks,
            'operational_risks': operational_risks,
            'risk_categories': category_scores,
            'overall_risk_score': overall_risk_score,
            'risk_level': risk_level,
            'violations': violations,
            'insights': insights,
            'timestamp': datetime.now().isoformat(),
            'presidio_enabled': self.analyzer is not None
        }
        
        self._print_risk_summary()
        return self.results
    
    def _analyze_privacy_risks_enhanced(self):
        """Enhanced privacy analysis with Presidio"""
        print("⏳ Analyzing privacy risks...")
        
        # Detect PII using Presidio and/or regex
        pii_detections = self._detect_pii_comprehensive()
        
        # Calculate re-identification risk
        reidentification_risk = self._calculate_reidentification_risk(pii_detections)
        
        # Analyze data minimization
        data_minimization_score = self._analyze_data_minimization()
        
        # Check anonymization techniques
        anonymization_level = self._assess_anonymization(pii_detections)
        
        # Group-level privacy risk
        group_privacy_risks = self._analyze_group_privacy_risks(pii_detections)
        
        # Calculate overall privacy risk score
        pii_count = len(pii_detections)
        pii_risk = min(pii_count * 0.1, 1.0)  # 0.1 per PII type, capped at 1.0
        
        privacy_risk_score = (
            pii_risk * 0.4 +
            reidentification_risk * 0.3 +
            (1 - data_minimization_score) * 0.2 +
            (1 if anonymization_level == 'NONE' else 0.5 if anonymization_level == 'PARTIAL' else 0) * 0.1
        )
        
        return {
            'risk_score': privacy_risk_score,
            'pii_detected': pii_detections,
            'pii_count': pii_count,
            'reidentification_risk': reidentification_risk,
            'data_minimization_score': data_minimization_score,
            'anonymization_level': anonymization_level,
            'group_privacy_risks': group_privacy_risks,
            'sensitive_attributes': self.protected_attributes,
            'detection_method': 'Presidio' if self.analyzer else 'Regex',
            'recommendations': self._generate_privacy_recommendations(
                pii_detections, reidentification_risk, anonymization_level
            )
        }
    
    def _detect_pii_comprehensive(self):
        """Comprehensive PII detection using Presidio + regex"""
        pii_detections = []
        detected_types = set()
        
        for col in self.df.columns:
            col_lower = col.lower()
            
            # Column name-based detection
            column_pii = self._detect_pii_from_column_name(col, col_lower)
            if column_pii:
                pii_type = column_pii['type']
                if pii_type not in detected_types:
                    pii_detections.append(column_pii)
                    detected_types.add(pii_type)
            
            # Content-based detection with Presidio
            if self.analyzer and self.df[col].dtype == 'object':
                content_pii = self._detect_pii_with_presidio(col)
                for pii in content_pii:
                    if pii['type'] not in detected_types:
                        pii_detections.append(pii)
                        detected_types.add(pii['type'])
            
            # Regex fallback for content
            elif self.df[col].dtype == 'object':
                regex_pii = self._detect_pii_with_regex(col)
                for pii in regex_pii:
                    if pii['type'] not in detected_types:
                        pii_detections.append(pii)
                        detected_types.add(pii['type'])
        
        return sorted(pii_detections, key=lambda x: x['severity'], reverse=True)
    
    def _detect_pii_from_column_name(self, col, col_lower):
        """Detect PII from column names"""
        name_patterns = {
            'EMAIL': ['email', 'e-mail', 'mail'],
            'PHONE': ['phone', 'mobile', 'tel', 'telephone'],
            'SSN': ['ssn', 'social security', 'social_security'],
            'ADDRESS': ['address', 'street', 'location', 'residence'],
            'ZIP_CODE': ['zip', 'postal', 'postcode'],
            'NAME': ['name', 'firstname', 'lastname', 'fullname'],
            'DOB': ['dob', 'birth', 'birthday', 'dateofbirth'],
            'ID': ['id', 'identifier', 'userid', 'user_id'],
            'IP_ADDRESS': ['ip', 'ipaddress', 'ip_address'],
            'CREDIT_CARD': ['card', 'credit', 'creditcard'],
            'PASSPORT': ['passport'],
            'LICENSE': ['license', 'licence', 'driver'],
            'BANK_ACCOUNT': ['account', 'bank_account', 'banking'],
        }
        
        for pii_type, keywords in name_patterns.items():
            if any(kw in col_lower for kw in keywords):
                severity = self._determine_pii_severity(pii_type)
                return {
                    'column': col,
                    'type': pii_type,
                    'severity': severity,
                    'detection_method': 'column_name',
                    'confidence': 0.9
                }
        return None
    
    def _detect_pii_with_presidio(self, column):
        """Detect PII in column content using Presidio"""
        detections = []
        
        # Sample values from column (max 100 for performance)
        sample_size = min(100, len(self.df))
        samples = self.df[column].dropna().sample(min(sample_size, len(self.df[column].dropna()))).astype(str)
        
        entity_counts = defaultdict(int)
        
        for value in samples:
            if len(str(value)) > 5:  # Skip very short values
                try:
                    results = self.analyzer.analyze(
                        text=str(value),
                        entities=self.PRESIDIO_ENTITIES,
                        language='en'
                    )
                    
                    for result in results:
                        if result.score > 0.5:  # Confidence threshold
                            entity_counts[result.entity_type] += 1
                except Exception as e:
                    continue
        
        # If entity detected in >20% of samples, mark column as PII
        threshold = sample_size * 0.2
        for entity_type, count in entity_counts.items():
            if count > threshold:
                severity = self._determine_pii_severity(entity_type)
                detections.append({
                    'column': column,
                    'type': entity_type,
                    'severity': severity,
                    'detection_method': 'presidio',
                    'confidence': min(count / sample_size, 1.0),
                    'occurrences': count
                })
        
        return detections
    
    def _detect_pii_with_regex(self, column):
        """Fallback PII detection using regex patterns"""
        detections = []
        
        # Sample values
        sample_size = min(100, len(self.df))
        samples = self.df[column].dropna().sample(min(sample_size, len(self.df[column].dropna()))).astype(str)
        
        for pii_type, pattern in self.PII_PATTERNS.items():
            matches = 0
            for value in samples:
                if re.search(pattern, str(value), re.IGNORECASE):
                    matches += 1
            
            # If pattern matches >15% of samples, mark as PII
            if matches > sample_size * 0.15:
                severity = self._determine_pii_severity(pii_type)
                detections.append({
                    'column': column,
                    'type': pii_type,
                    'severity': severity,
                    'detection_method': 'regex',
                    'confidence': min(matches / sample_size, 1.0),
                    'occurrences': matches
                })
        
        return detections
    
    def _determine_pii_severity(self, pii_type):
        """Determine severity level for PII type"""
        critical = ['SSN', 'US_SSN', 'CREDIT_CARD', 'US_BANK_NUMBER', 'PASSPORT', 
                   'US_PASSPORT', 'MEDICAL_LICENSE', 'MEDICAL_RECORD', 'CRYPTO']
        high = ['EMAIL_ADDRESS', 'PHONE_NUMBER', 'US_DRIVER_LICENSE', 'BANK_ACCOUNT',
               'IBAN_CODE', 'UK_NHS', 'AU_TFN', 'AU_MEDICARE']
        medium = ['PERSON', 'LOCATION', 'IP_ADDRESS', 'ADDRESS', 'DOB']
        
        pii_upper = pii_type.upper()
        if pii_upper in critical or any(c in pii_upper for c in critical):
            return 'CRITICAL'
        elif pii_upper in high or any(h in pii_upper for h in high):
            return 'HIGH'
        elif pii_upper in medium or any(m in pii_upper for m in medium):
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def _calculate_reidentification_risk(self, pii_detections):
        """Calculate risk of re-identifying individuals"""
        # Count quasi-identifiers
        quasi_identifiers = ['AGE', 'ZIP_CODE', 'GENDER', 'DOB', 'LOCATION']
        quasi_id_count = sum(1 for pii in pii_detections 
                            if any(qi in pii['type'].upper() for qi in quasi_identifiers))
        
        # Direct identifiers
        direct_identifiers = ['SSN', 'EMAIL', 'PHONE', 'NAME', 'PASSPORT']
        direct_id_count = sum(1 for pii in pii_detections
                             if any(di in pii['type'].upper() for di in direct_identifiers))
        
        # Calculate risk
        if direct_id_count > 0:
            return 1.0  # Very high risk with direct identifiers
        elif quasi_id_count >= 3:
            return 0.8  # High risk with multiple quasi-identifiers
        elif quasi_id_count >= 2:
            return 0.5  # Medium risk
        elif quasi_id_count >= 1:
            return 0.3  # Low-medium risk
        else:
            return 0.1  # Low risk
    
    def _analyze_data_minimization(self):
        """Assess if data collection follows minimization principle"""
        total_columns = len(self.df.columns)
        # Assume target + 1-2 protected attributes + 5-10 features is reasonable
        expected_min = 7
        expected_max = 15
        
        if total_columns <= expected_max:
            score = 1.0
        elif total_columns <= expected_max * 1.5:
            score = 0.7
        elif total_columns <= expected_max * 2:
            score = 0.4
        else:
            score = 0.2
        
        return score
    
    def _assess_anonymization(self, pii_detections):
        """Assess anonymization level"""
        critical_pii = [p for p in pii_detections if p['severity'] == 'CRITICAL']
        high_pii = [p for p in pii_detections if p['severity'] == 'HIGH']
        
        if len(critical_pii) > 0:
            return 'NONE'
        elif len(high_pii) > 2:
            return 'NONE'
        elif len(pii_detections) > 5:
            return 'PARTIAL'
        elif len(pii_detections) > 0:
            return 'PARTIAL'
        else:
            return 'FULL'
    
    def _analyze_group_privacy_risks(self, pii_detections):
        """Analyze privacy risks per demographic group"""
        group_risks = []
        
        for attr in self.protected_attributes:
            if attr in self.df.columns:
                groups = self.df[attr].unique()
                for group in groups:
                    if pd.notna(group):
                        group_size = len(self.df[self.df[attr] == group])
                        
                        # K-anonymity check: groups with <5 members at high risk
                        if group_size < 5:
                            group_risks.append({
                                'attribute': attr,
                                'group': str(group),
                                'size': int(group_size),
                                'risk': 'CRITICAL',
                                'issue': f'Group too small (n={group_size}) - re-identification risk'
                            })
                        elif group_size < 10:
                            group_risks.append({
                                'attribute': attr,
                                'group': str(group),
                                'size': int(group_size),
                                'risk': 'HIGH',
                                'issue': f'Small group size (n={group_size}) - elevated privacy risk'
                            })
        
        return group_risks
    
    def _generate_privacy_recommendations(self, pii_detections, reidentification_risk, anonymization_level):
        """Generate privacy recommendations"""
        recommendations = []
        
        if anonymization_level == 'NONE':
            recommendations.append({
                'priority': 'CRITICAL',
                'recommendation': 'Implement data anonymization techniques (k-anonymity, l-diversity, t-closeness)',
                'rationale': 'High volume of PII detected without anonymization'
            })
        
        if reidentification_risk > 0.7:
            recommendations.append({
                'priority': 'CRITICAL',
                'recommendation': 'Remove or hash direct identifiers (SSN, email, phone numbers)',
                'rationale': 'High re-identification risk from direct identifiers'
            })
            recommendations.append({
                'priority': 'HIGH',
                'recommendation': 'Apply differential privacy techniques to protect individual records',
                'rationale': 'Prevent inference attacks on individual data points'
            })
        
        critical_pii = [p for p in pii_detections if p['severity'] == 'CRITICAL']
        if len(critical_pii) > 0:
            recommendations.append({
                'priority': 'CRITICAL',
                'recommendation': f"Remove or encrypt critical PII: {', '.join(set(p['type'] for p in critical_pii))}",
                'rationale': 'Critical PII types detected that pose severe privacy risks'
            })
        
        recommendations.append({
            'priority': 'HIGH',
            'recommendation': 'Implement data encryption at rest and in transit',
            'rationale': 'Protect sensitive data from unauthorized access'
        })
        
        recommendations.append({
            'priority': 'MEDIUM',
            'recommendation': 'Establish data retention and deletion policies',
            'rationale': 'Minimize privacy risk by limiting data lifecycle'
        })
        
        recommendations.append({
            'priority': 'MEDIUM',
            'recommendation': 'Conduct regular privacy impact assessments (PIA)',
            'rationale': 'Continuous monitoring of privacy risks'
        })
        
        return recommendations
    
    def _analyze_ethical_risks_enhanced(self):
        """Enhanced ethical risk analysis"""
        print("⏳ Analyzing ethical risks...")
        
        # Extract bias information
        bias_score = self.bias_results.get('overall_bias_score', 0.0)
        fairness_violations = self.bias_results.get('fairness_violations', [])
        
        # Transparency assessment
        transparency_score = self._assess_transparency()
        
        # Accountability measures
        accountability_score = self._assess_accountability()
        
        # Autonomy and consent
        autonomy_score = self._assess_autonomy()
        
        # Social impact
        social_impact_risk = self._assess_social_impact(bias_score)
        
        # Calculate ethical risk score
        ethical_risk_score = (
            bias_score * 0.35 +  # Fairness is most important
            (1 - transparency_score) * 0.25 +
            (1 - accountability_score) * 0.20 +
            (1 - autonomy_score) * 0.10 +
            social_impact_risk * 0.10
        )
        
        return {
            'risk_score': ethical_risk_score,
            'fairness_issues': fairness_violations,
            'bias_score': bias_score,
            'transparency_score': transparency_score,
            'accountability_score': accountability_score,
            'autonomy_score': autonomy_score,
            'social_impact_risk': social_impact_risk,
            'affected_groups': self.protected_attributes,
            'recommendations': self._generate_ethical_recommendations(
                bias_score, transparency_score, accountability_score
            )
        }
    
    def _assess_transparency(self):
        """Assess model transparency"""
        model_type = self.model_results.get('model_type', 'Unknown')
        
        # Interpretable models
        if model_type in ['LogisticRegression', 'DecisionTreeClassifier', 'LinearRegression']:
            return 0.9
        # Partially interpretable
        elif model_type in ['RandomForestClassifier', 'GradientBoostingClassifier', 'XGBClassifier']:
            return 0.6
        # Black box models
        elif model_type in ['MLPClassifier', 'SVC', 'KNeighborsClassifier']:
            return 0.3
        else:
            return 0.5
    
    def _assess_accountability(self):
        """Assess accountability measures"""
        # This would check for logging, versioning, audit trails
        # For now, return moderate score
        return 0.6
    
    def _assess_autonomy(self):
        """Assess respect for autonomy and consent"""
        # Would check for consent mechanisms, opt-out options
        # For now, return moderate score
        return 0.5
    
    def _assess_social_impact(self, bias_score):
        """Assess potential social impact"""
        # High bias = high social impact risk
        if bias_score > 0.7:
            return 0.9
        elif bias_score > 0.5:
            return 0.7
        elif bias_score > 0.3:
            return 0.4
        else:
            return 0.2
    
    def _generate_ethical_recommendations(self, bias_score, transparency_score, accountability_score):
        """Generate ethical recommendations"""
        recommendations = []
        
        if bias_score > 0.5:
            recommendations.append({
                'priority': 'CRITICAL',
                'recommendation': 'Address fairness violations immediately - implement bias mitigation techniques',
                'rationale': f'High bias score ({bias_score:.1%}) indicates significant fairness issues'
            })
        
        if transparency_score < 0.5:
            recommendations.append({
                'priority': 'HIGH',
                'recommendation': 'Implement explainable AI techniques (SHAP, LIME) for model interpretability',
                'rationale': 'Low transparency score - users cannot understand model decisions'
            })
        
        if accountability_score < 0.6:
            recommendations.append({
                'priority': 'HIGH',
                'recommendation': 'Establish model governance framework with versioning, logging, and audit trails',
                'rationale': 'Insufficient accountability mechanisms in place'
            })
        
        recommendations.append({
            'priority': 'MEDIUM',
            'recommendation': 'Create ethics review board for model deployment and monitoring',
            'rationale': 'Ensure ongoing ethical oversight'
        })
        
        recommendations.append({
            'priority': 'MEDIUM',
            'recommendation': 'Implement feedback mechanisms for affected individuals',
            'rationale': 'Allow users to contest decisions and provide input'
        })
        
        return recommendations
    
    def _analyze_compliance_risks_enhanced(self):
        """Enhanced compliance risk analysis"""
        print("⏳ Analyzing compliance risks...")
        
        # GDPR compliance
        gdpr_compliance = self._assess_gdpr_compliance()
        
        # CCPA compliance
        ccpa_compliance = self._assess_ccpa_compliance()
        
        # HIPAA (if healthcare data)
        hipaa_compliance = self._assess_hipaa_compliance()
        
        # Equal Credit Opportunity Act (if credit/lending)
        ecoa_compliance = self._assess_ecoa_compliance()
        
        # Calculate compliance risk score
        compliance_scores = [
            gdpr_compliance['score'],
            ccpa_compliance['score'],
            hipaa_compliance['score'],
            ecoa_compliance['score']
        ]
        compliance_risk_score = 1 - (sum(compliance_scores) / len(compliance_scores))
        
        return {
            'risk_score': compliance_risk_score,
            'gdpr': gdpr_compliance,
            'ccpa': ccpa_compliance,
            'hipaa': hipaa_compliance,
            'ecoa': ecoa_compliance,
            'recommendations': self._generate_compliance_recommendations(
                gdpr_compliance, ccpa_compliance, hipaa_compliance, ecoa_compliance
            )
        }
    
    def _assess_gdpr_compliance(self):
        """Assess GDPR compliance"""
        checks = {
            'data_minimization': len(self.df.columns) < 20,  # Simplified check
            'purpose_limitation': False,  # Cannot determine from data
            'storage_limitation': False,  # Cannot determine
            'right_to_access': True,  # Data is accessible
            'right_to_erasure': False,  # Cannot determine
            'data_portability': True,  # CSV format
            'consent': False,  # Cannot determine
        }
        
        score = sum(checks.values()) / len(checks)
        issues = [k for k, v in checks.items() if not v]
        
        return {
            'score': score,
            'compliant_checks': [k for k, v in checks.items() if v],
            'non_compliant_checks': issues,
            'status': 'COMPLIANT' if score > 0.7 else 'PARTIAL' if score > 0.4 else 'NON_COMPLIANT'
        }
    
    def _assess_ccpa_compliance(self):
        """Assess CCPA compliance"""
        checks = {
            'notice_at_collection': False,
            'right_to_know': True,
            'right_to_delete': False,
            'right_to_opt_out': False,
            'non_discrimination': True
        }
        
        score = sum(checks.values()) / len(checks)
        
        return {
            'score': score,
            'compliant_checks': [k for k, v in checks.items() if v],
            'non_compliant_checks': [k for k, v in checks.items() if not v],
            'status': 'COMPLIANT' if score > 0.7 else 'PARTIAL' if score > 0.4 else 'NON_COMPLIANT'
        }
    
    def _assess_hipaa_compliance(self):
        """Assess HIPAA compliance (if healthcare data)"""
        # Check for health-related PII
        health_indicators = ['medical', 'health', 'diagnosis', 'treatment', 'prescription', 'mrn']
        has_health_data = any(any(ind in col.lower() for ind in health_indicators) for col in self.df.columns)
        
        if not has_health_data:
            return {'score': 1.0, 'applicable': False, 'status': 'NOT_APPLICABLE'}
        
        checks = {
            'encryption': False,
            'access_controls': False,
            'audit_trails': False,
            'breach_notification': False
        }
        
        score = sum(checks.values()) / len(checks)
        
        return {
            'score': score,
            'applicable': True,
            'compliant_checks': [k for k, v in checks.items() if v],
            'non_compliant_checks': [k for k, v in checks.items() if not v],
            'status': 'COMPLIANT' if score > 0.7 else 'PARTIAL' if score > 0.4 else 'NON_COMPLIANT'
        }
    
    def _assess_ecoa_compliance(self):
        """Assess Equal Credit Opportunity Act compliance"""
        # Check if this is credit/lending data
        credit_indicators = ['credit', 'loan', 'lending', 'mortgage', 'debt', 'income']
        is_credit_data = any(any(ind in col.lower() for ind in credit_indicators) for col in self.df.columns)
        
        if not is_credit_data:
            return {'score': 1.0, 'applicable': False, 'status': 'NOT_APPLICABLE'}
        
        # Check for prohibited basis discrimination
        bias_score = self.bias_results.get('overall_bias_score', 0.0)
        
        checks = {
            'no_discrimination': bias_score < 0.3,
            'adverse_action_notices': False,  # Cannot determine
            'record_retention': False,  # Cannot determine
            'monitoring': True  # We're doing it now
        }
        
        score = sum(checks.values()) / len(checks)
        
        return {
            'score': score,
            'applicable': True,
            'bias_score': bias_score,
            'compliant_checks': [k for k, v in checks.items() if v],
            'non_compliant_checks': [k for k, v in checks.items() if not v],
            'status': 'COMPLIANT' if score > 0.7 else 'PARTIAL' if score > 0.4 else 'NON_COMPLIANT'
        }
    
    def _generate_compliance_recommendations(self, gdpr, ccpa, hipaa, ecoa):
        """Generate compliance recommendations"""
        recommendations = []
        
        if gdpr['status'] != 'COMPLIANT':
            recommendations.append({
                'priority': 'HIGH',
                'recommendation': f"Address GDPR non-compliance: {', '.join(gdpr['non_compliant_checks'])}",
                'rationale': 'GDPR violations can result in significant fines'
            })
        
        if ccpa['status'] != 'COMPLIANT':
            recommendations.append({
                'priority': 'HIGH',
                'recommendation': f"Address CCPA requirements: {', '.join(ccpa['non_compliant_checks'])}",
                'rationale': 'CCPA compliance required for California residents'
            })
        
        if hipaa.get('applicable') and hipaa['status'] != 'COMPLIANT':
            recommendations.append({
                'priority': 'CRITICAL',
                'recommendation': f"Implement HIPAA safeguards: {', '.join(hipaa['non_compliant_checks'])}",
                'rationale': 'Healthcare data requires stringent HIPAA protections'
            })
        
        if ecoa.get('applicable') and ecoa['status'] != 'COMPLIANT':
            recommendations.append({
                'priority': 'CRITICAL',
                'recommendation': 'Address discriminatory patterns in credit decisions',
                'rationale': 'ECOA violations in lending can result in legal action'
            })
        
        return recommendations
    
    def _analyze_security_risks(self):
        """Analyze security risks"""
        print("⏳ Analyzing security risks...")
        
        # Adversarial attack vulnerability
        model_vulnerability = self._assess_adversarial_vulnerability()
        
        # Data poisoning risk
        poisoning_risk = self._assess_data_poisoning_risk()
        
        # Model extraction risk
        extraction_risk = self._assess_model_extraction_risk()
        
        # Membership inference risk
        membership_risk = self._assess_membership_inference_risk()
        
        security_risk_score = (
            model_vulnerability * 0.3 +
            poisoning_risk * 0.25 +
            extraction_risk * 0.25 +
            membership_risk * 0.20
        )
        
        return {
            'risk_score': security_risk_score,
            'adversarial_vulnerability': model_vulnerability,
            'data_poisoning_risk': poisoning_risk,
            'model_extraction_risk': extraction_risk,
            'membership_inference_risk': membership_risk,
            'recommendations': self._generate_security_recommendations(
                model_vulnerability, poisoning_risk
            )
        }
    
    def _assess_adversarial_vulnerability(self):
        """Assess vulnerability to adversarial attacks"""
        model_type = self.model_results.get('model_type', 'Unknown')
        
        # Deep learning models more vulnerable
        if 'Neural' in model_type or 'MLP' in model_type:
            return 0.8
        # Tree-based models more robust
        elif 'Tree' in model_type or 'Forest' in model_type:
            return 0.3
        # Linear models moderately robust
        elif 'Linear' in model_type or 'Logistic' in model_type:
            return 0.5
        else:
            return 0.6
    
    def _assess_data_poisoning_risk(self):
        """Assess risk of data poisoning attacks"""
        # Check data quality indicators
        missing_pct = self.df.isnull().sum().sum() / (len(self.df) * len(self.df.columns))
        
        if missing_pct > 0.2:
            return 0.7  # High missing data = higher risk
        elif missing_pct > 0.1:
            return 0.5
        else:
            return 0.3
    
    def _assess_model_extraction_risk(self):
        """Assess risk of model extraction attacks"""
        # Simple models easier to extract
        model_type = self.model_results.get('model_type', 'Unknown')
        
        if 'Linear' in model_type or 'Logistic' in model_type:
            return 0.7
        elif 'Tree' in model_type:
            return 0.6
        else:
            return 0.5
    
    def _assess_membership_inference_risk(self):
        """Assess membership inference attack risk"""
        # Models that overfit are more vulnerable
        train_acc = self.model_results.get('train_accuracy', 0)
        test_acc = self.model_results.get('accuracy', 0)
        
        if train_acc - test_acc > 0.15:  # Overfitting
            return 0.8
        elif train_acc - test_acc > 0.10:
            return 0.6
        else:
            return 0.4
    
    def _generate_security_recommendations(self, adversarial_vuln, poisoning_risk):
        """Generate security recommendations"""
        recommendations = []
        
        if adversarial_vuln > 0.6:
            recommendations.append({
                'priority': 'HIGH',
                'recommendation': 'Implement adversarial training and input validation',
                'rationale': 'Model vulnerable to adversarial attacks'
            })
        
        if poisoning_risk > 0.6:
            recommendations.append({
                'priority': 'HIGH',
                'recommendation': 'Implement data validation and anomaly detection in training pipeline',
                'rationale': 'Training data vulnerable to poisoning attacks'
            })
        
        recommendations.append({
            'priority': 'MEDIUM',
            'recommendation': 'Implement model access controls and rate limiting',
            'rationale': 'Prevent model extraction attacks'
        })
        
        recommendations.append({
            'priority': 'MEDIUM',
            'recommendation': 'Add differential privacy to model training',
            'rationale': 'Protect against membership inference attacks'
        })
        
        return recommendations
    
    def _analyze_operational_risks(self):
        """Analyze operational risks"""
        print("⏳ Analyzing operational risks...")
        
        # Model performance degradation risk
        performance_risk = self._assess_performance_degradation_risk()
        
        # Data drift risk
        drift_risk = self._assess_data_drift_risk()
        
        # Scalability risk
        scalability_risk = self._assess_scalability_risk()
        
        operational_risk_score = (
            performance_risk * 0.4 +
            drift_risk * 0.4 +
            scalability_risk * 0.2
        )
        
        return {
            'risk_score': operational_risk_score,
            'performance_degradation_risk': performance_risk,
            'data_drift_risk': drift_risk,
            'scalability_risk': scalability_risk,
            'recommendations': self._generate_operational_recommendations()
        }
    
    def _assess_performance_degradation_risk(self):
        """Assess risk of performance degradation over time"""
        # Check model accuracy
        accuracy = self.model_results.get('accuracy', 0)
        
        if accuracy < 0.7:
            return 0.8  # Already low performance
        elif accuracy < 0.8:
            return 0.5
        else:
            return 0.3
    
    def _assess_data_drift_risk(self):
        """Assess risk of data drift"""
        # Would need historical data for proper assessment
        # For now, return moderate risk
        return 0.5
    
    def _assess_scalability_risk(self):
        """Assess scalability risk"""
        model_type = self.model_results.get('model_type', 'Unknown')
        dataset_size = len(self.df)
        
        # KNN doesn't scale well
        if 'KNeighbors' in model_type:
            return 0.7
        # Tree-based scale reasonably
        elif 'Tree' in model_type or 'Forest' in model_type:
            return 0.4
        # Linear models scale well
        elif 'Linear' in model_type or 'Logistic' in model_type:
            return 0.2
        else:
            return 0.5
    
    def _generate_operational_recommendations(self):
        """Generate operational recommendations"""
        return [
            {
                'priority': 'HIGH',
                'recommendation': 'Implement continuous monitoring for model performance and data drift',
                'rationale': 'Detect degradation early'
            },
            {
                'priority': 'MEDIUM',
                'recommendation': 'Establish model retraining pipeline and schedule',
                'rationale': 'Maintain model accuracy over time'
            },
            {
                'priority': 'MEDIUM',
                'recommendation': 'Set up alerting for performance drops below threshold',
                'rationale': 'Enable rapid response to issues'
            }
        ]
    
    def _analyze_data_quality_risks_enhanced(self):
        """Enhanced data quality risk analysis"""
        print("⏳ Analyzing data quality risks...")
        
        # Missing data
        missing_pct = self.df.isnull().sum().sum() / (len(self.df) * len(self.df.columns))
        
        # Data completeness
        completeness_score = 1 - missing_pct
        
        # Data consistency
        consistency_score = self._assess_data_consistency()
        
        # Data accuracy proxy
        accuracy_score = self._assess_data_accuracy()
        
        # Sample size adequacy
        sample_size_score = self._assess_sample_size()
        
        data_quality_risk_score = (
            (1 - completeness_score) * 0.3 +
            (1 - consistency_score) * 0.25 +
            (1 - accuracy_score) * 0.25 +
            (1 - sample_size_score) * 0.20
        )
        
        return {
            'risk_score': data_quality_risk_score,
            'completeness_score': completeness_score,
            'consistency_score': consistency_score,
            'accuracy_score': accuracy_score,
            'sample_size_score': sample_size_score,
            'missing_percentage': missing_pct,
            'total_records': len(self.df),
            'recommendations': self._generate_data_quality_recommendations(
                completeness_score, consistency_score, sample_size_score
            )
        }
    
    def _assess_data_consistency(self):
        """Assess data consistency"""
        inconsistencies = 0
        total_checks = 0
        
        for col in self.df.select_dtypes(include=['object']).columns:
            total_checks += 1
            unique_count = self.df[col].nunique()
            total_count = len(self.df[col].dropna())
            
            # High cardinality in categorical = potential inconsistency
            if total_count > 0 and unique_count / total_count > 0.8:
                inconsistencies += 1
        
        if total_checks == 0:
            return 1.0
        
        return 1 - (inconsistencies / total_checks)
    
    def _assess_data_accuracy(self):
        """Assess data accuracy (proxy measures)"""
        accuracy_indicators = []
        
        # Check for outliers in numerical columns
        for col in self.df.select_dtypes(include=[np.number]).columns:
            Q1 = self.df[col].quantile(0.25)
            Q3 = self.df[col].quantile(0.75)
            IQR = Q3 - Q1
            outliers = ((self.df[col] < (Q1 - 3 * IQR)) | (self.df[col] > (Q3 + 3 * IQR))).sum()
            outlier_pct = outliers / len(self.df)
            accuracy_indicators.append(1 - min(outlier_pct, 0.5))
        
        if len(accuracy_indicators) == 0:
            return 0.7  # Default moderate score
        
        return np.mean(accuracy_indicators)
    
    def _assess_sample_size(self):
        """Assess if sample size is adequate"""
        n = len(self.df)
        n_features = len(self.df.columns) - 1  # Exclude target
        
        # Rule of thumb: 10-20 samples per feature
        min_required = n_features * 10
        ideal_required = n_features * 20
        
        if n >= ideal_required:
            return 1.0
        elif n >= min_required:
            return 0.7
        elif n >= min_required * 0.5:
            return 0.4
        else:
            return 0.2
    
    def _generate_data_quality_recommendations(self, completeness, consistency, sample_size):
        """Generate data quality recommendations"""
        recommendations = []
        
        if completeness < 0.8:
            recommendations.append({
                'priority': 'HIGH',
                'recommendation': 'Address missing data through imputation or removal',
                'rationale': f'Low data completeness ({completeness:.1%})'
            })
        
        if consistency < 0.7:
            recommendations.append({
                'priority': 'HIGH',
                'recommendation': 'Standardize data formats and values',
                'rationale': 'Inconsistent data detected'
            })
        
        if sample_size < 0.6:
            recommendations.append({
                'priority': 'MEDIUM',
                'recommendation': 'Collect more data samples',
                'rationale': 'Sample size may be inadequate for reliable modeling'
            })
        
        recommendations.append({
            'priority': 'MEDIUM',
            'recommendation': 'Implement data validation rules and checks',
            'rationale': 'Prevent future data quality issues'
        })
        
        return recommendations
    
    def _analyze_model_performance_risks(self):
        """Analyze risks related to model performance"""
        performance_risks = {
            'accuracy_risk': 'UNKNOWN',
            'precision_risk': 'UNKNOWN',
            'recall_risk': 'UNKNOWN',
            'overfitting_risk': 'UNKNOWN',
            'underfitting_risk': 'UNKNOWN',
            'recommendations': []
        }
        
        accuracy = self.model_results.get('accuracy', 0)
        precision = self.model_results.get('precision', 0)
        recall = self.model_results.get('recall', 0)
        train_accuracy = self.model_results.get('train_accuracy', accuracy)
        
        # Accuracy risk
        if accuracy < 0.7:
            performance_risks['accuracy_risk'] = 'HIGH'
            performance_risks['recommendations'].append("Model accuracy is low - consider feature engineering or model selection")
        elif accuracy < 0.8:
            performance_risks['accuracy_risk'] = 'MEDIUM'
        else:
            performance_risks['accuracy_risk'] = 'LOW'
        
        # Precision risk
        if precision < 0.7:
            performance_risks['precision_risk'] = 'HIGH'
            performance_risks['recommendations'].append("Low precision - high false positive rate")
        elif precision < 0.8:
            performance_risks['precision_risk'] = 'MEDIUM'
        else:
            performance_risks['precision_risk'] = 'LOW'
        
        # Recall risk
        if recall < 0.7:
            performance_risks['recall_risk'] = 'HIGH'
            performance_risks['recommendations'].append("Low recall - high false negative rate")
        elif recall < 0.8:
            performance_risks['recall_risk'] = 'MEDIUM'
        else:
            performance_risks['recall_risk'] = 'LOW'
        
        # Overfitting risk
        if train_accuracy - accuracy > 0.15:
            performance_risks['overfitting_risk'] = 'HIGH'
            performance_risks['recommendations'].append("Model shows signs of overfitting - consider regularization")
        elif train_accuracy - accuracy > 0.10:
            performance_risks['overfitting_risk'] = 'MEDIUM'
        else:
            performance_risks['overfitting_risk'] = 'LOW'
        
        # Underfitting risk
        if train_accuracy < 0.75:
            performance_risks['underfitting_risk'] = 'HIGH'
            performance_risks['recommendations'].append("Model may be underfitting - consider more complex model or feature engineering")
        elif train_accuracy < 0.85:
            performance_risks['underfitting_risk'] = 'MEDIUM'
        else:
            performance_risks['underfitting_risk'] = 'LOW'
        
        if not performance_risks['recommendations']:
            performance_risks['recommendations'].append("Model performance is acceptable - continue monitoring")
        
        return performance_risks
    
    def _calculate_weighted_risk_score(self, category_scores):
        """Calculate weighted overall risk score"""
        # Weights for each category
        weights = {
            'privacy': 0.25,
            'ethical': 0.25,
            'compliance': 0.20,
            'security': 0.15,
            'operational': 0.08,
            'data_quality': 0.07
        }
        
        weighted_score = sum(category_scores.get(cat, 0) * weight 
                            for cat, weight in weights.items())
        
        return weighted_score
    
    def _classify_risk_level(self, risk_score):
        """Classify overall risk level"""
        if risk_score >= 0.7:
            return 'CRITICAL'
        elif risk_score >= 0.5:
            return 'HIGH'
        elif risk_score >= 0.3:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def _detect_all_violations(self, privacy, ethical, compliance, security, operational, data_quality):
        """Detect all risk violations across categories"""
        violations = []
        
        # Privacy violations
        if privacy['risk_score'] > 0.7:
            violations.append({
                'category': 'privacy',
                'severity': 'CRITICAL' if privacy['risk_score'] > 0.8 else 'HIGH',
                'message': f"High privacy risk detected ({privacy['risk_score']:.1%})",
                'details': f"{privacy['pii_count']} PII types found, {privacy['anonymization_level']} anonymization"
            })
        
        critical_pii = [p for p in privacy['pii_detected'] if p['severity'] == 'CRITICAL']
        if len(critical_pii) > 0:
            violations.append({
                'category': 'privacy',
                'severity': 'CRITICAL',
                'message': 'Critical PII types detected without protection',
                'details': f"Types: {', '.join(set(p['type'] for p in critical_pii))}"
            })
        
        # Ethical violations
        if ethical['risk_score'] > 0.6:
            violations.append({
                'category': 'ethical',
                'severity': 'HIGH' if ethical['risk_score'] > 0.7 else 'MEDIUM',
                'message': f"Ethical concerns identified ({ethical['risk_score']:.1%})",
                'details': f"Bias score: {ethical['bias_score']:.1%}, Transparency: {ethical['transparency_score']:.1%}"
            })
        
        # Compliance violations
        compliance_issues = []
        if compliance['gdpr']['status'] != 'COMPLIANT':
            compliance_issues.append('GDPR')
        if compliance['ccpa']['status'] != 'COMPLIANT':
            compliance_issues.append('CCPA')
        if compliance.get('hipaa', {}).get('applicable') and compliance['hipaa']['status'] != 'COMPLIANT':
            compliance_issues.append('HIPAA')
        if compliance.get('ecoa', {}).get('applicable') and compliance['ecoa']['status'] != 'COMPLIANT':
            compliance_issues.append('ECOA')
        
        if compliance_issues:
            violations.append({
                'category': 'compliance',
                'severity': 'HIGH',
                'message': 'Compliance violations detected',
                'details': f"Non-compliant regulations: {', '.join(compliance_issues)}"
            })
        
        # Security violations
        if security['risk_score'] > 0.6:
            violations.append({
                'category': 'security',
                'severity': 'HIGH',
                'message': f"Security risks identified ({security['risk_score']:.1%})",
                'details': f"Adversarial vulnerability: {security['adversarial_vulnerability']:.1%}"
            })
        
        # Data quality violations
        if data_quality['risk_score'] > 0.5:
            violations.append({
                'category': 'data_quality',
                'severity': 'MEDIUM',
                'message': f"Data quality issues detected ({data_quality['risk_score']:.1%})",
                'details': f"Completeness: {data_quality['completeness_score']:.1%}, Consistency: {data_quality['consistency_score']:.1%}"
            })
        
        return sorted(violations, key=lambda x: {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}[x['severity']])
    
    def _generate_risk_insights(self, category_scores, violations, privacy, ethical):
        """Generate key risk insights"""
        insights = []
        
        # Overall risk insight
        overall_risk = self._calculate_weighted_risk_score(category_scores)
        insights.append(
            f"Overall risk score: {overall_risk:.1%} ({self._classify_risk_level(overall_risk)} risk)"
        )
        
        # Highest risk category
        if category_scores:
            max_cat = max(category_scores.items(), key=lambda x: x[1])
            insights.append(
                f"Highest risk category: {max_cat[0].title()} ({max_cat[1]:.1%})"
            )
        
        # Critical violations
        critical_violations = [v for v in violations if v['severity'] == 'CRITICAL']
        if critical_violations:
            insights.append(
                f"{len(critical_violations)} CRITICAL violations require immediate attention"
            )
        
        # PII detection
        if privacy['pii_count'] > 0:
            insights.append(
                f"{privacy['pii_count']} PII types detected using {privacy['detection_method']}"
            )
        
        # Bias impact
        if ethical['bias_score'] > 0.5:
            insights.append(
                f"High bias score ({ethical['bias_score']:.1%}) indicates fairness concerns"
            )
        
        return insights
    
    def _print_risk_summary(self):
        """Print risk analysis summary"""
        print("\n" + "=" * 70)
        print("RISK ANALYSIS SUMMARY")
        print("=" * 70)
        
        print(f"\n📊 Overall Risk: {self.results['overall_risk_score']:.1%} ({self.results['risk_level']})")
        print(f"🔒 Presidio: {'Enabled' if self.results['presidio_enabled'] else 'Disabled'}")
        
        print("\n📈 Category Scores:")
        for category, score in self.results['risk_categories'].items():
            emoji = "🔴" if score > 0.7 else "🟠" if score > 0.5 else "🟡" if score > 0.3 else "🟢"
            print(f"  {emoji} {category.title()}: {score:.1%}")
        
        print(f"\n⚠️  Violations: {len(self.results['violations'])}")
        for v in self.results['violations'][:5]:  # Show top 5
            print(f"  • [{v['severity']}] {v['message']}")
        
        print(f"\n💡 Key Insights:")
        for insight in self.results['insights'][:5]:
            print(f"  • {insight}")
        
        print("\n" + "=" * 70)
