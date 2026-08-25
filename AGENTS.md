# Agent entry guide

Use this repository without a frontend build step. Do not run npm, Node.js,
Vite, React, Tailwind, or another bundler: `web/index.html` is the shipped Web
application and is served directly by the Python API.

Start by running:

```sh
python3 scripts/skill.py manifest
python3 scripts/skill.py check
python3 scripts/skill.py doctor
```

Read JSON from stdout and use the process exit code as the success signal.
Before a real image request, run the same command with `--dry-run`. Do not make
a paid request, submit multiple/high-quality images, bind a public interface,
or overwrite user files without explicit authorization.

Core generation, Responses, fal.ai, REST, Agent, and Web paths require only
Python 3.9+ standard-library modules. The `requests` package is optional and is
needed only by declarative custom Providers.

Portable entrypoints:

- Generate or edit: `python3 scripts/skill.py generate ...`
- Agent orchestration: `python3 scripts/skill.py agent ...`
- Local Web/API: `python3 scripts/skill.py serve --host 127.0.0.1 --port 8765`

Never store API keys in task JSON, prompts, URLs, logs, or repository files.
