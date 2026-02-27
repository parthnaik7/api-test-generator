"""
Integration tests for the API Test Case Generator FastAPI application.

These tests run against a live (in-process) FastAPI instance using httpx.AsyncClient.
They validate the full HTTP contract of each API endpoint.

Run with:
    PYTHONPATH=backend pytest tests/test_api_integration.py -v --tb=short
"""
import os
import sys

import pytest
import pytest_asyncio
import yaml
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.main import app  # noqa: E402

# ── Fixtures ─────────────────────────────────────────────────────────────────

SAMPLE_SPEC_PATH = os.path.join(os.path.dirname(__file__), "sample-spec.yaml")


@pytest.fixture(scope="module")
def sample_spec_bytes() -> bytes:
    with open(SAMPLE_SPEC_PATH, "rb") as f:
        return f.read()


@pytest_asyncio.fixture
async def client():
    """In-process async HTTP client — no real network, no port binding, no drama."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c


# ── Health endpoint ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_endpoint_returns_200(client):
    """GET /health → 200. If this fails you have bigger problems than test coverage."""
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_endpoint_returns_ok_status(client):
    """GET /health → body contains status: ok."""
    response = await client.get("/health")
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


# ── /api/generate endpoint ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_with_valid_yaml_returns_200(client, sample_spec_bytes):
    """POST /api/generate with a valid YAML spec → 200 with test cases."""
    response = await client.post(
        "/api/generate",
        files={"file": ("sample-spec.yaml", sample_spec_bytes, "application/yaml")},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_generate_response_has_required_fields(client, sample_spec_bytes):
    """POST /api/generate → response body includes success, total, summary, test_cases."""
    response = await client.post(
        "/api/generate",
        files={"file": ("sample-spec.yaml", sample_spec_bytes, "application/yaml")},
    )
    body = response.json()
    assert body["success"] is True
    assert body["total"] > 0
    assert "summary" in body
    assert "test_cases" in body
    assert len(body["test_cases"]) == body["total"]


@pytest.mark.asyncio
async def test_generate_summary_contains_category_breakdown(client, sample_spec_bytes):
    """POST /api/generate → summary.by_category is populated."""
    response = await client.post(
        "/api/generate",
        files={"file": ("sample-spec.yaml", sample_spec_bytes, "application/yaml")},
    )
    body = response.json()
    by_cat = body["summary"]["by_category"]
    assert "positive" in by_cat
    assert "negative" in by_cat
    assert "security" in by_cat
    assert "boundary" in by_cat


@pytest.mark.asyncio
async def test_generate_all_test_cases_have_required_fields(client, sample_spec_bytes):
    """POST /api/generate → every test case has id, name, category, method, path, expected_status."""
    response = await client.post(
        "/api/generate",
        files={"file": ("sample-spec.yaml", sample_spec_bytes, "application/yaml")},
    )
    required = {"id", "name", "category", "method", "path", "expected_status"}
    for tc in response.json()["test_cases"]:
        assert required.issubset(tc.keys()), f"TC missing fields: {tc.get('id')}"


@pytest.mark.asyncio
async def test_generate_with_invalid_file_type_returns_400(client):
    """POST /api/generate with a .txt file → 400. We're generating API tests, not poetry."""
    response = await client.post(
        "/api/generate",
        files={"file": ("spec.txt", b"not a spec", "text/plain")},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_generate_with_invalid_yaml_content_returns_400(client):
    """POST /api/generate with structurally invalid YAML content → 400."""
    garbage = b": : : invalid yaml {{{]]]\n"
    response = await client.post(
        "/api/generate",
        files={"file": ("bad.yaml", garbage, "application/yaml")},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_generate_with_missing_paths_returns_400(client):
    """POST /api/generate with YAML missing 'paths' key → 400."""
    no_paths = yaml.dump({"openapi": "3.0.0", "info": {"title": "Bad", "version": "1.0"}})
    response = await client.post(
        "/api/generate",
        files={"file": ("no_paths.yaml", no_paths.encode(), "application/yaml")},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_generate_with_oversized_file_returns_413(client):
    """POST /api/generate with a >10 MB file → 413. Specs don't need to be novels."""
    oversized = b"a: b\n" * 3_000_000  # ~15 MB
    response = await client.post(
        "/api/generate",
        files={"file": ("huge.yaml", oversized, "application/yaml")},
    )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_generate_test_case_ids_are_unique(client, sample_spec_bytes):
    """POST /api/generate → all generated test case IDs must be unique."""
    response = await client.post(
        "/api/generate",
        files={"file": ("sample-spec.yaml", sample_spec_bytes, "application/yaml")},
    )
    ids = [tc["id"] for tc in response.json()["test_cases"]]
    assert len(ids) == len(set(ids)), "Duplicate test case IDs in response"


# ── /api/validate endpoint ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_with_valid_spec_returns_200(client, sample_spec_bytes):
    """POST /api/validate with valid YAML spec → 200, valid: true."""
    response = await client.post(
        "/api/validate",
        files={"file": ("sample-spec.yaml", sample_spec_bytes, "application/yaml")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True


@pytest.mark.asyncio
async def test_validate_response_includes_metadata(client, sample_spec_bytes):
    """POST /api/validate → response includes title, version, oas_version, endpoint_count."""
    response = await client.post(
        "/api/validate",
        files={"file": ("sample-spec.yaml", sample_spec_bytes, "application/yaml")},
    )
    body = response.json()
    assert "title" in body
    assert "version" in body
    assert "oas_version" in body
    assert body["endpoint_count"] > 0


@pytest.mark.asyncio
async def test_validate_with_invalid_spec_returns_400(client):
    """POST /api/validate with a spec missing 'openapi' → 400, valid: false."""
    bad_spec = yaml.dump({"paths": {"/foo": {"get": {"responses": {"200": {"description": "ok"}}}}}})
    response = await client.post(
        "/api/validate",
        files={"file": ("bad.yaml", bad_spec.encode(), "application/yaml")},
    )
    assert response.status_code == 400
    assert response.json()["valid"] is False
