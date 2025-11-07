"""
Bias Analyzer Module
Detects and quantifies bias in ML models using Presidio for enhanced demographic analysis
"""

import numpy as np
import pandas as pd
from collections import defaultdict
from typing import List, Dict, Any, Optional

# Presidio imports
try:
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    PRESIDIO_AVAILABLE = True
except ImportError:
    PRESIDIO_AVAILABLE = False
    print("⚠️  Presidio not available. Install with: pip install presidio-analyzer")


class BiasAnalyzer:
    """Analyze bias in ML model predictions with Presidio-enhanced demographic detection"""
    
    # Class-level cache for Presidio analyzer
    _presidio_analyzer = None
    _presidio_initialized = False
    _presidio_init_failed = False
    
    def __init__(self, X_test, y_test, y_pred, original_df, protected_attributes, target_column, use_presidio=False):
        self.X_test = X_test
        self.y_test = y_test
        self.y_pred = y_pred
        self.original_df = original_df
        self.protected_attributes = protected_attributes
        self.target_column = target_column
        self.results = {}
        self.use_presidio = use_presidio
        
        # Initialize Presidio only if requested and not already failed
        if self.use_presidio and PRESIDIO_AVAILABLE and not BiasAnalyzer._presidio_init_failed:
            if not BiasAnalyzer._presidio_initialized:
                self._init_presidio()
            self.analyzer = BiasAnalyzer._presidio_analyzer
        else:
            self.analyzer = None
    
    def _init_presidio(self):
        """Initialize Presidio analyzer with demographic-specific recognizers (cached at class level)"""
        try:
            print("⏳ Initializing Presidio analyzer (first time only)...")
            
            # Check if spaCy and model are available
            try:
                import spacy
                
                # Check if model exists WITHOUT loading it first
                model_name = "en_core_web_sm"
                if not spacy.util.is_package(model_name):
                    print(f"⚠️  spaCy model '{model_name}' not found.")
                    print(f"   To enable Presidio, install the model with:")
                    print(f"   python -m spacy download {model_name}")
                    print("   Continuing without Presidio-enhanced detection...")
                    BiasAnalyzer._presidio_init_failed = True
                    return
                
                # Model exists, now load it
                print(f"✓ spaCy model '{model_name}' found, loading...")
                nlp = spacy.load(model_name)
                
            except ImportError:
                print("⚠️  spaCy not installed. Install with: pip install spacy")
                BiasAnalyzer._presidio_init_failed = True
                return
            except Exception as e:
                print(f"⚠️  Error loading spaCy model: {e}")
                print("   Continuing without Presidio-enhanced detection...")
                BiasAnalyzer._presidio_init_failed = True
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
            BiasAnalyzer._presidio_analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
            
            # Add custom recognizers for demographic attributes
            self._add_demographic_recognizers()
            
            BiasAnalyzer._presidio_initialized = True
            print("✓ Presidio analyzer initialized successfully")
            
        except Exception as e:
            print(f"⚠️  Could not initialize Presidio: {e}")
            print("   Continuing without Presidio-enhanced detection...")
            BiasAnalyzer._presidio_init_failed = True
            BiasAnalyzer._presidio_analyzer = None
    
    def _add_demographic_recognizers(self):
        """Add custom recognizers for demographic attributes"""
        if not BiasAnalyzer._presidio_analyzer:
            return
            
        # Gender recognizer
        gender_patterns = [
            Pattern(name="gender_explicit", regex=r"\b(male|female|non-binary|other|prefer not to say)\b", score=0.9),
            Pattern(name="gender_pronouns", regex=r"\b(he/him|she/her|they/them)\b", score=0.7),
        ]
        gender_recognizer = PatternRecognizer(
            supported_entity="GENDER",
            patterns=gender_patterns,
            context=["gender", "sex"]
        )
        BiasAnalyzer._presidio_analyzer.registry.add_recognizer(gender_recognizer)
        
        # Age group recognizer
        age_patterns = [
            Pattern(name="age_range", regex=r"\b(\d{1,2})-(\d{1,2})\b", score=0.8),
            Pattern(name="age_group", regex=r"\b(under 18|18-24|25-34|35-44|45-54|55-64|65\+|senior|adult|teen)\b", score=0.9),
        ]
        age_recognizer = PatternRecognizer(
            supported_entity="AGE_GROUP",
            patterns=age_patterns,
            context=["age", "years old", "born"]
        )
        BiasAnalyzer._presidio_analyzer.registry.add_recognizer(age_recognizer)
        
        # Ethnicity/Race recognizer
        ethnicity_patterns = [
            Pattern(name="ethnicity", 
                   regex=r"\b(asian|black|white|hispanic|latino|latina|native american|pacific islander|african american|caucasian)\b", 
                   score=0.8),
        ]
        ethnicity_recognizer = PatternRecognizer(
            supported_entity="ETHNICITY",
            patterns=ethnicity_patterns,
            context=["race", "ethnicity", "ethnic"]
        )
        BiasAnalyzer._presidio_analyzer.registry.add_recognizer(ethnicity_recognizer)
    
    def detect_sensitive_attributes(self, df: pd.DataFrame) -> List[str]:
        """Use Presidio to detect columns containing sensitive demographic information"""
        if not self.analyzer:
            return []
        
        sensitive_cols = []
        
        for col in df.columns:
            # Sample some values from the column
            sample_values = df[col].dropna().astype(str).head(100).tolist()
            sample_text = " ".join(sample_values)
            
            # Analyze for demographic entities
            results = self.analyzer.analyze(
                text=sample_text,
                language='en',
                entities=["GENDER", "AGE_GROUP", "ETHNICITY", "PERSON", "LOCATION"]
            )
            
            if results:
                entity_types = [r.entity_type for r in results]
                print(f"  Column '{col}' contains: {set(entity_types)}")
                sensitive_cols.append(col)
        
        return sensitive_cols
    
    def analyze(self):
        """Perform comprehensive bias analysis with optional Presidio enhancement"""
        print("\n" + "="*70)
        print("🔍 BIAS ANALYSIS - FAIRNESS DETECTION")
        print("="*70)
        
        # Step 1: Use Presidio to detect additional sensitive attributes (if enabled)
        if self.use_presidio and self.analyzer and PRESIDIO_AVAILABLE:
            print("\nStep 1: Detecting sensitive demographic attributes with Presidio...")
            try:
                detected_sensitive = self.detect_sensitive_attributes(self.original_df)
                
                # Add detected attributes to protected attributes if not already included
                for attr in detected_sensitive:
                    if attr not in self.protected_attributes and attr != self.target_column:
                        print(f"  ➕ Adding detected sensitive attribute: {attr}")
                        self.protected_attributes.append(attr)
            except Exception as e:
                print(f"  ⚠️  Presidio detection failed: {e}")
                print("  Continuing with manual protected attributes...")
        else:
            print("\nStep 1: Using manually specified protected attributes")
            print(f"  Protected attributes: {self.protected_attributes}")
        
        # Step 2: Analyze demographic bias
        print("\nStep 2: Analyzing demographic bias across groups...")
        demographic_bias = self._analyze_demographic_bias()
        
        # Step 3: Calculate fairness metrics
        print("\nStep 3: Calculating fairness metrics...")
        fairness_metrics = self._calculate_fairness_metrics()
        
        # Step 4: Detect violations
        print("\nStep 4: Detecting fairness violations...")
        
        self.results = {
            'demographic_bias': demographic_bias,
            'fairness_metrics': fairness_metrics,
            'fairness_violations': self._detect_fairness_violations(),
            'fairness_assessment': self._assess_overall_fairness(),
            'overall_bias_score': 0.0,
            'presidio_enhanced': self.use_presidio and PRESIDIO_AVAILABLE and self.analyzer is not None
        }
        
        # Calculate overall bias score
        self.results['overall_bias_score'] = self._calculate_overall_bias_score()
        
        print("\n" + "="*70)
        print(f"✓ BIAS ANALYSIS COMPLETE - Score: {self.results['overall_bias_score']:.3f}")
        print("="*70 + "\n")
        
        return self.results
    
    def _analyze_demographic_bias(self):
        """Analyze bias across demographic groups"""
        bias_analysis = {}
        
        for attr in self.protected_attributes:
            if attr not in self.original_df.columns:
                continue
            
            # Get unique groups
            groups = self.original_df[attr].unique()
            
            # Calculate metrics for each group
            group_metrics = {}
            approval_rates = {}
            
            for group in groups:
                # Get indices for this group
                group_mask = self.original_df[attr] == group
                group_indices = self.original_df[group_mask].index
                
                # Get test set indices that are in this group
                test_indices = self.X_test.index
                common_indices = group_indices.intersection(test_indices)
                
                if len(common_indices) == 0:
                    continue
                
                # Get predictions for this group
                group_pred_indices = [i for i, idx in enumerate(test_indices) if idx in common_indices]
                group_preds = self.y_pred[group_pred_indices] if len(group_pred_indices) > 0 else []
                group_true = self.y_test.iloc[group_pred_indices] if len(group_pred_indices) > 0 else []
                
                if len(group_preds) == 0:
                    continue
                
                # Calculate approval rate (positive prediction rate)
                approval_rate = np.mean(group_preds) * 100
                approval_rates[str(group)] = float(approval_rate)
                
                # Calculate accuracy for this group
                accuracy = np.mean(group_preds == group_true) if len(group_true) > 0 else 0
                
                # Calculate false positive rate (FPR) and false negative rate (FNR)
                if len(group_true) > 0:
                    # True positives and false positives
                    true_positives = np.sum((group_preds == 1) & (group_true == 1))
                    false_positives = np.sum((group_preds == 1) & (group_true == 0))
                    false_negatives = np.sum((group_preds == 0) & (group_true == 1))
                    true_negatives = np.sum((group_preds == 0) & (group_true == 0))
                    
                    # Calculate rates
                    fpr = false_positives / (false_positives + true_negatives) if (false_positives + true_negatives) > 0 else 0
                    fnr = false_negatives / (false_negatives + true_positives) if (false_negatives + true_positives) > 0 else 0
                    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
                    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
                else:
                    fpr = fnr = precision = recall = 0
                
                group_metrics[str(group)] = {
                    'sample_size': len(group_preds),
                    'approval_rate': float(approval_rate),
                    'accuracy': float(accuracy),
                    'precision': float(precision),
                    'recall': float(recall),
                    'false_positive_rate': float(fpr),
                    'false_negative_rate': float(fnr),
                    'positive_predictions': int(np.sum(group_preds)),
                    'negative_predictions': int(len(group_preds) - np.sum(group_preds))
                }
            
            # Calculate statistical measures of disparity
            if approval_rates:
                rates_list = list(approval_rates.values())
                max_disparity = max(rates_list) - min(rates_list)
                mean_rate = np.mean(rates_list)
                std_rate = np.std(rates_list)
                coefficient_of_variation = (std_rate / mean_rate * 100) if mean_rate > 0 else 0
            else:
                max_disparity = mean_rate = std_rate = coefficient_of_variation = 0
            
            bias_analysis[attr] = {
                'group_metrics': group_metrics,
                'approval_rates': approval_rates,
                'max_disparity': float(max_disparity),
                'mean_approval_rate': float(mean_rate),
                'std_approval_rate': float(std_rate),
                'coefficient_of_variation': float(coefficient_of_variation),
                'disparity_ratio': float(max(rates_list) / min(rates_list)) if rates_list and min(rates_list) > 0 else 1.0
            }
        
        return bias_analysis
    
    def _calculate_fairness_metrics(self):
        """Calculate comprehensive fairness metrics with adaptive thresholds"""
        fairness_metrics = {}
        
        print(f"\nCalculating fairness metrics for protected attributes: {self.protected_attributes}")
        
        for attr in self.protected_attributes:
            if attr not in self.original_df.columns:
                print(f"  ⚠️  Attribute '{attr}' not found in dataframe")
                continue
            
            groups = self.original_df[attr].unique()
            # Remove NaN/None values from groups
            groups = [g for g in groups if pd.notna(g)]
            
            print(f"  Analyzing '{attr}' with {len(groups)} groups: {list(groups)}")
            
            if len(groups) < 2:
                print(f"  ⚠️  Skipping '{attr}' - needs at least 2 groups")
                continue
            
            # Get metrics for each group
            group_data = {}
            valid_groups = []
            
            for group in groups:
                # Handle different data types
                if pd.isna(group):
                    continue
                    
                group_mask = self.original_df[attr] == group
                group_indices = self.original_df[group_mask].index
                test_indices = self.X_test.index
                common_indices = group_indices.intersection(test_indices)
                
                if len(common_indices) == 0:
                    print(f"    ⚠️  No test samples for group '{group}'")
                    continue
                
                group_pred_indices = [i for i, idx in enumerate(test_indices) if idx in common_indices]
                group_preds = self.y_pred[group_pred_indices]
                group_true = self.y_test.iloc[group_pred_indices].values
                
                if len(group_preds) == 0:
                    continue
                
                # Calculate comprehensive metrics
                positive_rate = np.mean(group_preds)
                negative_rate = 1 - positive_rate
                
                # True positive rate (TPR) - Sensitivity/Recall
                true_positives = np.sum((group_preds == 1) & (group_true == 1))
                actual_positives = np.sum(group_true == 1)
                tpr = true_positives / actual_positives if actual_positives > 0 else 0
                
                # False positive rate (FPR)
                false_positives = np.sum((group_preds == 1) & (group_true == 0))
                actual_negatives = np.sum(group_true == 0)
                fpr = false_positives / actual_negatives if actual_negatives > 0 else 0
                
                # True negative rate (TNR) - Specificity
                true_negatives = np.sum((group_preds == 0) & (group_true == 0))
                tnr = true_negatives / actual_negatives if actual_negatives > 0 else 0
                
                # False negative rate (FNR)
                false_negatives = np.sum((group_preds == 0) & (group_true == 1))
                fnr = false_negatives / actual_positives if actual_positives > 0 else 0
                
                # Precision
                precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
                
                # F1 Score
                f1 = 2 * (precision * tpr) / (precision + tpr) if (precision + tpr) > 0 else 0
                
                # Accuracy
                accuracy = (true_positives + true_negatives) / len(group_preds) if len(group_preds) > 0 else 0
                
                # Selection rate (proportion of positive predictions)
                selection_rate = np.mean(group_preds == 1)
                
                group_data[str(group)] = {
                    'positive_rate': float(positive_rate),
                    'negative_rate': float(negative_rate),
                    'selection_rate': float(selection_rate),
                    'tpr': float(tpr),
                    'fpr': float(fpr),
                    'tnr': float(tnr),
                    'fnr': float(fnr),
                    'precision': float(precision),
                    'f1_score': float(f1),
                    'accuracy': float(accuracy),
                    'sample_size': int(len(group_preds)),
                    'positive_samples': int(actual_positives),
                    'negative_samples': int(actual_negatives)
                }
                valid_groups.append(str(group))
            
            if len(group_data) < 2:
                print(f"  ⚠️  Insufficient valid groups for '{attr}'")
                continue
            
            # Calculate adaptive thresholds based on data characteristics
            total_samples = sum(group_data[g]['sample_size'] for g in valid_groups)
            min_group_size = min(group_data[g]['sample_size'] for g in valid_groups)
            max_group_size = max(group_data[g]['sample_size'] for g in valid_groups)
            
            # Adjust thresholds for small sample sizes or imbalanced groups
            sample_size_factor = min(1.0, min_group_size / 30)  # Relax thresholds for small samples
            imbalance_factor = min_group_size / max_group_size if max_group_size > 0 else 1.0
            
            # Adaptive disparate impact threshold
            di_threshold = 0.8 if sample_size_factor > 0.8 and imbalance_factor > 0.5 else 0.7
            
            # Adaptive statistical parity threshold
            sp_threshold = 0.1 if sample_size_factor > 0.8 else 0.15
            
            # Adaptive equal opportunity threshold
            eo_threshold = 0.1 if sample_size_factor > 0.8 else 0.15
            
            print(f"    Adaptive thresholds: DI={di_threshold:.2f}, SP={sp_threshold:.2f}, EO={eo_threshold:.2f}")
            print(f"    Sample size factor: {sample_size_factor:.2f}, Imbalance factor: {imbalance_factor:.2f}")
            
            # Calculate fairness metrics comparing ALL groups
            positive_rates = [group_data[g]['positive_rate'] for g in valid_groups]
            selection_rates = [group_data[g]['selection_rate'] for g in valid_groups]
            tprs = [group_data[g]['tpr'] for g in valid_groups]
            fprs = [group_data[g]['fpr'] for g in valid_groups]
            fnrs = [group_data[g]['fnr'] for g in valid_groups]
            
            print(f"    Group positive rates: {dict(zip(valid_groups, [f'{r:.3f}' for r in positive_rates]))}")
            
            # Find min and max rates
            min_positive_rate = min(positive_rates) if positive_rates else 0
            max_positive_rate = max(positive_rates) if positive_rates else 0
            mean_positive_rate = np.mean(positive_rates) if positive_rates else 0
            
            min_selection_rate = min(selection_rates) if selection_rates else 0
            max_selection_rate = max(selection_rates) if selection_rates else 0
            
            min_tpr = min(tprs) if tprs else 0
            max_tpr = max(tprs) if tprs else 0
            
            min_fpr = min(fprs) if fprs else 0
            max_fpr = max(fprs) if fprs else 0
            
            min_fnr = min(fnrs) if fnrs else 0
            max_fnr = max(fnrs) if fnrs else 0
            
            # 1. Disparate Impact (4/5ths rule)
            disparate_impact = min_positive_rate / max_positive_rate if max_positive_rate > 0 else 1.0
            di_fair = di_threshold <= disparate_impact <= (1/di_threshold)
            
            # 2. Statistical Parity Difference
            statistical_parity_diff = max_positive_rate - min_positive_rate
            sp_fair = abs(statistical_parity_diff) < sp_threshold
            
            # 3. Equal Opportunity (TPR equality)
            equal_opportunity_diff = max_tpr - min_tpr
            eo_fair = abs(equal_opportunity_diff) < eo_threshold
            
            # 4. Equalized Odds (TPR and FPR equality)
            fpr_diff = max_fpr - min_fpr
            equalized_odds_fair = abs(equal_opportunity_diff) < eo_threshold and abs(fpr_diff) < eo_threshold
            
            # 5. Predictive Parity (Precision equality)
            precisions = [group_data[g]['precision'] for g in valid_groups]
            min_precision = min(precisions) if precisions else 0
            max_precision = max(precisions) if precisions else 0
            precision_diff = max_precision - min_precision
            predictive_parity_fair = abs(precision_diff) < sp_threshold
            
            # 6. Calibration (FNR equality)
            fnr_diff = max_fnr - min_fnr
            calibration_fair = abs(fnr_diff) < eo_threshold
            
            # Calculate overall fairness score for this attribute
            fairness_scores = [
                1.0 if di_fair else abs(1.0 - disparate_impact),
                1.0 if sp_fair else abs(statistical_parity_diff),
                1.0 if eo_fair else abs(equal_opportunity_diff),
                1.0 if equalized_odds_fair else max(abs(equal_opportunity_diff), abs(fpr_diff)),
                1.0 if predictive_parity_fair else abs(precision_diff),
                1.0 if calibration_fair else abs(fnr_diff)
            ]
            attribute_fairness_score = 1.0 - np.mean(fairness_scores)
            
            print(f"    Disparate Impact: {disparate_impact:.3f} {'✓ FAIR' if di_fair else '✗ UNFAIR'}")
            print(f"    Statistical Parity Diff: {statistical_parity_diff:.3f} {'✓ FAIR' if sp_fair else '✗ UNFAIR'}")
            print(f"    Equal Opportunity Diff: {equal_opportunity_diff:.3f} {'✓ FAIR' if eo_fair else '✗ UNFAIR'}")
            print(f"    Attribute Fairness Score: {attribute_fairness_score:.3f}")
            
            fairness_metrics[attr] = {
                'disparate_impact': {
                    'value': float(disparate_impact),
                    'threshold': float(di_threshold),
                    'fair': bool(di_fair),
                    'interpretation': f'Ratio of minimum to maximum positive rates across {len(valid_groups)} groups',
                    'min_group': valid_groups[positive_rates.index(min_positive_rate)],
                    'max_group': valid_groups[positive_rates.index(max_positive_rate)],
                    'min_rate': float(min_positive_rate),
                    'max_rate': float(max_positive_rate)
                },
                'statistical_parity_difference': {
                    'value': float(statistical_parity_diff),
                    'threshold': float(sp_threshold),
                    'fair': bool(sp_fair),
                    'interpretation': f'Difference between maximum and minimum positive rates',
                    'mean_rate': float(mean_positive_rate)
                },
                'equal_opportunity_difference': {
                    'value': float(equal_opportunity_diff),
                    'threshold': float(eo_threshold),
                    'fair': bool(eo_fair),
                    'interpretation': f'Difference in true positive rates (recall) across groups'
                },
                'equalized_odds': {
                    'tpr_diff': float(equal_opportunity_diff),
                    'fpr_diff': float(fpr_diff),
                    'fair': bool(equalized_odds_fair),
                    'interpretation': 'Both TPR and FPR should be equal across groups'
                },
                'predictive_parity': {
                    'precision_diff': float(precision_diff),
                    'fair': bool(predictive_parity_fair),
                    'interpretation': 'Precision should be equal across groups'
                },
                'calibration': {
                    'fnr_diff': float(fnr_diff),
                    'fair': bool(calibration_fair),
                    'interpretation': 'False negative rates should be equal across groups'
                },
                'attribute_fairness_score': float(attribute_fairness_score),
                'group_metrics': group_data,
                'sample_statistics': {
                    'total_samples': int(total_samples),
                    'min_group_size': int(min_group_size),
                    'max_group_size': int(max_group_size),
                    'imbalance_ratio': float(imbalance_factor),
                    'num_groups': int(len(valid_groups))
                }
            }
        
        return fairness_metrics
    
    def _detect_fairness_violations(self):
        """Detect specific fairness violations with detailed analysis"""
        violations = []
        
        fairness_metrics = self.results.get('fairness_metrics', {})
        
        for attr, metrics in fairness_metrics.items():
            # Get sample statistics for context
            sample_stats = metrics.get('sample_statistics', {})
            num_groups = sample_stats.get('num_groups', 0)
            imbalance_ratio = sample_stats.get('imbalance_ratio', 1.0)
            
            # 1. Check disparate impact
            di = metrics.get('disparate_impact', {})
            if not di.get('fair', True):
                severity = self._calculate_severity(
                    di['value'], 
                    di['threshold'], 
                    is_ratio=True,
                    imbalance_ratio=imbalance_ratio
                )
                
                min_group = di.get('min_group', 'Unknown')
                max_group = di.get('max_group', 'Unknown')
                min_rate = di.get('min_rate', 0)
                max_rate = di.get('max_rate', 0)
                
                violations.append({
                    'attribute': attr,
                    'metric': 'Disparate Impact',
                    'value': di['value'],
                    'threshold': di['threshold'],
                    'severity': severity,
                    'message': f"Disparate impact ratio of {di['value']:.3f} violates fairness threshold ({di['threshold']:.2f}-{1/di['threshold']:.2f}). Group '{min_group}' has {min_rate:.1%} approval vs '{max_group}' with {max_rate:.1%}.",
                    'affected_groups': [min_group, max_group],
                    'recommendation': self._get_di_recommendation(di['value'], min_group, max_group)
                })
            
            # 2. Check statistical parity
            spd = metrics.get('statistical_parity_difference', {})
            if not spd.get('fair', True):
                severity = self._calculate_severity(
                    abs(spd['value']), 
                    spd['threshold'],
                    is_ratio=False,
                    imbalance_ratio=imbalance_ratio
                )
                
                violations.append({
                    'attribute': attr,
                    'metric': 'Statistical Parity',
                    'value': spd['value'],
                    'threshold': spd['threshold'],
                    'severity': severity,
                    'message': f"Statistical parity difference of {spd['value']:.3f} exceeds threshold (±{spd['threshold']:.2f}). There's a {abs(spd['value']):.1%} difference in positive prediction rates across groups.",
                    'recommendation': "Review feature importance and consider debiasing techniques like reweighting or threshold optimization."
                })
            
            # 3. Check equal opportunity
            eod = metrics.get('equal_opportunity_difference', {})
            if not eod.get('fair', True):
                severity = self._calculate_severity(
                    abs(eod['value']), 
                    eod['threshold'],
                    is_ratio=False,
                    imbalance_ratio=imbalance_ratio
                )
                
                violations.append({
                    'attribute': attr,
                    'metric': 'Equal Opportunity',
                    'value': eod['value'],
                    'threshold': eod['threshold'],
                    'severity': severity,
                    'message': f"Equal opportunity difference of {eod['value']:.3f} exceeds threshold (±{eod['threshold']:.2f}). True positive rates vary by {abs(eod['value']):.1%} across groups.",
                    'recommendation': "Ensure the model has equal recall across protected groups. Consider adjusting decision thresholds per group."
                })
            
            # 4. Check equalized odds
            eq_odds = metrics.get('equalized_odds', {})
            if not eq_odds.get('fair', True):
                tpr_diff = eq_odds.get('tpr_diff', 0)
                fpr_diff = eq_odds.get('fpr_diff', 0)
                max_diff = max(abs(tpr_diff), abs(fpr_diff))
                
                severity = self._calculate_severity(
                    max_diff, 
                    0.1,
                    is_ratio=False,
                    imbalance_ratio=imbalance_ratio
                )
                
                violations.append({
                    'attribute': attr,
                    'metric': 'Equalized Odds',
                    'value': max_diff,
                    'threshold': 0.1,
                    'severity': severity,
                    'message': f"Equalized odds violated: TPR differs by {abs(tpr_diff):.3f} and FPR differs by {abs(fpr_diff):.3f} across groups.",
                    'recommendation': "Both true positive and false positive rates should be balanced. Consider post-processing methods like reject option classification."
                })
            
            # 5. Check predictive parity
            pred_parity = metrics.get('predictive_parity', {})
            if not pred_parity.get('fair', True):
                precision_diff = pred_parity.get('precision_diff', 0)
                
                severity = self._calculate_severity(
                    abs(precision_diff), 
                    0.1,
                    is_ratio=False,
                    imbalance_ratio=imbalance_ratio
                )
                
                violations.append({
                    'attribute': attr,
                    'metric': 'Predictive Parity',
                    'value': precision_diff,
                    'threshold': 0.1,
                    'severity': severity,
                    'message': f"Predictive parity difference of {precision_diff:.3f}. Precision varies by {abs(precision_diff):.1%} across groups.",
                    'recommendation': "Ensure positive predictions are equally accurate across groups. Review feature selection and calibration."
                })
            
            # 6. Check calibration (FNR equality)
            calibration = metrics.get('calibration', {})
            if not calibration.get('fair', True):
                fnr_diff = calibration.get('fnr_diff', 0)
                
                severity = self._calculate_severity(
                    abs(fnr_diff), 
                    0.1,
                    is_ratio=False,
                    imbalance_ratio=imbalance_ratio
                )
                
                violations.append({
                    'attribute': attr,
                    'metric': 'Calibration (FNR)',
                    'value': fnr_diff,
                    'threshold': 0.1,
                    'severity': severity,
                    'message': f"False negative rates differ by {abs(fnr_diff):.3f} across groups, indicating poor calibration.",
                    'recommendation': "Calibrate model predictions to ensure equal false negative rates. Consider using calibration techniques like Platt scaling."
                })
        
        # Sort violations by severity
        severity_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
        violations.sort(key=lambda x: severity_order.get(x['severity'], 999))
        
        return violations
    
    def _calculate_severity(self, value, threshold, is_ratio=False, imbalance_ratio=1.0):
        """Calculate violation severity based on value, threshold, and data characteristics"""
        if is_ratio:
            # For disparate impact (ratio metric)
            deviation = abs(1.0 - value)
            if deviation > 0.5 or value < 0.4:  # Very severe
                return 'CRITICAL'
            elif deviation > 0.3 or value < 0.6:
                return 'HIGH'
            elif deviation > 0.15:
                return 'MEDIUM'
            else:
                return 'LOW'
        else:
            # For difference metrics
            ratio = abs(value) / threshold if threshold > 0 else 0
            
            # Adjust severity based on group imbalance
            if imbalance_ratio < 0.3:  # Highly imbalanced groups
                if ratio > 3:
                    return 'CRITICAL'
                elif ratio > 2:
                    return 'HIGH'
                elif ratio > 1.5:
                    return 'MEDIUM'
                else:
                    return 'LOW'
            else:
                if ratio > 2.5:
                    return 'CRITICAL'
                elif ratio > 2:
                    return 'HIGH'
                elif ratio > 1.2:
                    return 'MEDIUM'
                else:
                    return 'LOW'
    
    def _get_di_recommendation(self, di_value, min_group, max_group):
        """Get specific recommendation based on disparate impact value"""
        if di_value < 0.5:
            return f"CRITICAL: Group '{min_group}' has less than half the approval rate of '{max_group}'. Investigate for systemic bias. Consider: 1) Reviewing training data for representation issues, 2) Examining feature correlations with protected attribute, 3) Implementing fairness constraints during training."
        elif di_value < 0.7:
            return f"HIGH: Significant disparity between groups. Recommended actions: 1) Analyze feature importance per group, 2) Consider reweighting samples, 3) Explore threshold optimization, 4) Review data collection process for bias."
        else:
            return f"MEDIUM: Moderate disparity detected. Monitor closely and consider: 1) Regular fairness audits, 2) Collecting more diverse training data, 3) Using fairness-aware algorithms."
    
    def _assess_overall_fairness(self):
        """Assess overall fairness of the model with weighted scoring"""
        violations = self.results.get('fairness_violations', [])
        fairness_metrics = self.results.get('fairness_metrics', {})
        
        # Count violations by severity
        critical_count = sum(1 for v in violations if v['severity'] == 'CRITICAL')
        high_severity_count = sum(1 for v in violations if v['severity'] == 'HIGH')
        medium_severity_count = sum(1 for v in violations if v['severity'] == 'MEDIUM')
        low_severity_count = sum(1 for v in violations if v['severity'] == 'LOW')
        
        # Calculate attribute-level fairness scores
        attribute_scores = []
        for attr, metrics in fairness_metrics.items():
            attr_score = metrics.get('attribute_fairness_score', 0)
            attribute_scores.append(attr_score)
        
        avg_attribute_score = np.mean(attribute_scores) if attribute_scores else 0
        
        # Determine if passes threshold (stricter criteria)
        passes_threshold = critical_count == 0 and high_severity_count == 0 and medium_severity_count <= 1
        
        assessment = {
            'passes_fairness_threshold': passes_threshold,
            'critical_violations': critical_count,
            'high_severity_violations': high_severity_count,
            'medium_severity_violations': medium_severity_count,
            'low_severity_violations': low_severity_count,
            'total_violations': len(violations),
            'avg_attribute_fairness_score': float(avg_attribute_score),
            'recommendation': self._get_fairness_recommendation(critical_count, high_severity_count, medium_severity_count)
        }
        
        return assessment
    
    def _get_fairness_recommendation(self, critical_count, high_count, medium_count):
        """Get recommendation based on violation counts"""
        if critical_count > 0:
            return "CRITICAL: Severe bias detected. DO NOT deploy this model without addressing critical fairness violations. Immediate remediation required."
        elif high_count > 0:
            return "HIGH PRIORITY: Significant fairness violations detected. Address high-severity issues before deployment. Consider fairness-aware training methods."
        elif medium_count > 2:
            return "WARNING: Multiple fairness issues detected. Review and address violations before deployment. Regular monitoring recommended."
        elif medium_count > 0:
            return "CAUTION: Minor fairness issues detected. Monitor closely and consider improvements. Regular fairness audits recommended."
        else:
            return "GOOD: No significant fairness violations detected. Continue monitoring to maintain fairness standards."
    
    def _calculate_overall_bias_score(self):
        """Calculate comprehensive overall bias score (0-1, higher means more bias)"""
        scores = []
        weights = []
        
        print("\nCalculating overall bias score...")
        
        # Score from fairness metrics (weighted by multiple fairness criteria)
        fairness_metrics = self.results.get('fairness_metrics', {})
        for attr, metrics in fairness_metrics.items():
            sample_stats = metrics.get('sample_statistics', {})
            num_groups = sample_stats.get('num_groups', 2)
            total_samples = sample_stats.get('total_samples', 1)
            
            # Calculate weight based on sample size (larger samples = more reliable = higher weight)
            sample_weight = min(1.0, total_samples / 100)
            
            # 1. Disparate Impact score (deviation from 1.0)
            di_value = metrics.get('disparate_impact', {}).get('value', 1.0)
            di_threshold = metrics.get('disparate_impact', {}).get('threshold', 0.8)
            
            if di_value < di_threshold:
                di_score = (di_threshold - di_value) / di_threshold
            elif di_value > (1 / di_threshold):
                di_score = (di_value - (1 / di_threshold)) / (1 / di_threshold)
            else:
                di_score = 0
            
            scores.append(di_score)
            weights.append(sample_weight * 1.5)  # Higher weight for disparate impact
            print(f"  {attr} - Disparate Impact: {di_value:.3f} → score: {di_score:.3f} (weight: {sample_weight * 1.5:.2f})")
            
            # 2. Statistical Parity score
            spd_value = abs(metrics.get('statistical_parity_difference', {}).get('value', 0))
            spd_threshold = metrics.get('statistical_parity_difference', {}).get('threshold', 0.1)
            spd_score = min(spd_value / spd_threshold, 1.0) if spd_threshold > 0 else 0
            
            scores.append(spd_score)
            weights.append(sample_weight)
            print(f"  {attr} - Statistical Parity Diff: {spd_value:.3f} → score: {spd_score:.3f} (weight: {sample_weight:.2f})")
            
            # 3. Equal Opportunity score
            eod_value = abs(metrics.get('equal_opportunity_difference', {}).get('value', 0))
            eod_threshold = metrics.get('equal_opportunity_difference', {}).get('threshold', 0.1)
            eod_score = min(eod_value / eod_threshold, 1.0) if eod_threshold > 0 else 0
            
            scores.append(eod_score)
            weights.append(sample_weight)
            print(f"  {attr} - Equal Opportunity Diff: {eod_value:.3f} → score: {eod_score:.3f} (weight: {sample_weight:.2f})")
            
            # 4. Equalized Odds score
            eq_odds = metrics.get('equalized_odds', {})
            tpr_diff = abs(eq_odds.get('tpr_diff', 0))
            fpr_diff = abs(eq_odds.get('fpr_diff', 0))
            eq_odds_score = (min(tpr_diff / 0.1, 1.0) + min(fpr_diff / 0.1, 1.0)) / 2
            
            scores.append(eq_odds_score)
            weights.append(sample_weight * 0.8)
            print(f"  {attr} - Equalized Odds: {max(tpr_diff, fpr_diff):.3f} → score: {eq_odds_score:.3f} (weight: {sample_weight * 0.8:.2f})")
            
            # 5. Predictive Parity score
            pred_parity = metrics.get('predictive_parity', {})
            precision_diff = abs(pred_parity.get('precision_diff', 0))
            pred_parity_score = min(precision_diff / 0.1, 1.0)
            
            scores.append(pred_parity_score)
            weights.append(sample_weight * 0.7)
            print(f"  {attr} - Predictive Parity Diff: {precision_diff:.3f} → score: {pred_parity_score:.3f} (weight: {sample_weight * 0.7:.2f})")
            
            # 6. Calibration score
            calibration = metrics.get('calibration', {})
            fnr_diff = abs(calibration.get('fnr_diff', 0))
            calibration_score = min(fnr_diff / 0.1, 1.0)
            
            scores.append(calibration_score)
            weights.append(sample_weight * 0.7)
            print(f"  {attr} - Calibration (FNR): {fnr_diff:.3f} → score: {calibration_score:.3f} (weight: {sample_weight * 0.7:.2f})")
        
        # Calculate weighted average
        if scores and weights:
            total_weight = sum(weights)
            if total_weight > 0:
                overall_score = sum(s * w for s, w in zip(scores, weights)) / total_weight
            else:
                overall_score = np.mean(scores)
        else:
            overall_score = 0.5  # Default if no metrics available
        
        # Apply non-linear scaling to emphasize high bias
        overall_score = min(overall_score ** 0.8, 1.0)
        
        print(f"\n  Overall Bias Score: {overall_score:.3f}")
        
        return float(overall_score)
