#!/usr/bin/env python3
"""Test network configuration."""
import importlib.machinery
import importlib.util
import os
import ssl
import urllib.request

RUNPROMPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runprompt")

passed = 0
failed = 0


class DummyResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass


def load_runprompt():
    loader = importlib.machinery.SourceFileLoader("runprompt_module", RUNPROMPT)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test(name, func):
    global passed, failed
    try:
        func()
        print("PASS %s" % name)
        passed += 1
    except AssertionError as e:
        print("FAIL %s" % name)
        print("   %s" % e)
        failed += 1


def reset_config(module, args=None):
    module.CONFIG["files"] = {}
    module.CONFIG["env"] = {}
    module.CONFIG["args"] = args or {}


def test_default_ssl_verification():
    """Default behavior should not override SSL verification."""
    module = load_runprompt()
    reset_config(module)
    
    # Save original context factory
    original_context = getattr(ssl, '_create_default_https_context', None)
    
    try:
        # Simulate the block in main()
        if module.get_conf("insecure"):
            ssl._create_default_https_context = ssl._create_unverified_context
            
        assert ssl._create_default_https_context is not ssl._create_unverified_context, \
            "Did not expect SSL context to be unverified by default"
    finally:
        if original_context:
            ssl._create_default_https_context = original_context


def test_insecure_context():
    """insecure flag should globally override the SSL context."""
    module = load_runprompt()
    reset_config(module, {"insecure": True})
    
    # Save original context factory
    original_context = getattr(ssl, '_create_default_https_context', None)
    
    try:
        # Simulate the block in main()
        if module.get_conf("insecure"):
            ssl._create_default_https_context = ssl._create_unverified_context
            
        assert ssl._create_default_https_context is ssl._create_unverified_context, \
            "Expected SSL context to be unverified when insecure is True"
    finally:
        if original_context:
            ssl._create_default_https_context = original_context


if __name__ == "__main__":
    test("default SSL verification", test_default_ssl_verification)
    test("insecure SSL context", test_insecure_context)

    print("")
    print("Passed: %d, Failed: %d" % (passed, failed))
    if failed > 0:
        exit(1)
