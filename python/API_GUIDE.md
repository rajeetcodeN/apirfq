# RFQ Intelligence API Guide

## Base URL
- **Local**: `http://localhost:8000`
- **Production**: `https://apirfq.onrender.com`

---

## Endpoints Overview

| Endpoint | Method | Purpose |
|---|---|---|
| `/process` | POST | Upload a file → Get extracted data |
| `/re-extract` | POST | Send text + feedback → Get corrected data instantly |
| `/correct` | POST | Save a correction → System learns for next time |
| `/health` | GET | Check system status |

---

## 1. `POST /process` — Main Extraction

Upload a PDF/image and get structured line items back.

### Request
```
Content-Type: multipart/form-data
```
| Field | Type | Required | Description |
|---|---|---|---|
| `file` | File | ✅ | The PDF or image file to process |

### Frontend Example
```javascript
const formData = new FormData();
formData.append('file', selectedFile);

const response = await fetch(`${API_BASE}/process`, {
  method: 'POST',
  body: formData
});

const result = await response.json();
```

### Response
```json
{
  "status": "success",
  "metadata": {
    "source": "hybrid_pdf",
    "document_type": "RFQ"
  },
  "header": {
    "rfq_number": "BES-2026-001",
    "supplier_name": "Würth",
    "document_type": "RFQ"
  },
  "data": {
    "requested_items": [
      {
        "pos": 1,
        "article_name": "PF-DIN6885-C45K-AS-20X12X100-M6",
        "quantity": 500,
        "unit": "pcs",
        "delivery_date": "2026-03-15",
        "config": {
          "material_id": "100-013-001.00-01",
          "standard": "DIN 6885",
          "form": "AS",
          "material": "C45+C",
          "dimensions": { "width": 20, "height": 12, "length": 100 },
          "features": [
            { "feature_type": "thread", "spec": "M6" }
          ],
          "weight_per_unit": null
        },
        "metadata": {
          "rule_confidence_score": 0.95,
          "raw_text_snippet": "001 Passfeder DIN6885 C45+C Form AS 20x12x100 M6",
          "status": "verified_correct"
        }
      }
    ]
  }
}
```

### Key Fields to Save in Frontend State

> [!IMPORTANT]
> You **must** save these from the response. They are needed for `/correct` and `/re-extract` later.

| Field | Where | Why you need it |
|---|---|---|
| `metadata.raw_text_snippet` | Inside each item | Required for `/correct` endpoint |
| `metadata.rule_confidence_score` | Inside each item | Show confidence badge in UI |
| `metadata.status` | Inside each item | Show verification status |
| The full OCR text | From the `/process` call context | Required for `/re-extract` endpoint |

