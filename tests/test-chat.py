#!/usr/bin/env python3
"""Test interactive chat mode."""
import subprocess
import os
import json
import threading
import time
import pty
import select
from http.server import HTTPServer, BaseHTTPRequestHandler

MOCK_PORT = 18860
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

def test_chat_loop():
    """Test that chat mode loops and maintains history."""
    responses = [
        {"choices": [{"message": {"role": "assistant", "content": "Hello there!"}}]},
        {"choices": [{"message": {"role": "assistant", "content": "I am doing well."}}]}
    ]
    server = start_server(MOCK_PORT, responses)
    try:
        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % MOCK_PORT
        env['OPENAI_API_KEY'] = 'test-key'
        
        # Remove RUNPROMPT_ vars
        for key in list(env.keys()):
            if key.startswith('RUNPROMPT_'):
                del env[key]

        returncode, stdout, stderr = run_with_pty(
            ['./runprompt', '--chat', 'tests/hello.prompt', '{"name": "World"}'],
            env=env,
            interactions=[
                ('Hello there!', 'How are you?'),     # Wait for 1st response, send 2nd message
                ('I am doing well.', ''),             # Wait for 2nd response, send empty line to exit
            ],
            timeout=5
        )
        
        assert returncode == 0, "Expected success, got: %s" % stderr
        assert len(MockHandler.received_requests) == 2, \
            "Expected 2 API requests, got %d.\nOutput:\n%s" % (
                len(MockHandler.received_requests), stdout)
        
        # Verify the second request contains the conversation history
        second_req = MockHandler.received_requests[1]['body']
        messages = second_req['messages']
        
        assert len(messages) == 3, "Expected 3 messages in history (user, assistant, user)"
        assert messages[0]['role'] == 'user'
        assert 'World' in messages[0]['content']
        assert messages[1]['role'] == 'assistant'
        assert messages[1]['content'] == 'Hello there!'
        assert messages[2]['role'] == 'user'
        assert messages[2]['content'] == 'How are you?'
        
    finally:
        server.shutdown()

def test_chat_frontmatter():
    """Test that chat mode can be enabled via frontmatter."""
    responses = [
        {"choices": [{"message": {"role": "assistant", "content": "Hi!"}}]},
        {"choices": [{"message": {"role": "assistant", "content": "Bye!"}}]}
    ]
    server = start_server(MOCK_PORT + 1, responses)
    import tempfile
    import shutil
    temp_dir = tempfile.mkdtemp()
    try:
        prompt_file = os.path.join(temp_dir, "chat.prompt")
        with open(prompt_file, "w") as f:
            f.write("---\nmodel: openai/gpt-4o\nchat: true\n---\nHello")

        env = os.environ.copy()
        env['OPENAI_BASE_URL'] = 'http://127.0.0.1:%d' % (MOCK_PORT + 1)
        env['OPENAI_API_KEY'] = 'test-key'
        
        # Remove RUNPROMPT_ vars
        for key in list(env.keys()):
            if key.startswith('RUNPROMPT_'):
                del env[key]

        returncode, stdout, stderr = run_with_pty(
            ['./runprompt', prompt_file],
            env=env,
            interactions=[
                ('Hi!', 'How are you?'),
                ('Bye!', ''),
            ],
            timeout=5
        )
        
        assert returncode == 0, "Expected success, got: %s" % stderr
        assert len(MockHandler.received_requests) == 2, "Expected 2 API requests"
        
    finally:
        server.shutdown()
        shutil.rmtree(temp_dir)

if __name__ == '__main__':
    test("chat loop maintains history", test_chat_loop)
    test("chat frontmatter", test_chat_frontmatter)
    print("")
    print("Passed: %d, Failed: %d" % (passed, failed))
    if failed > 0:
        exit(1)
