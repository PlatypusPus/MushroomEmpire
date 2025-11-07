import csv
import re
from pathlib import Path
from collections import Counter
from datetime import datetime

ROOT = Path("../Data/Politics")

# Try to import spaCy, fall back to basic extraction if not available
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
    USE_SPACY = True
except:
    USE_SPACY = False

# Regex patterns for deterministic detection
patterns = {
    "EMAIL": re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
    "PHONE": re.compile(r"(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}"),
    "UUID": re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),
    "IBAN": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{1,30}\b"),
    "DATE": re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}"),
    "URL": re.compile(r"https?://[^\s]+"),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
}

def find_entities(text):
    """Extract entities using regex patterns."""
    found = {}
    for label, pattern in patterns.items():
        matches = pattern.findall(text)
        if matches:
            found[label] = list(set(matches))[:5]  # Limit to 5 per type
    return found

def extract_with_spacy(text):
    """Extract named entities using spaCy."""
    if not USE_SPACY:
        return {}, {}, {}
    
    doc = nlp(text[:10000])  # Limit text length for performance
    
    persons = []
    orgs = []
    locations = []
    
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            persons.append(ent.text)
        elif ent.label_ == "ORG":
            orgs.append(ent.text)
        elif ent.label_ in ["GPE", "LOC"]:
            locations.append(ent.text)
    
    # Return most common entities
    return (
        dict(Counter(persons).most_common(5)),
        dict(Counter(orgs).most_common(5)),
        dict(Counter(locations).most_common(5))
    )

def extract_metadata(text, filename):
    """Extract basic metadata from text."""
    metadata = {
        "char_count": len(text),
        "word_count": len(text.split()),
        "line_count": text.count('\n') + 1,
        "file_extension": Path(filename).suffix,
    }
    return metadata

def detect_content_type(text):
    """Heuristic content type detection."""
    text_lower = text.lower()
    
    # Check for common document types
    if any(word in text_lower[:1000] for word in ['dear', 'sincerely', 'regards']):
        return "letter"
    elif any(word in text_lower[:500] for word in ['article', 'section', 'amendment']):
        return "legal"
    elif any(word in text_lower[:500] for word in ['press release', 'for immediate release']):
        return "press_release"
    elif re.search(r'^\s*#', text[:100], re.MULTILINE):
        return "markdown"
    elif '<html' in text_lower[:200]:
        return "html"
    else:
        return "unknown"

# Define fieldnames
fieldnames = [
    "filename", "file_extension", "char_count", "word_count", "line_count",
    "content_type", "text_preview",
    "EMAIL", "PHONE", "UUID", "IBAN", "DATE", "URL", "SSN",
    "persons", "organizations", "locations"
]

print("Processing files...")
with open("discovery_dataset.csv", "w", newline="", encoding="utf-8") as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    
    file_count = 0
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        
        # Skip binary files
        if path.suffix.lower() in ['.exe', '.dll', '.so', '.dylib', '.bin', '.jpg', '.png', '.gif', '.pdf']:
            continue
        
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"  Error reading {path.name}: {e}")
            continue
        
        if not text.strip():
            continue
        
        file_count += 1
        if file_count % 10 == 0:
            print(f"Processed {file_count} files...")
        
        # Initialize row
        row = {"filename": str(path.relative_to(ROOT.parent))}
        
        # Extract metadata
        metadata = extract_metadata(text, path.name)
        row.update(metadata)
        
        # Detect content type
        row["content_type"] = detect_content_type(text)
        row["text_preview"] = text[:500].replace('\n', ' ').replace('\r', ' ')
        
        # Extract entities with regex
        entities = find_entities(text)
        for key, values in entities.items():
            row[key] = "; ".join(values) if values else ""
        
        # Fill in missing pattern fields
        for pattern_key in ["EMAIL", "PHONE", "UUID", "IBAN", "DATE", "URL", "SSN"]:
            if pattern_key not in row:
                row[pattern_key] = ""
        
        # Extract named entities with spaCy
        if USE_SPACY:
            persons, orgs, locs = extract_with_spacy(text)
            row["persons"] = "; ".join([f"{k}({v})" for k, v in persons.items()])
            row["organizations"] = "; ".join([f"{k}({v})" for k, v in orgs.items()])
            row["locations"] = "; ".join([f"{k}({v})" for k, v in locs.items()])
        else:
            row["persons"] = ""
            row["organizations"] = ""
            row["locations"] = ""
        
        writer.writerow(row)

print(f"\nComplete! Processed {file_count} files.")
print(f"Output: discovery_dataset.csv")

# Print summary statistics
if file_count > 0:
    print("\nTo install spaCy for better entity extraction:")
    print("  pip install spacy")
    print("  python -m spacy download en_core_web_sm")