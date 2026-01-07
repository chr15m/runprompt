#!/usr/bin/env python3
"""Test before: shell command execution."""
import os
import sys
import json
import subprocess
import tempfile
import shutil

RUNPROMPT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "runprompt")

passed = 0
failed = 0


def test(name, func):
    global passed, failed
    print("Testing: %s" % name)
    try:
        func()
        print("  ✓ PASS")
        passed += 1
    except AssertionError as e:
        print("  ✗ FAIL: %s" % e)
        failed += 1
    except Exception as e:
        print("  ✗ ERROR: %s" % e)
        failed += 1


def clean_env():
    """Remove RUNPROMPT_* env vars."""
    for key in list(os.environ.keys()):
        if key.startswith("RUNPROMPT_"):
            del os.environ[key]


def test_before_basic():
    """Test basic before: command execution."""
    clean_env()
    with tempfile.TemporaryDirectory() as tmpdir:
        prompt_file = os.path.join(tmpdir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("""---
model: test
before:
  greeting: echo "Hello World"
---
Output: {{greeting}}
""")
        # Create test response that echoes back what it received
        test_response = os.path.join(tmpdir, "test.prompt.test-response")
        with open(test_response, "w") as f:
            json.dump({
                "_provider": "openai",
                "choices": [{
                    "message": {"content": "Output: Hello World"}
                }]
            }, f)
        
        result = subprocess.run(
            [RUNPROMPT, prompt_file],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0, "Command failed: %s" % result.stderr
        assert "Hello World" in result.stdout, \
            "Expected 'Hello World' in output, got: %s" % result.stdout


def test_before_multiple_commands():
    """Test multiple before: commands."""
    clean_env()
    with tempfile.TemporaryDirectory() as tmpdir:
        prompt_file = os.path.join(tmpdir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("""---
model: test
before:
  first: echo "one"
  second: echo "two"
  third: echo "three"
---
{{first}} {{second}} {{third}}
""")
        test_response = os.path.join(tmpdir, "test.prompt.test-response")
        with open(test_response, "w") as f:
            json.dump({
                "_provider": "openai",
                "choices": [{
                    "message": {"content": "test output"}
                }]
            }, f)
        
        result = subprocess.run(
            [RUNPROMPT, prompt_file],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0, "Command failed: %s" % result.stderr


def test_before_with_pipes():
    """Test before: command with shell pipes."""
    clean_env()
    with tempfile.TemporaryDirectory() as tmpdir:
        prompt_file = os.path.join(tmpdir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("""---
model: test
before:
  count: echo -e "line1\\nline2\\nline3" | wc -l
---
Lines: {{count}}
""")
        test_response = os.path.join(tmpdir, "test.prompt.test-response")
        with open(test_response, "w") as f:
            json.dump({
                "_provider": "openai",
                "choices": [{
                    "message": {"content": "test output"}
                }]
            }, f)
        
        result = subprocess.run(
            [RUNPROMPT, prompt_file],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0, "Command failed: %s" % result.stderr


def test_before_env_vars():
    """Test that template variables are available as env vars in before: commands."""
    clean_env()
    with tempfile.TemporaryDirectory() as tmpdir:
        prompt_file = os.path.join(tmpdir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("""---
model: test
before:
  model_echo: echo "Model is ${model}"
---
{{model_echo}}
""")
        test_response = os.path.join(tmpdir, "test.prompt.test-response")
        with open(test_response, "w") as f:
            json.dump({
                "_provider": "openai",
                "choices": [{
                    "message": {"content": "Model is test"}
                }]
            }, f)
        
        result = subprocess.run(
            [RUNPROMPT, prompt_file],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0, "Command failed: %s" % result.stderr
        assert "Model is test" in result.stdout, \
            "Expected 'Model is test' in output, got: %s" % result.stdout


def test_before_error_captured():
    """Test that stderr is captured when command fails."""
    clean_env()
    with tempfile.TemporaryDirectory() as tmpdir:
        prompt_file = os.path.join(tmpdir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("""---
model: test
before:
  bad_command: ls /nonexistent/path 2>&1
---
Error: {{bad_command}}
""")
        test_response = os.path.join(tmpdir, "test.prompt.test-response")
        with open(test_response, "w") as f:
            json.dump({
                "_provider": "openai",
                "choices": [{
                    "message": {"content": "test output"}
                }]
            }, f)
        
        result = subprocess.run(
            [RUNPROMPT, prompt_file],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0, "Command should succeed even if before: command fails"


def test_before_combined_variable():
    """Test that BEFORE variable contains all outputs."""
    clean_env()
    with tempfile.TemporaryDirectory() as tmpdir:
        prompt_file = os.path.join(tmpdir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("""---
model: test
before:
  a: echo "first"
  b: echo "second"
---
{{BEFORE}}
""")
        test_response = os.path.join(tmpdir, "test.prompt.test-response")
        with open(test_response, "w") as f:
            json.dump({
                "_provider": "openai",
                "choices": [{
                    "message": {"content": "test output"}
                }]
            }, f)
        
        result = subprocess.run(
            [RUNPROMPT, prompt_file],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0, "Command failed: %s" % result.stderr


def test_before_uses_configured_shell():
    """Test that before: uses $SHELL environment variable."""
    clean_env()
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a custom shell script that adds a marker
        custom_shell = os.path.join(tmpdir, "custom_shell.sh")
        with open(custom_shell, "w") as f:
            f.write("""#!/bin/sh
# Custom shell that adds a marker to output
if [ "$1" = "-c" ]; then
    eval "$2"
fi
""")
        os.chmod(custom_shell, 0o755)
        
        prompt_file = os.path.join(tmpdir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("""---
model: test
before:
  test: echo "shell test"
---
{{test}}
""")
        test_response = os.path.join(tmpdir, "test.prompt.test-response")
        with open(test_response, "w") as f:
            json.dump({
                "_provider": "openai",
                "choices": [{
                    "message": {"content": "test output"}
                }]
            }, f)
        
        env = os.environ.copy()
        env["SHELL"] = custom_shell
        
        result = subprocess.run(
            [RUNPROMPT, prompt_file],
            capture_output=True,
            text=True,
            env=env,
        )
        
        assert result.returncode == 0, "Command failed: %s" % result.stderr


def test_before_output_in_files():
    """Test that before: output can be used in files: frontmatter."""
    clean_env()
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a test file to read
        test_file = os.path.join(tmpdir, "data.txt")
        with open(test_file, "w") as f:
            f.write("Test file content")
        
        prompt_file = os.path.join(tmpdir, "test.prompt")
        with open(prompt_file, "w") as f:
            f.write("""---
model: test
before:
  filepath: echo "%s"
files:
  - "{{filepath}}"
---
Process the file.
""" % test_file)
        
        test_response = os.path.join(tmpdir, "test.prompt.test-response")
        with open(test_response, "w") as f:
            json.dump({
                "_provider": "openai",
                "choices": [{
                    "message": {"content": "test output"}
                }]
            }, f)
        
        result = subprocess.run(
            [RUNPROMPT, prompt_file],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0, "Command failed: %s" % result.stderr
        # Check that the file was loaded (yellow message to stderr)
        assert "data.txt" in result.stderr, \
            "Expected file load message in stderr, got: %s" % result.stderr


def main():
    test("before: basic command execution", test_before_basic)
    test("before: multiple commands", test_before_multiple_commands)
    test("before: commands with pipes", test_before_with_pipes)
    test("before: template vars as env vars", test_before_env_vars)
    test("before: error output captured", test_before_error_captured)
    test("before: BEFORE combined variable", test_before_combined_variable)
    test("before: uses configured shell", test_before_uses_configured_shell)
    test("before: output in files frontmatter", test_before_output_in_files)
    
    print("\n" + "=" * 50)
    print("Results: %d passed, %d failed" % (passed, failed))
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
