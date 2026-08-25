# Architecture

## Upstream relationship

`CookSleep/gpt_image_playground` is a TypeScript/React application. It calls Images, Responses, fal.ai, and custom providers directly from its TypeScript provider modules. It does not contain or depend on the Minis skill `gpt-image-tool`.

## Minis packaging

`gpt-image-playground` is the Minis skill layer. It provides CLI, REST/OpenAPI, Agent, Web, Profile, batch jobs, history, SQLite gallery, backups, and security controls.

The image request executor is vendored at:

```text
scripts/generate.py
```

This file originated from the separately installed Minis skill `gpt-image-tool`, but is now included in this skill so `gpt-image-playground` is self-contained. Older installations without the vendored file may temporarily fall back to:

```text
/var/minis/skills/gpt-image-tool/scripts/generate.py
```

The external skill is optional after installation and can be disabled independently.

## Portable runtime contract

The default runtime requires Python 3.9+ and no third-party packages. The Web
client is static HTML/CSS/JavaScript and has no build command. Agents should
discover entrypoints and contracts with `python3 scripts/skill.py manifest`.
`requests` remains an optional dependency only for declarative custom Provider
manifests; it is not required for Images, Responses, fal.ai, Agent, REST, or Web.

All Provider image downloads pass through `scripts/security.py`. This boundary
rejects non-public network targets and unsafe redirects, enforces response size
and media-type limits, and centralizes artifact redaction.

`scripts/task_schema.py` owns the versioned task boundary shared by REST and
agent-facing entrypoints. SQLite runs in WAL mode with a busy timeout and a
schema version record. Persisted queued/running jobs become retryable
`interrupted` jobs after restart; they are never resubmitted automatically.

## Model selection

A Profile can specify a model such as `gpt-5.6-sol`. Explicit CLI/task model selection wins over Profile `omit_model`. `omit_model` is only for providers that require the model field to be absent. Specifying both explicitly is rejected.

## Provider registry

The orchestration layer resolves a task through `scripts/provider_base.py`:

```text
Task
  -> ProviderRegistry.resolve()
  -> ProviderContext
  -> Images / Responses / fal / Custom adapter
  -> unified JSON result
```

The first migration keeps existing executors behind `ScriptProvider` so the CLI, REST, batch, and Agent contracts remain stable. The registry is the replacement boundary for the old direct script-path routing. Future provider clients can implement `Provider.run()` without changing task orchestration.

Provider selection:

```text
api_mode=responses -> Responses
provider=fal       -> fal
custom provider    -> Custom
otherwise          -> Images
```