### Frontend: Store the OCR text
The `/process` endpoint currently does not return the raw OCR text in the response (it's consumed internally). If you need it for `/re-extract`, you have two options:

**Option A** (Recommended): Store it server-side (in-memory or cache) and reference by `request_id`.
**Option B**: Modify `/process` to return `raw_text` in the response under a `debug` key.

---

## 2. `POST /re-extract` — Instant Re-Extraction with Feedback

Use this when the AI output is **wrong** and the user wants to **retry with a hint**. This re-runs the full AI extraction but with the user's feedback injected as a critical instruction.

### When to Use
- User clicks a **"Retry"** or **"Fix with Hint"** button.
- The AI completely misunderstood the document layout.
- A new format arrived and the AI needs guidance.

### Request
```
Content-Type: application/json
```
| Field | Type | Required | Description |
|---|---|---|---|
| `raw_text` | string | ✅ | The full OCR/native text of the document |
| `user_feedback` | string | ✅ | What the user wants the AI to fix |
| `native_text` | string | ❌ | Optional native PDF text for cross-validation |

### Frontend Example
```javascript
// User types: "The material is in the 3rd column, not the 2nd"
const feedback = userFeedbackInput.value;

const response = await fetch(`${API_BASE}/re-extract`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    raw_text: savedOcrText,           // The full text from the original /process call
    user_feedback: feedback,           // What the user wants fixed
    native_text: savedNativeText       // Optional
  })
});

const result = await response.json();
// result.data.requested_items -> Updated rows to replace in the grid
```

### Response
```json
{
  "status": "success",
  "data": {
    "requested_items": [
      { "pos": 1, "article_name": "...", "config": { ... }, "metadata": { ... } }
    ]
  },
  "message": "Re-extraction complete based on your feedback."
}
```

### Example Feedback Strings
These are real-world examples of what users might type:

| Scenario | Feedback String |
|---|---|
| Wrong column mapping | `"The material is in column 3, description is in column 2"` |
| Missing items | `"There are 15 items in total, you only extracted 10"` |
| Wrong dimensions | `"Dimensions are in format Length x Width x Height, not Width x Height x Length"` |
| Form confusion | `"B=20 means width is 20mm, the Form code is 'AS' which appears after the word 'Form'"` |
| Date format | `"Dates are in DD.MM.YYYY format, not MM/DD/YYYY"` |

---

## 3. `POST /correct` — Save Correction (Silent Learning)

Use this when a user **manually edits** a field in the data grid. The system silently saves this correction and uses it to improve future extractions for similar documents.

### When to Use
- User edits a cell in the grid (e.g., changes Form from "B" to "AS").
- User clicks "Save" after reviewing and fixing data.
- **This does NOT return new data** — it's fire-and-forget learning.

### Request
```
Content-Type: application/json
```
| Field | Type | Required | Description |
|---|---|---|---|
| `raw_text_snippet` | string | ✅ | The raw text line the AI originally parsed (from `item.metadata.raw_text_snippet`) |
| `correct_json` | object | ✅ | The corrected field values |
| `full_text_context` | string | ❌ | Full document text (helps with fingerprinting) |

### Frontend Example
```javascript
// When user edits a row and clicks Save
async function onRowSave(originalItem, editedRow) {
  await fetch(`${API_BASE}/correct`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      // 1. The original text line (from the extraction response)
      raw_text_snippet: originalItem.metadata.raw_text_snippet,

      // 2. What the user corrected it to
      correct_json: {
        form: editedRow.form,
        material: editedRow.material,
        dimensions: editedRow.dimensions,
        features: editedRow.features
      },

      // 3. Full document text for fingerprinting (optional but recommended)
      full_text_context: savedOcrText
    })
  });

  // No need to update the grid - the user already made the edit locally.
  // The system has silently learned for next time.
  showToast("✅ AI has learned from this correction");
}
```

### Response
```json
{
  "status": "success",
  "message": "Correction saved. The system has learned from this feedback."
}
```

---

## How It All Works Together (Flow Diagram)

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND                                 │
│                                                                 │
│  1. Upload PDF ──────────► POST /process ──────► Show in Grid   │
│                                                                 │
│  2. User sees errors?                                           │
│     ├─ Small fix ──────► Edit cell ──► POST /correct (learn)    │
│     └─ Big mess ───────► Type hint ──► POST /re-extract (retry) │
│                                        └──► Replace Grid Data   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                        BACKEND (Behind the scenes)              │
│                                                                 │
│  /process:                                                      │
│    1. OCR/Native text extraction                                │
│    2. PII Masking                                               │
│    3. Load learned corrections → Inject into AI prompt          │
│    4. Mistral AI extraction                                     │
│    5. Rule-based validation + confidence scoring                │
│    6. If confidence < 70% → AI Verifier double-checks           │
│    7. Return items with metadata                                │
│                                                                 │
│  /re-extract:                                                   │
│    1. Take raw text + user feedback                             │
│    2. Inject feedback as CRITICAL OVERRIDE in prompt            │
│    3. Re-run full extraction                                    │
│    4. Return corrected items                                    │
│                                                                 │
│  /correct:                                                      │
│    1. Save correction to data/corrections.json                  │
│    2. Next /process call for similar docs will use this          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Confidence Score & Status Guide

Each item in the response has `metadata.rule_confidence_score` and `metadata.status`:

| Score | Status | Meaning | UI Suggestion |
|---|---|---|---|
| 0.9 - 1.0 | *(no status)* | High confidence, passed rules | ✅ Green badge |
| 0.7 - 0.89 | *(no status)* | Medium confidence, passed rules | 🟡 Yellow badge |
| 0.5 - 0.69 | `verified_correct` | Low confidence, but AI verifier confirmed | 🟢 Green with ✓ icon |
| 0.5 - 0.69 | `auto_corrected_by_verifier` | Low confidence, AI verifier fixed it | 🔵 Blue "auto-fixed" badge |
| 0.5 - 0.69 | `flagged_by_verifier` | Low confidence, AI verifier couldn't fix | 🔴 Red "needs review" badge |
| < 0.5 | *(no status)* | Very low confidence | 🔴 Red highlight entire row |
