# Security, Code Quality, and GDPR Compliance Review

This review analyzes the RFQ Intelligence Python Backend (`main.py`, `services/*`). The primary context considered is deployment for a **Medium-Sized Company in Germany**, which requires strict adherence to GDPR (DSGVO), robust code maintainability, and enterprise-grade security.

---

## 🔒 1. Security & GDPR Compliance (Critical Findings)

### 🚨 CRITICAL: Unmasked Data Leakage via n8n Webhook (`main.py`)
- **Issue**: The application sends raw, unmasked file bytes (`send_to_n8n()` function) to an external cloud webhook (`nosta.app.n8n.cloud`). 
- **Risk**: This is a severe GDPR violation. Personal identifiable information (PII) such as employee names, signatures, addresses, and sensitive corporate IP (pricing, technical drawings) are transmitted to a 3rd party without prior masking. 
- **Recommendation**: Remove the n8n integration or ensure strictly masked text (not raw bytes) is sent. Confirm a Data Processing Agreement (DPA / AVV) is signed with n8n cloud.

### 🚨 CRITICAL: Masking Service is Deficient (`masking.py`)
- **Issue**: The `/health` check in `main.py` references a Spacy/Presidio robust NLP engine, but `services/masking.py` **only implements Regex-based masking**. 
- **Risk**: Regex explicitly misses human names (contact persons, signatures), unique project IDs, and non-standard addresses. Because AI (Mistral) processes these documents, uploading PII to external APIs without reliable masking violates data minimization (Art. 5(1)(c) GDPR).
- **Recommendation**: Reinstate the Spacy/Presidio NLP-based masking to actively detect `PERSON`, `ORG`, and `LOC` entities contextually.

### ⚠️ HIGH: Missing API Authentication (`main.py`)
- **Issue**: The FastAPI routes (`/process`, `/correct`, `/re-extract`) have **no authentication mechanisms** (e.g., JWT, OAuth2, or API Keys).
- **Risk**: Anyone with the server URL can upload documents, consume your Mistral API credits (Denial of Wallet attack), or spam the correction model (Data Poisoning).
- **Recommendation**: Implement `fastapi.security.OAuth2PasswordBearer` or simple API Key middleware using `Depends()`.

### ⚠️ HIGH: Permissive CORS Configuration (`main.py`)
- **Issue**: The CORS middleware uses a regex `r"https://.*\.vercel\.app"`.
- **Risk**: Any developer on Vercel can spin up a UI and bypass CORS to interact with your publicly exposed backend.
- **Recommendation**: Specify fully qualified domains for production or validate explicit origins via environment variables.

### ⚠️ MEDIUM: 3rd-Party LLM Dependency (Mistral API)
- **Issue**: Using Mistral AI for OCR and data extraction (`services.ocr`, `services.ai`).
- **GDPR Context**: Ensure you have explicitly opted out of data training (Mistral typically does this for API, but verify) and that you hold a valid AVV (Auftragsverarbeitungsvertrag) with Mistral AI. The `delete_from_mistral` function in `ocr.py` is a good technical step for Right to be Forgotten, but legal backing is required.

---

## 🛠 2. Code Quality & Architecture

### ❌ Brittle, Hardcoded Business Logic (`validator.py`, `masking.py`)
- **Issue**: Company names (`Nosta GmbH`, `REYHER`) and highly specific material catalogs (`["C45", "42CrMo4", ...]`) are hardcoded directly into the Python source files.
- **Impact**: The codebase is not generic. If the company onboard a new vendor or material, a developer must modify Python source code and redeploy, rather than updating a database or configuration file.
- **Fix**: Move `VALID_MATERIALS`, `MATERIAL_FIX_MAP`, and `known_companies` to a `.yaml`, `.json` configuration file, or fetch them dynamically from a database.

### ❌ Blocking Async Architecture (`ai.py` & `ocr.py`)
- **Issue**: The project heavily utilizes the synchronous `requests` library within an asynchronous FastAPI ecosystem. While `ai.py` attempts a workaround using `loop.run_in_executor`, `ocr.py` uses blocking `requests.post()` directly in the upload flow.
- **Impact**: Under high concurrency (multiple RFQs uploaded simultaneously), the server's thread pool will block, severely bottlenecking throughput and causing timeout crashes for users.
- **Fix**: Replace all `requests` usage with `httpx.AsyncClient`. You are already using `httpx` in `main.py` (`send_to_n8n`), so adopt it universally.

### ❌ Over-Broad Exception Handling
- **Issue**: Patterns like `except Exception as e:` are rampant across `main.py`, `validator.py`, and `ai.py` without capturing tracebacks properly.
- **Impact**: It swallows critical validation bugs, making system failures impossible to debug from logs.
- **Fix**: Catch specific exceptions (e.g., `httpx.TimeoutException`, `json.JSONDecodeError`) and use `logger.exception("...")` to natively capture stack traces.

### ⚠️ Monolithic Functions
- **Issue**: `process_file` in `main.py` routes ingestion, handles masking, calls AI, handles fallbacks, and formats responses across 120 lines.
- **Impact**: Reduced readability and harder to write unit tests for isolated pipeline steps.
- **Fix**: Refactor the pipeline into a cohesive Builder/Pipeline pattern natively within the `services` module.

---

## 🚀 Summary of Actions for Development Team

1. Implement **Token-based Authentication** immediately.
2. Sever or rewrite the **n8n webhook** integration to strictly send masked data.
3. Bring back **NLP-based PII Masking** (Spacy).
4. Extract material/vendor **hardcoded lists** into an external `.json` configuration that can be updated independently of code deployments.
5. Swap `requests` for `httpx.AsyncClient` across all Mistral API integrations to prevent thread blocking in production. 
