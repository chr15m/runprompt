# runprompt

Run LLM [.prompt](https://google.github.io/dotprompt/) files from your shell with a single-file Python script.

[Dotprompt](https://google.github.io/dotprompt/) is an prompt template format for LLMs where a `.prompt` file contains the prompt and metadata (model, schema, config) in a single file. You can use it to run LLM prompts and get structured responses right in your shell.

[Quick start](#quick-start) | [Examples](#examples) | [Tools](#tools) | [Template syntax](#template-syntax) | [Configuration](#configuration) | [Providers](#providers) | [Caching](#caching) | [Spec compliance](#spec-compliance)

## Quick start

```bash
curl -O https://raw.githubusercontent.com/chr15m/runprompt/main/runprompt
chmod +x runprompt
```

Create `hello.prompt`:

```yaml
---
model: anthropic/claude-sonnet-4-20250514
---
Say hello to {{name}}!
```

Run it:

```bash
export ANTHROPIC_API_KEY="your-key"
./runprompt hello.prompt '{"name": "World"}'
# alternatively pass data via STDIN.
echo '{"name": "World"}' | ./runprompt hello.prompt
```

(You can get an Anthropic key from here: <https://console.anthropic.com/settings/keys> see below for other keys.)

## Examples

In addition to the following, see the [tests folder](tests/) for more example `.prompt` files.

### Basic prompt with stdin

```yaml
---
model: anthropic/claude-sonnet-4-20250514
---
Summarize this text: {{STDIN}}
```

```bash
cat article.txt | ./runprompt summarize.prompt
```

The special `{{STDIN}}` variable always contains the raw stdin as a string. Both `{{STDIN}}` and `{{ARGS}}` are always available; if input is JSON it's also parsed into individual variables.

### Command line arguments

Pass arguments directly on the command line:

```yaml
---
model: anthropic/claude-sonnet-4-20250514
---
Process this: {{ARGS}}
```

```bash
./runprompt process.prompt Hello world, please summarize this text.
```

The special `{{ARGS}}` variable contains all arguments after the prompt file, joined with spaces. The `{{INPUT}}` variable contains STDIN if provided, otherwise ARGS.

### Structured JSON output

Extract structured data using an output schema:

```yaml
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
---
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

Use dot notation for nested values (e.g. `--output.format`). Pass template variables via stdin or as JSON argument:

```bash
echo '{"name": "Alice"}' | ./runprompt hello.prompt
./runprompt hello.prompt '{"name": "Alice"}'
```

See `--help` for all options.

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

```yaml
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
3. Additional paths via `--tool-path` or config file
4. Default config tool directories (if they exist):
   - `./.runprompt/tools`
   - `$XDG_CONFIG_HOME/runprompt/tools` (default: `~/.config/runprompt/tools`)
   - `~/.runprompt/tools`

```bash
./runprompt --tool-path ./my_tools --tool-path /shared/tools prompt.prompt
```

All paths are searched in addition to any `tool_path` entries in config files.

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

### Builtin tools

Runprompt includes builtin tools that can be used without creating external Python files:

```yaml
---
model: anthropic/claude-sonnet-4-20250514
tools:
  - builtin.fetch_clean
---
Please summarize this page: {{ARGS}}
```

Available builtin tools:

| Tool | Description |
|------|-------------|
| `calculator` | Safely evaluate mathematical expressions (arithmetic, trig, log, etc.) |
| `fetch_clean` | Fetch a URL and return a lightweight version of the page for LLM consumption |
| `datetime` | Return current date and time in ISO format (YYYY-MM-DDTHH:MM:SS) |
| `write_file('path')` | Write content to a specific file (parameterized) |

The `calculator`, `datetime`, and `fetch_clean` tools are marked as safe (auto-approved with `--safe-yes`). The `write_file` tool requires confirmation since it modifies the filesystem.

### Parameterized tools

Some builtin tools are "factories" that take arguments to create a specialized tool:

```yaml
---
model: anthropic/claude-sonnet-4-20250514
tools:
  - builtin.write_file('output.txt')
---
Write a haiku about coding to the file.
```

The `write_file('output.txt')` creates a tool that can only write to `output.txt`. The LLM provides the content, but cannot choose the path - this is a security feature that limits what files the LLM can modify.

Use `builtin.*` to import all builtin tools, or `builtin.tool_name` for a specific one.

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

Configuration values can be set from config file, env var or command line flag, with flags overriding env vars which override config file settings.

1. **Config files** (lowest priority, loaded in order):
   - `~/.runprompt/config.yml`
   - `$XDG_CONFIG_HOME/runprompt/config.yml` (default: `~/.config/runprompt/config.yml`)
   - `./.runprompt/config.yml` (project-local)
2. **Environment variables** (`RUNPROMPT_*` prefix)
3. **CLI flags** (highest priority)

### Config options

| Option | Config file | Environment variable | CLI flag |
|--------|-------------|---------------------|----------|
| Model | `model: openai/gpt-4o` | `RUNPROMPT_MODEL` | `--model` |
| Default model | `default_model: openai/gpt-4o` | `RUNPROMPT_DEFAULT_MODEL` | `--default-model` |
| Base URL | `base_url: http://...` | `RUNPROMPT_BASE_URL` | `--base-url` |
| Tool paths | `tool_path: [./tools]` | `RUNPROMPT_TOOL_PATH` | `--tool-path` |
| Cache | `cache: true` | `RUNPROMPT_CACHE=1` | `--cache` |
| Cache dir | `cache_dir: /path` | `RUNPROMPT_CACHE_DIR` | `--cache-dir` |
| Safe yes | `safe_yes: true` | `RUNPROMPT_SAFE_YES=1` | `--safe-yes` |
| Verbose | `verbose: true` | `RUNPROMPT_VERBOSE=1` | `--verbose` |

### API keys

API keys can be set via config file, `RUNPROMPT_*` env var, or native env var:

| Provider | Config file | RUNPROMPT env var | Native env var |
|----------|-------------|-------------------|----------------|
| Anthropic | `anthropic_api_key: sk-...` | `RUNPROMPT_ANTHROPIC_API_KEY` | `ANTHROPIC_API_KEY` |
| OpenAI | `openai_api_key: sk-...` | `RUNPROMPT_OPENAI_API_KEY` | `OPENAI_API_KEY` |
| Google AI | `google_api_key: ...` | `RUNPROMPT_GOOGLE_API_KEY` | `GOOGLE_API_KEY` |
| OpenRouter | `openrouter_api_key: ...` | `RUNPROMPT_OPENROUTER_API_KEY` | `OPENROUTER_API_KEY` |

Priority for API keys: config file, env var, then flag as fallback.

### Config file example

```yaml
# ./.runprompt/config.yml, ~/.config/runprompt/config.yml, or ~/.runprompt/config.yml
model: openai/gpt-4o
default_model: anthropic/claude-sonnet-4-20250514  # fallback if model not set anywhere
cache: true
safe_yes: true
tool_path:
  - ./tools
  - /shared/tools
openai_api_key: sk-...
```

The `default_model` is used as a fallback when no model is specified in the prompt file, config, environment, or CLI. This lets you set a preferred model that's used only when nothing else specifies one.

### Custom endpoint (Ollama, etc.)

Use `base_url` to point at any OpenAI-compatible endpoint:

```bash
# Via config file
# base_url: http://localhost:11434/v1

# Via environment variable
export RUNPROMPT_BASE_URL="http://localhost:11434/v1"

# Via CLI flag
./runprompt --base-url http://localhost:11434/v1 hello.prompt

# Legacy env vars also work (checked in this order)
export OPENAI_BASE_URL="http://localhost:11434/v1"
export OPENAI_API_BASE="http://localhost:11434/v1"  # OpenAI SDK v0.x style
export BASE_URL="http://localhost:11434/v1"
```

When a custom base URL is set, the provider prefix in the model string is ignored and the OpenAI-compatible API format is used.

### Verbose mode

Use `-v` or set `verbose: true` to see request/response details:

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
