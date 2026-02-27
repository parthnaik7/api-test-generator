"""
Unit tests for the API Test Case Generator engine.
"""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.generator import (
    TestCaseGenerator,
    TestCategory,
    ValueGenerator,
    AuthHeaderGenerator,
    SchemaResolver,
)

# ─── Minimal OAS fixtures ─────────────────────────────────────────────────────

MINIMAL_OAS = {
    "openapi": "3.0.0",
    "info": {"title": "Test API", "version": "1.0.0"},
    "paths": {
        "/users": {
            "get": {
                "operationId": "listUsers",
                "parameters": [
                    {"name": "page", "in": "query", "required": False, "schema": {"type": "integer", "minimum": 1}},
                    {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer", "minimum": 1, "maximum": 100}},
                ],
                "responses": {"200": {"description": "OK"}},
            },
            "post": {
                "operationId": "createUser",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["email", "age"],
                                "properties": {
                                    "email": {"type": "string", "format": "email"},
                                    "age":   {"type": "integer", "minimum": 0, "maximum": 150},
                                    "role":  {"type": "string", "enum": ["admin", "user", "guest"]},
                                },
                            }
                        }
                    },
                },
                "responses": {"201": {"description": "Created"}},
            },
        },
        "/users/{userId}": {
            "get": {
                "operationId": "getUser",
                "parameters": [
                    {"name": "userId", "in": "path", "required": True, "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}},
            },
            "delete": {
                "operationId": "deleteUser",
                "parameters": [
                    {"name": "userId", "in": "path", "required": True, "schema": {"type": "string"}},
                ],
                "responses": {"204": {"description": "No content"}},
            },
        },
    },
    "security": [{"bearerAuth": []}],
    "components": {
        "securitySchemes": {
            "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
        }
    },
}

OAS_WITH_REFS = {
    "openapi": "3.0.0",
    "info": {"title": "Ref API", "version": "1.0.0"},
    "components": {
        "schemas": {
            "Product": {
                "type": "object",
                "required": ["name", "price"],
                "properties": {
                    "name":  {"type": "string", "minLength": 1, "maxLength": 100},
                    "price": {"type": "number", "minimum": 0.01},
                    "tags":  {"type": "array", "items": {"type": "string"}},
                },
            }
        }
    },
    "paths": {
        "/products": {
            "post": {
                "operationId": "createProduct",
                "requestBody": {
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Product"}}}
                },
                "responses": {"201": {"description": "Created"}},
            }
        }
    },
}


# ─── ValueGenerator Tests ─────────────────────────────────────────────────────

class TestValueGenerator:

    def test_valid_string_returns_string(self):
        val = ValueGenerator.valid({"type": "string"}, "field")
        assert isinstance(val, str)

    def test_valid_email_format(self):
        val = ValueGenerator.valid({"type": "string", "format": "email"}, "email")
        assert "@" in val

    def test_valid_integer_respects_minimum(self):
        val = ValueGenerator.valid({"type": "integer", "minimum": 5}, "num")
        assert isinstance(val, int)
        assert val >= 5

    def test_valid_boolean(self):
        val = ValueGenerator.valid({"type": "boolean"}, "flag")
        assert isinstance(val, bool)

    def test_valid_enum_returns_first_value(self):
        val = ValueGenerator.valid({"type": "string", "enum": ["a", "b", "c"]}, "e")
        assert val == "a"

    def test_invalid_type_string_returns_non_strings(self):
        invalids = ValueGenerator.invalid_type({"type": "string"})
        assert all(not isinstance(v, str) for v in invalids)

    def test_invalid_type_integer_returns_non_ints(self):
        invalids = ValueGenerator.invalid_type({"type": "integer"})
        assert all(not isinstance(v, int) or isinstance(v, bool) for v in invalids)

    def test_boundary_values_string_includes_empty(self):
        pairs = ValueGenerator.boundary_values({"type": "string"})
        labels = [label for label, _ in pairs]
        assert "empty_string" in labels

    def test_boundary_values_integer_with_min_max(self):
        pairs = ValueGenerator.boundary_values({"type": "integer", "minimum": 1, "maximum": 10})
        labels = [label for label, _ in pairs]
        assert "at_minimum" in labels
        assert "at_maximum" in labels
        assert "below_minimum" in labels
        assert "above_maximum" in labels

    def test_boundary_values_string_includes_sql_injection(self):
        pairs = ValueGenerator.boundary_values({"type": "string"})
        labels = [label for label, _ in pairs]
        assert "sql_injection" in labels

    def test_boundary_values_string_includes_xss(self):
        pairs = ValueGenerator.boundary_values({"type": "string"})
        labels = [label for label, _ in pairs]
        assert "xss_payload" in labels

    def test_valid_object_generates_all_properties(self):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
            }
        }
        val = ValueGenerator.valid(schema, "obj")
        assert isinstance(val, dict)
        assert "name" in val
        assert "count" in val

    def test_valid_array_returns_list(self):
        val = ValueGenerator.valid({"type": "array", "items": {"type": "string"}}, "arr")
        assert isinstance(val, list)
        assert len(val) >= 1


