"""
Generalized Model Trainer Module
Trains ML models for binary/multi-class classification
"""

import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix, classification_report, roc_auc_score
)
import warnings
warnings.filterwarnings('ignore')

class GeneralizedModelTrainer:
    """Train and evaluate machine learning models"""
    
    def __init__(self, X_train, X_test, y_train, y_test, feature_names):
        self.X_train = X_train
        self.X_test = X_test
        self.y_train = y_train
        self.y_test = y_test
        self.feature_names = feature_names
        self.model = None
        self.y_pred = None
        self.y_pred_proba = None
        self.results = {}
    
    def train(self, model_type='random_forest'):
        """Train the model"""
        if model_type == 'random_forest':
            self.model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=-1
            )
        elif model_type == 'gradient_boosting':
            self.model = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42
            )
        elif model_type == 'logistic_regression':
            self.model = LogisticRegression(
                max_iter=1000,
                random_state=42,
                n_jobs=-1
            )
        
        # Train the model
        self.model.fit(self.X_train, self.y_train)
        
        # Make predictions
        self.y_pred = self.model.predict(self.X_test)
        
        # Get prediction probabilities
        if hasattr(self.model, 'predict_proba'):
            self.y_pred_proba = self.model.predict_proba(self.X_test)
        
        return self.model
    
    def evaluate(self):
        """Evaluate model performance"""
        # Calculate metrics
        accuracy = accuracy_score(self.y_test, self.y_pred)
        
        # Handle binary and multi-class cases
        average = 'binary' if len(np.unique(self.y_test)) == 2 else 'weighted'
        
        precision = precision_score(self.y_test, self.y_pred, average=average, zero_division=0)
        recall = recall_score(self.y_test, self.y_pred, average=average, zero_division=0)
        f1 = f1_score(self.y_test, self.y_pred, average=average, zero_division=0)
        
        # Confusion matrix
        cm = confusion_matrix(self.y_test, self.y_pred)
        
        # Classification report
        report = classification_report(self.y_test, self.y_pred, output_dict=True, zero_division=0)
        
        # ROC AUC (for binary classification)
        roc_auc = None
        if len(np.unique(self.y_test)) == 2 and self.y_pred_proba is not None:
            try:
                roc_auc = roc_auc_score(self.y_test, self.y_pred_proba[:, 1])
            except:
                roc_auc = None
        
        # Feature importance
        feature_importance = {}
        if hasattr(self.model, 'feature_importances_'):
            importances = self.model.feature_importances_
            feature_importance = dict(zip(self.feature_names, importances))
            # Sort by importance
            feature_importance = dict(sorted(feature_importance.items(), key=lambda x: x[1], reverse=True))
        
        # Store results
        self.results = {
            'model_type': type(self.model).__name__,
            'metrics': {
                'accuracy': float(accuracy),
                'precision': float(precision),
                'recall': float(recall),
                'f1': float(f1),
                'roc_auc': float(roc_auc) if roc_auc else None
            },
            'confusion_matrix': cm.tolist(),
            'classification_report': report,
            'feature_importance': feature_importance,
            'predictions': {
                'y_true': self.y_test.tolist() if hasattr(self.y_test, 'tolist') else list(self.y_test),
                'y_pred': self.y_pred.tolist() if hasattr(self.y_pred, 'tolist') else list(self.y_pred)
            }
        }
        
        return self.results
    
    def get_model_complexity(self):
        """Assess model complexity for risk analysis"""
        complexity = {
            'interpretability': 'medium',
            'complexity_score': 0.5
        }
        
        if isinstance(self.model, LogisticRegression):
            complexity['interpretability'] = 'high'
            complexity['complexity_score'] = 0.2
        elif isinstance(self.model, (RandomForestClassifier, GradientBoostingClassifier)):
            complexity['interpretability'] = 'medium'
            complexity['complexity_score'] = 0.6
        
        return complexity
    
    def predict(self, X):
        """Make predictions on new data"""
        if self.model is None:
            raise ValueError("Model not trained yet")
        return self.model.predict(X)
    
    def predict_proba(self, X):
        """Get prediction probabilities"""
        if self.model is None:
            raise ValueError("Model not trained yet")
        if hasattr(self.model, 'predict_proba'):
            return self.model.predict_proba(X)
        return None
