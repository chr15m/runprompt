#!/usr/bin/env python3
"""Test STDIN, ARGS, and INPUT variable handling."""
import subprocess
import os
import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

MOCK_PORT = 18800

passed = 0
failed = 0


class MockHandler(BaseHTTPRequestHandler):
    received_requests = []

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        MockHandler.received_requests.append({
            'path': self.path,
            'body': json.loads(body) if body else None
        })
        response = {
            "choices": [{
                "message": {
                    "content": "OK"
                }
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
    MockHandler.received_requests = []
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


def get_prompt_content(req):
    """Extract the prompt content from a request."""
    messages = req['body'].get('messages', [])
    if messages:
        return messages[0].get('content', '')
    return ''


def test_stdin_json_parsed():
    """Test that JSON from STDIN is parsed and variables are available."""
    server = start_server(MOCK_PORT)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % MOCK_PORT
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "Alice"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        prompt = get_prompt_content(MockHandler.received_requests[0])
        assert 'Alice' in prompt, "Expected 'Alice' in prompt, got: %s" % prompt
    finally:
        server.shutdown()


def test_args_json_parsed():
    """Test that JSON from ARGS is parsed and variables are available."""
    server = start_server(MOCK_PORT + 1)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 1)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', 'tests/hello.prompt', '{"name": "Bob"}'],
            capture_output=True,
            text=True,
            env=env
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        prompt = get_prompt_content(MockHandler.received_requests[0])
        assert 'Bob' in prompt, "Expected 'Bob' in prompt, got: %s" % prompt
    finally:
        server.shutdown()


def test_stdin_raw_string():
    """Test that non-JSON STDIN is available as raw string."""
    server = start_server(MOCK_PORT + 2)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 2)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', 'tests/stdin-test.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='This is raw text input'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        prompt = get_prompt_content(MockHandler.received_requests[0])
        assert 'This is raw text input' in prompt, \
            "Expected raw text in prompt, got: %s" % prompt
    finally:
        server.shutdown()


def test_args_raw_string():
    """Test that non-JSON ARGS is available as raw string."""
    server = start_server(MOCK_PORT + 3)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 3)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', 'tests/args-var-test.prompt', 'hello', 'world'],
            capture_output=True,
            text=True,
            env=env
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert len(MockHandler.received_requests) > 0, \
            "No requests received. stderr: %s" % result.stderr
        prompt = get_prompt_content(MockHandler.received_requests[0])
        assert 'hello world' in prompt, \
            "Expected 'hello world' in prompt, got: %s" % prompt
    finally:
        server.shutdown()


def test_stdin_variable_always_available():
    """Test that STDIN variable contains raw stdin regardless of JSON parsing."""
    server = start_server(MOCK_PORT + 4)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 4)
        env['OPENAI_API_KEY'] = 'test-key'
        # Create a prompt that uses STDIN directly
        result = subprocess.run(
            ['./runprompt', 'tests/stdin-var-test.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "Test"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        prompt = get_prompt_content(MockHandler.received_requests[0])
        # STDIN should contain the raw JSON string
        assert '{"name": "Test"}' in prompt, \
            "Expected raw JSON in STDIN, got: %s" % prompt
    finally:
        server.shutdown()


def test_args_variable_always_available():
    """Test that ARGS variable contains raw args regardless of JSON parsing."""
    server = start_server(MOCK_PORT + 5)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 5)
        env['OPENAI_API_KEY'] = 'test-key'
        # Create a prompt that uses ARGS directly
        result = subprocess.run(
            ['./runprompt', 'tests/args-var-test.prompt', '{"foo": "bar"}'],
            capture_output=True,
            text=True,
            env=env
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        prompt = get_prompt_content(MockHandler.received_requests[0])
        # ARGS should contain the raw JSON string
        assert '{"foo": "bar"}' in prompt, \
            "Expected raw JSON in ARGS, got: %s" % prompt
    finally:
        server.shutdown()


def test_input_prefers_stdin():
    """Test that INPUT contains STDIN when both STDIN and ARGS are provided."""
    server = start_server(MOCK_PORT + 6)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 6)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', 'tests/input-var-test.prompt', 'args-content'],
            capture_output=True,
            text=True,
            env=env,
            input='stdin-content'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        prompt = get_prompt_content(MockHandler.received_requests[0])
        # INPUT should contain STDIN, not ARGS
        assert 'stdin-content' in prompt, \
            "Expected INPUT to contain stdin-content, got: %s" % prompt
        assert 'args-content' not in prompt or prompt.count('args-content') == 0 or \
            'INPUT: stdin-content' in prompt, \
            "INPUT should prefer STDIN over ARGS"
    finally:
        server.shutdown()


def test_input_falls_back_to_args():
    """Test that INPUT contains ARGS when no STDIN is provided."""
    server = start_server(MOCK_PORT + 7)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 7)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', 'tests/input-var-test.prompt', 'args-only-content'],
            capture_output=True,
            text=True,
            env=env
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        prompt = get_prompt_content(MockHandler.received_requests[0])
        # INPUT should contain ARGS when no STDIN
        assert 'args-only-content' in prompt, \
            "Expected INPUT to contain args-only-content, got: %s" % prompt
    finally:
        server.shutdown()


def test_stdin_takes_precedence_for_json_parsing():
    """Test that STDIN JSON is used for variables when both STDIN and ARGS exist."""
    server = start_server(MOCK_PORT + 8)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 8)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', 'tests/hello.prompt', '{"name": "FromArgs"}'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "FromStdin"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        prompt = get_prompt_content(MockHandler.received_requests[0])
        # STDIN should take precedence for JSON parsing
        assert 'FromStdin' in prompt, \
            "Expected 'FromStdin' in prompt (STDIN precedence), got: %s" % prompt
        assert 'FromArgs' not in prompt, \
            "ARGS JSON should not override STDIN JSON"
    finally:
        server.shutdown()


if __name__ == '__main__':
    test("STDIN JSON parsed", test_stdin_json_parsed)
    test("ARGS JSON parsed", test_args_json_parsed)
    test("STDIN raw string", test_stdin_raw_string)
    test("ARGS raw string", test_args_raw_string)
    test("STDIN variable always available", test_stdin_variable_always_available)
    test("ARGS variable always available", test_args_variable_always_available)
    test("INPUT prefers STDIN", test_input_prefers_stdin)
    test("INPUT falls back to ARGS", test_input_falls_back_to_args)
    test("STDIN takes precedence for JSON parsing", test_stdin_takes_precedence_for_json_parsing)

    print("")
    print("Passed: %d, Failed: %d" % (passed, failed))
    if failed > 0:
        exit(1)
