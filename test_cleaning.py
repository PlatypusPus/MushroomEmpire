"""
Test script for data cleaning module
Demonstrates PII detection and anonymization on loan dataset
"""

import pandas as pd
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cleaning import DataCleaner, CleaningConfig


def test_basic_cleaning():
    """Test basic cleaning functionality"""
    print("\n" + "="*70)
    print("TEST 1: Basic PII Detection on Loan Dataset")
    print("="*70)
    
    # Load loan data
    df = pd.read_csv('Datasets/loan_data.csv')
    print(f"\n✓ Loaded dataset: {len(df)} rows × {len(df.columns)} columns")
    print(f"  Columns: {list(df.columns)}")
    
    # Initialize cleaner
    cleaner = DataCleaner(df)
    
    # Run cleaning in non-interactive mode (auto-apply strategies)
    print("\n🔍 Running PII detection...")
    cleaned_df, audit_report = cleaner.clean(
        risky_features=None,  # Auto-detect all
        interactive=False,  # Non-interactive for testing
        scan_all_cells=True
    )
    
    # Display results
    cleaner.print_audit_summary(audit_report)
    
    return cleaned_df, audit_report


def test_with_risky_features():
    """Test cleaning with specific risky features flagged"""
    print("\n" + "="*70)
    print("TEST 2: Cleaning with Pre-Flagged Risky Features")
    print("="*70)
    
    # Load loan data
    df = pd.read_csv('Datasets/loan_data.csv')
    
    # Simulate risky features from RiskAnalyzer
    risky_features = ['person_education', 'loan_intent', 'person_home_ownership']
    
    print(f"\n⚠️  Risky features flagged by RiskAnalyzer: {risky_features}")
    
    # Initialize cleaner
    cleaner = DataCleaner(df)
    
    # Run cleaning on flagged features only
    cleaned_df, audit_report = cleaner.clean(
        risky_features=risky_features,
        interactive=False,
        scan_all_cells=False  # Only scan risky columns
    )
    
    # Display results
    cleaner.print_audit_summary(audit_report)
    
    return cleaned_df, audit_report


def test_with_synthetic_pii():
    """Test with synthetic PII data"""
    print("\n" + "="*70)
    print("TEST 3: Synthetic PII Detection")
    print("="*70)
    
    # Create test DataFrame with obvious PII
    test_data = pd.DataFrame({
        'customer_id': [1, 2, 3, 4, 5],
        'email': [
            'john.doe@example.com',
            'alice.smith@company.org',
            'bob.jones@email.com',
            'carol.white@test.net',
            'dave.brown@sample.com'
        ],
        'phone': [
            '+1-555-123-4567',
            '555-234-5678',
            '(555) 345-6789',
            '555.456.7890',
            '5555678901'
        ],
        'ssn': [
            '123-45-6789',
            '234-56-7890',
            '345-67-8901',
            '456-78-9012',
            '567-89-0123'
        ],
        'notes': [
            'Customer called from 192.168.1.1',
            'Contact via email: test@example.com',
            'SSN verified: 111-22-3333',
            'Previous address: 123 Main St, Boston',
            'Phone backup: 555-999-8888'
        ],
        'amount': [1000, 2000, 1500, 3000, 2500]
    })
    
    print(f"\n✓ Created synthetic dataset with PII:")
    print(test_data.head())
    
    # Initialize cleaner
    cleaner = DataCleaner(test_data)
    
    # Run cleaning
    cleaned_df, audit_report = cleaner.clean(
        risky_features=None,
        interactive=False,
        scan_all_cells=True
    )
    
    print("\n🔒 Cleaned dataset:")
    print(cleaned_df.head())
    
    # Display results
    cleaner.print_audit_summary(audit_report)
    
    # Save outputs
    os.makedirs('output', exist_ok=True)
    cleaner.save_cleaned_data(cleaned_df, 'output/synthetic_cleaned.csv')
    cleaner.save_audit_report(audit_report, 'output/synthetic_audit.json')
    
    return cleaned_df, audit_report


