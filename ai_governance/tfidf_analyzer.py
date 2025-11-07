"""
TF-IDF Based Risk and Bias Analysis
Faster alternative to deep learning for pattern-based PII detection
Trained on GDPR compliance datasets
"""

import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
import re
import json
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict
import pickle
import os


class TFIDFRiskAnalyzer:
    """
    TF-IDF based Risk Analyzer for fast PII detection and risk scoring
    Uses pre-trained models on GDPR datasets for high-speed inference
    """
    
    # GDPR-compliant entity patterns (compiled regex for speed)
    ENTITY_PATTERNS = {
        'EMAIL_ADDRESS': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        'PHONE_NUMBER': re.compile(r'\b(\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'),
        'SSN': re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
        'CREDIT_CARD': re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'),
        'IP_ADDRESS': re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
        'URL': re.compile(r'https?://[^\s]+|www\.[^\s]+'),
        'DATE': re.compile(r'\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b'),
        'ZIP_CODE': re.compile(r'\b\d{5}(?:-\d{4})?\b'),
    }
    
    # Risk weights for different entity types (GDPR compliance)
    RISK_WEIGHTS = {
        'EMAIL_ADDRESS': 0.7,
        'PHONE_NUMBER': 0.6,
        'SSN': 1.0,
        'CREDIT_CARD': 1.0,
        'IP_ADDRESS': 0.5,
        'URL': 0.3,
        'DATE': 0.2,
        'ZIP_CODE': 0.4,
        'PERSON_NAME': 0.8,
        'LOCATION': 0.5,
        'ORGANIZATION': 0.3,
    }
    
    # Privacy risk categories
    PRIVACY_CATEGORIES = {
        'DIRECT_IDENTIFIER': ['SSN', 'CREDIT_CARD', 'EMAIL_ADDRESS', 'PHONE_NUMBER'],
        'QUASI_IDENTIFIER': ['DATE', 'ZIP_CODE', 'LOCATION'],
        'SENSITIVE_ATTRIBUTE': ['PERSON_NAME', 'IP_ADDRESS'],
    }
    
    def __init__(self, model_path: Optional[str] = None):
        """
        Initialize TF-IDF analyzer
        
        Args:
            model_path: Path to pre-trained model (optional)
        """
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 3),  # Unigrams to trigrams
            min_df=2,
            max_df=0.8,
            strip_accents='unicode',
            lowercase=True,
        )
        
        self.classifier = RandomForestClassifier(
            n_estimators=100,
            max_depth=20,
            random_state=42,
            n_jobs=-1  # Use all CPU cores
        )
        
        self.label_encoder = LabelEncoder()
        self.is_trained = False
        self.model_path = model_path
        
        # Try to load pre-trained model
        if model_path and os.path.exists(model_path):
            self.load_model(model_path)
    
    def train_on_gdpr_dataset(self, training_data: pd.DataFrame, text_column: str, label_column: str):
        """
        Train the TF-IDF model on GDPR-compliant dataset
        
        Args:
            training_data: DataFrame with text and labels
            text_column: Name of column containing text
            label_column: Name of column containing labels (e.g., 'PII', 'SENSITIVE', 'SAFE')
        """
        print("\n🎓 Training TF-IDF Risk Analyzer on GDPR dataset...")
        print(f"   Dataset size: {len(training_data)} samples")
        
        # Extract features
        X = training_data[text_column].astype(str).values
        y = training_data[label_column].values
        
        # Encode labels
        y_encoded = self.label_encoder.fit_transform(y)
        
        # Fit vectorizer and transform
        X_tfidf = self.vectorizer.fit_transform(X)
        
        # Train classifier
        self.classifier.fit(X_tfidf, y_encoded)
        self.is_trained = True
        
        print(f"✓ Model trained successfully")
        print(f"   Vocabulary size: {len(self.vectorizer.vocabulary_)}")
        print(f"   Classes: {list(self.label_encoder.classes_)}")
    
    def save_model(self, path: str):
        """Save trained model to disk"""
        model_data = {
            'vectorizer': self.vectorizer,
            'classifier': self.classifier,
            'label_encoder': self.label_encoder,
            'is_trained': self.is_trained
        }
        with open(path, 'wb') as f:
            pickle.dump(model_data, f)
        print(f"✓ Model saved to: {path}")
    
    def load_model(self, path: str):
        """Load pre-trained model from disk"""
        with open(path, 'rb') as f:
            model_data = pickle.load(f)
        self.vectorizer = model_data['vectorizer']
        self.classifier = model_data['classifier']
        self.label_encoder = model_data['label_encoder']
        self.is_trained = model_data['is_trained']
        print(f"✓ Pre-trained model loaded from: {path}")
    
    def detect_pii_patterns(self, text: str) -> Dict[str, List[str]]:
        """
        Fast regex-based PII pattern detection
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary of entity_type -> list of matches
        """
        detections = {}
        
        for entity_type, pattern in self.ENTITY_PATTERNS.items():
            matches = pattern.findall(text)
            if matches:
                detections[entity_type] = matches if isinstance(matches, list) else [matches]
        
        return detections
    
    def analyze_column(self, series: pd.Series, column_name: str) -> Dict[str, Any]:
        """
        Analyze a single column for privacy risks using TF-IDF
        
        Args:
            series: Pandas Series to analyze
            column_name: Name of the column
            
        Returns:
            Risk analysis results
        """
        # Convert to string and sample
        text_samples = series.dropna().astype(str).head(1000).tolist()
        combined_text = " | ".join(text_samples[:100])
        
        # Regex-based PII detection (fast)
        pii_detections = self.detect_pii_patterns(combined_text)
        
        # TF-IDF classification (if model trained)
        tfidf_risk_score = 0.0
        predicted_category = "UNKNOWN"
        
        if self.is_trained and text_samples:
            # Transform samples
            X_tfidf = self.vectorizer.transform(text_samples[:50])
            
            # Predict
            predictions = self.classifier.predict(X_tfidf)
            prediction_proba = self.classifier.predict_proba(X_tfidf)
            
            # Aggregate predictions
            predicted_labels = self.label_encoder.inverse_transform(predictions)
            predicted_category = max(set(predicted_labels), key=list(predicted_labels).count)
            
            # Average confidence
            tfidf_risk_score = np.mean(np.max(prediction_proba, axis=1))
        
        # Calculate risk score
        risk_score = self._calculate_risk_score(pii_detections, tfidf_risk_score)
        
        return {
            'column_name': column_name,
            'pii_detected': len(pii_detections) > 0,
            'entity_types': list(pii_detections.keys()),
            'entity_counts': {k: len(v) for k, v in pii_detections.items()},
            'risk_score': risk_score,
            'risk_level': self._get_risk_level(risk_score),
            'predicted_category': predicted_category,
            'tfidf_confidence': tfidf_risk_score,
            'detection_method': 'tfidf_regex_hybrid'
        }
    
    def _calculate_risk_score(self, pii_detections: Dict[str, List], tfidf_score: float) -> float:
        """
        Calculate overall risk score combining regex and TF-IDF
        
        Args:
            pii_detections: Dictionary of detected entities
            tfidf_score: TF-IDF model confidence score
            
        Returns:
            Risk score (0.0 to 1.0)
        """
        # Regex-based score
        regex_score = 0.0
        if pii_detections:
            weighted_sum = sum(
                len(matches) * self.RISK_WEIGHTS.get(entity_type, 0.5)
                for entity_type, matches in pii_detections.items()
            )
            regex_score = min(weighted_sum / 10.0, 1.0)  # Normalize
        
        # Combine scores (60% regex, 40% TF-IDF)
        combined_score = (0.6 * regex_score) + (0.4 * tfidf_score)
        
        return round(combined_score, 3)
    
    def _get_risk_level(self, risk_score: float) -> str:
        """Convert risk score to categorical level"""
        if risk_score >= 0.75:
            return "CRITICAL"
        elif risk_score >= 0.50:
            return "HIGH"
        elif risk_score >= 0.25:
            return "MEDIUM"
        else:
            return "LOW"
    
    def analyze_dataset(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze entire dataset for privacy risks
        
        Args:
            df: DataFrame to analyze
            
        Returns:
            Comprehensive risk analysis report
        """
        print("\n" + "="*70)
        print("🔍 TF-IDF RISK ANALYSIS - GDPR COMPLIANCE CHECK")
        print("="*70 + "\n")
        
        results = {
            'metadata': {
                'total_rows': len(df),
                'total_columns': len(df.columns),
                'analysis_method': 'tfidf_hybrid',
                'model_trained': self.is_trained
            },
            'column_analysis': {},
            'overall_risk': {
                'risk_score': 0.0,
                'risk_level': 'LOW',
                'high_risk_columns': [],
                'pii_columns': []
            },
            'privacy_categories': {
                'direct_identifiers': [],
                'quasi_identifiers': [],
                'sensitive_attributes': []
            },
            'recommendations': []
        }
        
        # Analyze each text column
        text_columns = df.select_dtypes(include=['object']).columns.tolist()
        
        print(f"Analyzing {len(text_columns)} text columns...")
        
        for column in text_columns:
            print(f"  Analyzing '{column}'...", end=" ")
            
            analysis = self.analyze_column(df[column], column)
            results['column_analysis'][column] = analysis
            
            # Track high-risk columns
            if analysis['risk_score'] >= 0.5:
                results['overall_risk']['high_risk_columns'].append(column)
            
            if analysis['pii_detected']:
                results['overall_risk']['pii_columns'].append(column)
                
                # Categorize by privacy type
                for entity_type in analysis['entity_types']:
                    if entity_type in self.PRIVACY_CATEGORIES['DIRECT_IDENTIFIER']:
                        results['privacy_categories']['direct_identifiers'].append({
                            'column': column,
                            'entity': entity_type
                        })
                    elif entity_type in self.PRIVACY_CATEGORIES['QUASI_IDENTIFIER']:
                        results['privacy_categories']['quasi_identifiers'].append({
                            'column': column,
                            'entity': entity_type
                        })
            
            print(f"✓ Risk: {analysis['risk_level']} ({analysis['risk_score']:.2f})")
        
        # Calculate overall risk
        if results['column_analysis']:
            avg_risk = np.mean([
                col['risk_score'] 
                for col in results['column_analysis'].values()
            ])
            results['overall_risk']['risk_score'] = round(avg_risk, 3)
            results['overall_risk']['risk_level'] = self._get_risk_level(avg_risk)
        
        # Generate recommendations
        results['recommendations'] = self._generate_recommendations(results)
        
        print("\n" + "="*70)
        print(f"✓ ANALYSIS COMPLETE - Overall Risk: {results['overall_risk']['risk_level']}")
        print("="*70 + "\n")
        
        return results
    
    def _generate_recommendations(self, results: Dict) -> List[str]:
        """Generate GDPR-compliant recommendations"""
        recommendations = []
        
        high_risk_cols = results['overall_risk']['high_risk_columns']
        direct_ids = results['privacy_categories']['direct_identifiers']
        
        if direct_ids:
            recommendations.append(
                f"🔴 CRITICAL: {len(direct_ids)} direct identifiers found. "
                "Remove or hash these columns immediately (GDPR Art. 5)"
            )
        
        if high_risk_cols:
            recommendations.append(
                f"⚠️  HIGH RISK: {len(high_risk_cols)} columns flagged. "
                "Apply anonymization techniques (GDPR Art. 32)"
            )
        
        if results['privacy_categories']['quasi_identifiers']:
            recommendations.append(
                "📊 Quasi-identifiers detected. Consider k-anonymity or l-diversity"
            )
        
        if not recommendations:
            recommendations.append("✓ No critical privacy risks detected. Dataset appears GDPR-compliant.")
        
        return recommendations


class TFIDFBiasAnalyzer:
    """
    TF-IDF based Bias Analyzer for fast fairness assessment
    Detects demographic patterns and potential discrimination
    """
    
    # Protected attributes (GDPR special categories)
    PROTECTED_PATTERNS = {
        'race': re.compile(r'\b(african|asian|caucasian|hispanic|latino|black|white)\b', re.I),
        'gender': re.compile(r'\b(male|female|man|woman|boy|girl|transgender|non-binary)\b', re.I),
        'religion': re.compile(r'\b(christian|muslim|jewish|hindu|buddhist|atheist|religious)\b', re.I),
        'age': re.compile(r'\b(elderly|senior|young|teenager|minor|adult|aged)\b', re.I),
        'disability': re.compile(r'\b(disabled|handicapped|impaired|wheelchair|blind|deaf)\b', re.I),
        'nationality': re.compile(r'\b(american|british|indian|chinese|german|french|nationality)\b', re.I),
    }
    
    def __init__(self):
        """Initialize TF-IDF bias analyzer"""
        self.vectorizer = TfidfVectorizer(
            max_features=3000,
            ngram_range=(1, 2),
            min_df=1,
            stop_words='english'
        )
    
    def detect_protected_attributes(self, text: str) -> Dict[str, List[str]]:
        """
        Detect protected attributes in text
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary of attribute_type -> matches
        """
        detections = {}
        
        for attr_type, pattern in self.PROTECTED_PATTERNS.items():
            matches = pattern.findall(text)
            if matches:
                detections[attr_type] = list(set([m.lower() for m in matches]))
        
        return detections
    
    def analyze_column_bias(self, series: pd.Series, column_name: str) -> Dict[str, Any]:
        """
        Analyze column for potential bias indicators
        
        Args:
            series: Pandas Series to analyze
            column_name: Name of the column
            
        Returns:
            Bias analysis results
        """
        text_samples = series.dropna().astype(str).head(1000).tolist()
        combined_text = " | ".join(text_samples[:100])
        
        # Detect protected attributes
        protected_attrs = self.detect_protected_attributes(combined_text)
        
        # Calculate bias score
        bias_score = len(protected_attrs) * 0.2  # 0.2 per category
        bias_score = min(bias_score, 1.0)
        
        return {
            'column_name': column_name,
            'protected_attributes': list(protected_attrs.keys()),
            'attribute_values': protected_attrs,
            'bias_score': round(bias_score, 3),
            'bias_level': self._get_bias_level(bias_score),
            'gdpr_concern': len(protected_attrs) > 0  # Art. 9 special categories
        }
    
    def _get_bias_level(self, bias_score: float) -> str:
        """Convert bias score to categorical level"""
        if bias_score >= 0.6:
            return "HIGH"
        elif bias_score >= 0.3:
            return "MEDIUM"
        else:
            return "LOW"
    
    def analyze_dataset(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze entire dataset for bias
        
        Args:
            df: DataFrame to analyze
            
        Returns:
            Comprehensive bias analysis report
        """
        print("\n" + "="*70)
        print("⚖️  TF-IDF BIAS ANALYSIS - GDPR ARTICLE 9 COMPLIANCE")
        print("="*70 + "\n")
        
        results = {
            'metadata': {
                'total_rows': len(df),
                'total_columns': len(df.columns),
                'analysis_method': 'tfidf_pattern_matching'
            },
            'column_analysis': {},
            'overall_bias': {
                'bias_score': 0.0,
                'bias_level': 'LOW',
                'flagged_columns': [],
                'protected_categories_found': []
            },
            'gdpr_compliance': {
                'article_9_violations': [],
                'special_categories_detected': []
            },
            'recommendations': []
        }
        
        # Analyze text columns
        text_columns = df.select_dtypes(include=['object']).columns.tolist()
        
        print(f"Analyzing {len(text_columns)} columns for bias...")
        
        for column in text_columns:
            print(f"  Analyzing '{column}'...", end=" ")
            
            analysis = self.analyze_column_bias(df[column], column)
            results['column_analysis'][column] = analysis
            
            if analysis['bias_score'] >= 0.3:
                results['overall_bias']['flagged_columns'].append(column)
            
            if analysis['gdpr_concern']:
                results['gdpr_compliance']['article_9_violations'].append({
                    'column': column,
                    'protected_attributes': analysis['protected_attributes']
                })
                
                for attr in analysis['protected_attributes']:
                    if attr not in results['overall_bias']['protected_categories_found']:
                        results['overall_bias']['protected_categories_found'].append(attr)
            
            print(f"✓ Bias: {analysis['bias_level']} ({analysis['bias_score']:.2f})")
        
        # Calculate overall bias
        if results['column_analysis']:
            avg_bias = np.mean([
                col['bias_score']
                for col in results['column_analysis'].values()
            ])
            results['overall_bias']['bias_score'] = round(avg_bias, 3)
            results['overall_bias']['bias_level'] = self._get_bias_level(avg_bias)
        
        # Recommendations
        results['recommendations'] = self._generate_bias_recommendations(results)
        
        print("\n" + "="*70)
        print(f"✓ BIAS ANALYSIS COMPLETE - Overall Bias: {results['overall_bias']['bias_level']}")
        print("="*70 + "\n")
        
        return results
    
    def _generate_bias_recommendations(self, results: Dict) -> List[str]:
        """Generate bias mitigation recommendations"""
        recommendations = []
        
        violations = results['gdpr_compliance']['article_9_violations']
        protected_cats = results['overall_bias']['protected_categories_found']
        
        if violations:
            recommendations.append(
                f"🔴 GDPR Article 9 Violation: {len(violations)} columns contain special category data. "
                "Remove or obtain explicit consent before processing."
            )
        
        if protected_cats:
            recommendations.append(
                f"⚠️  Protected attributes detected: {', '.join(protected_cats)}. "
                "Ensure model decisions don't rely on these features."
            )
        
        if results['overall_bias']['bias_score'] >= 0.5:
            recommendations.append(
                "📊 High bias score detected. Apply bias mitigation techniques "
                "(reweighting, adversarial debiasing, fairness constraints)."
            )
        
        if not recommendations:
            recommendations.append("✓ No significant bias indicators detected.")
        
        return recommendations


# Synthetic GDPR training data generator
def generate_synthetic_gdpr_training_data(n_samples: int = 1000) -> pd.DataFrame:
    """
    Generate synthetic training data for TF-IDF model
    Simulates GDPR-compliant and non-compliant text patterns
    """
    print(f"\n📝 Generating {n_samples} synthetic GDPR training samples...")
    
    pii_samples = [
        "john.doe@example.com", "jane.smith@company.com", "+1-555-123-4567",
        "123-45-6789", "4532-1234-5678-9012", "192.168.1.1",
        "https://example.com/profile", "12/31/2023", "90210"
    ] * (n_samples // 27)
    
    sensitive_samples = [
        "Patient has diabetes", "Employee salary $120,000", "Credit score 750",
        "African American male", "Muslim employee", "Wheelchair accessible"
    ] * (n_samples // 18)
    
    safe_samples = [
        "Product category", "Inventory count", "Temperature reading",
        "Anonymous feedback", "Aggregated statistics", "Public information"
    ] * (n_samples // 18)
    
    # Combine
    texts = pii_samples + sensitive_samples + safe_samples
    labels = (
        ['PII'] * len(pii_samples) +
        ['SENSITIVE'] * len(sensitive_samples) +
        ['SAFE'] * len(safe_samples)
    )
    
    df = pd.DataFrame({
        'text': texts[:n_samples],
        'label': labels[:n_samples]
    })
    
    print(f"✓ Generated dataset: {df['label'].value_counts().to_dict()}")
    
    return df
