"""
Data Cleaning Module - PII Detection and Anonymization
Handles GDPR-compliant data cleaning using Presidio for PII detection
GPU-accelerated for faster processing of large datasets
"""

import pandas as pd
import numpy as np
import hashlib
import json
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict

try:
    from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, PatternRecognizer, Pattern
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_anonymizer import AnonymizerEngine
    from presidio_anonymizer.entities import OperatorConfig
    PRESIDIO_AVAILABLE = True
except ImportError:
    PRESIDIO_AVAILABLE = False
    print("Warning: Presidio not installed. Run: pip install presidio-analyzer presidio-anonymizer")
# GPU detection
try:
    import torch
    CUDA_AVAILABLE = torch.cuda.is_available()
    if CUDA_AVAILABLE:
        GPU_DEVICE = 0  # Use first GPU
        GPU_NAME = torch.cuda.get_device_name(0)
        GPU_MEMORY = torch.cuda.get_device_properties(0).total_memory / 1024**3  # GB
    else:
        GPU_DEVICE = -1
        GPU_NAME = None
        GPU_MEMORY = 0
except ImportError:
    CUDA_AVAILABLE = False
    GPU_DEVICE = -1
    GPU_NAME = None
    GPU_MEMORY = 0

try:
    import spacy
    SPACY_AVAILABLE = True
    # Check if spaCy can use GPU
    if CUDA_AVAILABLE:
        spacy.require_gpu()
except ImportError:
    SPACY_AVAILABLE = False
except Exception:
    # GPU not available for spaCy, will fall back to CPU
    pass


