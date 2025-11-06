"""
Bias Analyzer Module
Detects and quantifies bias in ML models
"""

import numpy as np
import pandas as pd
from collections import defaultdict

class BiasAnalyzer:
    """Analyze bias in ML model predictions"""
    
    def __init__(self, X_test, y_test, y_pred, original_df, protected_attributes, target_column):
        self.X_test = X_test
        self.y_test = y_test
        self.y_pred = y_pred
        self.original_df = original_df
        self.protected_attributes = protected_attributes
        self.target_column = target_column
        self.results = {}
    
    def analyze(self):
        """Perform comprehensive bias analysis"""
        self.results = {
            'demographic_bias': self._analyze_demographic_bias(),
            'fairness_metrics': self._calculate_fairness_metrics(),
            'fairness_violations': self._detect_fairness_violations(),
            'fairness_assessment': self._assess_overall_fairness(),
            'overall_bias_score': 0.0
        }
        
        # Calculate overall bias score
        self.results['overall_bias_score'] = self._calculate_overall_bias_score()
        
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
                
                group_metrics[str(group)] = {
                    'sample_size': len(group_preds),
                    'approval_rate': float(approval_rate),
                    'accuracy': float(accuracy),
                    'positive_predictions': int(np.sum(group_preds)),
                    'negative_predictions': int(len(group_preds) - np.sum(group_preds))
                }
            
            bias_analysis[attr] = {
                'group_metrics': group_metrics,
                'approval_rates': approval_rates,
                'max_disparity': float(max(approval_rates.values()) - min(approval_rates.values())) if approval_rates else 0
            }
        
        return bias_analysis
    
    def _calculate_fairness_metrics(self):
        """Calculate standard fairness metrics"""
        fairness_metrics = {}
        
        for attr in self.protected_attributes:
            if attr not in self.original_df.columns:
                continue
            
            groups = self.original_df[attr].unique()
            if len(groups) < 2:
                continue
            
            # Get metrics for each group
            group_data = {}
            for group in groups:
                group_mask = self.original_df[attr] == group
                group_indices = self.original_df[group_mask].index
                test_indices = self.X_test.index
                common_indices = group_indices.intersection(test_indices)
                
                if len(common_indices) == 0:
                    continue
                
                group_pred_indices = [i for i, idx in enumerate(test_indices) if idx in common_indices]
                group_preds = self.y_pred[group_pred_indices]
                group_true = self.y_test.iloc[group_pred_indices]
                
                if len(group_preds) == 0:
                    continue
                
                # Calculate metrics
                positive_rate = np.mean(group_preds)
                
                # True positive rate (TPR) - Recall
                true_positives = np.sum((group_preds == 1) & (group_true == 1))
                actual_positives = np.sum(group_true == 1)
                tpr = true_positives / actual_positives if actual_positives > 0 else 0
                
                # False positive rate (FPR)
                false_positives = np.sum((group_preds == 1) & (group_true == 0))
                actual_negatives = np.sum(group_true == 0)
                fpr = false_positives / actual_negatives if actual_negatives > 0 else 0
                
                group_data[str(group)] = {
                    'positive_rate': float(positive_rate),
                    'tpr': float(tpr),
                    'fpr': float(fpr),
                    'sample_size': len(group_preds)
                }
            
            if len(group_data) < 2:
                continue
            
            # Calculate disparate impact
            group_names = list(group_data.keys())
            reference_group = group_names[0]
            comparison_group = group_names[1]
            
            ref_positive_rate = group_data[reference_group]['positive_rate']
            comp_positive_rate = group_data[comparison_group]['positive_rate']
            
            disparate_impact = comp_positive_rate / ref_positive_rate if ref_positive_rate > 0 else 0
            
            # Calculate statistical parity difference
            statistical_parity_diff = comp_positive_rate - ref_positive_rate
            
            # Calculate equal opportunity difference
            ref_tpr = group_data[reference_group]['tpr']
            comp_tpr = group_data[comparison_group]['tpr']
            equal_opportunity_diff = comp_tpr - ref_tpr
            
            fairness_metrics[attr] = {
                'disparate_impact': {
                    'value': float(disparate_impact),
                    'threshold': 0.8,
                    'fair': 0.8 <= disparate_impact <= 1.25,
                    'interpretation': 'Ratio of positive rates between groups'
                },
                'statistical_parity_difference': {
                    'value': float(statistical_parity_diff),
                    'threshold': 0.1,
                    'fair': abs(statistical_parity_diff) < 0.1,
                    'interpretation': 'Difference in positive rates'
                },
                'equal_opportunity_difference': {
                    'value': float(equal_opportunity_diff),
                    'threshold': 0.1,
                    'fair': abs(equal_opportunity_diff) < 0.1,
                    'interpretation': 'Difference in true positive rates'
                },
                'group_metrics': group_data
            }
        
        return fairness_metrics
    
    def _detect_fairness_violations(self):
        """Detect specific fairness violations"""
        violations = []
        
        fairness_metrics = self.results.get('fairness_metrics', {})
        
        for attr, metrics in fairness_metrics.items():
            # Check disparate impact
            di = metrics.get('disparate_impact', {})
            if not di.get('fair', True):
                violations.append({
                    'attribute': attr,
                    'metric': 'Disparate Impact',
                    'value': di['value'],
                    'threshold': di['threshold'],
                    'severity': 'HIGH' if di['value'] < 0.5 or di['value'] > 2.0 else 'MEDIUM',
                    'message': f"Disparate impact ratio of {di['value']:.3f} violates fairness threshold (0.8-1.25)"
                })
            
            # Check statistical parity
            spd = metrics.get('statistical_parity_difference', {})
            if not spd.get('fair', True):
                violations.append({
                    'attribute': attr,
                    'metric': 'Statistical Parity',
                    'value': spd['value'],
                    'threshold': spd['threshold'],
                    'severity': 'HIGH' if abs(spd['value']) > 0.2 else 'MEDIUM',
                    'message': f"Statistical parity difference of {spd['value']:.3f} exceeds threshold (0.1)"
                })
            
            # Check equal opportunity
            eod = metrics.get('equal_opportunity_difference', {})
            if not eod.get('fair', True):
                violations.append({
                    'attribute': attr,
                    'metric': 'Equal Opportunity',
                    'value': eod['value'],
                    'threshold': eod['threshold'],
                    'severity': 'HIGH' if abs(eod['value']) > 0.2 else 'MEDIUM',
                    'message': f"Equal opportunity difference of {eod['value']:.3f} exceeds threshold (0.1)"
                })
        
        return violations
    
    def _assess_overall_fairness(self):
        """Assess overall fairness of the model"""
        violations = self.results.get('fairness_violations', [])
        
        high_severity_count = sum(1 for v in violations if v['severity'] == 'HIGH')
        medium_severity_count = sum(1 for v in violations if v['severity'] == 'MEDIUM')
        
        passes_threshold = high_severity_count == 0 and medium_severity_count <= 1
        
        assessment = {
            'passes_fairness_threshold': passes_threshold,
            'high_severity_violations': high_severity_count,
            'medium_severity_violations': medium_severity_count,
            'total_violations': len(violations),
            'recommendation': self._get_fairness_recommendation(high_severity_count, medium_severity_count)
        }
        
        return assessment
    
    def _get_fairness_recommendation(self, high_count, medium_count):
        """Get recommendation based on violation counts"""
        if high_count > 0:
            return "CRITICAL: Immediate action required to address high-severity fairness violations"
        elif medium_count > 2:
            return "WARNING: Multiple fairness issues detected. Review and address violations"
        elif medium_count > 0:
            return "CAUTION: Minor fairness issues detected. Monitor and consider improvements"
        else:
            return "GOOD: No significant fairness violations detected"
    
    def _calculate_overall_bias_score(self):
        """Calculate overall bias score (0-1, lower is better)"""
        scores = []
        
        # Score from fairness metrics
        fairness_metrics = self.results.get('fairness_metrics', {})
        for attr, metrics in fairness_metrics.items():
            # Disparate impact score (deviation from 1.0)
            di_value = metrics.get('disparate_impact', {}).get('value', 1.0)
            di_score = abs(1.0 - di_value)
            scores.append(min(di_score, 1.0))
            
            # Statistical parity score
            spd_value = abs(metrics.get('statistical_parity_difference', {}).get('value', 0))
            scores.append(min(spd_value * 5, 1.0))  # Scale to 0-1
            
            # Equal opportunity score
            eod_value = abs(metrics.get('equal_opportunity_difference', {}).get('value', 0))
            scores.append(min(eod_value * 5, 1.0))  # Scale to 0-1
        
        # Average all scores
        overall_score = np.mean(scores) if scores else 0.0
        
        return float(overall_score)
