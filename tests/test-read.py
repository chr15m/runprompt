#!/usr/bin/env python3
"""Test --read file attachment functionality."""
import subprocess
import os
import json
import tempfile
import shutil
import threading
import time
import base64
from http.server import HTTPServer, BaseHTTPRequestHandler

MOCK_PORT = 18840

# 1x1 red PNG image (68 bytes)
TEST_IMAGE_PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk'
    '+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
)

passed = 0
failed = 0


class MockHandler(BaseHTTPRequestHandler):
    received_requests = []

    def do_GET(self):
        """Serve test files for URL tests."""
        if self.path == '/test-image.png':
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Content-Length', len(TEST_IMAGE_PNG))
            self.end_headers()
            self.wfile.write(TEST_IMAGE_PNG)
        elif self.path == '/test-page.html':
            content = b'<html><body>Test page content</body></html>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(404)
            self.end_headers()

    def do_HEAD(self):
        """Handle HEAD requests for MIME type detection."""
        if self.path == '/test-image.png':
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Content-Length', len(TEST_IMAGE_PNG))
            self.end_headers()
        elif self.path == '/test-page.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

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


def test_files_frontmatter_single_file():
    """Test reading a single file via frontmatter 'files:'."""
    server = start_server(MOCK_PORT + 14)
    temp_dir = tempfile.mkdtemp()
    try:
        prompt_file = os.path.join(temp_dir, "frontmatter-files.prompt")
        with open(prompt_file, "w") as f:
            f.write("""---
model: openai/gpt-4o
files:
  - README.md
---
Say hello to {{name}}!
""")

        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 14)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', prompt_file],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert len(MockHandler.received_requests) == 1, "Expected 1 request"
        content = get_user_content(MockHandler.received_requests[0])
        content_str = json.dumps(content)
        assert 'README.md' in content_str, "Expected README.md in content"
        assert '# runprompt' in content_str, "Expected README content"
    finally:
        server.shutdown()
        shutil.rmtree(temp_dir)


def test_files_frontmatter_and_cli_combined():
    """Test that frontmatter 'files:' and CLI --read are combined."""
    server = start_server(MOCK_PORT + 15)
    temp_dir = tempfile.mkdtemp()
    try:
        prompt_file = os.path.join(temp_dir, "frontmatter-files-and-cli.prompt")
        with open(prompt_file, "w") as f:
            f.write("""---
model: openai/gpt-4o
files:
  - README.md
---
Say hello to {{name}}!
""")

        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 15)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', '--read', 'LICENSE', prompt_file],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert len(MockHandler.received_requests) == 1, "Expected 1 request"
        content = get_user_content(MockHandler.received_requests[0])
        content_str = json.dumps(content)
        assert 'README.md' in content_str, "Expected README.md in content"
        assert '# runprompt' in content_str, "Expected README content"
        assert 'LICENSE' in content_str, "Expected LICENSE in content"
        assert 'Permission is hereby granted' in content_str, \
            "Expected LICENSE file content"
    finally:
        server.shutdown()
        shutil.rmtree(temp_dir)


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


