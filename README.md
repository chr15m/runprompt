# runprompt

A single-file Python script for running [Dotprompt](https://google.github.io/dotprompt/) files.

[Quick start](#quick-start) | [dotprompt](#what-is-dotprompt) | [Examples](#examples) | [Configuration](#configuration) | [Providers](#providers) | [Spec compliance](#spec-compliance)

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

## What is Dotprompt?

[Dotprompt](https://google.github.io/dotprompt/) is an executable prompt template format for GenAI. A `.prompt` file contains both the prompt template and metadata (model, schema, config) in a single file.

`runprompt` is a minimal, single-file Python implementation with no dependencies.

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

### CLI overrides

Override any frontmatter value from the command line:

```bash
./runprompt --model anthropic/claude-haiku-4-20250514 hello.prompt
./runprompt --name "Alice" hello.prompt
```

## Template syntax

Templates use [Handlebars syntax](https://google.github.io/dotprompt/reference/template/). Supported features:

- Variable interpolation: `{{variableName}}`, `{{object.property}}`
- Comments: `{{! this is a comment }}`
- Iteration: `{{#each items}}...{{/each}}` with `@index`, `@first`, `@last`, `@key`
- Sections: `{{#key}}...{{/key}}` (renders if truthy)
- Inverted sections: `{{^key}}...{{/key}}` (renders if falsy)

## Configuration

### Environment variables

Set API keys for your providers:

```bash
export ANTHROPIC_API_KEY="..."  # https://console.anthropic.com/settings/keys
export OPENAI_API_KEY="..."     # https://platform.openai.com/api-keys
export GOOGLE_API_KEY="..."     # https://aistudio.google.com/app/apikey
export OPENROUTER_API_KEY="..." # https://openrouter.ai/settings/keys
```

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

## Spec compliance

This is a minimal implementation of the [Dotprompt specification](https://google.github.io/dotprompt/). Not yet supported:

- Multi-message prompts (`{{role}}`, `{{history}}`)
- Conditionals (`{{#if}}`, `{{#unless}}`, `{{else}}`)
- Helpers (`{{json}}`, `{{media}}`, `{{section}}`)
- Model config (`temperature`, `maxOutputTokens`, etc.)
- Partials (`{{>partialName}}`)
- Nested Picoschema (objects, arrays of objects, enums)

See [TODO.md](TODO.md) for the full roadmap.
