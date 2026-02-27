"""
API Test Case Generator - FastAPI Application
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import traceback
from collections import Counter
from typing import Any

import yaml
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Support both `uvicorn app.main:app` (from backend/) and direct run
try:
    from app.generator import TestCaseGenerator
except ModuleNotFoundError:
    from generator import TestCaseGenerator


def create_app() -> Any:
    app = FastAPI(
        title="API Test Case Generator",
        description="Generates comprehensive test cases from OpenAPI Specification files.",
        version="1.0.0",
        contact={"name": "API TestGen", "url": "https://github.com/your-repo"},
        license_info={"name": "MIT"},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


app = create_app()


@app.get("/health", tags=["system"])
def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "version": "1.0.0"}


@app.post("/api/generate", tags=["generate"])
async def generate_test_cases(file: UploadFile = File(...)) -> JSONResponse:
    """
    Upload an OAS spec (JSON or YAML) and receive generated test cases.
    Accepts: .json, .yaml, .yml files (max 10 MB).
    """
    filename = file.filename or ""
    if not any(filename.endswith(ext) for ext in (".json", ".yaml", ".yml", ".raml")):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload a .json, .yaml, .yml, or .raml API specification.",
        )

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10 MB.")

    try:
        spec = _parse_spec(content, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse spec: {exc}") from exc

    _validate_spec_structure(spec)

    try:
        generator = TestCaseGenerator(spec)
        test_cases = generator.generate()
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Test generation failed: {exc}") from exc

    return JSONResponse(content={
        "success": True,
        "total": len(test_cases),
        "summary": _build_summary(test_cases),
        "test_cases": test_cases,
    })


@app.post("/api/validate", tags=["generate"])
async def validate_spec(file: UploadFile = File(...)) -> JSONResponse:
    """Validate an OAS spec without generating test cases."""
    filename = file.filename or ""
    content = await file.read()
    try:
        spec = _parse_spec(content, filename)
        _validate_spec_structure(spec)
        paths = spec.get("paths", {})
        endpoint_count = sum(
            1 for _, item in paths.items()
            for method in item
            if method.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
        )
        return JSONResponse(content={
            "valid": True,
            "title": spec.get("info", {}).get("title", "Untitled"),
            "version": spec.get("info", {}).get("version", "unknown"),
            "oas_version": spec.get("openapi", spec.get("swagger", "unknown")),
            "endpoint_count": endpoint_count,
        })
    except (ValueError, HTTPException) as exc:
        return JSONResponse(content={"valid": False, "error": str(exc)}, status_code=400)


def _parse_spec(content: bytes, filename: str) -> dict:
    try:
        if filename.endswith(".json"):
            return json.loads(content)
        if filename.endswith(".raml"):
            # Write RAML to a temporary file
            with tempfile.NamedTemporaryFile(suffix=".raml", delete=False) as temp_raml:
                temp_raml.write(content)
                temp_raml_path = temp_raml.name

            try:
                # Convert RAML to OAS JSON using raml-to-openapi
                # Ensure the subprocess runs in a directory where npx can find it, or use global
                result = subprocess.run(
                    ["npx", "-y", "raml-to-openapi", temp_raml_path],
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                # The output should be JSON. It might contain additional logs, but we parse what we can.
                outp = result.stdout
                try:
                    # Often the node tool just prints the JSON, but we check if it starts with '{'
                    json_start = outp.find('{')
                    if json_start != -1:
                        outp = outp[json_start:]
                    return json.loads(outp)
                except json.JSONDecodeError as decode_exc:
                    raise ValueError(f"Failed to parse converted RAML JSON: {decode_exc}\nOutput: {outp}")
            except subprocess.CalledProcessError as sub_exc:
                raise ValueError(f"Failed to convert RAML. Make sure Node.js and npx are installed.\nError: {sub_exc.stderr}")
            finally:
                if os.path.exists(temp_raml_path):
                    os.remove(temp_raml_path)
        return yaml.safe_load(content)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(str(exc)) from exc


def _validate_spec_structure(spec: dict) -> None:
    if not isinstance(spec, dict):
        raise HTTPException(status_code=400, detail="Spec must be a JSON/YAML object.")
    if "openapi" not in spec and "swagger" not in spec:
        raise HTTPException(status_code=400, detail="Missing 'openapi' or 'swagger' version field.")
    if "paths" not in spec:
        raise HTTPException(status_code=400, detail="Missing 'paths' field in spec.")


def _build_summary(test_cases: list[dict]) -> dict:
    return {
        "by_category": dict(Counter(tc["category"] for tc in test_cases)),
        "by_method": dict(Counter(tc["method"] for tc in test_cases)),
        "by_expected_status": dict(Counter(tc["expected_status"] for tc in test_cases)),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
