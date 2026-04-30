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
    """Default urlopen calls should not override SSL verification."""
    module = load_runprompt()
    reset_config(module)
    captured = {}
    original_urlopen = urllib.request.urlopen

    def fake_urlopen(req, **kwargs):
        captured.update(kwargs)
        return DummyResponse()

    try:
        urllib.request.urlopen = fake_urlopen
        module.open_url(urllib.request.Request("https://example.test"), timeout=5)
    finally:
        urllib.request.urlopen = original_urlopen

    assert captured.get("timeout") == 5, "Expected timeout to be passed through"
    assert "context" not in captured, "Did not expect SSL context by default"


def test_insecure_context():
    """insecure should pass an unverified SSL context."""
    module = load_runprompt()
    reset_config(module, {"insecure": True})
    captured = []
    original_urlopen = urllib.request.urlopen

    def fake_urlopen(req, **kwargs):
        captured.append(kwargs)
        return DummyResponse()

    try:
        urllib.request.urlopen = fake_urlopen
        module.open_url(urllib.request.Request("https://example.test"), timeout=5)
        module.open_url(urllib.request.Request("https://example.test"), timeout=10)
    finally:
        urllib.request.urlopen = original_urlopen

    context = captured[0].get("context")
    assert isinstance(context, ssl.SSLContext), "Expected SSL context"
    assert context.verify_mode == ssl.CERT_NONE, "Expected certificate verification disabled"
    assert context.check_hostname is False, "Expected hostname verification disabled"
    assert captured[1].get("context") is context, "Expected SSL context to be reused"


if __name__ == "__main__":
    test("default SSL verification", test_default_ssl_verification)
    test("insecure SSL context", test_insecure_context)

    print("")
    print("Passed: %d, Failed: %d" % (passed, failed))
    if failed > 0:
        exit(1)
