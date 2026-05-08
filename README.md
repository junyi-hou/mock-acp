# Mock-ACP

A mock ACP server that returns deterministic responses to all ACP protocol requests. Useful for testing ACP clients without a real agent.

## How it works

Responses are sourced from the [ACP Python SDK](https://github.com/agentclientprotocol/python-sdk)'s golden test fixtures (`vendor/acp-sdk/tests/golden/`). These are the canonical JSON payloads the SDK uses to validate protocol conformance, so they are always spec-correct.

The server runs over stdio and is launched as a subprocess by the client, matching the standard ACP transport model.

## Running

```bash
python src/main.py
```

## Request → Response reference

### `initialize`

Returns the golden `initialize_response.json`:

```json
{
  "protocolVersion": 1,
  "agentCapabilities": {
    "loadSession": true,
    "mcpCapabilities": {},
    "promptCapabilities": { "image": true, "audio": true, "embeddedContext": true },
    "sessionCapabilities": {}
  },
  "authMethods": []
}
```

### `new_session`

Returns the golden `new_session_response.json` with a fresh random `sessionId` per call:

```json
{ "sessionId": "<random uuid hex>" }
```

### `fork_session` / `resume_session`

Returns a new random `sessionId`. `resume_session` returns an empty response body.

### `load_session` / `close_session` / `set_session_mode` / `set_session_model` / `set_config_option` / `authenticate`

All return `null` (optional responses, indicating no-op).

### `list_sessions`

Returns an empty sessions list:

```json
{ "sessions": [] }
```

### `cancel` / `ext_notification`

No-op notifications, no response.

### `ext_method`

Returns `{}`.

### `prompt`

Returns `{ "stopReason": "end_turn" }`. Before returning, the server may emit `session_update` notifications depending on the prompt text (see below).

---

## Session update scenarios

Send a prompt with text `"test <scenario>"` to trigger specific `session_update` notifications. Use `"test all"` to fire all scenarios in sequence.

| Prompt text | Updates sent | Golden fixture(s) |
|---|---|---|
| `test agent_message` | `AgentMessageChunk` | `session_update_agent_message_chunk.json` |
| `test thought` | `AgentThoughtChunk` | `session_update_agent_thought_chunk.json` |
| `test plan` | `AgentPlanUpdate` | `session_update_plan.json` |
| `test tool_call` | `ToolCallStart` → `ToolCallProgress` × 2 | `session_update_tool_call.json`, `session_update_tool_call_update_content.json`, `session_update_tool_call_update_more_fields.json` |
| `test tool_call_read` | `ToolCallStart` (read variant) | `session_update_tool_call_read.json` |
| `test tool_call_edit` | `ToolCallStart` (edit variant) | `session_update_tool_call_edit.json` |
| `test tool_call_locations` | `ToolCallStart` (with locations + raw input) | `session_update_tool_call_locations_rawinput.json` |
| `test config_option` | `ConfigOptionUpdate` | `session_update_config_option_update.json` |
| `test user_message` | `UserMessageChunk` | `session_update_user_message_chunk.json` |
| `test available_commands` | `AvailableCommandsUpdate` (hand-crafted) | — |
| `test current_mode` | `CurrentModeUpdate` (hand-crafted) | — |
| `test session_info` | `SessionInfoUpdate` (hand-crafted) | — |
| `test usage` | `UsageUpdate` (hand-crafted) | — |
| `test all` | All of the above in order | — |

Scenarios without a golden fixture are constructed with minimal hard-coded values since the SDK does not ship golden data for those types.