def test_read_url_image_openai():
    """Test that image URLs are downloaded and base64 encoded for OpenAI."""
    server = start_server(MOCK_PORT + 8)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 8)
        env['OPENAI_API_KEY'] = 'test-key'
        image_url = 'http://127.0.0.1:%d/test-image.png' % (MOCK_PORT + 8)
        result = subprocess.run(
            ['./runprompt', '--read', image_url, 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        # Find the POST request (not GET for image)
        post_reqs = [r for r in MockHandler.received_requests
                     if r.get('body') is not None]
        assert len(post_reqs) >= 1, "Expected at least 1 POST request"
        content = get_user_content(post_reqs[0])
        content_str = json.dumps(content)
        # Should have image_url block with base64 data URL
        assert 'image_url' in content_str, "Expected image_url in content"
        assert 'data:image/png;base64,' in content_str, \
            "Expected base64 data URL in content"
    finally:
        server.shutdown()


def test_read_url_no_glob():
    """Test that URLs are not glob-expanded."""
    server = start_server(MOCK_PORT + 9)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 9)
        env['OPENAI_API_KEY'] = 'test-key'
        # URL with glob-like characters - will fail to fetch but should warn
        # not try to glob expand
        result = subprocess.run(
            ['./runprompt', '--read', 'http://127.0.0.1:%d/path/*.png' %
             (MOCK_PORT + 9), 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        # Should show warning about fetch failure, not "No files match" glob error
        assert 'Cannot fetch' in result.stderr, \
            "Expected fetch error, not glob error"
        assert 'No files match' not in result.stderr, \
            "URL should not be glob-expanded"
    finally:
        server.shutdown()


def test_read_url_text_content():
    """Test that non-image URLs are downloaded and included as text."""
    server = start_server(MOCK_PORT + 10)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 10)
        env['OPENAI_API_KEY'] = 'test-key'
        html_url = 'http://127.0.0.1:%d/test-page.html' % (MOCK_PORT + 10)
        result = subprocess.run(
            ['./runprompt', '--read', html_url, 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        # Find the POST request
        post_reqs = [r for r in MockHandler.received_requests
                     if r.get('body') is not None]
        assert len(post_reqs) >= 1, "Expected at least 1 POST request"
        content = get_user_content(post_reqs[0])
        content_str = json.dumps(content)
        # Should have the HTML content as text
        assert 'Test page content' in content_str, \
            "Expected HTML content in message"
    finally:
        server.shutdown()


def test_read_multiple_urls():
    """Test reading multiple URLs."""
    server = start_server(MOCK_PORT + 11)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 11)
        env['OPENAI_API_KEY'] = 'test-key'
        image_url = 'http://127.0.0.1:%d/test-image.png' % (MOCK_PORT + 11)
        html_url = 'http://127.0.0.1:%d/test-page.html' % (MOCK_PORT + 11)
        result = subprocess.run(
            ['./runprompt',
             '--read', image_url,
             '--read', html_url,
             'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        # Find the POST request
        post_reqs = [r for r in MockHandler.received_requests
                     if r.get('body') is not None]
        assert len(post_reqs) >= 1, "Expected at least 1 POST request"
        content = get_user_content(post_reqs[0])
        content_str = json.dumps(content)
        assert 'image_url' in content_str, "Expected image in content"
        assert 'Test page content' in content_str, "Expected HTML in content"
    finally:
        server.shutdown()


def test_read_mixed_files_and_urls():
    """Test reading both local files and URLs."""
    server = start_server(MOCK_PORT + 12)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 12)
        env['OPENAI_API_KEY'] = 'test-key'
        image_url = 'http://127.0.0.1:%d/test-image.png' % (MOCK_PORT + 12)
        result = subprocess.run(
            ['./runprompt',
             '--read', 'README.md',
             '--read', image_url,
             'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        # Find the POST request
        post_reqs = [r for r in MockHandler.received_requests
                     if r.get('body') is not None]
        assert len(post_reqs) >= 1, "Expected at least 1 POST request"
        content = get_user_content(post_reqs[0])
        content_str = json.dumps(content)
        assert 'README.md' in content_str, "Expected local file in content"
        assert 'image_url' in content_str, "Expected image URL in content"
    finally:
        server.shutdown()


def test_read_url_deduplication():
    """Test that duplicate URLs are only included once."""
    server = start_server(MOCK_PORT + 13)
    try:
        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 13)
        env['OPENAI_API_KEY'] = 'test-key'
        image_url = 'http://127.0.0.1:%d/test-image.png' % (MOCK_PORT + 13)
        result = subprocess.run(
            ['./runprompt',
             '--read', image_url,
             '--read', image_url,
             'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        # Find the POST request
        post_reqs = [r for r in MockHandler.received_requests
                     if r.get('body') is not None]
        assert len(post_reqs) >= 1, "Expected at least 1 POST request"
        content = get_user_content(post_reqs[0])
        content_str = json.dumps(content)
        # Count occurrences of the URL in file headers
        count = content_str.count('## File: %s' % image_url)
        assert count == 1, "Expected URL only once, found %d times" % count
    finally:
        server.shutdown()


if __name__ == '__main__':
    test("read single file", test_read_single_file)
    test("files frontmatter single file", test_files_frontmatter_single_file)
    test("files frontmatter and CLI combined", test_files_frontmatter_and_cli_combined)
    test("read multiple files", test_read_multiple_files)
    test("read glob pattern", test_read_glob_pattern)
    test("read nonexistent file warning", test_read_nonexistent_file_warning)
    test("read binary file", test_read_binary_file)
    test("read with prompt content", test_read_with_prompt_content)
    test("read empty glob no matches", test_read_empty_glob_no_matches)
    test("read skips directories", test_read_skips_directories)
    test("read URL image openai", test_read_url_image_openai)
    test("read URL no glob", test_read_url_no_glob)
    test("read URL text content", test_read_url_text_content)
    test("read multiple URLs", test_read_multiple_urls)
    test("read mixed files and URLs", test_read_mixed_files_and_urls)
    test("read URL deduplication", test_read_url_deduplication)

    print("")
    print("Passed: %d, Failed: %d" % (passed, failed))
    if failed > 0:
        exit(1)
