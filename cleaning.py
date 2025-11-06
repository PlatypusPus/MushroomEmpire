"""
Data Cleaning Module - PII Detection and Anonymization
Handles GDPR-compliant data cleaning using Presidio for PII detection
"""

import pandas as pd
import numpy as np
import hashlib
import json
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict

try:
    from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_anonymizer import AnonymizerEngine
    from presidio_anonymizer.entities import OperatorConfig
    PRESIDIO_AVAILABLE = True
except ImportError:
    PRESIDIO_AVAILABLE = False
    print("Warning: Presidio not installed. Run: pip install presidio-analyzer presidio-anonymizer")


class CleaningConfig:
    """Configuration for data cleaning strategies"""
    
    # Anonymization strategy mapping based on entity type and risk level
    STRATEGY_MAP = {
        # HIGH RISK - Remove completely (sensitive financial/identity data)
        "CREDIT_CARD": "REMOVE",
        "CRYPTO": "REMOVE",
        "IBAN_CODE": "REMOVE",
        "US_SSN": "REMOVE",
        "US_BANK_NUMBER": "REMOVE",
        "US_DRIVER_LICENSE": "REMOVE",
        "US_PASSPORT": "REMOVE",
        "MEDICAL_LICENSE": "REMOVE",
        
        # MEDIUM RISK - Hash (deterministic, irreversible)
        "EMAIL_ADDRESS": "HASH",
        "PHONE_NUMBER": "HASH",
        "PERSON": "HASH",  # Names
        "URL": "HASH",
        "IP_ADDRESS": "HASH",
        "AU_ABN": "HASH",
        "AU_ACN": "HASH",
        "AU_TFN": "HASH",
        
        # LOW RISK - Mask (keep format, hide details)
        "LOCATION": "MASK",
        "DATE_TIME": "GENERALIZE",
        "NRP": "MASK",  # Nationality/religious/political
        "US_ITIN": "MASK",
        
        # Numeric identifiers - depends on context
        "UK_NHS": "HASH",
        "SG_NRIC_FIN": "HASH",
        "IN_PAN": "HASH",
    }
    
    # Confidence thresholds
    HIGH_CONFIDENCE = 0.85
    MEDIUM_CONFIDENCE = 0.60
    
    # Risk levels
    RISK_LEVELS = {
        "REMOVE": "HIGH",
        "HASH": "MEDIUM", 
        "MASK": "LOW",
        "GENERALIZE": "LOW"
    }
    
    # GDPR compliance mapping
    GDPR_ARTICLE_MAPPING = {
        "CREDIT_CARD": "Art. 4(1) - Personal data identifier",
        "US_SSN": "Art. 4(1) - Personal data identifier",
        "EMAIL_ADDRESS": "Art. 4(1) - Personal data identifier",
        "PHONE_NUMBER": "Art. 4(1) - Personal data identifier",
        "PERSON": "Art. 4(1) - Personal data (name)",
        "LOCATION": "Art. 4(1) - Personal data (location)",
        "IP_ADDRESS": "Art. 4(1) - Online identifier",
        "MEDICAL_LICENSE": "Art. 9(1) - Special category data (health)",
        "NRP": "Art. 9(1) - Special category data (political/religious views)",
    }


