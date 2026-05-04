#!/usr/bin/env python3
"""Test configuration cascade functionality."""
import importlib.machinery
import importlib.util
import subprocess
import os
import json
import shutil
import tempfile
import threading
import time
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

MOCK_PORT = 18820
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
                "message": {"content": "OK"}
            }]
        }
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def log_message(self, format, *args):
        pass


class DummyResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass

    def read(self):
        response = {
            "choices": [{
                "message": {"content": "OK"}
            }]
        }
        return json.dumps(response).encode("utf-8")


def load_runprompt():
    loader = importlib.machinery.SourceFileLoader("runprompt_module", RUNPROMPT)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


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


def test_timeout_cascade_for_provider_request():
    """Test that timeout config reaches the provider request."""
    module = load_runprompt()
    captured = []
    original_urlopen = urllib.request.urlopen

    def fake_urlopen(req, **kwargs):
        captured.append(kwargs.get("timeout"))
        return DummyResponse()

    try:
        urllib.request.urlopen = fake_urlopen
        cases = [
            ({}, {}, {}, 120.0, "default"),
            ({"timeout": 30}, {}, {}, 30.0, "config file"),
            ({"timeout": 30}, {"timeout": 45}, {}, 45.0, "env"),
            ({"timeout": 30}, {"timeout": 45}, {"timeout": 60}, 60.0,
             "CLI args"),
        ]
        for files, env, args, expected, source in cases:
            module.CONFIG["files"] = files
            module.CONFIG["env"] = env
            module.CONFIG["args"] = args
            module.make_request("https://example.test/chat/completions",
                                "test-key", "gpt-4o",
                                [{"role": "user", "content": "hi"}],
                                {}, "openai")
            assert captured[-1] == expected, \
                "Expected timeout from %s, got: %s" % (source, captured[-1])
    finally:
        urllib.request.urlopen = original_urlopen


def test_timeout_cli_flag():
    """Test that --timeout is parsed as a config value."""
    module = load_runprompt()
    parsed = module.parse_args(["--timeout", "12.5", "test.prompt"])
    module.init_config(parsed)
    assert module.get_conf("timeout") == 12.5, \
        "Expected parsed timeout, got: %s" % module.get_conf("timeout")


