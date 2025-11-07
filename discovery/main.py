import csv, tempfile
import re
from pathlib import Path
from collections import Counter
from datetime import datetime
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse
import uvicorn
import pprint

app = FastAPI()

import spacy
from spacy.matcher import PhraseMatcher, Matcher
from collections import defaultdict
import re

try:
    nlp = spacy.load("en_core_web_trf")
    USE_TRF = True
except Exception:
    nlp = spacy.load("en_core_web_sm")
    USE_TRF = False

# small helper regexes for quick validation
email_re = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
phone_re = re.compile(r"(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}")
short_token_re = re.compile(r"^[A-Za-z]{1,2}$")

# blacklist/whitelist samples (extend for your domain)
BLACKLIST = set(["The", "In", "On", "And", "If", "But"])
WHITELIST_TITLES = set(["Dr.", "Mr.", "Mrs.", "Ms.", "Prof."])

# optional high-precision phrase matcher for domain terms (invoices etc.)
phrase_matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
for phrase in ["invoice number", "due date", "invoice", "total amount", "amount due", "customer name"]:
    phrase_matcher.add("INVOICE_FIELD", [nlp.make_doc(phrase)])

# generic matcher to capture patterns like "Name: John Doe"
matcher = Matcher(nlp.vocab)
matcher.add("KV_PATTERN", [
    [{"IS_ALPHA": True, "OP": "+"}, {"IS_PUNCT": True, "OP": "?"}, {"IS_TITLE": True, "OP": "+"}],
])

def find_regex_entities(text):
    emails = "; ".join(email_re.findall(text))
    phones = "; ".join(phone_re.findall(text))
    return {"EMAIL": emails, "PHONE": phones}


# chunking to process long texts without losing context
def chunk_text(text, max_chars=3000, overlap=200):
    start = 0
    L = len(text)
    while start < L:
        end = start + max_chars
        if end >= L:
            yield text[start:L]
            break
        # try to end at newline or space within a small window
        cut = text.rfind("\n", start, end)
        if cut <= start:
            cut = text.rfind(" ", start, end)
        if cut <= start:
            cut = end
        yield text[start:cut]
        start = max(cut - overlap, cut)  # overlap for context

def is_likely_name(ent_text):
    # filter out very short tokens and blacklisted tokens
    if short_token_re.match(ent_text):
        return False
    if any(tok.lower() in ("invoice", "total", "amount", "date", "http", "www") for tok in ent_text.split()):
        return False
    if ent_text.split()[0] in BLACKLIST:
        return False
    return True

def add_entity(agg, ent_text, ctx):
    rec = agg[ent_text]
    rec["count"] += 1
    if len(rec["examples"]) < 3:
        rec["examples"].append(ctx)

def extract_with_spacy(text):
    persons = defaultdict(lambda: {"count": 0, "examples": []})
    orgs = defaultdict(lambda: {"count": 0, "examples": []})
    locs = defaultdict(lambda: {"count": 0, "examples": []})

    for chunk in chunk_text(text):
        doc = nlp(chunk)
        for _, start, end in phrase_matcher(doc):
            span = doc[start:end]
        for match_id, start, end in matcher(doc):
            span = doc[start:end]
            # not necessarily an entity, but may give context

        for ent in doc.ents:
            text_ent = ent.text.strip()
            label = ent.label_

            # basic filtering rules
            if len(text_ent) < 2:
                continue
            if text_ent in BLACKLIST:
                continue

            # context snippet for examples (trim)
            sent_ctx = ent.sent.text.strip()
            if len(sent_ctx) > 200:
                sent_ctx = sent_ctx[:200] + "..."

            # label mapping - adapt to what spaCy model returns
            if label in ("PERSON", "PER", "PERSONS"):
                if is_likely_name(text_ent) or any(t in WHITELIST_TITLES for t in text_ent.split()):
                    add_entity(persons, text_ent, sent_ctx)
            elif label in ("ORG", "ORGANIZATION", "COMPANY"):
                add_entity(orgs, text_ent, sent_ctx)
            elif label in ("GPE", "LOC", "LOCATION", "CITY", "COUNTRY"):
                add_entity(locs, text_ent, sent_ctx)
            else:
                pass

        if USE_TRF:
            for ent in doc.ents:
                try:
                    vec_norms = [t.vector_norm for t in ent]
                    avg = sum(vec_norms) / max(len(vec_norms), 1)
                    # if avg very small it's likely low-quality
                    if avg < 5.0:
                        # treat low-norm ent as lower confidence, optionally skip
                        continue
                except Exception:
                    pass

    def finalize(d):
        out = {}
        for k, v in d.items():
            out[k] = {"count": v["count"], "examples": v["examples"]}
        return out

    return finalize(persons), finalize(orgs), finalize(locs)

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


# this route will accept every txt/log file that is not csv
@app.post("/api/files")
async def postFile(file: UploadFile):
    if file.filename.endswith("csv"):
        return {"error" : "Cannot accept csv files"}

    try:
        contents = await file.read()
        text = contents.decode("utf-8", errors="ignore")
    except Exception as e:
        return {"error": f"Could not read file: {e}"}

    # Skip empty uploads
    if not text.strip():
        return {"error": "File is empty or unreadable"}

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", newline="", encoding="utf-8") as csvfile:
        print("Processing files...")
        temp_path = Path(csvfile.name)
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        row = {"filename" : file.filename}

        
        # Extract metadata
        metadata = extract_metadata(text, row["filename"])
        row.update(metadata)
        
        # Detect content type
        row["content_type"] = detect_content_type(text)
        row["text_preview"] = text[:500].replace('\n', ' ').replace('\r', ' ')
        
        
        # Fill in missing pattern fields
        for pattern_key in ["EMAIL", "PHONE", "UUID", "IBAN", "DATE", "URL", "SSN"]:
            if pattern_key not in row:
                row[pattern_key] = ""
        
        persons, orgs, locs = extract_with_spacy(text)
        regex_entities = find_regex_entities(text)
        row.update(regex_entities)
        row["persons"] = "; ".join([f"{k} ({v['count']})" for k, v in persons.items()])
        row["organizations"] = "; ".join([f"{k} ({v['count']})" for k, v in orgs.items()])
        row["locations"] = "; ".join([f"{k} ({v['count']})" for k, v in locs.items()])

        
        writer.writerow(row)
        print(pprint.pprint(row))

        return FileResponse(
            temp_path, media_type="text/csv", filename="dataset.csv"
        )

if __name__ == '__main__':
   uvicorn.run(app) 