#!/usr/bin/env python3
"""Test save and load conversation context functionality."""
import subprocess
import os
import json
import tempfile
import shutil
import threading
import time
import base64
from http.server import HTTPServer, BaseHTTPRequestHandler

MOCK_PORT = 18870
RUNPROMPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runprompt")

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
                "message": {"content": "Hello from mock server!"}
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


def test_round_trip():
    """Test round-trip save and load of context."""
    import importlib.machinery
    import importlib.util
    
    loader = importlib.machinery.SourceFileLoader("runprompt_module", RUNPROMPT)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)

    temp_dir = tempfile.mkdtemp()
    try:
        filename = os.path.join(temp_dir, "context.json")
        meta = {"model": "openai/gpt-4o", "temperature": 0.5}
        messages = [{"role": "user", "content": "Hello"}]
        read_files = [{"path": "test.txt", "content": "file content", "is_binary": False, "mime_type": "text/plain"}]
        variables = {"name": "World"}
        prompt = "Say hello to World"

        module.save_context(filename, meta, messages, read_files, variables, prompt)
        assert os.path.exists(filename), "Context file should be created"

        loaded = module.load_context_file(filename)
        assert loaded["meta"] == meta, "Meta should match"
        assert loaded["messages"] == messages, "Messages should match"
        assert loaded["variables"] == variables, "Variables should match"
        assert loaded["prompt"] == prompt, "Prompt should match"
        assert loaded["read_files"][0]["content"] == "file content", "Read files content should match"
    finally:
        shutil.rmtree(temp_dir)


def test_binary_attachment_round_trip():
    """Test that binary attachments survive save/load with base64 encoding."""
    import importlib.machinery
    import importlib.util
    
    loader = importlib.machinery.SourceFileLoader("runprompt_module", RUNPROMPT)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)

    temp_dir = tempfile.mkdtemp()
    try:
        filename = os.path.join(temp_dir, "context.json")
        meta = {"model": "openai/gpt-4o"}
        messages = []
        binary_data = b"\x00\x01\x02\x03hello\xff"
        read_files = [{"path": "test.bin", "content": binary_data, "is_binary": True, "mime_type": "application/octet-stream"}]
        variables = {}
        prompt = "Process binary"

        module.save_context(filename, meta, messages, read_files, variables, prompt)
        
        # Verify it is stored as base64 in JSON
        with open(filename, "r") as f:
            raw_json = json.load(f)
            stored_file = raw_json["read_files"][0]
            assert stored_file["_is_b64"] is True, "Should have _is_b64 marker"
            assert stored_file["content"] == base64.b64encode(binary_data).decode("ascii"), "Should be base64 encoded"

        loaded = module.load_context_file(filename)
        assert loaded["read_files"][0]["content"] == binary_data, "Binary content should match original bytes"
        assert "is_b64" not in loaded["read_files"][0], "Marker should be removed"
    finally:
        shutil.rmtree(temp_dir)


def test_load_startup():
    """Test that --load startup resumes a session and continues a chat turn."""
    server = start_server(MOCK_PORT)
    temp_dir = tempfile.mkdtemp()
    try:
        context_file = os.path.join(temp_dir, "context.json")
        context_data = {
            "meta": {"model": "openai/gpt-4o"},
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ],
            "read_files": [],
            "variables": {},
            "prompt": "Hello"
        }
        with open(context_file, "w") as f:
            json.dump(context_data, f, indent=2)

        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % MOCK_PORT
        env['OPENAI_API_KEY'] = 'test-key'

        # Run runprompt with --load and provide a user turn via stdin
        result = subprocess.run(
            [RUNPROMPT, "--load", context_file],
            capture_output=True,
            text=True,
            env=env,
            input="How are you?\n"
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert len(MockHandler.received_requests) == 1, "Expected 1 request to mock server"
        req = MockHandler.received_requests[0]
        messages = req['body']['messages']
        assert len(messages) == 3, "Expected 3 messages in request"
        assert messages[0]['content'] == "Hello"
        assert messages[1]['content'] == "Hi there!"
        assert messages[2]['content'] == "How are you?"
    finally:
        server.shutdown()
        shutil.rmtree(temp_dir)


def test_autosave():
    """Test that --autosave automatically saves the context after a turn."""
    server = start_server(MOCK_PORT + 1)
    temp_dir = tempfile.mkdtemp()
    try:
        autosave_file = os.path.join(temp_dir, "autosave.json")
        prompt_file = os.path.join(temp_dir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("---\nmodel: openai/gpt-4o\n---\nHello!")

        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 1)
        env['OPENAI_API_KEY'] = 'test-key'
        env['RUNPROMPT_AUTOSAVE'] = '1'
        env['RUNPROMPT_AUTOSAVE_FILE'] = autosave_file

        result = subprocess.run(
            [RUNPROMPT, prompt_file],
            capture_output=True,
            text=True,
            env=env,
            input="{}"
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert os.path.exists(autosave_file), "Autosave file should be created"
        
        with open(autosave_file, "r") as f:
            saved = json.load(f)
            assert len(saved["messages"]) == 2, "Should contain user and assistant messages"
            assert saved["messages"][1]["content"] == "Hello from mock server!"
    finally:
        server.shutdown()
        shutil.rmtree(temp_dir)


def test_corrupt_load_exits_nonzero():
    """Test that loading a corrupt context file exits non-zero."""
    temp_dir = tempfile.mkdtemp()
    try:
        corrupt_file = os.path.join(temp_dir, "corrupt.json")
        with open(corrupt_file, "w") as f:
            f.write("{invalid json")

        env = clean_env()
        result = subprocess.run(
            [RUNPROMPT, "--load", corrupt_file],
            capture_output=True,
            text=True,
            env=env
        )
        assert result.returncode != 0, "Expected non-zero exit code for corrupt file"
        assert "Error" in result.stderr, "Expected error message in stderr"
    finally:
        shutil.rmtree(temp_dir)


def test_backup_existing_context():
    """Test that saving backs up an existing context file rather than overwriting it."""
    import importlib.machinery
    import importlib.util
    
    loader = importlib.machinery.SourceFileLoader("runprompt_module", RUNPROMPT)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)

    temp_dir = tempfile.mkdtemp()
    try:
        filename = os.path.join(temp_dir, "context.json")
        # Create initial file
        with open(filename, "w") as f:
            f.write("original content")

        meta = {"model": "openai/gpt-4o"}
        messages = []
        read_files = []
        variables = {}
        prompt = "New prompt"

        module.save_context(filename, meta, messages, read_files, variables, prompt)
        
        # Check backup exists
        bak_filename = filename + ".bak"
        assert os.path.exists(bak_filename), "Backup file should exist"
        with open(bak_filename, "r") as f:
            assert f.read() == "original content", "Backup should contain original content"
    finally:
        shutil.rmtree(temp_dir)


if __name__ == '__main__':
    test("round-trip save/load", test_round_trip)
    test("binary attachment round-trip", test_binary_attachment_round_trip)
    test("load startup turn continuation", test_load_startup)
    test("autosave functionality", test_autosave)
    test("corrupt load exits non-zero", test_corrupt_load_exits_nonzero)
    test("backup existing context", test_backup_existing_context)

    print("")
    print("Passed: %d, Failed: %d" % (passed, failed))
    if failed > 0:
        exit(1)
