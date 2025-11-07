"""
AI Governance Module - Bias Detection and Risk Analysis
"""

from .data_processor import DataProcessor
from .model_trainer import GeneralizedModelTrainer
from .bias_analyzer import BiasAnalyzer
from .risk_analyzer import RiskAnalyzer
from .report_generator import ReportGenerator, NumpyEncoder

import pandas as pd
import json

__version__ = '1.0.0'

__all__ = [
    'DataProcessor',
    'GeneralizedModelTrainer',
    'BiasAnalyzer',
    'RiskAnalyzer',
    'ReportGenerator',
    'NumpyEncoder',
    'AIGovernanceAnalyzer'
]


class AIGovernanceAnalyzer:
    """
    Main interface for AI Governance analysis
    
    Example:
        >>> analyzer = AIGovernanceAnalyzer()
        >>> report = analyzer.analyze('data.csv', 'target', ['gender', 'age'])
        >>> print(f"Bias Score: {report['summary']['overall_bias_score']:.3f}")
    """
    
    def __init__(self):
        """Initialize the analyzer"""
        self.processor = None
        self.trainer = None
        self.bias_analyzer = None
        self.risk_analyzer = None
        self.report_generator = None
    
    def analyze(self, data_path, target_column, protected_attributes):
        """
        Run complete AI governance analysis from file
        
        Args:
            data_path (str): Path to CSV file
            target_column (str): Name of target column
            protected_attributes (list): List of protected attribute column names
            
        Returns:
            dict: Complete analysis report
        """
        df = pd.read_csv(data_path)
        return self.analyze_dataframe(df, target_column, protected_attributes)
    
    def analyze_dataframe(self, df, target_column, protected_attributes):
        """
        Run complete AI governance analysis from DataFrame
        
        Args:
            df (pd.DataFrame): Input dataframe
            target_column (str): Name of target column
            protected_attributes (list): List of protected attribute column names
            
        Returns:
            dict: Complete analysis report
        """
        # Step 1: Process data
        self.processor = DataProcessor(df)
        self.processor.target_column = target_column
        self.processor.protected_attributes = protected_attributes
        self.processor.prepare_data()
        
        # Step 2: Train model
        self.trainer = GeneralizedModelTrainer(
            self.processor.X_train,
            self.processor.X_test,
            self.processor.y_train,
            self.processor.y_test,
            self.processor.feature_names
        )
        self.trainer.train()
        self.trainer.evaluate()
        
        # Step 3: Analyze bias (Presidio disabled by default to avoid initialization issues)
        self.bias_analyzer = BiasAnalyzer(
            self.processor.X_test,
            self.processor.y_test,
            self.trainer.y_pred,
            self.processor.df,
            self.processor.protected_attributes,
            self.processor.target_column,
            use_presidio=False  # Set to True to enable Presidio-enhanced detection
        )
        bias_results = self.bias_analyzer.analyze()
        
        # Step 4: Assess risks with Presidio-enhanced detection
        self.risk_analyzer = RiskAnalyzer(
            self.processor.df,
            self.trainer.results,
            bias_results,
            self.processor.protected_attributes,
            self.processor.target_column,
            use_presidio=False  # Set to True after installing: python -m spacy download en_core_web_sm
        )
        risk_results = self.risk_analyzer.analyze()
        
        # Step 5: Generate report
        self.report_generator = ReportGenerator(
            self.trainer.results,
            bias_results,
            risk_results,
            self.processor.df
        )
        
        return self.report_generator.generate_report()
    
    def save_report(self, report, output_path):
        """
        Save report to JSON file
        
        Args:
            report (dict): Analysis report
            output_path (str): Path to save JSON file
            
        Returns:
            str: Path to saved file
        """
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2, cls=NumpyEncoder)
        return output_path
    
    def get_summary(self, report):
        """
        Get executive summary from report
        
        Args:
            report (dict): Analysis report
            
        Returns:
            dict: Summary metrics
        """
        return report.get('summary', {})
