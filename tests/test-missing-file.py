#!/usr/bin/env python3
"""A missing prompt file must fail cleanly (no traceback)."""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys

RUNPROMPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "runprompt",
)
MISSING = os.path.join("tests", "does-not-exist-xyz.prompt")

passed = 0
failed = 0


def load_runprompt():
    loader = importlib.machinery.SourceFileLoader("runprompt_module", RUNPROMPT)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def check(name, func):
    global passed, failed
    try:
        func()
        print("PASS %s" % name)
        passed += 1
    except AssertionError as e:
        print("FAIL %s" % name)
        print("   %s" % e)
        failed += 1
    except Exception as e:
        print("FAIL %s" % name)
        print("   raised %s: %s" % (type(e).__name__, e))
        failed += 1


def test_parse_missing_file_exits_1():
    runprompt = load_runprompt()
    try:
        runprompt.parse_prompt_file(MISSING)
    except SystemExit as e:
        assert e.code == 1, "expected exit code 1, got %r" % (e.code,)
    else:
        raise AssertionError("expected SystemExit, file was read without error")


def test_cli_missing_file_no_traceback():
    cp = subprocess.run(
        [sys.executable, RUNPROMPT, MISSING, "--model", "test"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    assert cp.returncode == 1, "expected exit code 1, got %s" % cp.returncode
    assert "Traceback" not in cp.stderr, "stderr contains a traceback: %s" % cp.stderr


check("parse_prompt_file missing file exits 1", test_parse_missing_file_exits_1)
check("cli missing file has no traceback", test_cli_missing_file_no_traceback)

print("")
print("Passed: %d, Failed: %d" % (passed, failed))

if failed > 0:
    sys.exit(1)
