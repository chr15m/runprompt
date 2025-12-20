#!/usr/bin/env python3
"""Test tool calling functionality."""
import subprocess
import os
import sys
import json
import threading
import time
import pty
import select
from http.server import HTTPServer, BaseHTTPRequestHandler

MOCK_PORT = 18790

passed = 0
failed = 0


class MockHandler(BaseHTTPRequestHandler):
    responses = []
    request_count = 0
    received_requests = []

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        MockHandler.received_requests.append({
            'path': self.path,
            'headers': dict(self.headers),
            'body': json.loads(body) if body else None
        })
        response = MockHandler.responses[MockHandler.request_count] \
            if MockHandler.request_count < len(MockHandler.responses) \
            else {"choices": [{"message": {"content": "No more responses"}}]}
        MockHandler.request_count += 1
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def log_message(self, format, *args):
        pass


def run_server(server):
    server.serve_forever()


def run_with_pty(args, env, interactions, timeout=5):
    """Run a command with a pty, sending input based on expected output.
    
    interactions: list of (expect, send) tuples
        - expect: string to wait for in output, or None to send immediately
        - send: string to send (newline added automatically)
    """
    master_fd, slave_fd = pty.openpty()
    proc = subprocess.Popen(
        args,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=env,
    )
    os.close(slave_fd)
    
    output = b''
    interaction_idx = 0
    start_time = time.time()
    
    # Send any immediate inputs (expect=None) before reading output
    while interaction_idx < len(interactions):
        expect, send = interactions[interaction_idx]
        if expect is None:
            os.write(master_fd, (send + '\n').encode())
            interaction_idx += 1
        else:
            break
    
    while proc.poll() is None:
        if time.time() - start_time > timeout:
            proc.kill()
            proc.wait()
            raise subprocess.TimeoutExpired(
                args, timeout, output.decode(), output.decode())
        
        # Check if there's output to read
        ready, _, _ = select.select([master_fd], [], [], 0.1)
        if ready:
            try:
                chunk = os.read(master_fd, 1024)
                if chunk:
                    output += chunk
            except OSError:
                break
        
        # Check if we should send the next input
        if interaction_idx < len(interactions):
            expect, send = interactions[interaction_idx]
            if expect is None or expect.encode() in output:
                os.write(master_fd, (send + '\n').encode())
                interaction_idx += 1
    
    # Read any remaining output
    while True:
        ready, _, _ = select.select([master_fd], [], [], 0.1)
        if not ready:
            break
        try:
            chunk = os.read(master_fd, 1024)
            if not chunk:
                break
            output += chunk
        except OSError:
            break
    
    os.close(master_fd)
    proc.wait()
    
    decoded = output.decode()
    return proc.returncode, decoded, decoded


def start_server(port, responses):
    MockHandler.responses = responses
    MockHandler.request_count = 0
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


def test_tools_sent_in_request():
    """Test that tools are included in the API request."""
    responses = [
        {"choices": [{"message": {"content": "The sum is 5"}}]}
    ]
    server = start_server(MOCK_PORT, responses)
    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % MOCK_PORT
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', '--tools=sample_tools.*',
             '--tool-path=tests', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert len(MockHandler.received_requests) == 1, "Expected 1 request"
        req = MockHandler.received_requests[0]
        body = req['body']
        assert 'tools' in body, "Expected tools in request body"
        tool_names = [t['function']['name'] for t in body['tools']]
        assert 'add_numbers' in tool_names, "Expected add_numbers tool"
        assert 'greet' in tool_names, "Expected greet tool"
        assert 'no_docstring_func' not in tool_names, \
            "no_docstring_func should not be included"
    finally:
        server.shutdown()


def test_tool_schema_generation():
    """Test that tool schemas are correctly generated from Python functions."""
    responses = [
        {"choices": [{"message": {"content": "Done"}}]}
    ]
    server = start_server(MOCK_PORT + 1, responses)
    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 1)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', '--tools=sample_tools.add_numbers',
             '--tool-path=tests', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        req = MockHandler.received_requests[0]
        body = req['body']
        tools = body.get('tools', [])
        assert len(tools) == 1, "Expected 1 tool"
        func = tools[0]['function']
        assert func['name'] == 'add_numbers', "Wrong tool name"
        assert 'Adds two numbers' in func['description'], "Wrong description"
        params = func['parameters']
        assert params['properties']['a']['type'] == 'integer', "a should be integer"
        assert params['properties']['b']['type'] == 'integer', "b should be integer"
        assert 'a' in params['required'], "a should be required"
        assert 'b' in params['required'], "b should be required"
    finally:
        server.shutdown()


