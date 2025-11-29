#!/usr/bin/env python3
"""Test custom base URL override functionality."""
import subprocess
import sys
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


def test_base_url_env():
    """Test OPENAI_BASE_URL environment variable."""
    MockHandler.received_requests = []
    server = HTTPServer(('127.0.0.1', MOCK_PORT), MockHandler)
    thread = threading.Thread(target=run_server, args=(server,))
    thread.daemon = True
    thread.start()
    time.sleep(0.1)

    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % MOCK_PORT
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        print("stdout:", result.stdout)
        print("stderr:", result.stderr)
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert "Hello from mock server!" in result.stdout
        assert len(MockHandler.received_requests) == 1
        req = MockHandler.received_requests[0]
        assert req['path'] == '/chat/completions'
        assert 'Bearer test-key' in req['headers'].get('Authorization', '')
    finally:
        server.shutdown()

    print("PASS: test_base_url_env")


def test_base_url_cli():
    """Test --base-url CLI flag."""
    MockHandler.received_requests = []
    server = HTTPServer(('127.0.0.1', MOCK_PORT + 1), MockHandler)
    thread = threading.Thread(target=run_server, args=(server,))
    thread.daemon = True
    thread.start()
    time.sleep(0.1)

    try:
        env = os.environ.copy()
        env['OPENAI_API_KEY'] = 'cli-test-key'
        for key in ['OPENAI_BASE_URL', 'BASE_URL']:
            env.pop(key, None)
        result = subprocess.run(
            ['./runprompt', '--base-url', 'http://127.0.0.1:%d' % (MOCK_PORT + 1),
             'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        print("stdout:", result.stdout)
        print("stderr:", result.stderr)
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert "Hello from mock server!" in result.stdout
        assert len(MockHandler.received_requests) == 1
        req = MockHandler.received_requests[0]
        assert req['path'] == '/chat/completions'
        assert 'Bearer cli-test-key' in req['headers'].get('Authorization', '')
    finally:
        server.shutdown()

    print("PASS: test_base_url_cli")


def test_base_url_fallback():
    """Test BASE_URL fallback environment variable."""
    MockHandler.received_requests = []
    server = HTTPServer(('127.0.0.1', MOCK_PORT + 2), MockHandler)
    thread = threading.Thread(target=run_server, args=(server,))
    thread.daemon = True
    thread.start()
    time.sleep(0.1)

    try:
        env = os.environ.copy()
        env.pop('OPENAI_BASE_URL', None)
        env['BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 2)
        env['OPENAI_API_KEY'] = 'fallback-key'
        result = subprocess.run(
            ['./runprompt', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        print("stdout:", result.stdout)
        print("stderr:", result.stderr)
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert "Hello from mock server!" in result.stdout
    finally:
        server.shutdown()

    print("PASS: test_base_url_fallback")


def test_provider_ignored_with_base_url():
    """Test that provider prefix is ignored when base URL is set."""
    MockHandler.received_requests = []
    server = HTTPServer(('127.0.0.1', MOCK_PORT + 3), MockHandler)
    thread = threading.Thread(target=run_server, args=(server,))
    thread.daemon = True
    thread.start()
    time.sleep(0.1)

    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 3)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        print("stdout:", result.stdout)
        print("stderr:", result.stderr)
        assert result.returncode == 0
        req = MockHandler.received_requests[0]
        assert req['body']['model'] == 'claude-sonnet-4-20250514'
    finally:
        server.shutdown()

    print("PASS: test_provider_ignored_with_base_url")


if __name__ == '__main__':
    test_base_url_env()
    test_base_url_cli()
    test_base_url_fallback()
    test_provider_ignored_with_base_url()
    print("\nAll base URL tests passed!")
