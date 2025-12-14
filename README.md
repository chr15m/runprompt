# runprompt

A single-file Python script for running [Dotprompt](https://google.github.io/dotprompt/) files.

[Dotprompt](https://google.github.io/dotprompt/) is an prompt template format for LLMs where a `.prompt` file contains the prompt and metadata (model, schema, config) in a single file.

[Quick start](#quick-start) | [Examples](#examples) | [Tools](#tools) | [Configuration](#configuration) | [Providers](#providers) | [Caching](#caching) | [Spec compliance](#spec-compliance)

## Quick start

```bash
curl -O https://raw.githubusercontent.com/chr15m/runprompt/main/runprompt
chmod +x runprompt
```

Create `hello.prompt`:

```handlebars
---
model: anthropic/claude-sonnet-4-20250514
---
Say hello to {{name}}!
```

Run it:

```bash
export OPENAI_API_KEY="your-key"
echo '{"name": "World"}' | ./runprompt hello.prompt
```

(You can get an OpenAI key from here: <https://platform.openai.com/api-keys>)

## Examples

In addition to the following, see the [tests folder](tests/) for more example `.prompt` files.

### Basic prompt with stdin

```handlebars
---
model: anthropic/claude-sonnet-4-20250514
---
Summarize this text: {{STDIN}}
```

```bash
cat article.txt | ./runprompt summarize.prompt
```

The special `{{STDIN}}` variable always contains the raw stdin as a string.

### Command line arguments

Pass arguments directly on the command line:

```handlebars
---
model: anthropic/claude-sonnet-4-20250514
---
Process this: {{ARGS}}
```

```bash
./runprompt process.prompt Hello world, please summarize this text.
```

The special `{{ARGS}}` variable contains all arguments after the prompt file, joined with spaces.

### Structured JSON output

Extract structured data using an output schema:

```handlebars
---
model: anthropic/claude-sonnet-4-20250514
input:
  schema:
    text: string
output:
  format: json
  schema:
    name?: string, the person's name
    age?: number, the person's age
    occupation?: string, the person's job
---
Extract info from: {{text}}
```

```bash
echo "John is a 30 year old teacher" | ./runprompt extract.prompt
# {"name": "John", "age": 30, "occupation": "teacher"}
```

Schema uses [Picoschema](https://google.github.io/dotprompt/reference/picoschema/) format. Fields ending with `?` are optional. The format is `field: type, description`.

### Chaining prompts

Pipe structured output between prompts:

```bash
echo "John is 30" | ./runprompt extract.prompt | ./runprompt generate-bio.prompt
```

The JSON output from the first prompt becomes template variables in the second.

### Executable prompt files

Make `.prompt` files directly executable with a shebang:

```handlebars
#!/usr/bin/env runprompt
model: anthropic/claude-sonnet-4-20250514
---
Hello, I'm {{name}}!
```

```bash
chmod +x hello.prompt
echo '{"name": "World"}' | ./hello.prompt
```

Note: `runprompt` must be in your PATH, or use a relative/absolute path in the shebang (e.g. `#!/usr/bin/env ./runprompt`).

### CLI overrides

Override frontmatter values from the command line:

```bash
./runprompt --model anthropic/claude-haiku-4-20250514 hello.prompt
./runprompt --output.format json extract.prompt
```

Note: CLI overrides set frontmatter values (model, config, output format, etc.), not template variables. To pass template variables, use stdin:

```bash
echo '{"name": "Alice"}' | ./runprompt hello.prompt
```

## Tools

Tools allow the LLM to call Python functions during prompt execution. Define tools as Python functions with docstrings, and the LLM can use them to perform actions like reading files, making API calls, or interacting with the system.

### Defining tools

Create a Python file with functions. Any function with a docstring becomes a tool:

```python
# my_tools.py
def get_weather(city: str):
    """Gets the current weather for a city.
    
    Returns the temperature and conditions for the specified location.
    """
    # Your implementation here
    return {"temp": 72, "conditions": "sunny"}

def calculate(expression: str):
    """Evaluates a mathematical expression.
    
    Use this for arithmetic calculations.
    """
    return eval(expression)
```

### Using tools in prompts

Reference tools in the frontmatter using Python import syntax:

```handlebars
---
model: anthropic/claude-sonnet-4-20250514
tools:
  - my_tools.*
---
What's the weather in Tokyo and what's 15% of 847?
```

Tool specifications:

- `module.*` - Import all functions with docstrings from `module.py`
- `module.function_name` - Import a specific function

### Running prompts with tools

When the LLM wants to call a tool, you'll be prompted to confirm:

```
$ ./runprompt weather.prompt

I'll check the weather for you.

Tool call: get_weather
Arguments: {"city": "Tokyo"}

Run this tool? [y/n]: y

The weather in Tokyo is currently 72°F and sunny.
```

### Safe tools

Mark tools as "safe" to allow them to run without confirmation when using `--safe-yes`:

```python
# my_tools.py
def get_weather(city: str):
    """Gets the current weather for a city (read-only operation)."""
    return {"temp": 72, "conditions": "sunny"}

get_weather.safe = True  # Mark as safe

def delete_file(path: str):
    """Deletes a file from the filesystem."""
    os.remove(path)
    return "deleted"

# Not marked as safe - will always prompt for confirmation
```

Run with `--safe-yes` to auto-approve safe tools:

```bash
./runprompt --safe-yes weather.prompt
```

With `--safe-yes`:
- Tools marked with `fn.safe = True` run without prompting
- Tools without the safe attribute still prompt for confirmation

This is useful for automation where you trust certain read-only or low-risk operations but still want confirmation for potentially dangerous actions.

### Tool import paths

Tools are searched for in:

1. The current working directory
2. The directory containing the prompt file
3. Additional paths via `--tool-path`

```bash
./runprompt --tool-path ./my_tools --tool-path /shared/tools prompt.prompt
```

### Type hints

Type hints on function parameters map to JSON Schema types:

| Python | JSON Schema |
|--------|-------------|
| `str`  | `string`    |
| `int`  | `integer`   |
| `float`| `number`    |
| `bool` | `boolean`   |
| `list` | `array`     |
| `dict` | `object`    |

Parameters without type hints default to `string`.

### Error handling

If a tool raises an exception, the error is sent back to the LLM which can decide how to proceed:

```
Tool call: read_file
Arguments: {"path": "missing.txt"}

Run this tool? [y/n]: y
FileNotFoundError: [Errno 2] No such file or directory: 'missing.txt'

I couldn't read that file because it doesn't exist. Would you like me to try a different path?
```

### Underscore prefix

Files or functions starting with `_` are excluded from wildcard imports:

```python
# _helpers.py - this entire file is excluded from wildcard imports
# my_tools.py
def _private_helper():  # excluded from wildcard imports
    """Internal helper function."""
    pass

def public_tool():  # included in wildcard imports
    """A tool available to the LLM."""
    pass
```

Use `_` prefix for helper functions you don't want exposed as tools.

## Template syntax

Templates use a useful subset of [Handlebars/Mustache syntax](https://google.github.io/dotprompt/reference/template/). Supported features:

- Variable interpolation: `{{variableName}}`, `{{object.property}}`
- Comments: `{{! this is a comment }}`
- Conditionals: `{{#if key}}...{{/if}}`, `{{#if key}}...{{else}}...{{/if}}`
- Negated conditionals: `{{#unless key}}...{{/unless}}`, `{{#unless key}}...{{else}}...{{/unless}}`
- Iteration: `{{#each items}}...{{/each}}` with `@index`, `@first`, `@last`, `@key`
- Sections: `{{#key}}...{{/key}}` (renders if truthy)
- Inverted sections: `{{^key}}...{{/key}}` (renders if falsy)

Falsy values: `false`, `0`, `""` (empty string), `[]` (empty list), missing/undefined variables.

## Configuration

### Environment variables

Set API keys for your providers:

```bash
export ANTHROPIC_API_KEY="..."  # https://console.anthropic.com/settings/keys
export OPENAI_API_KEY="..."     # https://platform.openai.com/api-keys
export GOOGLE_API_KEY="..."     # https://aistudio.google.com/app/apikey
export OPENROUTER_API_KEY="..." # https://openrouter.ai/settings/keys
```

### Custom endpoint (Ollama, etc.)

Use `OPENAI_BASE_URL` or `BASE_URL` to point at any OpenAI-compatible endpoint:

```bash
# Use Ollama
export OPENAI_BASE_URL="http://localhost:11434/v1"
./runprompt hello.prompt

# Or via CLI flag
./runprompt --base-url http://localhost:11434/v1 hello.prompt
```

When a custom base URL is set, the provider prefix in the model string is ignored and the OpenAI-compatible API format is used.

### RUNPROMPT_* overrides

Override any frontmatter value via environment variables prefixed with `RUNPROMPT_`:

```bash
export RUNPROMPT_MODEL="anthropic/claude-haiku-4-20250514"
./runprompt hello.prompt
```

This is useful for setting defaults across multiple prompt runs.

### Verbose mode

Use `-v` to see request/response details:

```bash
./runprompt -v hello.prompt
```

## Providers

Models are specified as `provider/model-name`:

| Provider | Model format | API key |
|----------|--------------|---------|
| Anthropic | `anthropic/claude-sonnet-4-20250514` | [Get key](https://console.anthropic.com/settings/keys) |
| OpenAI | `openai/gpt-4o` | [Get key](https://platform.openai.com/api-keys) |
| Google AI | `googleai/gemini-1.5-pro` | [Get key](https://aistudio.google.com/app/apikey) |
| OpenRouter | `openrouter/anthropic/claude-sonnet-4-20250514` | [Get key](https://openrouter.ai/settings/keys) |

[OpenRouter](https://openrouter.ai) provides access to models from many providers (Anthropic, Google, Meta, etc.) through a single API key.

## Caching

Enable response caching to avoid redundant API calls during development:

```bash
# Enable caching with -c or --cache
./runprompt --cache hello.prompt

# Second run with same input uses cached response
./runprompt --cache hello.prompt
```

You can also enable the cache across a whole pipeline with the env var:

```bash
export RUNPROMPT_CACHE=1; echo "..." | ./runprompt a.prompt | ./runprompt b.prompt
```

Cached responses are stored in `~/.cache/runprompt/` (or `$XDG_CACHE_HOME/runprompt/`), based on the inputs applied to the template and frontmatter.

See `--help` for more information.

## Spec compliance

This is a minimal implementation of the [Dotprompt specification](https://google.github.io/dotprompt/). Not yet supported:

- Multi-message prompts (`{{role}}`, `{{history}}`)
- Helpers (`{{json}}`, `{{media}}`, `{{section}}`)
- Model config (`temperature`, `maxOutputTokens`, etc.)
- Partials (`{{>partialName}}`)
- Nested Picoschema (objects, arrays of objects, enums)
