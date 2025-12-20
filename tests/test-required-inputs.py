#!/usr/bin/env python3
"""Test required input schema validation."""
import subprocess
import os
import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

MOCK_PORT = 18830

passed = 0
failed = 0


class MockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        response = {
            "choices": [{
                "message": {"content": "OK"}
            }]
        }
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def log_message(self, format, *args):
        pass


def run_server(server):
    server.serve_forever()


def start_server(port):
    server = HTTPServer(('127.0.0.1', port), MockHandler)
    thread = threading.Thread(target=run_server, args=(server,))
    thread.daemon = True
    thread.start()
    time.sleep(0.1)
    return server


def test(name, func):
    global passed, failed
    try:
        func()
        print("✅ %s" % name)
        passed += 1
    except AssertionError as e:
        print("❌ %s" % name)
        print("   %s" % e)
        failed += 1


def clean_env():
    """Return a copy of environ with RUNPROMPT_* vars removed."""
    env = os.environ.copy()
    for key in list(env.keys()):
        if key.startswith('RUNPROMPT_'):
            del env[key]
    return env


def test_missing_required_field():
    """Test that missing required field shows error."""
    env = clean_env()
    env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % MOCK_PORT
    env['OPENAI_API_KEY'] = 'test-key'
    result = subprocess.run(
        ['./runprompt', 'tests/required-schema.prompt'],
        capture_output=True,
        text=True,
        env=env,
        input='{}'
    )
    assert result.returncode == 1, "Expected failure, got success"
    assert 'Missing required input field' in result.stderr, \
        "Expected error message, got: %s" % result.stderr
    assert 'name' in result.stderr, "Expected 'name' in error"


def test_missing_multiple_required_fields():
    """Test that multiple missing required fields are listed."""
    env = clean_env()
    env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % MOCK_PORT
    env['OPENAI_API_KEY'] = 'test-key'
    result = subprocess.run(
        ['./runprompt', 'tests/required-schema.prompt'],
        capture_output=True,
        text=True,
        env=env,
        input='{"age": 30}'
    )
    assert result.returncode == 1, "Expected failure, got success"
    assert 'name' in result.stderr, "Expected 'name' in error"


def test_optional_field_not_required():
    """Test that optional fields don't cause errors when missing."""
    server = start_server(MOCK_PORT + 1)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 1)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', 'tests/required-schema.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "Alice"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
    finally:
        server.shutdown()


def test_all_required_fields_provided():
    """Test that providing all required fields succeeds."""
    server = start_server(MOCK_PORT + 2)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 2)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', 'tests/required-schema.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "Alice", "age": 30}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
    finally:
        server.shutdown()


def test_empty_string_counts_as_missing():
    """Test that empty string for required field is treated as missing."""
    env = clean_env()
    env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % MOCK_PORT
    env['OPENAI_API_KEY'] = 'test-key'
    result = subprocess.run(
        ['./runprompt', 'tests/required-schema.prompt'],
        capture_output=True,
        text=True,
        env=env,
        input='{"name": ""}'
    )
    assert result.returncode == 1, "Expected failure, got success"
    assert 'name' in result.stderr, "Expected 'name' in error"


def test_schema_displayed_in_error():
    """Test that the expected schema is shown in error message."""
    env = clean_env()
    env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % MOCK_PORT
    env['OPENAI_API_KEY'] = 'test-key'
    result = subprocess.run(
        ['./runprompt', 'tests/required-schema.prompt'],
        capture_output=True,
        text=True,
        env=env,
        input='{}'
    )
    assert result.returncode == 1, "Expected failure"
    assert 'Expected input schema' in result.stderr, \
        "Expected schema display in error"
    assert '(required)' in result.stderr, "Expected (required) marker"
    assert '(optional)' in result.stderr, "Expected (optional) marker"


def test_no_schema_no_validation():
    """Test that prompts without input schema don't validate."""
    server = start_server(MOCK_PORT + 3)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 3)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{}'
        )
        # hello.prompt has no input schema, so should succeed
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
    finally:
        server.shutdown()


if __name__ == '__main__':
    test("missing required field", test_missing_required_field)
    test("missing multiple required fields", test_missing_multiple_required_fields)
    test("optional field not required", test_optional_field_not_required)
    test("all required fields provided", test_all_required_fields_provided)
    test("empty string counts as missing", test_empty_string_counts_as_missing)
    test("schema displayed in error", test_schema_displayed_in_error)
    test("no schema no validation", test_no_schema_no_validation)

    print("")
    print("Passed: %d, Failed: %d" % (passed, failed))
    if failed > 0:
        exit(1)