def test_interactive_mode():
    """Test interactive mode (requires user input)"""
    print("\n" + "="*70)
    print("TEST 4: Interactive Mode (Manual Decisions)")
    print("="*70)
    
    # Create ambiguous test data
    test_data = pd.DataFrame({
        'id': [1, 2, 3],
        'description': [
            'Customer from Paris contacted us',  # Paris = location or name?
            'Spoke with Jordan about the account',  # Jordan = location or name?
            'Meeting scheduled for March 15th'  # Date
        ],
        'value': [100, 200, 300]
    })
    
    print(f"\n✓ Created dataset with ambiguous PII:")
    print(test_data)
    
    print("\n⚠️  This test requires user input for ambiguous cases.")
    print("    You'll be prompted to choose anonymization strategies.")
    
    proceed = input("\nProceed with interactive test? (y/n): ").strip().lower()
    
    if proceed == 'y':
        cleaner = DataCleaner(test_data)
        cleaned_df, audit_report = cleaner.clean(
            risky_features=None,
            interactive=True,  # Enable interactive prompts
            scan_all_cells=True
        )
        
        print("\n🔒 Cleaned dataset:")
        print(cleaned_df)
        
        cleaner.print_audit_summary(audit_report)
    else:
        print("  Skipped interactive test.")


def demonstrate_integration_with_analysis():
    """Demonstrate how cleaning integrates with AI governance pipeline"""
    print("\n" + "="*70)
    print("INTEGRATION DEMO: Cleaning → Analysis Workflow")
    print("="*70)
    
    # Load data
    df = pd.read_csv('Datasets/loan_data.csv')
    
    print("\n📊 Workflow:")
    print("  1. Original dataset → Risk Analysis")
    print("  2. Risk Analysis → Identifies risky features")
    print("  3. Risky features → Data Cleaning (this step)")
    print("  4. Cleaned dataset → Re-run Analysis (optional)")
    
    # Simulate risky features from analysis
    simulated_risky_features = ['person_education', 'loan_intent']
    
    print(f"\n⚠️  Step 2 Output (simulated): Risky features = {simulated_risky_features}")
    
    # Step 3: Clean data
    print("\n🔒 Step 3: Cleaning risky features...")
    cleaner = DataCleaner(df)
    cleaned_df, audit_report = cleaner.clean(
        risky_features=simulated_risky_features,
        interactive=False,
        scan_all_cells=False
    )
    
    # Save both datasets
    os.makedirs('output', exist_ok=True)
    df.to_csv('output/loan_data_original.csv', index=False)
    cleaner.save_cleaned_data(cleaned_df, 'output/loan_data_cleaned.csv')
    cleaner.save_audit_report(audit_report, 'output/cleaning_audit.json')
    
    print("\n💾 Saved files:")
    print("  - output/loan_data_original.csv (original)")
    print("  - output/loan_data_cleaned.csv (cleaned)")
    print("  - output/cleaning_audit.json (audit report)")
    
    print("\n📈 Step 4: User can now choose which dataset to analyze:")
    print("  Option A: Analyze cleaned dataset (privacy-compliant)")
    print("  Option B: Analyze original dataset (for comparison)")
    print("  Option C: Analyze both and compare results")
    
    cleaner.print_audit_summary(audit_report)


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("🧪 DATA CLEANING MODULE - TEST SUITE")
    print("="*70)
    
    print("\nAvailable tests:")
    print("  1. Basic PII detection on loan dataset")
    print("  2. Cleaning with pre-flagged risky features")
    print("  3. Synthetic PII detection (comprehensive)")
    print("  4. Interactive mode (requires user input)")
    print("  5. Integration workflow demonstration")
    print("  6. Run all non-interactive tests")
    
    choice = input("\nSelect test (1-6): ").strip()
    
    if choice == '1':
        test_basic_cleaning()
    elif choice == '2':
        test_with_risky_features()
    elif choice == '3':
        test_with_synthetic_pii()
    elif choice == '4':
        test_interactive_mode()
    elif choice == '5':
        demonstrate_integration_with_analysis()
    elif choice == '6':
        print("\n🏃 Running all non-interactive tests...\n")
        test_basic_cleaning()
        test_with_risky_features()
        test_with_synthetic_pii()
        demonstrate_integration_with_analysis()
        print("\n✅ All tests completed!")
    else:
        print("Invalid choice. Run: python test_cleaning.py")


if __name__ == '__main__':
    main()
