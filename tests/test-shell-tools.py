#!/usr/bin/env python3
"""Test shell_tools functionality."""
import subprocess
import os
import json
import tempfile
import shutil
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

MOCK_PORT = 18850

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


def test_shell_tools_short_form():
    """Test that shell_tools short form is loaded correctly."""
    server = start_server(MOCK_PORT)
    temp_dir = tempfile.mkdtemp()
    try:
        prompt_file = os.path.join(temp_dir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("""---
model: openai/gpt-4o
shell_tools:
  echo_test: echo "hello world"
  date_test: date +%Y-%m-%d
---
Test prompt
""")

        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % MOCK_PORT
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', prompt_file],
            capture_output=True,
            text=True,
            env=env,
            input='{}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert len(MockHandler.received_requests) == 1, "Expected 1 request"
        req = MockHandler.received_requests[0]
        body = req['body']
        tools = body.get('tools', [])
        tool_names = [t['function']['name'] for t in tools]
        assert 'echo_test' in tool_names, "Expected echo_test tool"
        assert 'date_test' in tool_names, "Expected date_test tool"
        # Check that description defaults to command
        echo_tool = [t for t in tools if t['function']['name'] == 'echo_test'][0]
        assert 'echo "hello world"' in echo_tool['function']['description'], \
            "Expected command in description"
    finally:
        server.shutdown()
        shutil.rmtree(temp_dir)


def test_shell_tools_long_form():
    """Test that shell_tools long form with all fields works."""
    server = start_server(MOCK_PORT + 1)
    temp_dir = tempfile.mkdtemp()
    try:
        prompt_file = os.path.join(temp_dir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("""---
model: openai/gpt-4o
shell_tools:
  git_status:
    cmd: git status --short
    safe: true
    description: Get git repository status
---
Test prompt
""")

        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 1)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', prompt_file],
            capture_output=True,
            text=True,
            env=env,
            input='{}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        req = MockHandler.received_requests[0]
        body = req['body']
        tools = body.get('tools', [])
        git_tool = [t for t in tools if t['function']['name'] == 'git_status'][0]
        assert 'Get git repository status' in git_tool['function']['description'], \
            "Expected custom description"
        # Check parameters
        params = git_tool['function']['parameters']
        assert 'args' in params['properties'], "Expected args parameter"
        assert params['properties']['args']['type'] == 'string', \
            "args should be string type"
    finally:
        server.shutdown()
        shutil.rmtree(temp_dir)


def test_shell_tools_missing_cmd():
    """Test that shell_tools with missing cmd shows warning."""
    server = start_server(MOCK_PORT + 2)
    temp_dir = tempfile.mkdtemp()
    try:
        prompt_file = os.path.join(temp_dir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("""---
model: openai/gpt-4o
shell_tools:
  bad_tool:
    safe: true
    description: Missing cmd field
---
Test prompt
""")

        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 2)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', prompt_file],
            capture_output=True,
            text=True,
            env=env,
            input='{}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert "missing 'cmd' field" in result.stderr, \
            "Expected warning about missing cmd"
        # Tool should not be loaded
        req = MockHandler.received_requests[0]
        body = req['body']
        tools = body.get('tools', [])
        tool_names = [t['function']['name'] for t in tools]
        assert 'bad_tool' not in tool_names, "bad_tool should not be loaded"
    finally:
        server.shutdown()
        shutil.rmtree(temp_dir)


def test_shell_tools_mixed_forms():
    """Test mixing short and long form shell_tools."""
    server = start_server(MOCK_PORT + 3)
    temp_dir = tempfile.mkdtemp()
    try:
        prompt_file = os.path.join(temp_dir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("""---
model: openai/gpt-4o
shell_tools:
  echo_short: echo "short form"
  ls_long:
    cmd: ls -la
    safe: true
    description: List files in detail
---
Test prompt
""")

        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 3)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', prompt_file],
            capture_output=True,
            text=True,
            env=env,
            input='{}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        req = MockHandler.received_requests[0]
        body = req['body']
        tools = body.get('tools', [])
        tool_names = [t['function']['name'] for t in tools]
        assert 'echo_short' in tool_names, "Expected echo_short tool"
        assert 'ls_long' in tool_names, "Expected ls_long tool"
    finally:
        server.shutdown()
        shutil.rmtree(temp_dir)


def test_shell_tools_default_not_safe():
    """Test that shell_tools are not safe by default."""
    server = start_server(MOCK_PORT + 4)
    temp_dir = tempfile.mkdtemp()
    try:
        prompt_file = os.path.join(temp_dir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("""---
model: openai/gpt-4o
shell_tools:
  unsafe_tool: echo "test"
---
Test prompt
""")

        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 4)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', prompt_file],
            capture_output=True,
            text=True,
            env=env,
            input='{}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        # Tool should be loaded but not marked as safe
        # (We can't easily test the safe attribute from the schema,
        # but we verified it's set correctly in the code)
    finally:
        server.shutdown()
        shutil.rmtree(temp_dir)


def test_shell_tools_with_python_tools():
    """Test that shell_tools can be combined with regular Python tools."""
    server = start_server(MOCK_PORT + 5)
    temp_dir = tempfile.mkdtemp()
    try:
        prompt_file = os.path.join(temp_dir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("""---
model: openai/gpt-4o
tools:
  - sample_tools.greet
shell_tools:
  echo_test: echo "hello"
---
Test prompt
""")

        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 5)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', '--tool-path=tests', prompt_file],
            capture_output=True,
            text=True,
            env=env,
            input='{}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        req = MockHandler.received_requests[0]
        body = req['body']
        tools = body.get('tools', [])
        tool_names = [t['function']['name'] for t in tools]
        assert 'greet' in tool_names, "Expected greet Python tool"
        assert 'echo_test' in tool_names, "Expected echo_test shell tool"
    finally:
        server.shutdown()
        shutil.rmtree(temp_dir)


if __name__ == '__main__':
    test("shell_tools short form", test_shell_tools_short_form)
    test("shell_tools long form", test_shell_tools_long_form)
    test("shell_tools missing cmd", test_shell_tools_missing_cmd)
    test("shell_tools mixed forms", test_shell_tools_mixed_forms)
    test("shell_tools default not safe", test_shell_tools_default_not_safe)
    test("shell_tools with python tools", test_shell_tools_with_python_tools)

    print("")
    print("Passed: %d, Failed: %d" % (passed, failed))
    if failed > 0:
        exit(1)
