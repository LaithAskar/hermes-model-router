# Hermes Model Router

**Cost-aware, explainable task routing for [Hermes Agent](https://github.com/NousResearch/hermes-agent).**

This project chooses a model/provider based on task fit, quality, speed, and an optional cost budget. It is provider-neutral: the included profiles are examples, not hard-coded requirements.

## Why this exists

A single “best model” is usually wasteful. Frontier reasoning is valuable for difficult coding and high-stakes review, while fast inexpensive models are better for routine transformations. Hermes already supports model configuration, auxiliary assignments, and failure fallbacks; this project adds a small routing layer for **task-fit selection**.

## Design principles

- **Explicit beats magical:** callers can pass `--kind coding` or use the conservative classifier.
- **Explainable:** every decision returns task, model, confidence, and reason.
- **Cost-aware:** an optional budget influences ranking; quality is never silently assumed free.
- **Provider-neutral:** model profiles are configuration data and can be replaced for any Hermes setup.
- **Fail safe:** low-confidence requests become `general`; no LLM call is required to classify.
- **Privacy first:** task text stays local in this library. Do not send secrets to a routing service.

## Quick start

```bash
python3 -m hermes_router.cli "Fix the authentication bug and add tests"
python3 -m hermes_router.cli "Research current papers and compare sources" --kind research
python3 -m hermes_router.cli "Summarize these notes" --budget 0.50

# Ask before accepting a proposed switch; blank/anything other than yes denies.
python3 -m hermes_router.cli \
  "Fix the authentication bug" \
  --ask \
  --current-provider nous \
  --current-model google/gemini-3.7-flash
```

The output is JSON containing the selected provider and model. The repository now also includes a native Hermes plugin and an optional Hermes Desktop pane.

With `--ask`, the router presents the proposed destination and defaults to **deny**. The MVP does not edit Hermes configuration, restart the gateway, or switch a live session. An integration must perform that side effect only after receiving `approved: true`.

The first execution adapter is intentionally conservative: after approval it starts a **new bounded `hermes chat` process** with an argv list (`shell=False`). It does not rewrite `~/.hermes/config.yaml` and does not hot-swap an existing conversation. Native live-session switching is available as a separate Phase 2 adapter using Hermes' authenticated TUI gateway protocol, with the same fail-closed approval boundary.

## Native session switching

The library also provides a Phase 2 adapter for an **already-authorized Hermes TUI gateway connection**. The caller owns endpoint discovery and authentication; this project does not read dashboard tokens, OAuth credentials, `.env`, or private Hermes configuration.

The session switch contract is deliberately fail-closed:

1. Bind approval to the exact route, session ID, current provider/model, and `session` scope.
2. Re-read `session.status` immediately before switching.
3. Refuse inactive, busy, or stale sessions.
4. Invoke Hermes' native session-only command through `slash.exec`:
   ```text
   /model <model> --provider <provider> --session
   ```
5. Re-read `session.status` and verify the actual active provider/model.

The adapter never adds `--global`, never writes Hermes configuration, never retries a failed mutation automatically, and surfaces the prompt-cache reset as a user-visible approval consequence. See `hermes_router.session_switch` and `hermes_router.tui_gateway`.

## Hermes plugin

The native plugin exposes three proposal-only surfaces:

- Tool: `route_model`
- Slash command: `/route [--kind KIND] [--budget COST] -- <task>`
- CLI command: `hermes model-router [--kind KIND] [--budget COST] <task>`

Every surface classifies locally and returns an explainable route. The native plugin itself is deliberately side-effect free: it never switches a session, submits the task, reads credentials, or changes global configuration.

Validate a checkout with Hermes' real plugin loader:

```bash
hermes plugins doctor . --ci
```

Install without enabling:

```bash
hermes plugins install LaithAskar/hermes-model-router --no-enable
```

Then explicitly enable it when ready:

```bash
hermes plugins enable hermes-model-router
```

Plugin installation/enabling changes the local Hermes plugin configuration and may require a new Hermes session. Review the source and command before doing so.

## Optional Hermes Desktop pane

`desktop/plugin.js` adds a **Model Router** pane with a two-step flow:

1. **Propose route** — reads the active session status and asks the native `/route` command for a local proposal.
2. **Approve and switch** — revalidates the exact session/provider/model snapshot, invokes only `/model <model> --provider <provider> --session`, then verifies the new active route.

The pane is disabled by default. It fails closed if the session is busy or stale, never uses `--global`, never submits the task automatically, and leaves Hermes' native fallback chain unchanged. It requires the native plugin to be enabled first.

The desktop file is shipped in Hermes' unified-package layout, so a native plugin installation places it under `~/.hermes/plugins/hermes-model-router/desktop/plugin.js` where Hermes Desktop can discover it. It remains disabled by default until the user enables it in **Settings → Plugins**.

> The plugin does not intercept every prompt or silently route it. Automatic interception would weaken the exact, user-visible approval boundary. Routing remains an explicit propose → approve → verified session switch.

## Recommended architecture

```text
User request
    -> local classifier or explicit task lane
    -> profile scorer: fit + quality + speed + cost budget
    -> RouteDecision
    -> Hermes session/model selection
    -> optional independent review for high-stakes work
```

The router should not mutate `~/.hermes/config.yaml` on every message. Prefer a Hermes plugin, wrapper, or lane-specific invocation so active sessions do not unexpectedly lose prompt-cache continuity. Model fallback remains Hermes' job.

## Current example profiles

These are the profiles tested against the author's setup and must be customized by users:

- Coding: OpenAI Codex / `gpt-5.6-sol`
- Research: Nous / `google/gemini-3.7-flash`
- Daily: Nous / `deepseek/deepseek-v4-flash-0731`
- Deeper review: Nous / `deepseek/deepseek-v4-pro-20260813`
- Backup: Kimi / `kimi-k3`

Model IDs, availability, pricing, and provider access change. Do not treat these examples as universal defaults.

## Roadmap

- YAML/TOML profile configuration
- Native plugin packaging and a desktop approval pane
- Provider capability discovery and live pricing adapters
- Usage feedback: success rate, latency, and cost per task class
- Privacy-preserving local routing history
- Human confirmation for low-confidence or high-cost switches
- A/B evaluation harness rather than unverified model rankings

## Development

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile hermes_router/*.py
node --check desktop/plugin.js
hermes plugins doctor . --ci
```

## License

MIT

## Status

Public plugin MVP. The native plugin selects and explains routes without side effects; the optional desktop pane can perform an explicitly approved, stale-checked, session-only switch. It never silently intercepts prompts or changes global Hermes configuration.

> Never commit API keys, OAuth tokens, cookies, private Hermes config, or personal data.

## Routing log

When integrating this into an agent, record provider/model, why it was chosen, and only category-level data sent—not raw prompts, credentials, or private files.

The project is not affiliated with or endorsed by Nous Research unless explicitly stated by the maintainers.