def test_tool_execution_flow():
    """Test the full tool call and response flow with user approval via pty."""
    responses = [
        # First response: model requests tool call
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "add_numbers",
                            "arguments": '{"a": 2, "b": 3}'
                        }
                    }]
                }
            }]
        },
        # Second response: model uses tool result
        {
            "choices": [{
                "message": {
                    "content": "The result of adding 2 and 3 is 5."
                }
            }]
        }
    ]
    server = start_server(MOCK_PORT + 2, responses)
    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 2)
        env['OPENAI_API_KEY'] = 'test-key'
        # Use pty to provide JSON input and 'y' for tool confirmation
        returncode, stdout, stderr = run_with_pty(
            ['./runprompt', '--tools=sample_tools.add_numbers',
             '--tool-path=tests', 'tests/hello.prompt'],
            env=env,
            interactions=[
                (None, '{"name": "World"}'),
                ('Run this tool?', 'y'),
            ],
            timeout=5
        )
        assert returncode == 0, "Expected success, got: %s" % stderr
        assert len(MockHandler.received_requests) == 2, "Expected 2 requests"
        # Check second request includes tool result
        second_req = MockHandler.received_requests[1]['body']
        messages = second_req['messages']
        tool_msg = [m for m in messages if m.get('role') == 'tool']
        assert len(tool_msg) == 1, "Expected tool result message"
        assert tool_msg[0]['tool_call_id'] == 'call_123', "Wrong tool call id"
        assert '5' in tool_msg[0]['content'], "Expected result 5 in tool response"
    finally:
        server.shutdown()


def test_tool_user_decline():
    """Test that declining tool execution sends error to model."""
    responses = [
        # First response: model requests tool call
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_456",
                        "type": "function",
                        "function": {
                            "name": "add_numbers",
                            "arguments": '{"a": 1, "b": 2}'
                        }
                    }]
                }
            }]
        },
        # Second response: model handles declined tool
        {
            "choices": [{
                "message": {
                    "content": "I understand you declined the tool."
                }
            }]
        }
    ]
    server = start_server(MOCK_PORT + 3, responses)
    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 3)
        env['OPENAI_API_KEY'] = 'test-key'
        # Use pty to provide JSON input and 'n' to decline tool
        returncode, stdout, stderr = run_with_pty(
            ['./runprompt', '--tools=sample_tools.add_numbers',
             '--tool-path=tests', 'tests/hello.prompt'],
            env=env,
            interactions=[
                (None, '{"name": "World"}'),
                ('Run this tool?', 'n'),
            ],
            timeout=5
        )
        assert returncode == 0, "Expected success, got: %s" % stderr
        assert len(MockHandler.received_requests) == 2, "Expected 2 requests"
        second_req = MockHandler.received_requests[1]['body']
        messages = second_req['messages']
        tool_msg = [m for m in messages if m.get('role') == 'tool']
        assert len(tool_msg) == 1, "Expected tool result message"
        assert 'declined' in tool_msg[0]['content'].lower(), \
            "Expected decline message in tool response"
    finally:
        server.shutdown()


def test_specific_tool_import():
    """Test importing a specific tool function."""
    responses = [
        {"choices": [{"message": {"content": "Done"}}]}
    ]
    server = start_server(MOCK_PORT + 4, responses)
    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 4)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', '--tools=sample_tools.greet',
             '--tool-path=tests', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        req = MockHandler.received_requests[0]
        body = req['body']
        tools = body.get('tools', [])
        tool_names = [t['function']['name'] for t in tools]
        assert 'greet' in tool_names, "Expected greet tool"
        assert 'add_numbers' not in tool_names, \
            "add_numbers should not be included"
    finally:
        server.shutdown()


def test_unknown_tool_error():
    """Test that unknown tool calls are handled gracefully."""
    responses = [
        # Model requests unknown tool
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_789",
                        "type": "function",
                        "function": {
                            "name": "unknown_tool",
                            "arguments": '{}'
                        }
                    }]
                }
            }]
        },
        # Model handles error
        {
            "choices": [{
                "message": {
                    "content": "That tool is not available."
                }
            }]
        }
    ]
    server = start_server(MOCK_PORT + 5, responses)
    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 5)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', '--tools=sample_tools.greet',
             '--tool-path=tests', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert 'Unknown tool' in result.stderr, "Expected unknown tool error"
        assert len(MockHandler.received_requests) == 2, "Expected 2 requests"
    finally:
        server.shutdown()


