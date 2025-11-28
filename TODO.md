# Dotprompt Spec Compliance Roadmap

Comparison of `runprompt` against the [Dotprompt specification](https://github.com/google/dotprompt).

## Currently Implemented ✓

### Frontmatter
- [x] YAML frontmatter parsing with `---` delimiters
- [x] `model` - Provider/model specification (`provider/model-name`)
- [x] `output.format` - JSON output format
- [x] `output.schema` - Basic Picoschema (types, descriptions, optional fields)

### Template
- [x] Variable interpolation - `{{variableName}}`
- [x] Dot notation - `{{object.property}}`
- [x] Comments - `{{! comment }}`
- [x] `{{#each}}` - Array/object iteration with `@index`, `@first`, `@last`, `@key`
- [x] Section blocks - `{{#key}}...{{/key}}`
- [x] Inverted sections - `{{^key}}...{{/key}}`

## Priority 1: Core Template Features

### Multi-message prompts
- [ ] `{{role "roleName"}}` - Split template into system/user/model/tool messages
- [ ] `{{history}}` - Insert conversation history
- [ ] Build proper `messages` array for API requests

### Conditionals
- [ ] `{{#if condition}}...{{/if}}`
- [ ] `{{else}}`
- [ ] `{{#unless condition}}...{{/unless}}`

### Helpers
- [ ] `{{json varName}}` - Serialize variable as JSON
- [ ] `{{media url=urlVariable}}` - Insert media content
- [ ] `{{section "sectionName"}}` - Named section positioning

### Escaping
- [ ] `\{{var}}` - Escaped expressions (render literal `{{var}}`)
- [ ] `{{{var}}}` - Triple-brace (currently same as double)

## Priority 2: Model Configuration

### Config passthrough
- [ ] `config.temperature`
- [ ] `config.maxOutputTokens`
- [ ] `config.topK`
- [ ] `config.topP`
- [ ] `config.stopSequences`
- [ ] `config.version` - Model version pinning

## Priority 3: Input Handling

- [ ] `input.default` - Default values for variables
- [ ] `input.schema` - Input validation against schema
- [ ] `@metadata.prompt` - Access frontmatter from template
- [ ] `@metadata.docs` - Access document context
- [ ] `@metadata.messages` - Access message history
- [ ] `@root` - Reference root context

## Priority 4: Extended Picoschema

### Types
- [ ] `integer` - Integer type (currently treated as number)
- [ ] `null` - Null type
- [ ] `any` - Any type (empty schema)

### Complex structures
- [ ] `fieldName(object): ...` - Nested objects
- [ ] `fieldName(array): ...` - Arrays with nested schema
- [ ] `fieldName(enum): [A, B, C]` - Enum values
- [ ] `(*): type` - Wildcard fields

## Priority 5: Advanced Features

### Partials
- [ ] `{{>partialName}}` - Include partial templates
- [ ] `{{>partialName arg=value}}` - Partials with arguments
- [ ] `{{>partialName this}}` - Partials with context

### Tools
- [ ] `tools` - Named tool definitions in frontmatter
- [ ] Tool request/response loop

### Naming
- [ ] `name` - Prompt name (infer from filename)
- [ ] `variant` - Prompt variant (infer from `name.variant.prompt`)

### Metadata
- [ ] `metadata` - Arbitrary metadata object
- [ ] Namespaced extensions - `mycorp.auth` → `ext.mycorp.auth`

## Out of Scope (for now)

- Document context (`context` array)
- Multiple candidates
- Custom helper registration API
- Streaming responses
