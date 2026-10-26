---
type: Plugin Reference
title: Agent
description: 'Drive ChiSurf in plain words: the agent runs the analysis tools of the loaded session, asks when a request is ambiguous, and scripts pipelines over the plugin and core APIs.'
resource: chisurf/plugins/core/agent/
tags: [reference, plugins, agent, tools, system, ai]
anchor: plugin-agent
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-agent)=
# Agent

Drive ChiSurf in plain words: the agent runs the analysis tools of the loaded session, asks when a request is ambiguous, and scripts pipelines over the plugin and core APIs.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `agent` |
| Menu path | Tools → System → **Agent** |
| Categories | Tools, System, AI |
| Version | 1.0.0 |
| Surfaces | emtk |
| State namespace | `agent` |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [The workflow agent — driving ChiSurf in plain words](/concepts/workflow_agent.md)
- **Workflow** — [The AI assistant: operating ChiSurf in plain language](/guides/40_ai_assistant.md)

## Source

- Plugin package: `chisurf/plugins/core/agent/`
- Manifest: {src}`chisurf/plugins/core/agent/manifest.json`
