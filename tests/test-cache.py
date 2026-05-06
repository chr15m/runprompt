#!/usr/bin/env python3
"""Test response caching functionality."""
import subprocess
import os
import json
import shutil
import tempfile
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

MOCK_PORT = 18780

passed = 0
failed = 0


class MockHandler(BaseHTTPRequestHandler):
    request_count = 0

    def do_POST(self):
        MockHandler.request_count += 1
        response = {
            "choices": [{
                "message": {
                    "content": "Response #%d" % MockHandler.request_count
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
    MockHandler.request_count = 0
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


def test_cache_hit():
    """Test that second request uses cache."""
    server = start_server(MOCK_PORT)
    cache_dir = tempfile.mkdtemp()
    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % MOCK_PORT
        env['OPENAI_API_KEY'] = 'test-key'
        env['RUNPROMPT_CACHE_DIR'] = cache_dir

        # First request - should hit API
        result1 = subprocess.run(
            ['./runprompt', '--model', 'openai/gpt-4o', '--cache', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result1.returncode == 0, "First request failed: %s" % result1.stderr
        assert "Response #1" in result1.stdout, "Expected Response #1"
        assert MockHandler.request_count == 1, "Expected 1 API request"

        # Second request - should use cache
        result2 = subprocess.run(
            ['./runprompt', '--model', 'openai/gpt-4o', '--cache', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result2.returncode == 0, "Second request failed: %s" % result2.stderr
        assert "Response #1" in result2.stdout, "Expected cached Response #1"
        assert MockHandler.request_count == 1, "Expected no additional API request"

        # Verify cache file exists
        cache_files = os.listdir(cache_dir)
        assert len(cache_files) == 1, "Expected 1 cache file, got %d" % len(cache_files)
        assert cache_files[0].endswith('.json'), "Cache file should be .json"
    finally:
        server.shutdown()
        shutil.rmtree(cache_dir)


def test_cache_miss_different_input():
    """Test that different input causes cache miss."""
    server = start_server(MOCK_PORT + 1)
    cache_dir = tempfile.mkdtemp()
    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 1)
        env['OPENAI_API_KEY'] = 'test-key'
        env['RUNPROMPT_CACHE_DIR'] = cache_dir

        # First request
        result1 = subprocess.run(
            ['./runprompt', '--model', 'openai/gpt-4o', '--cache', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "Alice"}'
        )
        assert result1.returncode == 0, "First request failed"
        assert MockHandler.request_count == 1, "Expected 1 API request"

        # Second request with different input - should miss cache
        result2 = subprocess.run(
            ['./runprompt', '--model', 'openai/gpt-4o', '--cache', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "Bob"}'
        )
        assert result2.returncode == 0, "Second request failed"
        assert MockHandler.request_count == 2, "Expected 2 API requests (cache miss)"
    finally:
        server.shutdown()
        shutil.rmtree(cache_dir)


def test_cache_disabled_by_default():
    """Test that caching is disabled without --cache flag."""
    server = start_server(MOCK_PORT + 2)
    cache_dir = tempfile.mkdtemp()
    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 2)
        env['OPENAI_API_KEY'] = 'test-key'
        env['RUNPROMPT_CACHE_DIR'] = cache_dir

        # First request without --cache
        result1 = subprocess.run(
            ['./runprompt', '--model', 'openai/gpt-4o', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result1.returncode == 0, "First request failed"

        # Second request without --cache
        result2 = subprocess.run(
            ['./runprompt', '--model', 'openai/gpt-4o', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result2.returncode == 0, "Second request failed"
        assert MockHandler.request_count == 2, "Expected 2 API requests (no caching)"

        # Verify no cache files created
        cache_files = os.listdir(cache_dir)
        assert len(cache_files) == 0, "Expected no cache files"
    finally:
        server.shutdown()
        shutil.rmtree(cache_dir)


def test_cache_env_var():
    """Test RUNPROMPT_CACHE=1 enables caching."""
    server = start_server(MOCK_PORT + 3)
    cache_dir = tempfile.mkdtemp()
    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 3)
        env['OPENAI_API_KEY'] = 'test-key'
        env['RUNPROMPT_CACHE_DIR'] = cache_dir
        env['RUNPROMPT_CACHE'] = '1'

        # First request - should hit API
        result1 = subprocess.run(
            ['./runprompt', '--model', 'openai/gpt-4o', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result1.returncode == 0, "First request failed"
        assert MockHandler.request_count == 1, "Expected 1 API request"

        # Second request - should use cache
        result2 = subprocess.run(
            ['./runprompt', '--model', 'openai/gpt-4o', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result2.returncode == 0, "Second request failed"
        assert MockHandler.request_count == 1, "Expected cache hit"
    finally:
        server.shutdown()
        shutil.rmtree(cache_dir)


def test_clear_cache():
    """Test --clear-cache removes cached responses."""
    cache_dir = tempfile.mkdtemp()
    try:
        # Create a fake cache file
        cache_file = os.path.join(cache_dir, "test123.json")
        with open(cache_file, "w") as f:
            f.write("{}")

        env = os.environ.copy()
        env['RUNPROMPT_CACHE_DIR'] = cache_dir

        result = subprocess.run(
            ['./runprompt', '--clear-cache'],
            capture_output=True,
            text=True,
            env=env
        )
        assert result.returncode == 0, "clear-cache failed"
        assert "Cleared 1" in result.stdout, "Expected clear message"

        # Verify cache is empty
        cache_files = os.listdir(cache_dir)
        assert len(cache_files) == 0, "Expected empty cache"
    finally:
        shutil.rmtree(cache_dir)


if __name__ == '__main__':
    test("cache hit", test_cache_hit)
    test("cache miss different input", test_cache_miss_different_input)
    test("cache disabled by default", test_cache_disabled_by_default)
    test("cache env var", test_cache_env_var)
    test("clear cache", test_clear_cache)

    print("")
    print("Passed: %d, Failed: %d" % (passed, failed))
    if failed > 0:
        exit(1)
