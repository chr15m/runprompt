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


def test_comments():
    print("\n--- Comments ---")
    test("simple comment", "Hello {{! this is a comment }}World", {}, "Hello World")
    test("comment removes entirely", "{{! comment }}", {}, "")
    test("comment with variable", "{{! ignore }}{{name}}", {"name": "Alice"}, "Alice")
    test("multiline comment", "Hello {{! this\nis\nmultiline }}World", {}, "Hello World")
    test("comment between variables", "{{a}}{{! middle }}{{b}}", {"a": "X", "b": "Y"}, "XY")


def test_loop_variables():
    print("\n--- Loop variables (@index, @first, @last) ---")
    test("@index", "{{#items}}{{@index}}{{/items}}", {"items": ["a", "b", "c"]}, "012")
    test("@index with value", "{{#items}}{{@index}}:{{.}} {{/items}}", 
         {"items": ["a", "b", "c"]}, "0:a 1:b 2:c ")
    test("@first", "{{#items}}{{#@first}}first{{/@first}}{{.}}{{/items}}", 
         {"items": ["a", "b", "c"]}, "firstabc")
    test("@last", "{{#items}}{{.}}{{#@last}}!{{/@last}}{{/items}}", 
         {"items": ["a", "b", "c"]}, "abc!")
    test("@index with objects", "{{#people}}{{@index}}:{{name}} {{/people}}", 
         {"people": [{"name": "Alice"}, {"name": "Bob"}]}, "0:Alice 1:Bob ")
    test("@first @last single item", "{{#items}}{{#@first}}F{{/@first}}{{#@last}}L{{/@last}}{{/items}}", 
         {"items": ["x"]}, "FL")


def test_if_conditional():
    print("\n--- {{#if}} conditional ---")
    test("if truthy", "{{#if show}}yes{{/if}}", {"show": True}, "yes")
    test("if falsy false", "{{#if show}}yes{{/if}}", {"show": False}, "")
    test("if falsy empty string", "{{#if show}}yes{{/if}}", {"show": ""}, "")
    test("if falsy zero", "{{#if show}}yes{{/if}}", {"show": 0}, "")
    test("if falsy empty list", "{{#if items}}yes{{/if}}", {"items": []}, "")
    test("if missing", "{{#if show}}yes{{/if}}", {}, "")
    test("if truthy string", "{{#if name}}Hello {{name}}{{/if}}", 
         {"name": "World"}, "Hello World")
    test("if truthy number", "{{#if count}}Count: {{count}}{{/if}}", 
         {"count": 42}, "Count: 42")
    test("if truthy list", "{{#if items}}has items{{/if}}", 
         {"items": [1, 2]}, "has items")
    # if with else
    test("if else truthy", "{{#if show}}yes{{else}}no{{/if}}", 
         {"show": True}, "yes")
    test("if else falsy", "{{#if show}}yes{{else}}no{{/if}}", 
         {"show": False}, "no")
    test("if else empty string", "{{#if name}}Hello {{name}}{{else}}Hello stranger{{/if}}", 
         {"name": ""}, "Hello stranger")
    test("if else missing", "{{#if name}}Hello {{name}}{{else}}Hello stranger{{/if}}", 
         {}, "Hello stranger")
    test("if else with value", "{{#if name}}Hello {{name}}{{else}}Hello stranger{{/if}}", 
         {"name": "Alice"}, "Hello Alice")


def test_unless_conditional():
    print("\n--- {{#unless}} conditional ---")
    test("unless truthy", "{{#unless show}}yes{{/unless}}", {"show": True}, "")
    test("unless falsy", "{{#unless show}}yes{{/unless}}", {"show": False}, "yes")
    test("unless empty string", "{{#unless show}}yes{{/unless}}", {"show": ""}, "yes")
    test("unless missing", "{{#unless show}}yes{{/unless}}", {}, "yes")
    test("unless empty list", "{{#unless items}}no items{{/unless}}", 
         {"items": []}, "no items")
    test("unless non-empty list", "{{#unless items}}no items{{/unless}}", 
         {"items": [1]}, "")
    # unless with else
    test("unless else truthy", "{{#unless show}}no{{else}}yes{{/unless}}", 
         {"show": True}, "yes")
    test("unless else falsy", "{{#unless show}}no{{else}}yes{{/unless}}", 
         {"show": False}, "no")
    test("unless else missing", "{{#unless name}}Anonymous{{else}}{{name}}{{/unless}}", 
         {}, "Anonymous")
    test("unless else with value", "{{#unless name}}Anonymous{{else}}{{name}}{{/unless}}", 
         {"name": "Bob"}, "Bob")


