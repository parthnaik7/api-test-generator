"""
API Test Case Generator Engine
Generates comprehensive test cases from OpenAPI Specification (OAS) without AI.
Covers: positive, negative, boundary, data type, auth, and combinatorial scenarios.
"""

from __future__ import annotations

import copy
import itertools
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Domain Types
# ---------------------------------------------------------------------------

class TestCategory(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    BOUNDARY = "boundary"
    SECURITY = "security"
    DATA_TYPE = "data_type"
    COMBINATORIAL = "combinatorial"


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


@dataclass
class TestCase:
    id: str
    name: str
    description: str
    category: TestCategory
    method: str
    path: str
    path_params: dict[str, Any] = field(default_factory=dict)
    query_params: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    expected_status: int = 200
    expected_behavior: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "method": self.method,
            "path": self.path,
            "path_params": self.path_params,
            "query_params": self.query_params,
            "headers": self.headers,
            "body": self.body,
            "expected_status": self.expected_status,
            "expected_behavior": self.expected_behavior,
            "tags": self.tags,
        }


# ---------------------------------------------------------------------------
# Value Generators
# ---------------------------------------------------------------------------

class ValueGenerator:
    """Generates typed test values for schema properties."""

    _STRING_FORMATS = {
        "email": ("valid@example.com", "invalid-email", "a" * 256 + "@b.com"),
        "uuid": ("550e8400-e29b-41d4-a716-446655440000", "not-a-uuid", ""),
        "date": ("2024-01-15", "2024-13-45", "not-a-date"),
        "date-time": ("2024-01-15T10:30:00Z", "2024-01-15 bad", ""),
        "uri": ("https://example.com/path", "not a uri", ""),
        "ipv4": ("192.168.1.1", "999.999.999.999", ""),
        "ipv6": ("2001:0db8:85a3:0000:0000:8a2e:0370:7334", "invalid", ""),
        "hostname": ("example.com", "invalid host!", ""),
        "byte": ("dGVzdA==", "not-base64!!!", ""),
        "binary": ("binary-content", "", None),
        "password": ("SecureP@ss123", "", "a"),
        "phone": ("+1-555-0100", "abc", ""),
    }

    @classmethod
    def valid(cls, schema: dict, name: str = "field") -> Any:
        return cls._generate(schema, name, mode="valid")

    @classmethod
    def invalid_type(cls, schema: dict) -> list[Any]:
        """Return values of wrong types for the given schema type."""
        t = schema.get("type", "string")
        mapping = {
            "string": [123, True, [], {}],
            "integer": ["not_int", True, [], {}],
            "number": ["not_num", [], {}],
            "boolean": ["true", 1, [], {}],
            "array": ["not_array", 123, {}],
            "object": ["not_object", 123, []],
        }
        return mapping.get(t, ["invalid"])

    @classmethod
    def boundary_values(cls, schema: dict) -> list[tuple[str, Any]]:
        """Return (label, value) boundary pairs for a schema."""
        t = schema.get("type", "string")
        results: list[tuple[str, Any]] = []

        if t in ("integer", "number"):
            minimum = schema.get("minimum") or schema.get("exclusiveMinimum")
            maximum = schema.get("maximum") or schema.get("exclusiveMaximum")
            exclusive_min = "exclusiveMinimum" in schema
            exclusive_max = "exclusiveMaximum" in schema

            if minimum is not None:
                results.append(("at_minimum", minimum))
                results.append(("below_minimum", minimum - 1))
                if not exclusive_min:
                    results.append(("just_above_minimum", minimum + 1))
            if maximum is not None:
                results.append(("at_maximum", maximum))
                results.append(("above_maximum", maximum + 1))
                if not exclusive_max:
                    results.append(("just_below_maximum", maximum - 1))
            if not results:
                results = [
                    ("zero", 0),
                    ("negative", -1),
                    ("max_int", 2**31 - 1),
                    ("min_int", -(2**31)),
                    ("large_float", 1.7976931348623157e+308 if t == "number" else None),
                ]
                results = [(lbl, v) for lbl, v in results if v is not None]

        elif t == "string":
            min_len = schema.get("minLength", 0)
            max_len = schema.get("maxLength")
            results.append(("empty_string", ""))
            results.append(("single_char", "a"))
            results.append(("at_min_length", "a" * max(min_len, 1)))
            if min_len > 0:
                results.append(("below_min_length", "a" * (min_len - 1)))
            if max_len:
                results.append(("at_max_length", "a" * max_len))
                results.append(("above_max_length", "a" * (max_len + 1)))
            else:
                results.append(("very_long_string", "a" * 10000))
            results.append(("whitespace_only", "   "))
            results.append(("special_chars", "!@#$%^&*()<>?/\\|{}[]~`"))
            results.append(("unicode", "测试テスト한국어αβγ"))
            results.append(("sql_injection", "'; DROP TABLE users; --"))
            results.append(("xss_payload", "<script>alert('xss')</script>"))
            results.append(("newlines", "line1\nline2\r\nline3"))
            results.append(("null_byte", "test\x00value"))

        elif t == "array":
            min_items = schema.get("minItems", 0)
            max_items = schema.get("maxItems")
            results.append(("empty_array", []))
            results.append(("single_item_array", [cls._generate(schema.get("items", {}), "item", "valid")]))
            if min_items > 0:
                results.append(("below_min_items", []))
            if max_items:
                valid_item = cls._generate(schema.get("items", {}), "item", "valid")
                results.append(("at_max_items", [valid_item] * max_items))
                results.append(("above_max_items", [valid_item] * (max_items + 1)))

        return results

    @classmethod
    def _generate(cls, schema: dict, name: str, mode: str) -> Any:
        if not schema:
            return "test_value"

        # Handle $ref resolution placeholder
        if "$ref" in schema:
            return {"$ref_placeholder": schema["$ref"]}

        schema_type = schema.get("type", "string")
        enum_values = schema.get("enum")
        if enum_values:
            return enum_values[0] if mode == "valid" else "NOT_IN_ENUM_LIST"

        if schema_type == "string":
            fmt = schema.get("format", "")
            fmt_vals = cls._STRING_FORMATS.get(fmt)
            if fmt_vals:
                return fmt_vals[0] if mode == "valid" else fmt_vals[1]
            pattern = schema.get("pattern")
            if pattern:
                return cls._pattern_example(pattern)
            return "test_" + name[:20] if mode == "valid" else ""

        elif schema_type == "integer":
            minimum = schema.get("minimum", 1)
            maximum = schema.get("maximum")
            val = max(minimum, 1)
            if maximum:
                val = min(val, maximum)
            return val

        elif schema_type == "number":
            minimum = schema.get("minimum", 0.0)
            return float(maximum if (maximum := schema.get("maximum")) else minimum + 1.5)

        elif schema_type == "boolean":
            return True

        elif schema_type == "array":
            items_schema = schema.get("items", {"type": "string"})
            return [cls._generate(items_schema, name + "_item", mode)]

        elif schema_type == "object":
            return cls._generate_object(schema, mode)

        elif schema_type == "null":
            return None

        return "test_value"

    @classmethod
    def _generate_object(cls, schema: dict, mode: str) -> dict:
        result = {}
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for prop_name, prop_schema in properties.items():
            if mode == "valid" or prop_name in required:
                result[prop_name] = cls._generate(prop_schema, prop_name, mode)
        return result

    @classmethod
    def _pattern_example(cls, pattern: str) -> str:
        """Generate a simple example string matching common patterns."""
        common = {
            r"^\d+$": "12345",
            r"^[A-Z]{2,3}$": "AB",
            r"^\+?[0-9\-\s()]+$": "+1-555-0100",
            r"^[a-zA-Z0-9_]+$": "test_User1",
            r"^[a-z0-9]+$": "testvalue123",
        }
        for pat, val in common.items():
            if pat == pattern:
                return val
        return "PATTERN_MATCH_EXAMPLE"