def test_safe_yes_auto_approves_safe_tools():
    """Test that --safe-yes auto-approves tools marked as safe."""
    responses = [
        # First response: model requests safe tool call
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_safe",
                        "type": "function",
                        "function": {
                            "name": "greet",
                            "arguments": '{"name": "Alice"}'
                        }
                    }]
                }
            }]
        },
        # Second response: model uses tool result
        {
            "choices": [{
                "message": {
                    "content": "I greeted Alice for you."
                }
            }]
        }
    ]
    server = start_server(MOCK_PORT + 6, responses)
    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 6)
        env['OPENAI_API_KEY'] = 'test-key'
        # No tool confirmation needed - should auto-approve because greet.safe = True
        result = subprocess.run(
            ['./runprompt', '--safe-yes', '--tools=sample_tools.greet',
             '--tool-path=tests', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert len(MockHandler.received_requests) == 2, "Expected 2 requests"
        # Check that tool was executed (result sent back)
        second_req = MockHandler.received_requests[1]['body']
        messages = second_req['messages']
        tool_msg = [m for m in messages if m.get('role') == 'tool']
        assert len(tool_msg) == 1, "Expected tool result message"
        assert 'Hello, Alice!' in tool_msg[0]['content'], \
            "Expected greeting in tool response"
    finally:
        server.shutdown()


def test_builtin_tool_wildcard():
    """Test that builtin.* loads all builtin tools."""
    responses = [
        {"choices": [{"message": {"content": "Done"}}]}
    ]
    server = start_server(MOCK_PORT + 8, responses)
    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 8)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', '--tools=builtin.*', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        req = MockHandler.received_requests[0]
        body = req['body']
        tools = body.get('tools', [])
        tool_names = [t['function']['name'] for t in tools]
        assert 'fetch_clean' in tool_names, "Expected fetch_clean builtin tool"
    finally:
        server.shutdown()


def test_builtin_tool_specific():
    """Test that builtin.fetch_clean loads the specific tool."""
    responses = [
        {"choices": [{"message": {"content": "Done"}}]}
    ]
    server = start_server(MOCK_PORT + 9, responses)
    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 9)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', '--tools=builtin.fetch_clean', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        req = MockHandler.received_requests[0]
        body = req['body']
        tools = body.get('tools', [])
        assert len(tools) == 1, "Expected exactly 1 tool"
        assert tools[0]['function']['name'] == 'fetch_clean', \
            "Expected fetch_clean tool"
        # Check schema
        params = tools[0]['function']['parameters']
        assert 'url' in params['properties'], "Expected url parameter"
        assert params['properties']['url']['type'] == 'string', \
            "url should be string type"
    finally:
        server.shutdown()


def test_builtin_write_file_factory():
    """Test that builtin.write_file('path') creates a parameterized tool."""
    responses = [
        {"choices": [{"message": {"content": "Done"}}]}
    ]
    server = start_server(MOCK_PORT + 11, responses)
    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 11)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', "--tools=builtin.write_file('test_output.txt')",
             'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        req = MockHandler.received_requests[0]
        body = req['body']
        tools = body.get('tools', [])
        assert len(tools) == 1, "Expected exactly 1 tool, got %d" % len(tools)
        func = tools[0]['function']
        assert func['name'] == 'write_file', \
            "Expected tool name 'write_file', got '%s'" % func['name']
        assert 'test_output.txt' in func['description'], \
            "Expected path in description"
        # Should have 'content' parameter, not 'path'
        params = func['parameters']
        assert 'content' in params['properties'], \
            "Expected 'content' parameter"
        assert 'path' not in params['properties'], \
            "Should not have 'path' parameter"
    finally:
        server.shutdown()


def test_builtin_write_file_execution():
    """Test that write_file tool actually writes to the specified file."""
    import tempfile
    import shutil
    # Create a temp directory for the test
    temp_dir = tempfile.mkdtemp()
    test_file = os.path.join(temp_dir, 'test_write.txt')
    try:
        responses = [
            # First response: model requests write_file tool call
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_write",
                            "type": "function",
                            "function": {
                                "name": "write_file",
                                "arguments": '{"content": "Hello from LLM!"}'
                            }
                        }]
                    }
                }]
            },
            # Second response: model confirms
            {
                "choices": [{
                    "message": {
                        "content": "I wrote the file for you."
                    }
                }]
            }
        ]
        server = start_server(MOCK_PORT + 12, responses)
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 12)
        env['OPENAI_API_KEY'] = 'test-key'
        # Use pty to provide input and 'y' for tool confirmation
        returncode, stdout, stderr = run_with_pty(
            ['./runprompt', "--tools=builtin.write_file('%s')" % test_file,
             'tests/hello.prompt'],
            env=env,
            interactions=[
                (None, '{"name": "World"}'),
                ('Run this tool?', 'y'),
            ],
            timeout=5
        )
        assert returncode == 0, "Expected success, got: %s" % stderr
        # Check file was written
        assert os.path.exists(test_file), "File should have been created"
        with open(test_file, 'r') as f:
            content = f.read()
        assert content == "Hello from LLM!", \
            "Expected 'Hello from LLM!', got '%s'" % content
    finally:
        shutil.rmtree(temp_dir)
        server.shutdown()