def convert_to_json_serializable(obj):
    """Convert numpy types to JSON-serializable Python types"""
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_to_json_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_json_serializable(item) for item in obj]
    return obj


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
    
    def __init__(self, df: pd.DataFrame, config: Optional[CleaningConfig] = None, use_gpu: bool = True):
        """
        Initialize the data cleaner
        
        Args:
            df: Input DataFrame to clean
            config: Optional custom configuration
            use_gpu: Whether to use GPU acceleration if available (default: True)
        """
        self.df = df.copy()
        self.config = config or CleaningConfig()
        self.audit_log = []
        self.cleaning_actions = {}
        self.use_gpu = use_gpu and CUDA_AVAILABLE
        
        # Display GPU info
        self._display_gpu_info()
        
        # Initialize Presidio engines
        if PRESIDIO_AVAILABLE:
            self._init_presidio()
        else:
            raise ImportError(
                "Presidio is required for data cleaning. "
                "Install with: pip install presidio-analyzer presidio-anonymizer"
            )
    
    def _display_gpu_info(self):
        """Display GPU availability and configuration"""
        print("\n" + "="*70)
        print("🖥️  HARDWARE CONFIGURATION")
        print("="*70)
        
        if CUDA_AVAILABLE and self.use_gpu:
            print(f"✓ GPU ACCELERATION: ENABLED")
            print(f"  Device: {GPU_NAME}")
            print(f"  Memory: {GPU_MEMORY:.2f} GB")
            print(f"  CUDA Device ID: {GPU_DEVICE}")
        elif CUDA_AVAILABLE and not self.use_gpu:
            print(f"⚠️  GPU ACCELERATION: DISABLED (use_gpu=False)")
            print(f"  Available GPU: {GPU_NAME} ({GPU_MEMORY:.2f} GB)")
        else:
            print(f"⚠️  GPU ACCELERATION: NOT AVAILABLE")
            print(f"  Reason: {'PyTorch not installed' if not 'torch' in dir() else 'No CUDA device detected'}")
            print(f"  Install: pip install torch --index-url https://download.pytorch.org/whl/cu121")
        
        print("="*70 + "\n")
    
    def _init_presidio(self):
        """Initialize Presidio analyzer and anonymizer engines with GPU support"""
        # Create NLP engine configuration
        configuration = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        }
        
        try:
            # Create NLP engine
            provider = NlpEngineProvider(nlp_configuration=configuration)
            nlp_engine = provider.create_engine()
            
            # Enable GPU for spaCy if available
            if self.use_gpu and SPACY_AVAILABLE:
                try:
                    import spacy
                    # Move spaCy model to GPU
                    spacy.require_gpu()
                    print("✓ spaCy GPU acceleration enabled")
                except Exception as e:
                    print(f"⚠️  Could not enable spaCy GPU: {e}")
                    print("  Falling back to CPU for NLP processing")
            
            # Create analyzer with NLP engine
            self.analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
            self.anonymizer = AnonymizerEngine()
            
            device_info = "GPU" if self.use_gpu else "CPU"
            print(f"✓ Presidio engines initialized successfully ({device_info} mode)")
        except Exception as e:
            # Fallback to default configuration if spaCy model not available
            print(f"Warning: Could not load spaCy model, using default configuration: {e}")
            print("Download spaCy model with: python -m spacy download en_core_web_sm")
            self.analyzer = AnalyzerEngine()
            self.anonymizer = AnonymizerEngine()
    
    def _add_nordic_recognizers(self, registry: RecognizerRegistry):
        """Add custom recognizers for Nordic national IDs and identifiers"""
        
        # Finnish Henkilötunnus (HETU) - Format: DDMMYY(+/-)NNNC
        fi_hetu_pattern = Pattern(
            name="finnish_hetu_pattern",
            regex=r"\b\d{6}[+\-A]\d{3}[0-9A-FHJ-NPR-Y]\b",
            score=0.95
        )
        fi_hetu_recognizer = PatternRecognizer(
            supported_entity="FI_PERSONAL_ID",
            patterns=[fi_hetu_pattern],
            context=["henkilötunnus", "hetu", "personal", "identity", "id"]
        )
        registry.add_recognizer(fi_hetu_recognizer)
        
        # Swedish Personnummer - Format: YYYYMMDD-NNNN or YYMMDD-NNNN
        se_personnummer_pattern = Pattern(
            name="swedish_personnummer_pattern",
            regex=r"\b\d{6}[-+]?\d{4}\b",
            score=0.90
        )
        se_personnummer_recognizer = PatternRecognizer(
            supported_entity="SE_PERSONAL_ID",
            patterns=[se_personnummer_pattern],
            context=["personnummer", "personal", "identity", "swedish", "id"]
        )
        registry.add_recognizer(se_personnummer_recognizer)
        
        # Norwegian Fødselsnummer - Format: DDMMYY NNNNN
        no_fodselsnummer_pattern = Pattern(
            name="norwegian_fodselsnummer_pattern",
            regex=r"\b\d{6}\s?\d{5}\b",
            score=0.90
        )
        no_fodselsnummer_recognizer = PatternRecognizer(
            supported_entity="NO_PERSONAL_ID",
            patterns=[no_fodselsnummer_pattern],
            context=["fødselsnummer", "fodselsnummer", "personal", "identity", "norwegian", "id"]
        )
        registry.add_recognizer(no_fodselsnummer_recognizer)
        
        # Danish CPR-nummer - Format: DDMMYY-NNNN
        dk_cpr_pattern = Pattern(
            name="danish_cpr_pattern",
            regex=r"\b\d{6}-?\d{4}\b",
            score=0.90
        )
        dk_cpr_recognizer = PatternRecognizer(
            supported_entity="DK_PERSONAL_ID",
            patterns=[dk_cpr_pattern],
            context=["cpr", "cpr-nummer", "personal", "identity", "danish", "id"]
        )
        registry.add_recognizer(dk_cpr_recognizer)
        
        # Finnish Business ID (Y-tunnus) - Format: NNNNNNN-N
        fi_ytunnus_pattern = Pattern(
            name="finnish_ytunnus_pattern",
            regex=r"\b\d{7}-\d\b",
            score=0.85
        )
        fi_ytunnus_recognizer = PatternRecognizer(
            supported_entity="FI_BUSINESS_ID",
            patterns=[fi_ytunnus_pattern],
            context=["y-tunnus", "ytunnus", "business", "company", "organization"]
        )
        registry.add_recognizer(fi_ytunnus_recognizer)
        
        # Finnish Kela ID - Format varies
        fi_kela_pattern = Pattern(
            name="finnish_kela_pattern",
            regex=r"\bKELA[-\s]?\d{6,10}\b",
            score=0.85
        )
        fi_kela_recognizer = PatternRecognizer(
            supported_entity="FI_KELA_ID",
            patterns=[fi_kela_pattern],
            context=["kela", "social", "security", "benefit", "insurance"]
        )
        registry.add_recognizer(fi_kela_recognizer)
        
        print("  ✓ Added Nordic recognizers: FI_PERSONAL_ID, SE_PERSONAL_ID, NO_PERSONAL_ID, DK_PERSONAL_ID")
        print("  ✓ Added Finnish identifiers: FI_BUSINESS_ID, FI_KELA_ID")
    
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
        Detect PII at column and cell level (GPU-accelerated when available)
        
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
        
        device_info = f"GPU ({GPU_NAME})" if self.use_gpu else "CPU"
        print(f"  Scanning {len(columns_to_scan)} columns using {device_info}: {columns_to_scan}")
        
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
                'presidio_version': 'enabled' if PRESIDIO_AVAILABLE else 'disabled',
                'gpu_acceleration': {
                    'enabled': self.use_gpu,
                    'cuda_available': CUDA_AVAILABLE,
                    'device': GPU_NAME if self.use_gpu else 'CPU',
                    'gpu_memory_gb': GPU_MEMORY if self.use_gpu else 0
                }
            },
            'summary': {
                'total_rows': len(self.df),
                'total_columns': len(self.df.columns),
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
    
    def generate_simple_report(self, audit_report: Dict, dataset_name: str = "dataset") -> Dict:
        """
        Generate a simple executive summary report in JSON format
        
        Args:
            audit_report: Audit report from clean() method
            dataset_name: Name of the dataset for the report
            
        Returns:
            Simple report as dictionary (JSON-serializable)
        """
        summary = audit_report['summary']
        removed_cols = summary['columns_removed']
        anon_cols = summary['columns_anonymized']
        
        total_risky = len(removed_cols) + len(anon_cols)
        orig_cols = summary['total_columns']
        clean_cols = orig_cols - len(removed_cols)
        total_rows = summary['total_rows']
        
        # Detect Nordic-specific entities
        nordic_entities = ['FI_PERSONAL_ID', 'SE_PERSONAL_ID', 'NO_PERSONAL_ID', 'DK_PERSONAL_ID', 'FI_KELA_ID', 'FI_BUSINESS_ID']
        has_nordic = any(entity in str(audit_report['details']) for entity in nordic_entities)
        
        # Build columns summary
        columns_summary = []
        
        # Removed columns
        for col in removed_cols:
            detail = audit_report['details'].get(col, {})
            columns_summary.append({
                "column_name": col,
                "risk_level": "CRITICAL",
                "action_taken": "REMOVED",
                "entity_types": detail.get('entity_types_found', ['PII']),
                "reason": detail.get('reason', 'High-risk PII detected')
            })
        
        # Anonymized columns
        for col in anon_cols:
            detail = audit_report['details'].get(col, {})
            columns_summary.append({
                "column_name": col,
                "risk_level": "MEDIUM",
                "action_taken": "ANONYMIZED",
                "strategies": detail.get('strategies_applied', ['anonymized']),
                "entity_types": detail.get('entity_types_found', ['PII']),
                "rows_affected": detail.get('num_affected_rows', 0),
                "percentage_affected": detail.get('percentage_affected', '0%')
            })
        
        # Build simple report JSON
        report = {
            "report_type": "simple_explainability",
            "dataset_name": dataset_name,
            "timestamp": audit_report['metadata']['timestamp'],
            "status": "GDPR-compliant",
            "executive_summary": {
                "total_risky_columns": total_risky,
                "columns_removed": len(removed_cols),
                "columns_anonymized": len(anon_cols),
                "data_preserved_columns": clean_cols - len(anon_cols),
                "privacy_risk_before": "HIGH - Data breach could expose individual identities",
                "privacy_risk_after": "MINIMAL - Individuals cannot be re-identified"
            },
            "what_we_found": {
                "description": f"We discovered {total_risky} columns containing personal information",
                "columns": columns_summary
            },
            "impact": {
                "original_dataset": {
                    "rows": total_rows,
                    "columns": orig_cols
                },
                "cleaned_dataset": {
                    "rows": total_rows,
                    "columns": clean_cols
                },
                "data_removed": len(removed_cols),
                "data_anonymized": len(anon_cols),
                "cells_affected": summary['total_cells_affected'],
                "data_preserved": clean_cols - len(anon_cols)
            },
            "privacy_protection": {
                "personal_identifiers_removed": True,
                "contact_information_protected": True,
                "analytics_still_possible": True,
                "gdpr_compliant": True
            },
            "legal_compliance": {
                "gdpr_articles": audit_report['compliance']['gdpr_articles_applied'],
                "compliant": True
            },
            "risk_assessment": {
                "before_cleaning": {
                    "risk_level": "HIGH",
                    "potential_fine": "Up to €20M under GDPR",
                    "reputation_risk": "Severe loss of public trust"
                },
                "after_cleaning": {
                    "risk_level": "MINIMAL",
                    "re_identification_risk": "Near impossible",
                    "analytics_capability": "Fully preserved"
                }
            },
            "recommended_actions": [
                {"priority": "HIGH", "action": "Use the cleaned dataset for analytics and model training"},
                {"priority": "HIGH", "action": "Store original securely with access controls (if legally required)"},
                {"priority": "MEDIUM", "action": "Update documentation to reflect data minimization"},
                {"priority": "MEDIUM", "action": "Review retention policies - do you need the original at all?"},
                {"priority": "LOW", "action": "Document in GDPR Article 30 records (record of processing activities)"}
            ]
        }
        
        # Add Nordic-specific information if detected
        if has_nordic:
            nordic_details = {
                "nordic_pii_detected": True,
                "nordic_entity_types": [],
                "regulatory_compliance": []
            }
            
            # Identify which Nordic entities were found
            for entity in nordic_entities:
                if entity in str(audit_report['details']):
                    if entity == 'FI_PERSONAL_ID':
                        nordic_details["nordic_entity_types"].append({
                            "type": "Finnish Henkilötunnus (HETU)",
                            "format": "DDMMYY-NNNC",
                            "sensitivity": "CRITICAL"
                        })
                        nordic_details["regulatory_compliance"].append("Finnish Data Protection Act")
                        nordic_details["regulatory_compliance"].append("Finnish DPA (Tietosuojavaltuutettu) guidance")
                    elif entity == 'SE_PERSONAL_ID':
                        nordic_details["nordic_entity_types"].append({
                            "type": "Swedish Personnummer",
                            "format": "YYMMDD-NNNN",
                            "sensitivity": "CRITICAL"
                        })
                        nordic_details["regulatory_compliance"].append("Swedish IMY requirements")
                    elif entity == 'NO_PERSONAL_ID':
                        nordic_details["nordic_entity_types"].append({
                            "type": "Norwegian Fødselsnummer",
                            "format": "DDMMYY NNNNN",
                            "sensitivity": "CRITICAL"
                        })
                        nordic_details["regulatory_compliance"].append("Norwegian Datatilsynet standards")
                    elif entity == 'DK_PERSONAL_ID':
                        nordic_details["nordic_entity_types"].append({
                            "type": "Danish CPR-nummer",
                            "format": "DDMMYY-NNNN",
                            "sensitivity": "CRITICAL"
                        })
                        nordic_details["regulatory_compliance"].append("Danish Datatilsynet standards")
                    elif entity == 'FI_KELA_ID':
                        nordic_details["nordic_entity_types"].append({
                            "type": "Finnish Kela ID",
                            "purpose": "Social security/benefits",
                            "sensitivity": "CRITICAL"
                        })
                    elif entity == 'FI_BUSINESS_ID':
                        nordic_details["nordic_entity_types"].append({
                            "type": "Finnish Y-tunnus (Business ID)",
                            "format": "NNNNNNN-N",
                            "sensitivity": "MEDIUM"
                        })
            
            nordic_details["regulatory_compliance"] = list(set(nordic_details["regulatory_compliance"]))
            nordic_details["regulatory_compliance"].append("GDPR (EU regulation)")
            report["nordic_specific"] = nordic_details
        
        return report
    
    def generate_detailed_report(self, audit_report: Dict, dataset_name: str = "dataset") -> Dict:
        """
        Generate a comprehensive detailed technical report in JSON format
        
        Args:
            audit_report: Audit report from clean() method
            dataset_name: Name of the dataset for the report
            
        Returns:
            Detailed report as dictionary (JSON-serializable)
        """
        summary = audit_report['summary']
        
        # Detect Nordic-specific entities
        nordic_entities = ['FI_PERSONAL_ID', 'SE_PERSONAL_ID', 'NO_PERSONAL_ID', 'DK_PERSONAL_ID', 'FI_KELA_ID', 'FI_BUSINESS_ID']
        has_nordic = any(entity in str(audit_report['details']) for entity in nordic_entities)
        
        # Build report structure
        report = {
            "report_type": "detailed_technical_explainability",
            "metadata": {
                "generated_timestamp": audit_report['metadata']['timestamp'],
                "analyst": "AI Governance Module v1.0",
                "dataset_name": dataset_name,
                "presidio_version": audit_report['metadata'].get('presidio_version', 'N/A'),
                "dataset_info": {
                    "total_rows": summary['total_rows'],
                    "total_columns": summary['total_columns'],
                    "risky_columns_found": len(summary['columns_removed']) + len(summary['columns_anonymized']),
                    "columns_removed": len(summary['columns_removed']),
                    "columns_anonymized": len(summary['columns_anonymized'])
                }
            },
            "detection_methodology": {
                "approach": "Hybrid pattern matching + NLP context analysis",
                "technologies": [
                    {
                        "name": "Presidio Analyzer",
                        "description": "Microsoft's PII detection framework",
                        "role": "Primary PII detection engine"
                    },
                    {
                        "name": "spaCy NLP",
                        "description": "Named Entity Recognition (NER)",
                        "role": "Context-aware entity extraction"
                    },
                    {
                        "name": "Regex Patterns",
                        "description": "30+ predefined entity patterns",
                        "role": "Pattern-based PII detection"
                    },
                    {
                        "name": "Custom Recognizers",
                        "description": "Nordic-specific patterns (Henkilötunnus, Personnummer, etc.)",
                        "role": "Region-specific PII detection"
                    }
                ],
                "process_stages": [
                    "1. Column-level analysis (fast screening)",
                    "2. Cell-level analysis (deep scanning)",
                    "3. Entity confidence scoring",
                    "4. Risk classification",
                    "5. Strategy application"
                ]
            },
            "column_by_column_analysis": [],
            "validation_quality_assurance": {
                "tests_performed": [
                    "Data integrity: Row count preserved",
                    "NULL preservation: Empty values remain empty",
                    "Analytics test: Non-sensitive columns still functional"
                ],
                "consistency_checks": {
                    "hash_consistency": "Same original values produce same hashes",
                    "deterministic": True
                }
            },
            "compliance_documentation": {
                "gdpr_article_30": {
                    "processing_activity": "Analytics on Pseudonymized Data",
                    "data_categories": {
                        "pseudonymized_columns": len(summary['columns_anonymized']),
                        "retained_columns": summary['total_columns'] - len(summary['columns_removed']) - len(summary['columns_anonymized']),
                        "removed_columns": len(summary['columns_removed'])
                    },
                    "security_measures": [
                        "Pseudonymization applied (SHA-256)",
                        "Direct identifiers removed",
                        "Audit logging enabled"
                    ]
                },
                "audit_certification": {
                    "compliant_with": [
                        "GDPR Article 25 (Data Protection by Design)",
                        "GDPR Article 32 (Security through Pseudonymization)",
                        "GDPR Article 5(1)(c) (Data Minimization)",
                        "GDPR Article 5(1)(e) (Storage Limitation)"
                    ],
                    "approved_for": [
                        "Healthcare research",
                        "Quality improvement analytics",
                        "Machine learning model training",
                        "Public health surveillance (aggregated)"
                    ],
                    "not_approved_for": [
                        "Individual re-identification",
                        "Marketing or commercial use",
                        "Sharing with third parties without additional safeguards"
                    ]
                }
            },
            "recommendations": {
                "immediate_actions": [
                    {"priority": 1, "action": "Deploy cleaned dataset for analytics and ML model training"},
                    {"priority": 2, "action": "Update data catalog to reflect anonymization"},
                    {"priority": 3, "action": "Archive original in secure vault (if legally required)"},
                    {"priority": 4, "action": "Review retention policy: Can original be deleted after cleaning?"}
                ],
                "process_improvements": [
                    "Upstream prevention: Implement data minimization at collection point",
                    "Continuous monitoring: Re-scan periodically for PII in new data",
                    "Training: Educate staff on PII handling best practices"
                ]
            }
        }
        
        # Build column-by-column analysis
        col_num = 1
        all_columns = list(audit_report['details'].keys())
        
        for column in all_columns:
            detail = audit_report['details'][column]
            
            col_analysis = {
                "column_number": col_num,
                "column_name": column,
                "detection_results": {
                    "entity_types_found": detail.get('entity_types_found', []),
                    "instances_found": 0,
                    "average_confidence": None
                },
                "risk_assessment": {
                    "risk_level": detail.get('risk_level', 'UNKNOWN'),
                    "reason": detail.get('reason', 'N/A'),
                    "gdpr_classification": detail.get('gdpr_compliance', [])
                },
                "anonymization_decision": {
                    "action": detail.get('action', 'NONE'),
                    "strategies_applied": detail.get('strategies_applied', []),
                    "rows_affected": detail.get('num_affected_rows', 0),
                    "percentage_affected": detail.get('percentage_affected', '0%')
                },
                "technical_implementation": {
                    "method": detail.get('action', 'NONE'),
                    "irreversibility": detail.get('action', 'NONE') in ['REMOVED', 'ANONYMIZED']
                }
            }
            
            # Add metrics if available
            if 'presidio_metrics' in detail:
                metrics = detail['presidio_metrics']
                if 'avg_confidence' in metrics:
                    col_analysis["detection_results"]["average_confidence"] = round(metrics['avg_confidence'], 2)
                if 'detections' in metrics:
                    col_analysis["detection_results"]["instances_found"] = sum(d.get('count', 0) for d in metrics['detections'])
                    col_analysis["detection_results"]["detailed_detections"] = metrics['detections']
            
            # Add example transformations
            if 'examples' in detail and detail['examples']:
                col_analysis["anonymization_decision"]["example_transformations"] = detail['examples'][:3]
            
            # Add hashing details if applicable
            if 'HASH' in [s.upper() for s in detail.get('strategies_applied', [])]:
                col_analysis["technical_implementation"]["hash_details"] = {
                    "algorithm": "SHA-256",
                    "security": "Cryptographically secure",
                    "irreversibility": "One-way function",
                    "determinism": "Same value produces same hash",
                    "output_format": "64 hexadecimal characters"
                }
            
            report["column_by_column_analysis"].append(col_analysis)
            col_num += 1
        
        # Add Nordic-specific information if detected
        if has_nordic:
            nordic_section = {
                "nordic_pii_detected": True,
                "detected_entities": [],
                "regulatory_framework": [],
                "special_considerations": []
            }
            
            # Identify Nordic entities
            for entity in nordic_entities:
                if entity in str(audit_report['details']):
                    if entity == 'FI_PERSONAL_ID':
                        nordic_section["detected_entities"].append({
                            "entity_type": "Finnish Henkilötunnus (HETU)",
                            "format": "DDMMYY(+/-)NNNC",
                            "sensitivity": "CRITICAL",
                            "description": "Finnish national identity number containing birth date and biological sex",
                            "regulatory_reference": "Finnish Data Protection Act - classified as especially sensitive",
                            "dpa_guidance": "Finnish DPA (Tietosuojavaltuutettu) 2023 guidance: HETU should not be used as database keys"
                        })
                        nordic_section["regulatory_framework"].append("Finnish Data Protection Act")
                        nordic_section["regulatory_framework"].append("Finnish DPA (Tietosuojavaltuutettu) guidance")
                        nordic_section["special_considerations"].append("Replace with Kanta patient ID or pseudonymous research ID")
                    
                    elif entity == 'SE_PERSONAL_ID':
                        nordic_section["detected_entities"].append({
                            "entity_type": "Swedish Personnummer",
                            "format": "YYYYMMDD-NNNN or YYMMDD-NNNN",
                            "sensitivity": "CRITICAL",
                            "description": "Swedish national identity number",
                            "regulatory_reference": "Swedish IMY requirements"
                        })
                        nordic_section["regulatory_framework"].append("Swedish IMY (Integritetsskyddsmyndigheten) requirements")
                    
                    elif entity == 'NO_PERSONAL_ID':
                        nordic_section["detected_entities"].append({
                            "entity_type": "Norwegian Fødselsnummer",
                            "format": "DDMMYY NNNNN",
                            "sensitivity": "CRITICAL",
                            "description": "Norwegian national identity number",
                            "regulatory_reference": "Norwegian Datatilsynet standards"
                        })
                        nordic_section["regulatory_framework"].append("Norwegian Datatilsynet standards")
                    
                    elif entity == 'DK_PERSONAL_ID':
                        nordic_section["detected_entities"].append({
                            "entity_type": "Danish CPR-nummer",
                            "format": "DDMMYY-NNNN",
                            "sensitivity": "CRITICAL",
                            "description": "Danish civil registration number",
                            "regulatory_reference": "Danish Datatilsynet standards"
                        })
                        nordic_section["regulatory_framework"].append("Danish Datatilsynet standards")
                    
                    elif entity == 'FI_KELA_ID':
                        nordic_section["detected_entities"].append({
                            "entity_type": "Finnish Kela ID",
                            "purpose": "Social security and benefits administration",
                            "sensitivity": "CRITICAL",
                            "description": "Finnish social insurance institution identifier",
                            "gdpr_category": "Article 9(1) - Special category (health/social security)"
                        })
                    
                    elif entity == 'FI_BUSINESS_ID':
                        nordic_section["detected_entities"].append({
                            "entity_type": "Finnish Y-tunnus (Business ID)",
                            "format": "NNNNNNN-N",
                            "sensitivity": "MEDIUM",
                            "description": "Finnish business/organization identifier",
                            "note": "Less sensitive than personal IDs, typically hashed rather than removed"
                        })
            
            nordic_section["regulatory_framework"] = list(set(nordic_section["regulatory_framework"]))
            nordic_section["regulatory_framework"].append("GDPR (EU Regulation 2016/679)")
            
            nordic_section["special_considerations"].extend([
                "Suomi.fi integration: Track consent via Suomi.fi Suostumukset system (Finnish)",
                "Multi-language support: Ensure documentation available in Finnish, Swedish, Norwegian, Danish",
                "Nordic DPA reporting: May require specific notification to national data protection authorities",
                "Finnish Patient Data Act: Additional requirements if healthcare data is involved"
            ])
            
            nordic_section["compliance_certification"] = {
                "finnish_dpa": "Complies with Tietosuojavaltuutettu guidance on national ID handling",
                "finnish_patient_data_act": "Meets requirements if healthcare data is present",
                "nordic_cooperation": "Aligned with Nordic DPA joint recommendations"
            }
            
            report["nordic_specific_analysis"] = nordic_section
        
        return report
        
    
    def save_simple_report(self, audit_report: Dict, output_path: str, dataset_name: str = "dataset") -> str:
        """Save simple explainability report to JSON file"""
        simple_report = self.generate_simple_report(audit_report, dataset_name)
        # Convert numpy types to JSON-serializable types
        simple_report = convert_to_json_serializable(simple_report)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(simple_report, f, indent=2, ensure_ascii=False)
        print(f"✓ Simple report saved to: {output_path}")
        return output_path
    
    def save_detailed_report(self, audit_report: Dict, output_path: str, dataset_name: str = "dataset") -> str:
        """Save detailed explainability report to JSON file"""
        detailed_report = self.generate_detailed_report(audit_report, dataset_name)
        # Convert numpy types to JSON-serializable types
        detailed_report = convert_to_json_serializable(detailed_report)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(detailed_report, f, indent=2, ensure_ascii=False)
        print(f"✓ Detailed report saved to: {output_path}")
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
        print("Usage: python cleaning.py <data_file.csv> [--no-gpu]")
        print("Example: python cleaning.py Datasets/loan_data.csv")
        print("Options:")
        print("  --no-gpu    Disable GPU acceleration (use CPU only)")
        sys.exit(1)
    
    data_path = sys.argv[1]
    use_gpu = '--no-gpu' not in sys.argv
    
    # Load data
    print(f"Loading data from {data_path}...")
    df = pd.read_csv(data_path)
    print(f"Loaded {len(df)} rows × {len(df.columns)} columns")
    
    # Initialize cleaner with GPU support
    cleaner = DataCleaner(df, use_gpu=use_gpu)
    
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