def test_config_file_model():
    """Test that model can be set from config file."""
    server = start_server(MOCK_PORT)
    config_dir = tempfile.mkdtemp()
    try:
        # Create config file
        runprompt_dir = os.path.join(config_dir, ".runprompt")
        os.makedirs(runprompt_dir)
        config_file = os.path.join(runprompt_dir, "config.yml")
        with open(config_file, "w") as f:
            f.write("model: openai/gpt-4o-from-config\n")

        # Create a prompt file without model
        prompt_file = os.path.join(config_dir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("---\n---\nHello {{name}}!")

        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % MOCK_PORT
        env['OPENAI_API_KEY'] = 'test-key'
        env['HOME'] = config_dir  # So ~/.runprompt is found

        result = subprocess.run(
            [RUNPROMPT, prompt_file],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}',
            cwd=config_dir
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        assert len(MockHandler.received_requests) == 1, "Expected 1 request"
        req = MockHandler.received_requests[0]
        assert req['body']['model'] == 'gpt-4o-from-config', \
            "Expected model from config, got: %s" % req['body'].get('model')
    finally:
        server.shutdown()
        shutil.rmtree(config_dir)


def test_env_overrides_config_file():
    """Test that env var overrides config file."""
    server = start_server(MOCK_PORT + 1)
    config_dir = tempfile.mkdtemp()
    try:
        # Create config file with one model
        runprompt_dir = os.path.join(config_dir, ".runprompt")
        os.makedirs(runprompt_dir)
        config_file = os.path.join(runprompt_dir, "config.yml")
        with open(config_file, "w") as f:
            f.write("model: openai/from-config\n")

        # Create a prompt file without model
        prompt_file = os.path.join(config_dir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("---\n---\nHello {{name}}!")

        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 1)
        env['OPENAI_API_KEY'] = 'test-key'
        env['HOME'] = config_dir
        env['RUNPROMPT_MODEL'] = 'openai/from-env'  # Should override config

        result = subprocess.run(
            [RUNPROMPT, prompt_file],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}',
            cwd=config_dir
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        req = MockHandler.received_requests[0]
        assert req['body']['model'] == 'from-env', \
            "Expected model from env, got: %s" % req['body'].get('model')
    finally:
        server.shutdown()
        shutil.rmtree(config_dir)


def test_cli_overrides_env():
    """Test that CLI flag overrides env var."""
    server = start_server(MOCK_PORT + 2)
    config_dir = tempfile.mkdtemp()
    try:
        # Create a prompt file without model
        prompt_file = os.path.join(config_dir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("---\n---\nHello {{name}}!")

        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 2)
        env['OPENAI_API_KEY'] = 'test-key'
        env['RUNPROMPT_MODEL'] = 'openai/from-env'

        result = subprocess.run(
            [RUNPROMPT, '--model=openai/from-cli', prompt_file],
            capture_output=True,
            text=True,
            env=env,
            input='{"name": "World"}',
            cwd=config_dir
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        req = MockHandler.received_requests[0]
        assert req['body']['model'] == 'from-cli', \
            "Expected model from CLI, got: %s" % req['body'].get('model')
    finally:
        server.shutdown()
        shutil.rmtree(config_dir)


def test_local_config_overrides_home():
    """Test that ./.runprompt overrides ~/.runprompt."""
    server = start_server(MOCK_PORT + 3)
    home_dir = tempfile.mkdtemp()
    work_dir = tempfile.mkdtemp()
    try:
        # Create home config
        home_runprompt = os.path.join(home_dir, ".runprompt")
        os.makedirs(home_runprompt)
        with open(os.path.join(home_runprompt, "config.yml"), "w") as f:
            f.write("model: openai/from-home\n")

        # Create local config
        local_runprompt = os.path.join(work_dir, ".runprompt")
        os.makedirs(local_runprompt)
        with open(os.path.join(local_runprompt, "config.yml"), "w") as f:
            f.write("model: openai/from-local\n")

        # Create prompt file
        prompt_file = os.path.join(work_dir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("---\n---\nHello!")

        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 3)
        env['OPENAI_API_KEY'] = 'test-key'
        env['HOME'] = home_dir
        # Clear XDG to avoid interference
        env.pop('XDG_CONFIG_HOME', None)

        result = subprocess.run(
            [RUNPROMPT, prompt_file],
            capture_output=True,
            text=True,
            env=env,
            input='{}',
            cwd=work_dir
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        req = MockHandler.received_requests[0]
        assert req['body']['model'] == 'from-local', \
            "Expected model from local config, got: %s" % req['body'].get('model')
    finally:
        server.shutdown()
        shutil.rmtree(home_dir)
        shutil.rmtree(work_dir)


def test_api_key_from_config():
    """Test that API key can be set from config file."""
    server = start_server(MOCK_PORT + 4)
    config_dir = tempfile.mkdtemp()
    try:
        # Create config file with API key
        runprompt_dir = os.path.join(config_dir, ".runprompt")
        os.makedirs(runprompt_dir)
        with open(os.path.join(runprompt_dir, "config.yml"), "w") as f:
            f.write("openai_api_key: key-from-config\n")

        prompt_file = os.path.join(config_dir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("---\nmodel: openai/gpt-4o\n---\nHello!")

        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 4)
        env['HOME'] = config_dir
        # Don't set OPENAI_API_KEY - should come from config
        env.pop('OPENAI_API_KEY', None)

        result = subprocess.run(
            [RUNPROMPT, prompt_file],
            capture_output=True,
            text=True,
            env=env,
            input='{}',
            cwd=config_dir
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        req = MockHandler.received_requests[0]
        assert 'Bearer key-from-config' in req['headers'].get('Authorization', ''), \
            "Expected API key from config in auth header"
    finally:
        server.shutdown()
        shutil.rmtree(config_dir)


def test_tool_path_from_config():
    """Test that tool_path can be set from config file."""
    server = start_server(MOCK_PORT + 5)
    config_dir = tempfile.mkdtemp()
    try:
        # Create tools directory with a tool
        tools_dir = os.path.join(config_dir, "my_tools")
        os.makedirs(tools_dir)
        with open(os.path.join(tools_dir, "test_tool.py"), "w") as f:
            f.write('def my_tool(x: str):\n    """A test tool."""\n    return x\n')

        # Create config file with tool_path
        runprompt_dir = os.path.join(config_dir, ".runprompt")
        os.makedirs(runprompt_dir)
        with open(os.path.join(runprompt_dir, "config.yml"), "w") as f:
            f.write("tool_path:\n  - %s\n" % tools_dir)

        prompt_file = os.path.join(config_dir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("---\nmodel: openai/gpt-4o\ntools:\n  - test_tool.*\n---\nHello!")

        env = clean_env()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 5)
        env['OPENAI_API_KEY'] = 'test-key'
        env['HOME'] = config_dir

        result = subprocess.run(
            [RUNPROMPT, prompt_file],
            capture_output=True,
            text=True,
            env=env,
            input='{}',
            cwd=config_dir
        )
        assert result.returncode == 0, "Expected success, got: %s" % result.stderr
        req = MockHandler.received_requests[0]
        tools = req['body'].get('tools', [])
        tool_names = [t['function']['name'] for t in tools]
        assert 'my_tool' in tool_names, \
            "Expected my_tool from config tool_path, got: %s" % tool_names
    finally:
        server.shutdown()
        shutil.rmtree(config_dir)


if __name__ == '__main__':
    test("timeout cascade for provider request", test_timeout_cascade_for_provider_request)
    test("timeout CLI flag", test_timeout_cli_flag)
    test("config file model", test_config_file_model)
    test("env overrides config file", test_env_overrides_config_file)
    test("CLI overrides env", test_cli_overrides_env)
    test("local config overrides home", test_local_config_overrides_home)
    test("API key from config", test_api_key_from_config)
    test("tool_path from config", test_tool_path_from_config)

    print("")
    print("Passed: %d, Failed: %d" % (passed, failed))
    if failed > 0:
        exit(1)