def test_builtin_factory_without_args_warns():
    """Test that using a factory tool without args shows a warning."""
    responses = [
        {"choices": [{"message": {"content": "Done"}}]}
    ]
    server = start_server(MOCK_PORT + 13, responses)
    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 13)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', '--tools=builtin.write_file',
             'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert 'requires arguments' in result.stderr, \
            "Expected warning about required arguments"
    finally:
        server.shutdown()


def test_builtin_wildcard_skips_factories():
    """Test that builtin.* does not include factory tools."""
    responses = [
        {"choices": [{"message": {"content": "Done"}}]}
    ]
    server = start_server(MOCK_PORT + 14, responses)
    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 14)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', '--tools=builtin.*', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        req = MockHandler.received_requests[0]
        body = req['body']
        tools = body.get('tools', [])
        tool_names = [t['function']['name'] for t in tools]
        assert 'write_file' not in tool_names, \
            "Factory tool should not be included in wildcard"
        assert 'fetch_clean' in tool_names, \
            "Regular builtin should be included"
        assert 'calculator' in tool_names, \
            "Regular builtin should be included"
    finally:
        server.shutdown()


def test_builtin_tool_unknown():
    """Test that unknown builtin tool shows warning."""
    responses = [
        {"choices": [{"message": {"content": "Done"}}]}
    ]
    server = start_server(MOCK_PORT + 10, responses)
    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 10)
        env['OPENAI_API_KEY'] = 'test-key'
        result = subprocess.run(
            ['./runprompt', '--tools=builtin.nonexistent', 'tests/hello.prompt'],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}'
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert 'Unknown builtin tool' in result.stderr, \
            "Expected warning about unknown builtin tool"
    finally:
        server.shutdown()


def test_safe_yes_still_prompts_unsafe_tools():
    """Test that --safe-yes still prompts for tools not marked as safe."""
    responses = [
        # First response: model requests unsafe tool call
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_unsafe",
                        "type": "function",
                        "function": {
                            "name": "add_numbers",
                            "arguments": '{"a": 1, "b": 2}'
                        }
                    }]
                }
            }]
        },
        # Second response: model uses tool result
        {
            "choices": [{
                "message": {
                    "content": "The sum is 3."
                }
            }]
        }
    ]
    server = start_server(MOCK_PORT + 7, responses)
    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 7)
        env['OPENAI_API_KEY'] = 'test-key'
        # With --safe-yes, unsafe tools should still require confirmation
        # Use pty to provide 'y' for the prompt
        returncode, stdout, stderr = run_with_pty(
            ['./runprompt', '--safe-yes', '--tools=sample_tools.add_numbers',
             '--tool-path=tests', 'tests/hello.prompt'],
            env=env,
            interactions=[
                (None, '{"name": "World"}'),
                ('Run this tool?', 'y'),
            ],
            timeout=5
        )
        assert returncode == 0, "Expected success, got: %s" % stderr
        # Tool call summary should be printed (proves it prompted)
        assert 'Tool: add_numbers' in stderr, \
            "Expected tool summary in stderr"
        # Should have prompted for confirmation
        assert 'Run this tool?' in stderr, \
            "Expected tool confirmation prompt for unsafe tool"
        assert len(MockHandler.received_requests) == 2, "Expected 2 requests"
    finally:
        server.shutdown()


if __name__ == '__main__':
    test("tools sent in request", test_tools_sent_in_request)
    test("tool schema generation", test_tool_schema_generation)
    test("tool execution flow", test_tool_execution_flow)
    test("tool user decline", test_tool_user_decline)
    test("specific tool import", test_specific_tool_import)
    test("unknown tool error", test_unknown_tool_error)
    test("safe-yes auto-approves safe tools", test_safe_yes_auto_approves_safe_tools)
    test("safe-yes still prompts unsafe tools", test_safe_yes_still_prompts_unsafe_tools)
    test("builtin tool wildcard", test_builtin_tool_wildcard)
    test("builtin tool specific", test_builtin_tool_specific)
    test("builtin tool unknown", test_builtin_tool_unknown)
    test("builtin write_file factory", test_builtin_write_file_factory)
    test("builtin write_file execution", test_builtin_write_file_execution)
    test("builtin factory without args warns", test_builtin_factory_without_args_warns)
    test("builtin wildcard skips factories", test_builtin_wildcard_skips_factories)

    print("")
    print("Passed: %d, Failed: %d" % (passed, failed))
    if failed > 0:
        exit(1)
