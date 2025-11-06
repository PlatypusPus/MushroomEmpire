"""
Data Processor Module
Handles data loading, preprocessing, and feature detection
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
import re

class DataProcessor:
    """Process and prepare data for analysis"""
    
    def __init__(self, df):
        self.df = df.copy()
        self.original_df = df.copy()
        self.target_column = None
        self.protected_attributes = []
        self.numerical_features = []
        self.categorical_features = []
        self.feature_names = []
        self.encoders = {}
        self.scaler = StandardScaler()
        
        self.X_train = None
        self.X_test = None
        self.y_train = None
        self.y_test = None
        
        # Auto-detect column types
        self._detect_column_types()
    
    def _detect_column_types(self):
        """Automatically detect numerical and categorical columns"""
        for col in self.df.columns:
            if self.df[col].dtype in ['int64', 'float64']:
                # Check if it's actually categorical (few unique values)
                if self.df[col].nunique() < 10 and self.df[col].nunique() / len(self.df) < 0.05:
                    self.categorical_features.append(col)
                else:
                    self.numerical_features.append(col)
            else:
                self.categorical_features.append(col)
    
    def _detect_pii_columns(self):
        """Detect potential PII columns"""
        pii_keywords = [
            'name', 'email', 'phone', 'address', 'ssn', 'social',
            'passport', 'license', 'id', 'zip', 'postal'
        ]
        
        pii_columns = []
        for col in self.df.columns:
            col_lower = col.lower()
            if any(keyword in col_lower for keyword in pii_keywords):
                pii_columns.append(col)
        
        return pii_columns
    
    def prepare_data(self, test_size=0.2, random_state=42):
        """Prepare data for model training"""
        # Handle missing values
        self.df = self.df.dropna()
        
        # Separate features and target
        if self.target_column is None:
            # Auto-detect target (last column or column with 'target', 'label', 'status')
            target_candidates = [col for col in self.df.columns 
                               if any(keyword in col.lower() for keyword in ['target', 'label', 'status', 'class'])]
            self.target_column = target_candidates[0] if target_candidates else self.df.columns[-1]
        
        # Prepare features
        feature_cols = [col for col in self.df.columns if col != self.target_column]
        X = self.df[feature_cols].copy()
        y = self.df[self.target_column].copy()
        
        # Encode categorical variables
        for col in self.categorical_features:
            if col in X.columns:
                le = LabelEncoder()
                X[col] = le.fit_transform(X[col].astype(str))
                self.encoders[col] = le
        
        # Store feature names
        self.feature_names = X.columns.tolist()
        
        # Split data
        self.X_train, self.X_test, self.y_train, self.y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, stratify=y if y.nunique() < 10 else None
        )
        
        # Scale numerical features
        numerical_cols = [col for col in self.numerical_features if col in self.X_train.columns]
        if numerical_cols:
            self.X_train[numerical_cols] = self.scaler.fit_transform(self.X_train[numerical_cols])
            self.X_test[numerical_cols] = self.scaler.transform(self.X_test[numerical_cols])
        
        return self.X_train, self.X_test, self.y_train, self.y_test
    
    def get_data_summary(self):
        """Get summary statistics of the dataset"""
        summary = {
            'total_records': len(self.df),
            'total_features': len(self.df.columns),
            'numerical_features': len(self.numerical_features),
            'categorical_features': len(self.categorical_features),
            'missing_values': self.df.isnull().sum().to_dict(),
            'target_column': self.target_column,
            'protected_attributes': self.protected_attributes,
            'pii_columns': self._detect_pii_columns(),
            'target_distribution': self.df[self.target_column].value_counts().to_dict() if self.target_column else {}
        }
        return summary
    
    def get_protected_attribute_stats(self):
        """Get statistics for protected attributes"""
        stats = {}
        for attr in self.protected_attributes:
            if attr in self.df.columns:
                stats[attr] = {
                    'unique_values': self.df[attr].nunique(),
                    'value_counts': self.df[attr].value_counts().to_dict(),
                    'missing_count': self.df[attr].isnull().sum()
                }
        return stats
