#!/usr/bin/env python3
import sys
import os
import importlib.util
import importlib.machinery

# Import from runprompt by path (no .py extension)
runprompt_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "runprompt"
)
loader = importlib.machinery.SourceFileLoader("runprompt", runprompt_path)
spec = importlib.util.spec_from_loader("runprompt", loader)
runprompt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runprompt)
render_template = runprompt.render_template

passed = 0
failed = 0


def test(name, template, variables, expected):
    global passed, failed
    result = render_template(template, variables)
    if result == expected:
        print("✅ %s" % name)
        passed += 1
        return True
    else:
        print("❌ %s" % name)
        print("   Expected: %r" % expected)
        print("   Got:      %r" % result)
        failed += 1
        return False


def test_basic_interpolation():
    print("\n--- Basic variable interpolation ---")
    test("simple variable", "Hello {{name}}!", {"name": "World"}, "Hello World!")
    test("multiple variables", "{{a}} and {{b}}", {"a": "X", "b": "Y"}, "X and Y")
    test("missing variable", "Hello {{name}}!", {}, "Hello !")
    test("variable with spaces", "{{ name }}", {"name": "World"}, "World")
    test("number variable", "Count: {{n}}", {"n": 42}, "Count: 42")
    test("empty template", "", {"name": "World"}, "")
    test("no variables", "Hello World!", {"name": "Test"}, "Hello World!")


def test_dot_notation():
    print("\n--- Dot notation ---")
    test("dot notation", "{{person.name}}", {"person": {"name": "Alice"}}, "Alice")
    test("deep dot notation", "{{a.b.c}}", {"a": {"b": {"c": "deep"}}}, "deep")


def test_sections():
    print("\n--- Sections ---")
    test("section truthy", "{{#show}}yes{{/show}}", {"show": True}, "yes")
    test("section falsy", "{{#show}}yes{{/show}}", {"show": False}, "")
    test("section missing", "{{#show}}yes{{/show}}", {}, "")
    test("section with string", "{{#name}}Hello {{name}}{{/name}}", {"name": "World"}, "Hello World")
    test("section empty string", "{{#name}}yes{{/name}}", {"name": ""}, "")


def test_section_lists():
    print("\n--- Section lists ---")
    test("section list", "{{#items}}{{.}}{{/items}}", {"items": ["a", "b", "c"]}, "abc")
    test("section list objects", "{{#people}}{{name}} {{/people}}", 
         {"people": [{"name": "Alice"}, {"name": "Bob"}]}, "Alice Bob ")
    test("section empty list", "{{#items}}x{{/items}}", {"items": []}, "")


def test_inverted_sections():
    print("\n--- Inverted sections ---")
    test("inverted truthy", "{{^show}}yes{{/show}}", {"show": True}, "")
    test("inverted falsy", "{{^show}}yes{{/show}}", {"show": False}, "yes")
    test("inverted missing", "{{^show}}yes{{/show}}", {}, "yes")
    test("inverted empty list", "{{^items}}none{{/items}}", {"items": []}, "none")
    test("inverted non-empty list", "{{^items}}none{{/items}}", {"items": [1]}, "")


def test_combined():
    print("\n--- Combined ---")
    test("section and inverted", "{{#items}}have{{/items}}{{^items}}none{{/items}}", 
         {"items": []}, "none")
    test("section and inverted with items", "{{#items}}have{{/items}}{{^items}}none{{/items}}", 
         {"items": [1]}, "have")


def main():
    test_basic_interpolation()
    test_dot_notation()
    test_sections()
    test_section_lists()
    test_inverted_sections()
    test_combined()

    print("\n" + "=" * 40)
    print("Passed: %d, Failed: %d" % (passed, failed))
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