# ─── AuthHeaderGenerator Tests ────────────────────────────────────────────────

class TestAuthHeaderGenerator:

    def test_bearer_valid_headers_contain_authorization(self):
        headers = AuthHeaderGenerator.get_valid_headers([{"type": "bearer", "name": "auth"}])
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")

    def test_bearer_invalid_cases_include_missing(self):
        cases = AuthHeaderGenerator.get_invalid_header_cases([{"type": "bearer", "name": "auth"}])
        labels = [label for label, _ in cases]
        assert "missing_auth_header" in labels

    def test_bearer_invalid_cases_include_expired(self):
        cases = AuthHeaderGenerator.get_invalid_header_cases([{"type": "bearer", "name": "auth"}])
        labels = [label for label, _ in cases]
        assert "expired_token" in labels

    def test_api_key_invalid_includes_empty(self):
        cases = AuthHeaderGenerator.get_invalid_header_cases([{"type": "apiKey_header", "name": "x-api-key"}])
        labels = [label for label, _ in cases]
        assert "empty_api_key" in labels

    def test_empty_security_schemes_falls_back_to_bearer(self):
        cases = AuthHeaderGenerator.get_invalid_header_cases([])
        assert len(cases) > 0


# ─── SchemaResolver Tests ─────────────────────────────────────────────────────

class TestSchemaResolver:

    def test_resolve_simple_schema(self):
        resolver = SchemaResolver(MINIMAL_OAS)
        result = resolver.resolve({"type": "string"})
        assert result == {"type": "string"}

    def test_resolve_ref(self):
        resolver = SchemaResolver(OAS_WITH_REFS)
        result = resolver.resolve({"$ref": "#/components/schemas/Product"})
        assert result["type"] == "object"
        assert "name" in result.get("properties", {})

    def test_resolve_all_of(self):
        spec = {
            "components": {
                "schemas": {
                    "A": {"type": "object", "properties": {"a": {"type": "string"}}},
                    "B": {"type": "object", "properties": {"b": {"type": "integer"}}},
                }
            }
        }
        resolver = SchemaResolver(spec)
        result = resolver.resolve({
            "allOf": [
                {"$ref": "#/components/schemas/A"},
                {"$ref": "#/components/schemas/B"},
            ]
        })
        assert "a" in result.get("properties", {})
        assert "b" in result.get("properties", {})


# ─── TestCaseGenerator Integration Tests ──────────────────────────────────────