# ---------------------------------------------------------------------------
# Auth Header Generator
# ---------------------------------------------------------------------------

class AuthHeaderGenerator:
    """Generates valid and invalid authentication header combinations."""

    # A structurally valid JWT with minimal claims — won't pass real signature validation,
    # but that's exactly the point: we're testing the API, not your JWT library.
    _VALID_JWT = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IlRlc3QgVXNlciIsImlhdCI6MTUxNjIzOTAyMn0"
        ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )

    # Simulated low-privilege token — valid structure, but claims insufficient scope.
    # Expect the API to return 403 Forbidden, not 401 Unauthorized.
    _LOW_PRIVILEGE_JWT = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiI5ODc2NTQzMjEwIiwicm9sZSI6InJlYWQtb25seSIsImlhdCI6MTUxNjIzOTAyMn0"
        ".low_privilege_sig"
    )

    SECURITY_SCHEMES = {
        "bearer": {
            "valid": {"Authorization": f"Bearer {_LOW_PRIVILEGE_JWT}"},  # overridden in get_valid_headers
            "invalid": [
                ("missing_auth_header", {}),
                ("empty_bearer_token", {"Authorization": "Bearer "}),
                ("malformed_bearer", {"Authorization": "Bearer invalid.token.here"}),
                ("expired_token", {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJleHAiOjE1MTYyMzkwMjJ9.expired"}),
                ("wrong_scheme", {"Authorization": "Basic dXNlcjpwYXNz"}),
                ("no_bearer_prefix", {"Authorization": "eyJhbGciOiJIUzI1NiJ9.payload.sig"}),
                ("extra_spaces", {"Authorization": "Bearer  extra  spaces"}),
                ("bearer_lowercase", {"authorization": "bearer token123"}),
                ("sql_injection_token", {"Authorization": "Bearer ' OR '1'='1"}),
                ("very_long_token", {"Authorization": "Bearer " + "a" * 5000}),
                ("special_chars_token", {"Authorization": "Bearer !@#$%^&*()"}),
            ],
            # 403: authenticated, but lacks permissions (read-only token hitting a write endpoint)
            "forbidden": [
                ("insufficient_scope", {"Authorization": f"Bearer {_LOW_PRIVILEGE_JWT}"}),
                ("read_only_token_on_write", {"Authorization": "Bearer read_only_access_token_xyz"}),
            ],
        },
        "basic": {
            "valid": {"Authorization": "Basic dXNlcjpwYXNzd29yZA=="},  # user:password
            "invalid": [
                ("missing_auth_header", {}),
                ("empty_credentials", {"Authorization": "Basic "}),
                ("non_base64", {"Authorization": "Basic not-valid-base64!!!"}),
                ("missing_colon", {"Authorization": "Basic dXNlcm5hbWU="}),  # "username" no colon
                ("empty_username", {"Authorization": "Basic OnBhc3N3b3Jk"}),  # :password
                ("empty_password", {"Authorization": "Basic dXNlcjoA"}),  # user:\x00
                ("wrong_scheme", {"Authorization": "Bearer faketoken"}),
            ],
            "forbidden": [],
        },
        "apiKey_header": {
            "valid": {"X-API-Key": "valid-api-key-12345"},
            "invalid": [
                ("missing_api_key", {}),
                ("empty_api_key", {"X-API-Key": ""}),
                ("wrong_key_name", {"API-Key": "valid-api-key-12345"}),
                ("invalid_api_key_value", {"X-API-Key": "invalid-key"}),
                ("sql_injection", {"X-API-Key": "'; DROP TABLE api_keys; --"}),
                ("very_long_key", {"X-API-Key": "k" * 5000}),
            ],
            "forbidden": [
                ("insufficient_permissions", {"X-API-Key": "read-only-api-key-00000"}),
            ],
        },
        "apiKey_query": {
            "valid": {"api_key": "valid-api-key-12345"},
            "invalid": [
                ("missing_api_key", {}),
                ("empty_api_key_param", {"api_key": ""}),
                ("invalid_key_value", {"api_key": "wrong-key"}),
            ],
            "forbidden": [],
        },
        "oauth2": {
            "valid": {"Authorization": "Bearer valid_oauth2_access_token"},
            "invalid": [
                ("missing_token", {}),
                ("revoked_token", {"Authorization": "Bearer revoked_token_12345"}),
                ("wrong_scope_token", {"Authorization": "Bearer insufficient_scope_token"}),
                ("expired_access_token", {"Authorization": "Bearer expired_access_token"}),
            ],
            "forbidden": [
                ("insufficient_scope", {"Authorization": "Bearer valid_but_low_scope_token"}),
            ],
        },
    }

    @classmethod
    def get_valid_headers(cls, security_schemes: list[dict]) -> dict[str, str]:
        """Return a valid auth header for the first recognised security scheme."""
        headers = {}
        for scheme in security_schemes:
            scheme_type = scheme.get("type", "bearer")
            scheme_data = cls.SECURITY_SCHEMES.get(scheme_type, cls.SECURITY_SCHEMES["bearer"])
            # For bearer use the well-formed JWT, not the low-privilege one stored in the dict
            if scheme_type == "bearer":
                headers.update({"Authorization": f"Bearer {cls._VALID_JWT}"})
            else:
                headers.update(scheme_data["valid"])
        return headers

    @classmethod
    def get_invalid_header_cases(cls, security_schemes: list[dict]) -> list[tuple[str, dict]]:
        """Return (label, headers) pairs that should trigger a 401 Unauthorized response."""
        cases = []
        for scheme in security_schemes:
            scheme_type = scheme.get("type", "bearer")
            scheme_data = cls.SECURITY_SCHEMES.get(scheme_type, cls.SECURITY_SCHEMES["bearer"])
            cases.extend(scheme_data["invalid"])
        if not cases:
            cases = cls.SECURITY_SCHEMES["bearer"]["invalid"]
        return cases

    @classmethod
    def get_forbidden_header_cases(cls, security_schemes: list[dict]) -> list[tuple[str, dict]]:
        """Return (label, headers) pairs that should trigger a 403 Forbidden response.

        These represent authenticated-but-unauthorised scenarios:
        valid credentials, wrong role/scope. A 403 means the server knows who you
        are, it just doesn't like you very much.
        """
        cases: list[tuple[str, dict]] = []
        for scheme in security_schemes:
            scheme_type = scheme.get("type", "bearer")
            scheme_data = cls.SECURITY_SCHEMES.get(scheme_type, cls.SECURITY_SCHEMES["bearer"])
            cases.extend(scheme_data.get("forbidden", []))
        if not cases:
            cases = cls.SECURITY_SCHEMES["bearer"].get("forbidden", [])
        return cases


# ---------------------------------------------------------------------------
# Schema Resolver
# ---------------------------------------------------------------------------

class SchemaResolver:
    """Resolves $ref references within an OAS spec."""

    def __init__(self, spec: dict):
        self.spec = spec
        self.components = spec.get("components", spec.get("definitions", {}))

    def resolve(self, schema: dict, depth: int = 0) -> dict:
        if depth > 10:
            return {"type": "string", "description": "max_depth_reached"}
        if "$ref" in schema:
            return self._resolve_ref(schema["$ref"], depth)
        if "allOf" in schema:
            return self._merge_all_of(schema["allOf"], depth)
        if "oneOf" in schema or "anyOf" in schema:
            variants = schema.get("oneOf") or schema.get("anyOf")
            return self.resolve(variants[0], depth + 1) if variants else {}
        if schema.get("type") == "object" and "properties" in schema:
            resolved = copy.deepcopy(schema)
            resolved["properties"] = {
                k: self.resolve(v, depth + 1)
                for k, v in schema["properties"].items()
            }
            return resolved
        if schema.get("type") == "array" and "items" in schema:
            resolved = copy.deepcopy(schema)
            resolved["items"] = self.resolve(schema["items"], depth + 1)
            return resolved
        return schema

    def _resolve_ref(self, ref: str, depth: int) -> dict:
        parts = ref.lstrip("#/").split("/")
        node = self.spec
        for part in parts:
            if isinstance(node, dict):
                node = node.get(part, {})
            else:
                return {}
        return self.resolve(node, depth + 1) if isinstance(node, dict) else {}

    def _merge_all_of(self, schemas: list, depth: int) -> dict:
        merged: dict = {"type": "object", "properties": {}, "required": []}
        for s in schemas:
            resolved = self.resolve(s, depth + 1)
            merged["properties"].update(resolved.get("properties", {}))
            merged["required"].extend(resolved.get("required", []))
        return merged


# ---------------------------------------------------------------------------
# Test Case Generator
# ---------------------------------------------------------------------------

class TestCaseGenerator:
    """
    Main engine that parses an OAS spec and generates exhaustive test cases.
    """

    def __init__(self, spec: dict):
        self.spec = spec
        self.resolver = SchemaResolver(spec)
        self._counter = 0
        self._content_type_header = {"Content-Type": "application/json", "Accept": "application/json"}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def generate(self) -> list[dict]:
        test_cases: list[TestCase] = []
        paths = self.spec.get("paths", {})
        global_security = self.spec.get("security", [])
        security_schemes = self._extract_security_schemes(global_security)

        for path, path_item in paths.items():
            for method_str, operation in path_item.items():
                if method_str.upper() not in [m.value for m in HttpMethod]:
                    continue
                method = method_str.upper()
                op_security = operation.get("security", global_security)
                op_sec_schemes = self._extract_security_schemes(op_security)
                effective_security = op_sec_schemes or security_schemes

                test_cases.extend(self._generate_for_operation(path, method, operation, effective_security))

        return [tc.to_dict() for tc in test_cases]

    # ------------------------------------------------------------------ #
    # Per-Operation Generation
    # ------------------------------------------------------------------ #

    def _generate_for_operation(
        self,
        path: str,
        method: str,
        operation: dict,
        security_schemes: list[dict],
    ) -> list[TestCase]:
        cases: list[TestCase] = []
        parameters = self._collect_parameters(operation)
        request_body_schema = self._extract_request_body_schema(operation)
        success_code = self._primary_success_code(operation)
        op_id = operation.get("operationId", self._path_to_id(path, method))
        tags = operation.get("tags", [])

        valid_headers = {**self._content_type_header}
        if security_schemes:
            valid_headers.update(AuthHeaderGenerator.get_valid_headers(security_schemes))
        # RFC 7231 / Postman best practice: always send correlation/tracing headers
        valid_headers["X-Request-ID"] = "test-req-00000000-0000-0000-0000-000000000001"
        valid_headers["X-Correlation-ID"] = "test-corr-00000000-0000-0000-0000-000000000001"

        valid_path_params = self._build_valid_params(parameters, "path")
        valid_query_params = self._build_valid_params(parameters, "query")
        valid_body = ValueGenerator.valid(request_body_schema) if request_body_schema else None

        # 1. Happy path
        cases.append(self._make_case(
            op_id=op_id, suffix="happy_path",
            description=f"Verify {method} {path} returns {success_code} with all valid inputs",
            category=TestCategory.POSITIVE,
            method=method, path=path,
            path_params=valid_path_params,
            query_params=valid_query_params,
            headers=valid_headers,
            body=valid_body,
            expected_status=success_code,
            expected_behavior=f"Should return HTTP {success_code} with a valid response body",
            tags=tags,
        ))

        # 2. Auth / Security tests — 401 Unauthorized
        if security_schemes:
            for label, bad_headers in AuthHeaderGenerator.get_invalid_header_cases(security_schemes):
                headers = {**self._content_type_header, **bad_headers}
                cases.append(self._make_case(
                    op_id=op_id, suffix=f"security_{label}",
                    description=f"Verify {method} {path} returns 401 when auth is: {label}",
                    category=TestCategory.SECURITY,
                    method=method, path=path,
                    path_params=valid_path_params,
                    query_params=valid_query_params,
                    headers=headers,
                    body=valid_body,
                    expected_status=401,
                    expected_behavior="Should return HTTP 401 Unauthorized",
                    tags=tags,
                ))

            # 2b. 403 Forbidden — authenticated but lacks permissions (Postman / Sauce Labs pattern)
            for label, forbidden_headers in AuthHeaderGenerator.get_forbidden_header_cases(security_schemes):
                merged = {**self._content_type_header, **valid_headers, **forbidden_headers}
                cases.append(self._make_case(
                    op_id=op_id, suffix=f"security_forbidden_{label}",
                    description=(
                        f"Verify {method} {path} returns 403 when authenticated with "
                        f"insufficient permissions: {label}"
                    ),
                    category=TestCategory.SECURITY,
                    method=method, path=path,
                    path_params=valid_path_params,
                    query_params=valid_query_params,
                    headers=merged,
                    body=valid_body,
                    expected_status=403,
                    expected_behavior="Should return HTTP 403 Forbidden (authenticated, but not authorised)",
                    tags=tags,
                ))

        # 3. Parameter tests (negative + boundary + data type)
        for param in parameters:
            p_name = param.get("name", "param")
            p_in = param.get("in", "query")
            p_schema = self.resolver.resolve(param.get("schema", {"type": "string"}))
            required = param.get("required", False)

            if required:
                # Missing required param
                modified_path_p = dict(valid_path_params)
                modified_query_p = dict(valid_query_params)
                if p_in == "path":
                    modified_path_p.pop(p_name, None)
                else:
                    modified_query_p.pop(p_name, None)
                cases.append(self._make_case(
                    op_id=op_id, suffix=f"param_missing_{p_name}",
                    description=f"Verify {method} {path} returns 400 when required parameter '{p_name}' is absent",
                    category=TestCategory.NEGATIVE,
                    method=method, path=path,
                    path_params=modified_path_p,
                    query_params=modified_query_p,
                    headers=valid_headers,
                    body=valid_body,
                    expected_status=400,
                    expected_behavior=f"Should return HTTP 400 Bad Request: missing required param '{p_name}'",
                    tags=tags,
                ))

            # Invalid type values
            for bad_val in ValueGenerator.invalid_type(p_schema):
                label = str(type(bad_val).__name__)
                dest_p = dict(valid_path_params) if p_in == "path" else dict(valid_query_params)
                dest_q = dict(valid_query_params)
                if p_in == "path":
                    dest_p[p_name] = bad_val
                else:
                    dest_q[p_name] = bad_val
                cases.append(self._make_case(
                    op_id=op_id, suffix=f"param_invalid_type_{p_name}_{label}",
                    description=f"Verify {method} {path} rejects param '{p_name}' with wrong type ({label})",
                    category=TestCategory.DATA_TYPE,
                    method=method, path=path,
                    path_params=dest_p if p_in == "path" else valid_path_params,
                    query_params=dest_q,
                    headers=valid_headers,
                    body=valid_body,
                    expected_status=400,
                    expected_behavior=f"Should return HTTP 400: invalid type for '{p_name}'",
                    tags=tags,
                ))

            # Boundary values
            for b_label, b_val in ValueGenerator.boundary_values(p_schema):
                exp_status = 400 if "invalid" in b_label or "above" in b_label or "below" in b_label else success_code
                dest_p = dict(valid_path_params)
                dest_q = dict(valid_query_params)
                if p_in == "path":
                    dest_p[p_name] = b_val
                else:
                    dest_q[p_name] = b_val
                cases.append(self._make_case(
                    op_id=op_id, suffix=f"boundary_{p_name}_{b_label}",
                    description=f"Boundary test for param '{p_name}': {b_label} = {repr(b_val)!r:.80}",
                    category=TestCategory.BOUNDARY,
                    method=method, path=path,
                    path_params=dest_p if p_in == "path" else valid_path_params,
                    query_params=dest_q,
                    headers=valid_headers,
                    body=valid_body,
                    expected_status=exp_status,
                    expected_behavior=f"Boundary '{b_label}': expect HTTP {exp_status}",
                    tags=tags,
                ))

        # 4. Request body tests
        if request_body_schema:
            cases.extend(self._generate_body_tests(
                op_id, method, path, valid_path_params, valid_query_params,
                valid_headers, request_body_schema, success_code, tags
            ))

        # 5. Content-Type negative
        if request_body_schema and method in ("POST", "PUT", "PATCH"):
            for ct, exp in [
                ("text/plain", 415),
                ("application/xml", 415),
                ("", 400),
                ("application/json", 400), # we need a separate label since 'application/json; charset=invalid' resolves to application_json
            ]:
                if ct == "application/json":
                    ct = "application/json; charset=invalid"
                bad_ct_headers = {**valid_headers, "Content-Type": ct}
                
                # Sanitize the content type for the test name
                ct_label = ct.replace('/', '_').replace(';', '').replace(' ', '_').replace('-', '_')
                
                cases.append(self._make_case(
                    op_id=op_id, suffix=f"content_type_{ct_label}",
                    description=f"Verify {method} {path} returns {exp} for Content-Type: '{ct}'",
                    category=TestCategory.NEGATIVE,
                    method=method, path=path,
                    path_params=valid_path_params,
                    query_params=valid_query_params,
                    headers=bad_ct_headers,
                    body=valid_body,
                    expected_status=exp,
                    expected_behavior=f"Should return HTTP {exp} for unsupported Content-Type",
                    tags=tags,
                ))

        # 6. HTTP Method negative (wrong methods)
        if method in ("GET", "DELETE"):
            cases.append(self._make_case(
                op_id=op_id, suffix="wrong_method_post",
                description=f"Verify {path} returns 405 when POST is used instead of {method}",
                category=TestCategory.NEGATIVE,
                method="POST",
                path=path,
                path_params=valid_path_params,
                query_params=valid_query_params,
                headers=valid_headers,
                body=None,
                expected_status=405,
                expected_behavior="Should return HTTP 405 Method Not Allowed",
                tags=tags,
            ))

        # 7. Combinatorial: optional params on/off pairs
        optional_params = [p for p in parameters if not p.get("required", False)]
        if 2 <= len(optional_params) <= 6:
            cases.extend(self._generate_combinatorial(
                op_id, method, path, valid_path_params, valid_query_params,
                valid_headers, valid_body, optional_params, success_code, tags
            ))

        # 8. CORS preflight (BrowserStack / web-app testing standard)
        # OPTIONS requests are often untested until someone deploys and the browser screams.
        cases.append(self._make_case(
            op_id=op_id, suffix="cors_preflight",
            description=(
                f"Verify {path} responds correctly to a CORS preflight OPTIONS request. "
                "Any browser-facing API must handle this or developers will spend a full "
                "afternoon staring at 'blocked by CORS policy' errors."
            ),
            category=TestCategory.NEGATIVE,
            method="OPTIONS",
            path=path,
            path_params=valid_path_params,
            query_params={},
            headers={
                "Origin": "https://test.example.com",
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "Authorization, Content-Type, X-Request-ID",
            },
            body=None,
            expected_status=200,
            expected_behavior=(
                "Should return HTTP 200/204 with Access-Control-Allow-Origin, "
                "Access-Control-Allow-Methods, and Access-Control-Allow-Headers headers"
            ),
            tags=tags,
        ))

        # 9. Accept header negotiation → 406 (Postman/Sauce Labs API contract standard)
        if method not in ("OPTIONS",):
            cases.append(self._make_case(
                op_id=op_id, suffix="accept_header_xml_406",
                description=(
                    f"Verify {method} {path} returns 406 Not Acceptable when the client "
                    "demands application/xml and the server only speaks JSON."
                ),
                category=TestCategory.NEGATIVE,
                method=method,
                path=path,
                path_params=valid_path_params,
                query_params=valid_query_params,
                headers={**valid_headers, "Accept": "application/xml"},
                body=valid_body,
                expected_status=406,
                expected_behavior="Should return HTTP 406 Not Acceptable — no common media type",
                tags=tags,
            ))

        # 10. Rate limiting → 429 (Postman monitor / load-test gateway standard)
        # Real rate-limit testing requires tooling like k6 or Gatling for volume,
        # but this case documents the expected surface behaviour.
        cases.append(self._make_case(
            op_id=op_id, suffix="rate_limit_exceeded",
            description=(
                f"Verify {method} {path} returns 429 Too Many Requests when the client "
                "exceeds the allowed request rate. The response should include a "
                "Retry-After or X-RateLimit-Reset header."
            ),
            category=TestCategory.NEGATIVE,
            method=method,
            path=path,
            path_params=valid_path_params,
            query_params=valid_query_params,
            headers={**valid_headers, "X-Simulate-Rate-Limit": "true"},
            body=valid_body,
            expected_status=429,
            expected_behavior="Should return HTTP 429 with Retry-After header",
            tags=tags,
        ))

        # 11. Large payload → 413 (OWASP / Sauce Labs security standard)
        if method in ("POST", "PUT", "PATCH"):
            cases.append(self._make_case(
                op_id=op_id, suffix="large_payload_413",
                description=(
                    f"Verify {method} {path} returns 413 Payload Too Large when the request "
                    "body exceeds the server's maximum allowed size."
                ),
                category=TestCategory.NEGATIVE,
                method=method,
                path=path,
                path_params=valid_path_params,
                query_params=valid_query_params,
                headers=valid_headers,
                body={"data": "A" * 10_000_000},
                expected_status=413,
                expected_behavior="Should return HTTP 413 Request Entity Too Large",
                tags=tags,
            ))

        # 12. Idempotency check for PUT/PATCH (Postman / REST best-practice standard)
        # Sending the same mutating request twice should produce the same result.
        if method in ("PUT", "PATCH"):
            cases.append(self._make_case(
                op_id=op_id, suffix="idempotency_duplicate_request",
                description=(
                    f"Verify {method} {path} is idempotent: sending the same request a second "
                    "time should return the same status as the first call. "
                    "This is a REST contract requirement, not a optional feature."
                ),
                category=TestCategory.POSITIVE,
                method=method,
                path=path,
                path_params=valid_path_params,
                query_params=valid_query_params,
                headers={**valid_headers, "Idempotency-Key": "test-idem-key-abc123"},
                body=valid_body,
                expected_status=success_code,
                expected_behavior=(
                    f"Second call must return HTTP {success_code} — same as first call. "
                    "No side effects from duplicate submission."
                ),
                tags=tags,
            ))

        return cases

    # ------------------------------------------------------------------ #
    # Body Test Generation
    # ------------------------------------------------------------------ #

    def _generate_body_tests(
        self,
        op_id: str,
        method: str,
        path: str,
        valid_path_params: dict,
        valid_query_params: dict,
        valid_headers: dict,
        schema: dict,
        success_code: int,
        tags: list[str],
    ) -> list[TestCase]:
        cases: list[TestCase] = []
        properties = schema.get("properties", {})
        required_fields = schema.get("required", [])

        # Null body
        cases.append(self._make_case(
            op_id=op_id, suffix="body_null",
            description=f"Verify {method} {path} returns 400 for null request body",
            category=TestCategory.NEGATIVE,
            method=method, path=path,
            path_params=valid_path_params, query_params=valid_query_params,
            headers=valid_headers, body=None,
            expected_status=400,
            expected_behavior="Should return HTTP 400 Bad Request: missing body",
            tags=tags,
        ))

        # Empty object body
        cases.append(self._make_case(
            op_id=op_id, suffix="body_empty_object",
            description=f"Verify {method} {path} returns 400 for empty {{}} body",
            category=TestCategory.NEGATIVE,
            method=method, path=path,
            path_params=valid_path_params, query_params=valid_query_params,
            headers=valid_headers, body={},
            expected_status=400 if required_fields else success_code,
            expected_behavior="Should return HTTP 400 if required fields are missing",
            tags=tags,
        ))

        # Per-field tests
        for field_name, field_schema in properties.items():
            resolved_schema = self.resolver.resolve(field_schema)
            is_required = field_name in required_fields

            # Missing required field
            if is_required:
                body_without = {k: ValueGenerator.valid(self.resolver.resolve(v), k)
                                for k, v in properties.items() if k != field_name}
                cases.append(self._make_case(
                    op_id=op_id, suffix=f"body_missing_required_{field_name}",
                    description=f"Verify {method} {path} returns 400 when required field '{field_name}' is absent",
                    category=TestCategory.NEGATIVE,
                    method=method, path=path,
                    path_params=valid_path_params, query_params=valid_query_params,
                    headers=valid_headers, body=body_without,
                    expected_status=400,
                    expected_behavior=f"Should return HTTP 400: missing required field '{field_name}'",
                    tags=tags,
                ))

            # Wrong type
            for bad_val in ValueGenerator.invalid_type(resolved_schema):
                type_label = type(bad_val).__name__
                bad_body = {k: ValueGenerator.valid(self.resolver.resolve(v), k)
                            for k, v in properties.items()}
                bad_body[field_name] = bad_val
                cases.append(self._make_case(
                    op_id=op_id, suffix=f"body_field_wrong_type_{field_name}_{type_label}",
                    description=f"Verify {method} {path} rejects field '{field_name}' with type {type_label}",
                    category=TestCategory.DATA_TYPE,
                    method=method, path=path,
                    path_params=valid_path_params, query_params=valid_query_params,
                    headers=valid_headers, body=bad_body,
                    expected_status=422,
                    expected_behavior=f"Should return HTTP 422: invalid type for field '{field_name}'",
                    tags=tags,
                ))

            # Null field value
            null_body = {k: ValueGenerator.valid(self.resolver.resolve(v), k)
                         for k, v in properties.items()}
            null_body[field_name] = None
            cases.append(self._make_case(
                op_id=op_id, suffix=f"body_field_null_{field_name}",
                description=f"Verify {method} {path} handles null value for field '{field_name}'",
                category=TestCategory.NEGATIVE,
                method=method, path=path,
                path_params=valid_path_params, query_params=valid_query_params,
                headers=valid_headers, body=null_body,
                expected_status=400 if is_required else success_code,
                expected_behavior=f"Null '{field_name}': expect HTTP {400 if is_required else success_code}",
                tags=tags,
            ))

            # Enum validation
            if "enum" in resolved_schema:
                bad_enum_body = {k: ValueGenerator.valid(self.resolver.resolve(v), k)
                                 for k, v in properties.items()}
                bad_enum_body[field_name] = "INVALID_ENUM_VALUE_XYZ"
                cases.append(self._make_case(
                    op_id=op_id, suffix=f"body_field_invalid_enum_{field_name}",
                    description=f"Verify {method} {path} rejects invalid enum value for '{field_name}'",
                    category=TestCategory.NEGATIVE,
                    method=method, path=path,
                    path_params=valid_path_params, query_params=valid_query_params,
                    headers=valid_headers, body=bad_enum_body,
                    expected_status=422,
                    expected_behavior=f"Should return HTTP 422: '{field_name}' must be one of {resolved_schema['enum']}",
                    tags=tags,
                ))

            # Boundary values for field
            for b_label, b_val in ValueGenerator.boundary_values(resolved_schema):
                boundary_body = {k: ValueGenerator.valid(self.resolver.resolve(v), k)
                                 for k, v in properties.items()}
                boundary_body[field_name] = b_val
                exp_s = 400 if ("above" in b_label or "below" in b_label) else success_code
                cases.append(self._make_case(
                    op_id=op_id, suffix=f"body_boundary_{field_name}_{b_label}",
                    description=f"Boundary '{b_label}' for body field '{field_name}': value={repr(b_val)!r:.60}",
                    category=TestCategory.BOUNDARY,
                    method=method, path=path,
                    path_params=valid_path_params, query_params=valid_query_params,
                    headers=valid_headers, body=boundary_body,
                    expected_status=exp_s,
                    expected_behavior=f"Boundary '{b_label}': expect HTTP {exp_s}",
                    tags=tags,
                ))

        # Extra unknown field (additionalProperties)
        extra_body = {k: ValueGenerator.valid(self.resolver.resolve(v), k)
                      for k, v in properties.items()}
        extra_body["_unknown_field_xyz"] = "unexpected_value"
        cases.append(self._make_case(
            op_id=op_id, suffix="body_extra_unknown_field",
            description=f"Verify {method} {path} handles unexpected additional field in body",
            category=TestCategory.NEGATIVE,
            method=method, path=path,
            path_params=valid_path_params, query_params=valid_query_params,
            headers=valid_headers, body=extra_body,
            expected_status=400,
            expected_behavior="Should return HTTP 400 if additionalProperties are not allowed",
            tags=tags,
        ))

        # Deeply nested invalid
        cases.append(self._make_case(
            op_id=op_id, suffix="body_malformed_json_structure",
            description=f"Verify {method} {path} returns 400 for a non-object body",
            category=TestCategory.NEGATIVE,
            method=method, path=path,
            path_params=valid_path_params, query_params=valid_query_params,
            headers=valid_headers, body=["array", "instead", "of", "object"],
            expected_status=400,
            expected_behavior="Should return HTTP 400 for array body when object is expected",
            tags=tags,
        ))

        return cases

    # ------------------------------------------------------------------ #
    # Combinatorial Tests
    # ------------------------------------------------------------------ #

    def _generate_combinatorial(
        self,
        op_id: str,
        method: str,
        path: str,
        valid_path_params: dict,
        valid_query_params: dict,
        valid_headers: dict,
        valid_body: Any,
        optional_params: list[dict],
        success_code: int,
        tags: list[str],
    ) -> list[TestCase]:
        cases: list[TestCase] = []
        names = [p["name"] for p in optional_params]

        # Pairwise combinations (2-way)
        for r in range(2, min(len(names) + 1, 4)):
            for combo in itertools.combinations(names, r):
                combo_query = dict(valid_query_params)
                # Include only this combination of optional params
                for p in optional_params:
                    if p["name"] not in combo:
                        combo_query.pop(p["name"], None)
                label = "_".join(combo)
                cases.append(self._make_case(
                    op_id=op_id, suffix=f"combo_{label}",
                    description=f"Verify {method} {path} with optional params: {list(combo)}",
                    category=TestCategory.COMBINATORIAL,
                    method=method, path=path,
                    path_params=valid_path_params, query_params=combo_query,
                    headers=valid_headers, body=valid_body,
                    expected_status=success_code,
                    expected_behavior=f"Should return HTTP {success_code} with optional params {list(combo)} provided",
                    tags=tags,
                ))

        # No optional params at all
        base_query = {k: v for k, v in valid_query_params.items()
                      if k not in [p["name"] for p in optional_params]}
        cases.append(self._make_case(
            op_id=op_id, suffix="combo_no_optional_params",
            description=f"Verify {method} {path} works with no optional parameters",
            category=TestCategory.COMBINATORIAL,
            method=method, path=path,
            path_params=valid_path_params, query_params=base_query,
            headers=valid_headers, body=valid_body,
            expected_status=success_code,
            expected_behavior=f"Should return HTTP {success_code} with only required params",
            tags=tags,
        ))

        return cases

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _make_case(self, op_id: str, suffix: str, **kwargs) -> TestCase:
        self._counter += 1
        tc_id = f"{op_id}_{self._counter:04d}"
        
        def to_snake(s: str) -> str:
            s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', str(s))
            s = s.lower()
            words = [w for w in re.split(r'[^a-z0-9]+', s) if w]
            return "_".join(words)

        # Enforce strict snake_case naming convention: tc_{operationId}_{category}_{scenario}
        category = kwargs.get("category")
        if category and suffix:
            c_str = to_snake(category.value)
            s_str = to_snake(suffix)
            o_id = to_snake(op_id)
            kwargs["name"] = f"tc_{o_id}_{c_str}_{s_str}"
        elif "name" in kwargs:
            clean_name = to_snake(kwargs["name"])
            if not clean_name.startswith("tc_"):
                clean_name = f"tc_{clean_name}"
            kwargs["name"] = clean_name.replace("tc_tc_", "tc_")
            
        return TestCase(id=tc_id, **kwargs)

    def _collect_parameters(self, operation: dict) -> list[dict]:
        params = operation.get("parameters", [])
        return [self.resolver.resolve(p) if "$ref" in p else p for p in params]

    def _extract_request_body_schema(self, operation: dict) -> dict | None:
        body = operation.get("requestBody", {})
        if not body:
            return None
        content = body.get("content", {})
        json_content = content.get("application/json", {})
        schema = json_content.get("schema", {})
        return self.resolver.resolve(schema) if schema else None

    def _build_valid_params(self, parameters: list[dict], location: str) -> dict:
        result = {}
        for param in parameters:
            if param.get("in") == location:
                name = param.get("name", "param")
                schema = self.resolver.resolve(param.get("schema", {"type": "string"}))
                result[name] = ValueGenerator.valid(schema, name)
        return result

    def _primary_success_code(self, operation: dict) -> int:
        responses = operation.get("responses", {})
        for code in (200, 201, 202, 204):
            if str(code) in responses:
                return code
        # Pick first 2xx
        for code_str in responses:
            try:
                code = int(code_str)
                if 200 <= code < 300:
                    return code
            except ValueError:
                pass
        return 200

    def _extract_security_schemes(self, security_requirements: list[dict]) -> list[dict]:
        if not security_requirements:
            return []
        components = self.spec.get("components", {})
        scheme_defs = components.get("securitySchemes", self.spec.get("securityDefinitions", {}))
        schemes = []
        for req in security_requirements:
            for scheme_name in req:
                defn = scheme_defs.get(scheme_name, {})
                s_type = defn.get("type", "http")
                s_scheme = defn.get("scheme", "bearer")
                if s_type == "http" and s_scheme == "bearer":
                    schemes.append({"type": "bearer", "name": scheme_name})
                elif s_type == "http" and s_scheme == "basic":
                    schemes.append({"type": "basic", "name": scheme_name})
                elif s_type == "apiKey":
                    in_loc = defn.get("in", "header")
                    schemes.append({"type": f"apiKey_{in_loc}", "name": scheme_name, "paramName": defn.get("name", "X-API-Key")})
                elif s_type == "oauth2":
                    schemes.append({"type": "oauth2", "name": scheme_name})
                else:
                    schemes.append({"type": "bearer", "name": scheme_name})
        return schemes

    @staticmethod
    def _path_to_id(path: str, method: str) -> str:
        cleaned = re.sub(r"[{}]", "", path)
        cleaned = re.sub(r"[^a-zA-Z0-9]", " ", cleaned)
        parts = cleaned.split()
        if not parts:
            return method.lower()
        camel_path = "".join(p.capitalize() for p in parts)
        return f"{method.lower()}{camel_path}"