def test_dot_notation_conditionals():
    print("\n--- Dot notation in conditionals ---")
    test("if with dot notation truthy", 
         "{{#if user.active}}active{{/if}}", 
         {"user": {"active": True}}, "active")
    test("if with dot notation falsy", 
         "{{#if user.active}}active{{/if}}", 
         {"user": {"active": False}}, "")
    test("if with dot notation missing", 
         "{{#if user.active}}active{{/if}}", 
         {"user": {}}, "")
    test("if else with dot notation", 
         "{{#if user.name}}Hello {{user.name}}{{else}}Hello guest{{/if}}", 
         {"user": {"name": "Alice"}}, "Hello Alice")
    test("if else with dot notation missing", 
         "{{#if user.name}}Hello {{user.name}}{{else}}Hello guest{{/if}}", 
         {"user": {}}, "Hello guest")
    test("unless with dot notation", 
         "{{#unless user.banned}}welcome{{/unless}}", 
         {"user": {"banned": False}}, "welcome")
    test("deep dot notation in if", 
         "{{#if a.b.c}}deep{{/if}}", 
         {"a": {"b": {"c": True}}}, "deep")


def test_nested_conditionals():
    print("\n--- Nested conditionals ---")
    # Nested if
    test("nested if both true", 
         "{{#if a}}{{#if b}}both{{/if}}{{/if}}", 
         {"a": True, "b": True}, "both")
    test("nested if outer true inner false", 
         "{{#if a}}{{#if b}}both{{else}}only a{{/if}}{{/if}}", 
         {"a": True, "b": False}, "only a")
    test("nested if outer false", 
         "{{#if a}}{{#if b}}both{{/if}}{{else}}none{{/if}}", 
         {"a": False, "b": True}, "none")
    # if inside unless
    test("if inside unless", 
         "{{#unless a}}{{#if b}}b only{{/if}}{{/unless}}", 
         {"a": False, "b": True}, "b only")
    # unless inside if
    test("unless inside if", 
         "{{#if a}}{{#unless b}}a not b{{/unless}}{{/if}}", 
         {"a": True, "b": False}, "a not b")
    # Triple nesting
    test("triple nested", 
         "{{#if a}}{{#if b}}{{#if c}}all{{/if}}{{/if}}{{/if}}", 
         {"a": True, "b": True, "c": True}, "all")
    # Mixed nesting: if with else inside unless
    test("if else inside unless", 
         "{{#unless a}}{{#if b}}yes{{else}}no{{/if}}{{/unless}}", 
         {"a": False, "b": True}, "yes")
    test("if else inside unless falsy", 
         "{{#unless a}}{{#if b}}yes{{else}}no{{/if}}{{/unless}}", 
         {"a": False, "b": False}, "no")
    # Mixed nesting: unless with else inside if
    test("unless else inside if", 
         "{{#if a}}{{#unless b}}not b{{else}}has b{{/unless}}{{/if}}", 
         {"a": True, "b": False}, "not b")
    test("unless else inside if truthy", 
         "{{#if a}}{{#unless b}}not b{{else}}has b{{/unless}}{{/if}}", 
         {"a": True, "b": True}, "has b")


def test_each_helper():
    print("\n--- {{#each}} helper ---")
    # each with list
    test("each list", "{{#each items}}{{.}}{{/each}}", 
         {"items": ["a", "b", "c"]}, "abc")
    test("each list with @index", "{{#each items}}{{@index}}:{{.}} {{/each}}", 
         {"items": ["a", "b", "c"]}, "0:a 1:b 2:c ")
    test("each list objects", "{{#each people}}{{name}} {{/each}}", 
         {"people": [{"name": "Alice"}, {"name": "Bob"}]}, "Alice Bob ")
    test("each empty list", "{{#each items}}x{{/each}}", {"items": []}, "")
    # each with dict
    test("each dict", "{{#each person}}{{@key}}:{{.}} {{/each}}", 
         {"person": {"name": "Alice", "age": 30}}, "name:Alice age:30 ")
    test("each dict @index", "{{#each person}}{{@index}}-{{@key}} {{/each}}", 
         {"person": {"a": 1, "b": 2}}, "0-a 1-b ")
    test("each dict @first @last", 
         "{{#each person}}{{#@first}}[{{/@first}}{{@key}}{{#@last}}]{{/@last}}{{/each}}", 
         {"person": {"a": 1, "b": 2, "c": 3}}, "[abc]")
    test("each dict nested values", "{{#each people}}{{name}}({{age}}) {{/each}}", 
         {"people": {"p1": {"name": "Alice", "age": 30}, "p2": {"name": "Bob", "age": 25}}}, 
         "Alice(30) Bob(25) ")


def main():
    test_basic_interpolation()
    test_dot_notation()
    test_sections()
    test_section_lists()
    test_inverted_sections()
    test_combined()
    test_comments()
    test_loop_variables()
    test_if_conditional()
    test_unless_conditional()
    test_dot_notation_conditionals()
    test_nested_conditionals()
    test_each_helper()

    print("\n" + "=" * 40)
    print("Passed: %d, Failed: %d" % (passed, failed))
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
