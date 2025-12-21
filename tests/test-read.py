#!/usr/bin/env python3
"""Test --read file attachment functionality."""
import subprocess
import os
import json
import tempfile
import shutil
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

MOCK_PORT = 18840

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


def get_user_content(req):
    """Extract the user message content from a request."""
    messages = req['body'].get('messages', [])
    if messages:
        return messages[0].get('content', [])
    return []


def test_read_single_file():
    """Test reading a single file with --read."""
    server = start_server(MOCK_PORT)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % MOCK_PORT
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', '--read', 'README.md', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert len(MockHandler.received_requests) == 1, "Expected 1 request"
        content = get_user_content(MockHandler.received_requests[0])
        # Content should be a list with multiple parts
        assert isinstance(content, list), "Expected list content for multipart"
        # Find the file header
        content_str = json.dumps(content)
        assert 'README.md' in content_str, "Expected README.md in content"
        assert '# runprompt' in content_str, "Expected README content"
    finally:
        server.shutdown()


def test_read_multiple_files():
    """Test reading multiple files with multiple --read flags."""
    server = start_server(MOCK_PORT + 1)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 1)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', '--read', 'README.md', '--read', 'runprompt',
             'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        content = get_user_content(MockHandler.received_requests[0])
        content_str = json.dumps(content)
        assert 'README.md' in content_str, "Expected README.md in content"
        assert 'runprompt' in content_str, "Expected runprompt file in content"
    finally:
        server.shutdown()


def test_read_glob_pattern():
    """Test reading files with glob pattern."""
    server = start_server(MOCK_PORT + 2)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 2)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', '--read', 'tests/*.py', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        content = get_user_content(MockHandler.received_requests[0])
        content_str = json.dumps(content)
        # Check that known test files are included
        assert 'test-mustache.py' in content_str, \
            "Expected test-mustache.py in content"
        assert 'test-tools.py' in content_str, \
            "Expected test-tools.py in content"
        assert 'sample_tools.py' in content_str, \
            "Expected sample_tools.py in content"
    finally:
        server.shutdown()


def test_read_nonexistent_file_warning():
    """Test that nonexistent file shows warning but continues."""
    server = start_server(MOCK_PORT + 3)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 3)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', '--read', 'nonexistent_file_xyz.txt',
             'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert 'No files match' in result.stderr, \
            "Expected warning about no matching files"
    finally:
        server.shutdown()


def test_read_binary_file():
    """Test that binary files are detected and handled."""
    server = start_server(MOCK_PORT + 4)
    temp_dir = tempfile.mkdtemp()
    try:
        # Create a binary file with null bytes
        binary_file = os.path.join(temp_dir, 'test.bin')
        with open(binary_file, 'wb') as f:
            f.write(b'\x00\x01\x02\x03binary content\x00\xff')

        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 4)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', '-v', '--read', binary_file, 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        # Verbose output should indicate binary
        assert 'binary' in result.stderr.lower(), \
            "Expected binary detection in verbose output"
    finally:
        server.shutdown()
        shutil.rmtree(temp_dir)


def test_read_with_prompt_content():
    """Test that read files are combined with prompt content."""
    server = start_server(MOCK_PORT + 5)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 5)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', '--read', 'README.md', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "TestUser"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        content = get_user_content(MockHandler.received_requests[0])
        content_str = json.dumps(content)
        # Should have both file content and rendered prompt
        assert 'README.md' in content_str, "Expected file reference"
        assert 'Say hello to TestUser' in content_str, \
            "Expected rendered prompt with variable"
    finally:
        server.shutdown()


def test_read_empty_glob_no_matches():
    """Test glob pattern that matches nothing shows warning."""
    server = start_server(MOCK_PORT + 6)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 6)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', '--read', 'tests/*.nonexistent',
             'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert 'No files match' in result.stderr, \
            "Expected warning about no matching files"
    finally:
        server.shutdown()


def test_read_skips_directories():
    """Test that directories in glob results are skipped."""
    server = start_server(MOCK_PORT + 7)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 7)
        env['OPENAI_API_KEY'] = 'test-key'
        # Use a pattern that might match directories
        result = subprocess.run(
            ['./runprompt', '--read', 'tests/*', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        # Should succeed without errors about directories
    finally:
        server.shutdown()


if __name__ == '__main__':
    test("read single file", test_read_single_file)
    test("read multiple files", test_read_multiple_files)
    test("read glob pattern", test_read_glob_pattern)
    test("read nonexistent file warning", test_read_nonexistent_file_warning)
    test("read binary file", test_read_binary_file)
    test("read with prompt content", test_read_with_prompt_content)
    test("read empty glob no matches", test_read_empty_glob_no_matches)
    test("read skips directories", test_read_skips_directories)

    print("")
    print("Passed: %d, Failed: %d" % (passed, failed))
    if failed > 0:
        exit(1)
