#!/usr/bin/env python3
"""Test custom base URL override functionality."""
import subprocess
import os
import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

MOCK_PORT = 18765
MOCK_RESPONSE = {
    "choices": [{
        "message": {
            "content": "Hello from mock server!"
        }
    }]
}

passed = 0
failed = 0


class MockHandler(BaseHTTPRequestHandler):
    received_requests = []

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        MockHandler.received_requests.append({
            'path': self.path,
            'headers': dict(self.headers),
            'body': json.loads(body) if body else None
        })
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(MOCK_RESPONSE).encode('utf-8'))

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


def test_base_url_env():
    """Test OPENAI_BASE_URL environment variable."""
    server = start_server(MOCK_PORT)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % MOCK_PORT
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', '--model', 'openai/gpt-4o', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert "Hello from mock server!" in result.stdout, "Unexpected output"
        assert len(MockHandler.received_requests) == 1, "Expected 1 request"
        req = MockHandler.received_requests[0]
        assert req['path'] == '/chat/completions', "Wrong path"
        assert 'Bearer test-key' in req['headers'].get('Authorization', ''), \
            "Missing auth header"
    finally:
        server.shutdown()


def test_base_url_cli():
    """Test --base-url CLI flag."""
    server = start_server(MOCK_PORT + 1)
    try:
        env = clean_env()
        env['OPENAI_API_KEY'] = 'cli-test-key'
        for key in ['OPENAI_BASE_URL', 'BASE_URL']:
            env.pop(key, None)
        result = subprocess.run(
            ['./runprompt', '--model', 'openai/gpt-4o', '--base-url', 'http://127.0.0.1:%d' % (MOCK_PORT + 1),
             'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert "Hello from mock server!" in result.stdout, "Unexpected output"
        assert len(MockHandler.received_requests) == 1, "Expected 1 request"
        req = MockHandler.received_requests[0]
        assert req['path'] == '/chat/completions', "Wrong path"
        assert 'Bearer cli-test-key' in req['headers'].get('Authorization', ''), \
            "Missing auth header"
    finally:
        server.shutdown()


def test_base_url_fallback():
    """Test BASE_URL fallback environment variable."""
    server = start_server(MOCK_PORT + 2)
    try:
        env = clean_env()
        env.pop('OPENAI_BASE_URL', None)
        env['BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 2)
        env['OPENAI_API_KEY'] = 'fallback-key'
        result = subprocess.run(
            ['./runprompt', '--model', 'openai/gpt-4o', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert "Hello from mock server!" in result.stdout, "Unexpected output"
    finally:
        server.shutdown()


def test_provider_ignored_with_base_url():
    """Test that provider prefix is ignored when base URL is set."""
    server = start_server(MOCK_PORT + 3)
    try:
        env = clean_env()
        env['BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 3)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        req = MockHandler.received_requests[0]
        print("DEBUG: model in request body: %s" % req['body'].get('model'))
        print("DEBUG: full request body: %s" % json.dumps(req['body'], indent=2))
        assert req['body']['model'] == 'claude-sonnet-4-20250514', \
            "Provider prefix not stripped from model, got: %s" % req['body'].get('model')
    finally:
        server.shutdown()


if __name__ == '__main__':
    test("base-url env var", test_base_url_env)
    test("base-url cli flag", test_base_url_cli)
    test("base-url fallback", test_base_url_fallback)
    test("provider ignored with base-url", test_provider_ignored_with_base_url)

    print("")
    print("Passed: %d, Failed: %d" % (passed, failed))
    if failed > 0:
        exit(1)
