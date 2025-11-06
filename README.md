# AI Governance Module

A Python package for detecting bias and analyzing risks in machine learning models. Provides comprehensive fairness metrics, privacy risk assessment, and ethical AI evaluation.

## Features

### 🎯 Bias Detection
- **Fairness Metrics**: Disparate Impact, Statistical Parity Difference, Equal Opportunity Difference
- **Demographic Analysis**: Group-wise performance evaluation
- **Violation Detection**: Automatic flagging with severity levels

### 🛡️ Risk Assessment
- **Privacy Risks**: PII detection, GDPR compliance, data exposure analysis
- **Ethical Risks**: Fairness, transparency, accountability, social impact
- **Compliance Risks**: Regulatory adherence (GDPR, CCPA, AI Act)
- **Data Quality**: Missing data, class imbalance, outlier detection

### 🤖 Machine Learning
- Generalized classification model (works with any dataset)
- Auto-detection of feature types and protected attributes
- Comprehensive performance metrics
- Feature importance analysis

## Installation

```bash
pip install -r requirements.txt
```

Or install as a package:

```bash
pip install -e .
```

## Quick Start

```python
from ai_governance import AIGovernanceAnalyzer

# Initialize analyzer
analyzer = AIGovernanceAnalyzer()

# Run complete analysis
report = analyzer.analyze(
    data_path='your_data.csv',
    target_column='target',
    protected_attributes=['gender', 'age', 'race']
)

# Access results
print(f"Bias Score: {report['summary']['overall_bias_score']:.3f}")
print(f"Risk Level: {report['summary']['risk_level']}")
print(f"Model Accuracy: {report['summary']['model_accuracy']:.3f}")

# Save report
analyzer.save_report(report, 'governance_report.json')
```

## Module Structure

```
ai_governance/
├── __init__.py              # Main API
├── data_processor.py        # Data preprocessing
├── model_trainer.py         # ML model training
├── bias_analyzer.py         # Bias detection
├── risk_analyzer.py         # Risk assessment
└── report_generator.py      # Report generation
```

## API Reference

### AIGovernanceAnalyzer

Main class for running AI governance analysis.

```python
analyzer = AIGovernanceAnalyzer()

# Analyze from DataFrame
report = analyzer.analyze_dataframe(
    df=dataframe,
    target_column='target',
    protected_attributes=['gender', 'age']
)

# Analyze from file
report = analyzer.analyze(
    data_path='data.csv',
    target_column='target',
    protected_attributes=['gender', 'age']
)
```

### Individual Components

```python
from ai_governance import (
    DataProcessor,
    GeneralizedModelTrainer,
    BiasAnalyzer,
    RiskAnalyzer,
    ReportGenerator
)

# Process data
processor = DataProcessor(df)
processor.target_column = 'target'
processor.protected_attributes = ['gender', 'age']
processor.prepare_data()

# Train model
trainer = GeneralizedModelTrainer(
    processor.X_train,
    processor.X_test,
    processor.y_train,
    processor.y_test,
    processor.feature_names
)
trainer.train()
trainer.evaluate()

# Analyze bias
bias_analyzer = BiasAnalyzer(
    processor.X_test,
    processor.y_test,
    trainer.y_pred,
    processor.df,
    processor.protected_attributes,
    processor.target_column
)
bias_results = bias_analyzer.analyze()

# Assess risks
risk_analyzer = RiskAnalyzer(
    processor.df,
    trainer.results,
    bias_results,
    processor.protected_attributes,
    processor.target_column
)
risk_results = risk_analyzer.analyze()

# Generate report
report_gen = ReportGenerator(
    trainer.results,
    bias_results,
    risk_results,
    processor.df
)
report = report_gen.generate_report()
```

## Report Structure

The module generates comprehensive JSON reports:

```json
{
  "metadata": {
    "report_id": "unique_id",
    "generated_at": "timestamp",
    "dataset_info": {}
  },
  "summary": {
    "overall_bias_score": 0.0-1.0,
    "overall_risk_score": 0.0-1.0,
    "risk_level": "LOW|MEDIUM|HIGH",
    "model_accuracy": 0.0-1.0,
    "fairness_violations_count": 0
  },
  "model_performance": {},
  "bias_analysis": {},
  "risk_assessment": {},
  "key_findings": [],
  "recommendations": []
}
```

## Metrics Interpretation

### Bias Score (0-1, lower is better)
- **0.0 - 0.3**: Low bias ✅
- **0.3 - 0.5**: Moderate bias ⚠️
- **0.5 - 1.0**: High bias ❌

### Risk Score (0-1, lower is better)
- **0.0 - 0.4**: LOW risk ✅
- **0.4 - 0.7**: MEDIUM risk ⚠️
- **0.7 - 1.0**: HIGH risk ❌

### Fairness Metrics
- **Disparate Impact**: Fair range 0.8 - 1.25
- **Statistical Parity**: Fair threshold < 0.1
- **Equal Opportunity**: Fair threshold < 0.1

## Requirements

- Python 3.8+
- pandas >= 2.0.0
- numpy >= 1.24.0
- scikit-learn >= 1.3.0

See `requirements.txt` for complete list.

## Integration Examples

### FastAPI Backend

```python
from fastapi import FastAPI, UploadFile
from ai_governance import AIGovernanceAnalyzer

app = FastAPI()
analyzer = AIGovernanceAnalyzer()

@app.post("/analyze")
async def analyze(file: UploadFile, target: str, protected: list):
    df = pd.read_csv(file.file)
    report = analyzer.analyze_dataframe(df, target, protected)
    return report
```

### Flask Backend

```python
from flask import Flask, request, jsonify
from ai_governance import AIGovernanceAnalyzer

app = Flask(__name__)
analyzer = AIGovernanceAnalyzer()

@app.route('/analyze', methods=['POST'])
def analyze():
    file = request.files['file']
    df = pd.read_csv(file)
    report = analyzer.analyze_dataframe(
        df,
        request.form['target'],
        request.form.getlist('protected')
    )
    return jsonify(report)
```

## License

MIT License

## Contributing

Contributions welcome! Please open an issue or submit a pull request.

## Citation

If you use this module in your research or project, please cite:

```
AI Governance Module - Bias Detection and Risk Analysis
https://github.com/PlatypusPus/MushroomEmpire
```