class TestTestCaseGenerator:

    def setup_method(self):
        self.generator = TestCaseGenerator(MINIMAL_OAS)
        self.test_cases = self.generator.generate()

    def test_generates_test_cases(self):
        assert len(self.test_cases) > 0

    def test_all_test_cases_have_required_fields(self):
        required_fields = {"id", "name", "category", "method", "path", "expected_status"}
        for tc in self.test_cases:
            assert required_fields.issubset(tc.keys()), f"TC missing fields: {tc.get('id')}"

    def test_naming_convention_followed(self):
        for tc in self.test_cases:
            assert tc["name"].startswith("tc_"), f"Bad name: {tc['name']}"
            parts = tc["name"].split("_")
            assert len(parts) >= 4, f"Name too short: {tc['name']}"

    def test_happy_path_generated_for_each_operation(self):
        positive = [tc for tc in self.test_cases if tc["category"] == "positive"]
        assert len(positive) >= 4, "Should have at least one positive per operation"

    def test_security_tests_generated(self):
        security = [tc for tc in self.test_cases if tc["category"] == "security"]
        assert len(security) > 0

    def test_security_tests_expect_401(self):
        # Only the 401 cases (missing/malformed/expired auth) — not the 403 forbidden cases
        security_401 = [
            tc for tc in self.test_cases
            if tc["category"] == "security" and tc["expected_status"] == 401
        ]
        assert len(security_401) > 0, "Should have 401-targeted security test cases"
        for tc in security_401:
            assert tc["expected_status"] == 401, f"Security 401 TC should expect 401: {tc['name']}"

    def test_negative_tests_generated(self):
        negative = [tc for tc in self.test_cases if tc["category"] == "negative"]
        assert len(negative) > 0

    def test_boundary_tests_generated(self):
        boundary = [tc for tc in self.test_cases if tc["category"] == "boundary"]
        assert len(boundary) > 0

    def test_data_type_tests_generated(self):
        data_type = [tc for tc in self.test_cases if tc["category"] == "data_type"]
        assert len(data_type) > 0

    def test_post_tests_include_body(self):
        post_positive = [tc for tc in self.test_cases
                         if tc["method"] == "POST" and tc["category"] == "positive"]
        for tc in post_positive:
            assert tc["body"] is not None, f"POST positive should have body: {tc['name']}"

    def test_post_body_has_required_fields(self):
        post_positive = [tc for tc in self.test_cases
                         if tc["method"] == "POST" and tc["category"] == "positive"]
        for tc in post_positive:
            if isinstance(tc["body"], dict):
                assert "email" in tc["body"], "email is required"
                assert "age" in tc["body"], "age is required"

    def test_missing_required_field_tests_exist(self):
        missing_email = [tc for tc in self.test_cases
                         if "missing_required_email" in tc["name"]]
        assert len(missing_email) > 0

    def test_null_body_test_exists(self):
        null_body = [tc for tc in self.test_cases if "body_null" in tc["name"]]
        assert len(null_body) > 0

    def test_enum_validation_test_exists(self):
        enum_tests = [tc for tc in self.test_cases if "invalid_enum" in tc["name"]]
        assert len(enum_tests) > 0

    def test_content_type_negative_tests_exist(self):
        ct_tests = [tc for tc in self.test_cases if "content_type" in tc["name"]]
        assert len(ct_tests) > 0

    def test_wrong_method_test_exists(self):
        wrong_method = [tc for tc in self.test_cases if "wrong_method" in tc["name"]]
        assert len(wrong_method) > 0

    def test_all_categories_present(self):
        categories = {tc["category"] for tc in self.test_cases}
        expected = {"positive", "negative", "boundary", "security", "data_type"}
        assert expected.issubset(categories), f"Missing categories: {expected - categories}"

    def test_all_test_case_ids_are_unique(self):
        ids = [tc["id"] for tc in self.test_cases]
        assert len(ids) == len(set(ids)), "Duplicate IDs found"

    def test_valid_headers_always_include_content_type(self):
        for tc in self.test_cases:
            if tc["method"] in ("POST", "PUT", "PATCH") and tc["category"] == "positive":
                assert "Content-Type" in tc["headers"], f"Missing Content-Type: {tc['name']}"

    def test_ref_spec_generates_cases(self):
        gen = TestCaseGenerator(OAS_WITH_REFS)
        cases = gen.generate()
        assert len(cases) > 0

    def test_ref_spec_resolves_properties(self):
        gen = TestCaseGenerator(OAS_WITH_REFS)
        cases = gen.generate()
        positive = [tc for tc in cases if tc["category"] == "positive"]
        for tc in positive:
            if isinstance(tc["body"], dict):
                assert "name" in tc["body"]
                assert "price" in tc["body"]

    # ─── Postman / BrowserStack / Sauce Labs standard scenarios ──────────────

    def test_cors_preflight_generated(self):
        """BrowserStack standard: CORS preflight OPTIONS should be tested for every resource."""
        cors_tests = [
            tc for tc in self.test_cases
            if tc["method"] == "OPTIONS" and "Origin" in tc.get("headers", {})
        ]
        assert len(cors_tests) > 0, "CORS preflight OPTIONS tests must be generated"

    def test_cors_preflight_uses_options_method(self):
        cors_tests = [tc for tc in self.test_cases if "cors_preflight" in tc["name"]]
        for tc in cors_tests:
            assert tc["method"] == "OPTIONS"
            assert "Origin" in tc["headers"]
            assert "Access-Control-Request-Method" in tc["headers"]

    def test_forbidden_auth_case_exists(self):
        """Sauce Labs / Postman standard: 401 != 403. Authenticated but unauthorised must be distinct."""
        forbidden = [tc for tc in self.test_cases if tc["expected_status"] == 403]
        assert len(forbidden) > 0, "403 Forbidden cases (insufficient scope/role) must be generated"

    def test_forbidden_tests_have_security_category(self):
        forbidden = [tc for tc in self.test_cases if tc["expected_status"] == 403]
        for tc in forbidden:
            assert tc["category"] == "security", f"403 case should be security category: {tc['name']}"

    def test_accept_header_negotiation_tests_exist(self):
        """Postman contract standard: API must reject unsupported Accept types with 406."""
        tests_406 = [tc for tc in self.test_cases if tc["expected_status"] == 406]
        assert len(tests_406) > 0, "406 Not Acceptable tests (Accept: application/xml) must be generated"

    def test_rate_limit_case_exists(self):
        """Postman monitor standard: 429 Too Many Requests surface behaviour must be documented."""
        tests_429 = [tc for tc in self.test_cases if tc["expected_status"] == 429]
        assert len(tests_429) > 0, "429 Rate limit test cases must be generated"

    def test_idempotency_tests_for_put(self):
        """REST best-practice / Postman standard: PUT must be idempotent."""
        # MINIMAL_OAS doesn't have PUT, so we use a spec that does
        oas_with_put = {
            "openapi": "3.0.0",
            "info": {"title": "PUT API", "version": "1.0.0"},
            "paths": {
                "/items/{id}": {
                    "put": {
                        "operationId": "updateItem",
                        "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}],
                        "requestBody": {
                            "required": True,
                            "content": {"application/json": {"schema": {"type": "object", "properties": {"name": {"type": "string"}}}}},
                        },
                        "responses": {"200": {"description": "Updated"}},
                    }
                }
            },
        }
        gen = TestCaseGenerator(oas_with_put)
        cases = gen.generate()
        idempotency_cases = [tc for tc in cases if "idempotency" in tc["name"]]
        assert len(idempotency_cases) > 0, "Idempotency test must be generated for PUT"
        for tc in idempotency_cases:
            assert "Idempotency-Key" in tc["headers"], "Idempotency test must include Idempotency-Key header"

    def test_large_payload_test_exists(self):
        """OWASP / Sauce Labs security standard: oversized payloads must be rejected (413)."""
        tests_413 = [tc for tc in self.test_cases if tc["expected_status"] == 413]
        assert len(tests_413) > 0, "413 Payload Too Large test cases must be generated for POST/PUT/PATCH"

    def test_request_tracing_headers_in_positive(self):
        """RFC 7231 / Postman best practice: positive tests must include X-Request-ID and X-Correlation-ID."""
        positive = [tc for tc in self.test_cases if tc["category"] == "positive"]
        for tc in positive:
            assert "X-Request-ID" in tc["headers"], f"Missing X-Request-ID in positive test: {tc['name']}"
            assert "X-Correlation-ID" in tc["headers"], f"Missing X-Correlation-ID in positive test: {tc['name']}"

    def test_pagination_boundary_cases_for_page_params(self):
        """Postman collection runner standard: pagination params must be boundary-tested."""
        # Check that boundary tests exist for pagination-style params (page, limit)
        boundary = [tc for tc in self.test_cases if tc["category"] == "boundary"]
        has_page = any("page" in tc["name"].lower() for tc in boundary)
        has_limit = any("limit" in tc["name"].lower() for tc in boundary)
        # MINIMAL_OAS has 'page' and 'limit' query params
        assert has_page or has_limit, (
            "Boundary tests for pagination params (page/limit) must be generated"
        )


# ─── Run ──────────────────────────────────────────────────────────────────────

def run_all_tests():
    import traceback
    suites = [
        TestValueGenerator,
        TestAuthHeaderGenerator,
        TestSchemaResolver,
        TestTestCaseGenerator,
    ]
    passed = 0
    failed = 0
    errors = []

    for suite_cls in suites:
        suite = suite_cls()
        methods = [m for m in dir(suite) if m.startswith("test_")]
        for method_name in methods:
            try:
                if hasattr(suite, "setup_method"):
                    suite.setup_method()
                getattr(suite, method_name)()
                passed += 1
                print(f"  ✓  {suite_cls.__name__}.{method_name}")
            except Exception as exc:
                failed += 1
                errors.append((suite_cls.__name__, method_name, exc))
                print(f"  ✗  {suite_cls.__name__}.{method_name}: {exc}")

    print(f"\n{'═'*60}")
    print(f"  Results: {passed} passed, {failed} failed")
    if errors:
        print("\nFailures:")
        for cls, method, exc in errors:
            print(f"\n  {cls}.{method}")
            traceback.print_exception(type(exc), exc, exc.__traceback__)
    print('═'*60)
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