class DataCleaner:
    """
    Main class for detecting and anonymizing PII in datasets
    
    Example:
        >>> cleaner = DataCleaner(df)
        >>> cleaned_df, audit_report = cleaner.clean(
        ...     risky_features=['email', 'phone'],
        ...     interactive=True
        ... )
    """
    
    def __init__(self, df: pd.DataFrame, config: Optional[CleaningConfig] = None):
        """
        Initialize the data cleaner
        
        Args:
            df: Input DataFrame to clean
            config: Optional custom configuration
        """
        self.df = df.copy()
        self.config = config or CleaningConfig()
        self.audit_log = []
        self.cleaning_actions = {}
        
        # Initialize Presidio engines
        if PRESIDIO_AVAILABLE:
            self._init_presidio()
        else:
            raise ImportError(
                "Presidio is required for data cleaning. "
                "Install with: pip install presidio-analyzer presidio-anonymizer"
            )
    
    def _init_presidio(self):
        """Initialize Presidio analyzer and anonymizer engines"""
        # Create NLP engine configuration
        configuration = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        }
        
        try:
            # Create NLP engine
            provider = NlpEngineProvider(nlp_configuration=configuration)
            nlp_engine = provider.create_engine()
            
            # Create analyzer with NLP engine
            self.analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
            self.anonymizer = AnonymizerEngine()
            
            print("✓ Presidio engines initialized successfully")
        except Exception as e:
            # Fallback to default configuration if spaCy model not available
            print(f"Warning: Could not load spaCy model, using default configuration: {e}")
            print("Download spaCy model with: python -m spacy download en_core_web_sm")
            self.analyzer = AnalyzerEngine()
            self.anonymizer = AnonymizerEngine()
    
    def clean(
        self, 
        risky_features: Optional[List[str]] = None,
        interactive: bool = True,
        scan_all_cells: bool = True
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Main cleaning method - detect and anonymize PII
        
        Args:
            risky_features: List of column names flagged as risky (from RiskAnalyzer)
            interactive: Whether to prompt user for ambiguous cases
            scan_all_cells: Whether to scan cell contents for embedded PII
            
        Returns:
            Tuple of (cleaned_df, audit_report)
        """
        print("\n" + "="*70)
        print("🔒 GDPR-COMPLIANT DATA CLEANING - PRESIDIO PII DETECTION")
        print("="*70 + "\n")
        
        cleaned_df = self.df.copy()
        
        # Step 1: Detect PII in flagged columns and text fields
        print("Step 1/4: Detecting PII using Presidio...")
        pii_detections = self._detect_pii(cleaned_df, risky_features, scan_all_cells)
        
        if not pii_detections:
            print("✓ No PII detected in dataset")
            return cleaned_df, self._generate_audit_report(cleaned_df)
        
        # Step 2: Classify by risk level
        print("\nStep 2/4: Classifying PII by risk level...")
        risk_classification = self._classify_risk(pii_detections)
        self._display_risk_summary(risk_classification)
        
        # Step 3: Apply anonymization strategies
        print("\nStep 3/4: Applying anonymization strategies...")
        for column, detections in pii_detections.items():
            cleaned_df = self._process_column(
                cleaned_df, 
                column, 
                detections,
                interactive
            )
        
        # Step 4: Generate audit report
        print("\nStep 4/4: Generating audit report...")
        audit_report = self._generate_audit_report(cleaned_df)
        
        print("\n" + "="*70)
        print("✓ DATA CLEANING COMPLETED")
        print("="*70 + "\n")
        
        return cleaned_df, audit_report
    
    def _detect_pii(
        self, 
        df: pd.DataFrame, 
        risky_columns: Optional[List[str]],
        scan_all_cells: bool
    ) -> Dict[str, List[Dict]]:
        """
        Detect PII at column and cell level
        
        Returns:
            Dictionary mapping column names to list of detected entities
        """
        pii_detections = defaultdict(list)
        
        # Determine which columns to scan
        if risky_columns:
            columns_to_scan = [col for col in risky_columns if col in df.columns]
        else:
            # Scan all text/object columns if no risky features specified
            columns_to_scan = df.select_dtypes(include=['object']).columns.tolist()
        
        # Also scan all text columns if requested
        if scan_all_cells:
            text_columns = df.select_dtypes(include=['object']).columns.tolist()
            columns_to_scan = list(set(columns_to_scan + text_columns))
        
        print(f"  Scanning {len(columns_to_scan)} columns: {columns_to_scan}")
        
        for column in columns_to_scan:
            print(f"  Analyzing '{column}'...", end=" ")
            
            # Sample values for analysis (avoid scanning millions of rows)
            sample_values = df[column].dropna().astype(str).head(1000).tolist()
            
            if not sample_values:
                print("(empty)")
                continue
            
            # Combine sample values for batch analysis
            combined_text = " | ".join(sample_values[:100])  # Limit to first 100
            
            # Analyze with Presidio
            results = self.analyzer.analyze(
                text=combined_text,
                language='en',
                entities=None  # Detect all entity types
            )
            
            if results:
                # Aggregate by entity type
                entity_summary = defaultdict(lambda: {'count': 0, 'scores': []})
                
                for result in results:
                    entity_summary[result.entity_type]['count'] += 1
                    entity_summary[result.entity_type]['scores'].append(result.score)
                
                # Store detection results
                for entity_type, info in entity_summary.items():
                    avg_confidence = np.mean(info['scores'])
                    pii_detections[column].append({
                        'entity_type': entity_type,
                        'count': info['count'],
                        'avg_confidence': avg_confidence,
                        'max_confidence': max(info['scores']),
                        'min_confidence': min(info['scores'])
                    })
                
                detected_types = [d['entity_type'] for d in pii_detections[column]]
                print(f"✓ Found: {', '.join(detected_types)}")
            else:
                print("(no PII)")
        
        return dict(pii_detections)
    
    def _classify_risk(self, pii_detections: Dict[str, List[Dict]]) -> Dict[str, Dict]:
        """
        Classify detected PII by risk level
        
        Returns:
            Dictionary with HIGH/MEDIUM/LOW risk classifications
        """
        risk_classification = {
            'HIGH': defaultdict(list),
            'MEDIUM': defaultdict(list),
            'LOW': defaultdict(list),
            'UNKNOWN': defaultdict(list)
        }
        
        for column, detections in pii_detections.items():
            for detection in detections:
                entity_type = detection['entity_type']
                strategy = self.config.STRATEGY_MAP.get(entity_type, 'UNKNOWN')
                risk_level = self.config.RISK_LEVELS.get(strategy, 'UNKNOWN')
                
                risk_classification[risk_level][column].append({
                    'entity_type': entity_type,
                    'strategy': strategy,
                    'confidence': detection['avg_confidence'],
                    'count': detection['count']
                })
        
        return risk_classification
    
    def _display_risk_summary(self, risk_classification: Dict[str, Dict]):
        """Display risk summary to user"""
        for risk_level in ['HIGH', 'MEDIUM', 'LOW', 'UNKNOWN']:
            detections = risk_classification[risk_level]
            if detections:
                symbol = "🔴" if risk_level == "HIGH" else "🟡" if risk_level == "MEDIUM" else "🟢"
                print(f"\n  {symbol} {risk_level} RISK:")
                for column, entities in detections.items():
                    entity_list = [f"{e['entity_type']} ({e['count']})" for e in entities]
                    print(f"    - {column}: {', '.join(entity_list)}")
    
    def _process_column(
        self, 
        df: pd.DataFrame, 
        column: str, 
        detections: List[Dict],
        interactive: bool
    ) -> pd.DataFrame:
        """
        Process a single column with detected PII
        
        Args:
            df: DataFrame to modify
            column: Column name
            detections: List of PII detections in this column
            interactive: Whether to prompt user
            
        Returns:
            Modified DataFrame
        """
        # Determine strategies for each entity type
        strategies = {}
        needs_prompt = []
        
        for detection in detections:
            entity_type = detection['entity_type']
            confidence = detection['avg_confidence']
            default_strategy = self.config.STRATEGY_MAP.get(entity_type)
            
            # Decide if we need to prompt user
            if confidence < self.config.MEDIUM_CONFIDENCE or default_strategy is None:
                needs_prompt.append(detection)
            else:
                strategies[entity_type] = default_strategy
        
        # Interactive prompts for ambiguous cases
        if interactive and needs_prompt:
            print(f"\n  ⚠️  Column '{column}' has ambiguous PII detections:")
            for i, detection in enumerate(needs_prompt, 1):
                print(f"    {i}. {detection['entity_type']} "
                      f"(confidence: {detection['avg_confidence']:.2f}, "
                      f"count: {detection['count']})")
            
            strategy = self._prompt_user_strategy(column, needs_prompt)
            for detection in needs_prompt:
                strategies[detection['entity_type']] = strategy
        
        # Apply strategies
        action_log = {
            'column': column,
            'detections': detections,
            'strategies': strategies,
            'examples': []
        }
        
        # Determine overall column strategy (most conservative)
        if 'REMOVE' in strategies.values():
            # Remove entire column
            df = df.drop(columns=[column])
            action_log['action'] = 'REMOVED_COLUMN'
            action_log['reason'] = "Contains HIGH risk PII requiring removal"
            print(f"    ❌ Removed column '{column}' (HIGH risk PII)")
        else:
            # Anonymize cell-by-cell
            original_values = df[column].copy()
            df[column] = df[column].apply(
                lambda x: self._anonymize_value(str(x), strategies) if pd.notna(x) else x
            )
            
            # Collect examples
            action_log['examples'] = self._collect_examples(original_values, df[column], 5)
            action_log['action'] = 'ANONYMIZED'
            action_log['num_affected'] = (original_values != df[column]).sum()
            
            strategy_desc = ', '.join(set(strategies.values()))
            print(f"    ✓ Anonymized column '{column}' using {strategy_desc}")
        
        self.cleaning_actions[column] = action_log
        return df
    
    def _anonymize_value(self, value: str, strategies: Dict[str, str]) -> str:
        """
        Anonymize a single cell value based on detected PII types
        
        Args:
            value: Original value
            strategies: Dictionary of entity_type -> strategy
            
        Returns:
            Anonymized value
        """
        if not value or value == 'nan':
            return value
        
        # Analyze this specific value
        results = self.analyzer.analyze(text=value, language='en')
        
        if not results:
            return value  # No PII detected
        
        # Apply anonymization using Presidio
        anonymized_result = self.anonymizer.anonymize(
            text=value,
            analyzer_results=results,
            operators=self._get_presidio_operators(strategies)
        )
        
        return anonymized_result.text
    
    def _get_presidio_operators(self, strategies: Dict[str, str]) -> Dict[str, OperatorConfig]:
        """
        Convert our strategies to Presidio operators
        
        Args:
            strategies: Dictionary of entity_type -> strategy
            
        Returns:
            Dictionary of entity_type -> OperatorConfig
        """
        operators = {}
        
        for entity_type, strategy in strategies.items():
            if strategy == 'HASH':
                operators[entity_type] = OperatorConfig("hash", {"hash_type": "sha256"})
            elif strategy == 'MASK':
                operators[entity_type] = OperatorConfig("mask", {
                    "masking_char": "*",
                    "chars_to_mask": 100,
                    "from_end": False
                })
            elif strategy == 'GENERALIZE':
                operators[entity_type] = OperatorConfig("replace", {"new_value": "[REDACTED]"})
            else:  # REMOVE handled at column level
                operators[entity_type] = OperatorConfig("replace", {"new_value": ""})
        
        return operators
    
    def _prompt_user_strategy(self, column: str, detections: List[Dict]) -> str:
        """
        Prompt user to choose anonymization strategy
        
        Args:
            column: Column name
            detections: List of ambiguous detections
            
        Returns:
            Chosen strategy
        """
        print(f"\n  Choose strategy for column '{column}':")
        print("    [1] REMOVE - Delete entire column (HIGH risk)")
        print("    [2] HASH - One-way hash (MEDIUM risk, irreversible)")
        print("    [3] MASK - Hide with *** (LOW risk, format preserved)")
        print("    [4] KEEP - No changes (not recommended)")
        
        while True:
            try:
                choice = input("\n  Choice (1-4): ").strip()
                if choice == '1':
                    return 'REMOVE'
                elif choice == '2':
                    return 'HASH'
                elif choice == '3':
                    return 'MASK'
                elif choice == '4':
                    return 'KEEP'
                else:
                    print("  Invalid choice. Please enter 1-4.")
            except Exception:
                print("  Invalid input. Please enter 1-4.")
    
    def _collect_examples(
        self, 
        original: pd.Series, 
        anonymized: pd.Series, 
        n: int = 5
    ) -> List[Dict[str, str]]:
        """
        Collect example transformations for audit report
        
        Args:
            original: Original values
            anonymized: Anonymized values
            n: Number of examples to collect
            
        Returns:
            List of before/after examples
        """
        examples = []
        changes = original != anonymized
        changed_indices = original[changes].index[:n]
        
        for idx in changed_indices:
            examples.append({
                'before': str(original[idx])[:50],  # Truncate long values
                'after': str(anonymized[idx])[:50]
            })
        
        return examples
    
    def _generate_audit_report(self, cleaned_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Generate comprehensive audit report
        
        Returns:
            Detailed audit report with explanations
        """
        report = {
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'original_rows': len(self.df),
                'original_columns': len(self.df.columns),
                'cleaned_rows': len(cleaned_df),
                'cleaned_columns': len(cleaned_df.columns),
                'presidio_version': 'enabled' if PRESIDIO_AVAILABLE else 'disabled'
            },
            'summary': {
                'columns_removed': [],
                'columns_anonymized': [],
                'total_cells_affected': 0
            },
            'details': {},
            'compliance': {
                'gdpr_articles_applied': set(),
                'risk_mitigation': {}
            }
        }
        
        # Process each action
        for column, action_log in self.cleaning_actions.items():
            if action_log['action'] == 'REMOVED_COLUMN':
                report['summary']['columns_removed'].append(column)
                
                # Build detailed entry
                detail = {
                    'action': 'REMOVED',
                    'reason': action_log['reason'],
                    'entity_types_found': [d['entity_type'] for d in action_log['detections']],
                    'risk_level': 'HIGH',
                    'presidio_metrics': {
                        'detections': action_log['detections']
                    },
                    'gdpr_compliance': self._get_gdpr_explanation(action_log['detections'])
                }
                
            else:  # ANONYMIZED
                report['summary']['columns_anonymized'].append(column)
                report['summary']['total_cells_affected'] += action_log.get('num_affected', 0)
                
                # Build detailed entry
                detail = {
                    'action': 'ANONYMIZED',
                    'strategies_applied': list(set(action_log['strategies'].values())),
                    'reason': self._explain_anonymization(action_log),
                    'entity_types_found': [d['entity_type'] for d in action_log['detections']],
                    'num_affected_rows': action_log.get('num_affected', 0),
                    'percentage_affected': f"{(action_log.get('num_affected', 0) / len(self.df) * 100):.1f}%",
                    'examples': action_log.get('examples', [])[:3],  # Show top 3
                    'presidio_metrics': {
                        'avg_confidence': np.mean([d['avg_confidence'] for d in action_log['detections']]),
                        'detections': action_log['detections']
                    },
                    'gdpr_compliance': self._get_gdpr_explanation(action_log['detections'])
                }
            
            report['details'][column] = detail
            
            # Track GDPR articles
            for gdpr_ref in detail['gdpr_compliance']:
                report['compliance']['gdpr_articles_applied'].add(gdpr_ref)
        
        # Convert set to list for JSON serialization
        report['compliance']['gdpr_articles_applied'] = list(
            report['compliance']['gdpr_articles_applied']
        )
        
        return report
    
    def _explain_anonymization(self, action_log: Dict) -> str:
        """Generate human-readable explanation of anonymization"""
        entity_types = [d['entity_type'] for d in action_log['detections']]
        strategies = list(set(action_log['strategies'].values()))
        
        explanation = f"Contains {', '.join(entity_types)} entities. "
        explanation += f"Applied {', '.join(strategies).lower()} anonymization to protect privacy."
        
        return explanation
    
    def _get_gdpr_explanation(self, detections: List[Dict]) -> List[str]:
        """Get GDPR article references for detected entities"""
        gdpr_refs = []
        
        for detection in detections:
            entity_type = detection['entity_type']
            if entity_type in self.config.GDPR_ARTICLE_MAPPING:
                gdpr_refs.append(self.config.GDPR_ARTICLE_MAPPING[entity_type])
        
        return list(set(gdpr_refs))  # Remove duplicates
    
    def save_cleaned_data(self, cleaned_df: pd.DataFrame, output_path: str) -> str:
        """
        Save cleaned dataset to CSV
        
        Args:
            cleaned_df: Cleaned DataFrame
            output_path: Path to save file
            
        Returns:
            Path to saved file
        """
        cleaned_df.to_csv(output_path, index=False)
        print(f"✓ Cleaned data saved to: {output_path}")
        return output_path
    
    def save_audit_report(self, audit_report: Dict, output_path: str) -> str:
        """
        Save audit report to JSON
        
        Args:
            audit_report: Audit report dictionary
            output_path: Path to save file
            
        Returns:
            Path to saved file
        """
        # Convert numpy types to native Python types for JSON serialization
        import numpy as np
        
        def convert_numpy(obj):
            if isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, dict):
                return {key: convert_numpy(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [convert_numpy(item) for item in obj]
            elif isinstance(obj, set):
                return list(obj)
            return obj
        
        audit_report = convert_numpy(audit_report)
        
        with open(output_path, 'w') as f:
            json.dump(audit_report, f, indent=2)
        print(f"✓ Audit report saved to: {output_path}")
        return output_path
    
    def print_audit_summary(self, audit_report: Dict):
        """
        Print human-readable audit summary
        
        Args:
            audit_report: Audit report dictionary
        """
        print("\n" + "="*70)
        print("📊 CLEANING AUDIT SUMMARY")
        print("="*70)
        
        summary = audit_report['summary']
        metadata = audit_report['metadata']
        
        print(f"\n📈 Dataset Changes:")
        print(f"  Original: {metadata['original_rows']} rows × {metadata['original_columns']} columns")
        print(f"  Cleaned:  {metadata['cleaned_rows']} rows × {metadata['cleaned_columns']} columns")
        
        if summary['columns_removed']:
            print(f"\n❌ Removed Columns ({len(summary['columns_removed'])}):")
            for col in summary['columns_removed']:
                print(f"  - {col}")
        
        if summary['columns_anonymized']:
            print(f"\n🔒 Anonymized Columns ({len(summary['columns_anonymized'])}):")
            for col in summary['columns_anonymized']:
                detail = audit_report['details'][col]
                print(f"  - {col}: {detail['num_affected_rows']} rows affected "
                      f"({detail['percentage_affected']})")
        
        print(f"\n📝 Total cells anonymized: {summary['total_cells_affected']}")
        
        print(f"\n⚖️  GDPR Compliance:")
        for article in audit_report['compliance']['gdpr_articles_applied']:
            print(f"  - {article}")
        
        print("\n" + "="*70 + "\n")


def main():
    """Example usage and testing"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python cleaning.py <data_file.csv>")
        print("Example: python cleaning.py Datasets/loan_data.csv")
        sys.exit(1)
    
    data_path = sys.argv[1]
    
    # Load data
    print(f"Loading data from {data_path}...")
    df = pd.read_csv(data_path)
    print(f"Loaded {len(df)} rows × {len(df.columns)} columns")
    
    # Initialize cleaner
    cleaner = DataCleaner(df)
    
    # Run cleaning (interactive mode)
    cleaned_df, audit_report = cleaner.clean(
        risky_features=None,  # Auto-detect
        interactive=True,
        scan_all_cells=True
    )
    
    # Save results
    output_base = data_path.replace('.csv', '_cleaned')
    cleaner.save_cleaned_data(cleaned_df, f"{output_base}.csv")
    cleaner.save_audit_report(audit_report, f"{output_base}_audit.json")
    
    # Print summary
    cleaner.print_audit_summary(audit_report)


if __name__ == '__main__':
    main()
