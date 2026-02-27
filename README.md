# api-test-generator

> **Zero AI. Pure logic. Zero excuses for untested APIs.**

Stop manually writing `should return 400 when email is missing` for the 47th time.
Paste in your OpenAPI spec. Get hundreds of test cases back. Go touch grass.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)](https://fastapi.tiangolo.com)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](#running-tests)

---

## 🤔 Why does this exist?

Because API testing is one of those things everyone *knows* they should do properly, and nobody
actually does. You write the happy path, maybe a 404 check if you're feeling adventurous, and call
it a day. Meanwhile your production API accepts `{ "age": "<script>alert(1)</script>" }` without
blinking.

This tool generates the exhaustive test suite your QA engineer would write — if you had a QA
engineer, and they had infinite patience, and they really hated your server.

---

## 🚀 What does it actually generate?

| Category | What It Does | Why You'd Otherwise Skip It |
|---|---|---|
| **Positive** | Happy path with all valid inputs | "It obviously works lol" |
| **Negative** | Missing fields, null bodies, wrong Content-Type | "Who would send that?" |
| **Boundary** | Min/max values, empty strings, 10,000-char strings, SQL injection, XSS | "We sanitise inputs. Probably." |
| **Security** | Missing auth, malformed JWT, expired tokens, wrong scheme, SQL in Bearer | "Security is the infra team's problem" |
| **Forbidden (403)** | Authenticated with insufficient scope/role | "Wait, 401 and 403 are different?" |
| **Data Type** | Wrong primitives, arrays where objects expected, invalid enums | "TypeScript will catch that" (narrator: it didn't) |
| **Combinatorial** | Pairwise combinations of optional parameters | "I'll test that edge case later" |
| **CORS Preflight** | OPTIONS request with Origin + Access-Control headers | "It worked on localhost" |
| **Accept Negotiation** | `Accept: application/xml` → should return 406, not a stack trace | Nobody checks this. Ever. |
| **Rate Limiting (429)** | Documents expected behaviour when you flood the API | "We'll add rate limits in v2" |
| **Large Payload (413)** | Request body bigger than your API can stomach | "Max request size? What's that?" |
| **Idempotency** | PUT/PATCH twice should give the same result | REST spec says so. Just saying. |

---

## 🗂️ Project Structure

```
api-test-generator/
├── backend/                  # FastAPI application
│   ├── app/
│   │   ├── main.py           # FastAPI routes & app factory
│   │   ├── generator.py      # Core test generation engine (the smart bit)
│   │   └── __init__.py
│   └── requirements.txt
├── docs/                     # GitHub Pages frontend (static, no build step)
│   ├── index.html
│   ├── css/styles.css
│   └── js/app.js
├── tests/
│   ├── test_generator.py     # Unit tests for the generator engine
│   ├── test_api_integration.py  # FastAPI integration tests
│   └── sample-spec.yaml      # A sample OAS spec to kick the tyres on
└── README.md
```

---

## ⚡ Quick Start

### Backend (FastAPI)

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or, if you're a Makefile person:
```bash
make install && make run
```

API lives at:
- **Swagger UI**: http://localhost:8000/docs  ← click around, it's fine
- **Health Check**: `GET /health`
- **Generate**: `POST /api/generate`
- **Validate**: `POST /api/validate`

### Frontend (GitHub Pages)

The `docs/` folder is a self-contained static app. No webpack. No `npm run build`. No regrets.

```bash
cd docs && python -m http.server 3000
# Then open http://localhost:3000 and point it at your backend.
```

For GitHub Pages: **Settings → Pages → Source: `main` branch, `/docs` folder**. Done.

---

## 🔌 API Reference

### `POST /api/generate`

Upload your OAS spec (`.json`, `.yaml`, `.yml`) and receive a list of generated test cases.

**Request:** `multipart/form-data`, field name `file`. Max 10 MB. (If your spec is bigger than 10 MB,
that's a separate problem.)

**Response:**
```json
{
  "success": true,
  "total": 312,
  "summary": {
    "by_category": { "positive": 14, "negative": 120, "security": 88, "boundary": 60, "data_type": 30 },
    "by_method":   { "GET": 55, "POST": 140, "PUT": 70, "DELETE": 47 },
    "by_expected_status": { "200": 14, "400": 90, "401": 77, "403": 14, "406": 10, "413": 5, "429": 10 }
  },
  "test_cases": [
    {
      "id": "createUser_0001",
      "name": "TC_createUser_POSITIVE_happy_path",
      "description": "Verify POST /users returns 201 with all valid inputs",
      "category": "positive",
      "method": "POST",
      "path": "/users",
      "path_params": {},
      "query_params": {},
      "headers": {
        "Content-Type": "application/json",
        "Authorization": "Bearer eyJ...",
        "X-Request-ID": "test-req-00000000-0000-0000-0000-000000000001",
        "X-Correlation-ID": "test-corr-00000000-0000-0000-0000-000000000001"
      },
      "body": { "email": "valid@example.com", "age": 25 },
      "expected_status": 201,
      "expected_behavior": "Should return HTTP 201 with a valid response body",
      "tags": ["users"]
    }
  ]
}
```

### `POST /api/validate`
Validate a spec without generating test cases. Useful for CI gates or when you just want to feel
better about your YAML indentation before the real work starts.

### `GET /health`
Returns `{"status": "ok", "version": "1.0.0"}`. If this fails, you have a deployment problem,
not a testing problem.

---

## 🧪 Test Case Naming Convention

Naming inspired by Postman collections and BrowserStack test suites:

```
TC_{operationId}_{CATEGORY}_{scenario_description}

Examples:
  TC_createUser_POSITIVE_happy_path
  TC_createUser_NEGATIVE_body_missing_required_email
  TC_createUser_SECURITY_MISSING_AUTH_HEADER
  TC_createUser_SECURITY_FORBIDDEN_INSUFFICIENT_SCOPE
  TC_createUser_BOUNDARY_body_password_ABOVE_MAX_LENGTH
  TC_createUser_DATATYPE_body_age_as_str
  TC_listUsers_CORS_preflight_OPTIONS
  TC_createUser_NEGATIVE_accept_header_xml_only
  TC_createUser_NEGATIVE_rate_limit_exceeded
  TC_createUser_NEGATIVE_large_payload
  TC_updateUser_POSITIVE_idempotency_duplicate_request
```

---

## 🧑‍💻 Running Tests

```bash
# Unit tests (generator engine — no server needed)
PYTHONPATH=backend pytest tests/test_generator.py -v

# Integration tests (spins up a real FastAPI app in-process)
PYTHONPATH=backend pytest tests/test_api_integration.py -v

# Everything, because you're thorough now apparently
PYTHONPATH=backend pytest tests/ -v --tb=short
```

---

## 🧩 Extending the Generator

### Add new boundary scenarios
Edit `ValueGenerator.boundary_values()` in `backend/app/generator.py`.

### Add new security schemes
Add a new key to `AuthHeaderGenerator.SECURITY_SCHEMES` with `valid`, `invalid`, and `forbidden`
sub-keys. The `forbidden` list generates 403 tests; `invalid` generates 401 tests.

### Add new test categories
Add a case to `TestCaseGenerator._generate_for_operation()`. The pattern is consistent throughout.
Resist the urge to use AI to add test cases about AI test cases. It gets recursive fast.

---

## 🔒 Security & Privacy

- The backend **never stores uploaded specs** — files are processed in memory and discarded
- No external API calls during generation (it really is just logic, no magic tokens required)
- CORS is open by default for local dev — restrict `allow_origins` in production
- The SQL injection and XSS strings in boundary tests are *inputs to be tested against your API*,
  not actual attacks. Please don't file a security report because `'; DROP TABLE users; --` appears
  in a test fixture.

---

## 📦 Deployment

### Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t api-test-generator .
docker run -p 8000:8000 api-test-generator
```

### Railway / Render / Fly.io
Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

---

## 🛠️ Tech Stack

- **Backend**: Python 3.10+, FastAPI, PyYAML
- **Testing**: pytest, httpx (async client), pytest-asyncio
- **Frontend**: Vanilla HTML/CSS/JS — zero dependencies, zero build step, zero existential dread
- **Hosting**: GitHub Pages (frontend) + any Python host (backend)
- **AI used**: None. It's just `if` statements and `for` loops dressed up nicely.

---

## 📄 License

MIT © 2025 api-test-generator contributors

> *"Untested code is legacy code. Legacy code is someone else's problem.  
>  That someone else is usually future you at 11pm before a release."*
