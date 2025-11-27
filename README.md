# runprompt

A single-file Python script for running [.prompt files](https://github.com/google/dotprompt).

[Quick start](#quick-start) | [Examples](#examples) | [Configuration](#configuration) | [Providers](#providers)

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
export ANTHROPIC_API_KEY="your-key"
echo '{"name": "World"}' | ./runprompt hello.prompt
```

## Examples

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

Fields ending with `?` are optional. The format is `field: type, description`.

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

## Configuration

### Environment variables

Set API keys for your providers:

```bash
export ANTHROPIC_API_KEY="..."
export OPENAI_API_KEY="..."
export GOOGLE_API_KEY="..."
export OPENROUTER_API_KEY="..."
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

| Provider | Model format | API key env var |
|----------|--------------|-----------------|
| Anthropic | `anthropic/claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` |
| OpenAI | `openai/gpt-4o` | `OPENAI_API_KEY` |
| Google AI | `googleai/gemini-1.5-pro` | `GOOGLE_API_KEY` |
| OpenRouter | `openrouter/anthropic/claude-sonnet-4-20250514` | `OPENROUTER_API_KEY` |

[OpenRouter](https://openrouter.ai) provides access to models from many providers (Anthropic, Google, Meta, etc.) through a single API key.
