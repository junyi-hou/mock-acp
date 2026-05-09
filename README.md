# Mock-ACP

A mock ACP server that returns deterministic responses to all ACP protocol requests. Useful for testing ACP clients without a real agent.

## How it works

Responses are sourced from two places:

- **`vendor/acp-sdk/tests/golden/`** — the [ACP Python SDK](https://github.com/agentclientprotocol/python-sdk)'s canonical JSON fixtures, used verbatim. These are spec-correct by definition.
- **`fixtures/`** — hand-crafted fixtures for message types not covered by the SDK's golden set.

The server runs over stdio and is launched as a subprocess by the client, matching the standard ACP transport model.

## Running

```bash
python src/main.py
```

## Request → Response reference

### Client → Agent requests

| Method | Response |
|---|---|
| `initialize` | Golden `initialize_response.json` (protocol v1, all capabilities) |
| `session/new` | Golden `new_session_response.json` with a fresh random `sessionId` |
| `session/fork` | Fresh random `sessionId` |
| `session/resume` | Empty response body |
| `session/list` | `{ "sessions": [] }` |
| `session/load` | `null` |
| `session/close` | `null` |
| `session/set_mode` | `null` |
| `session/set_model` | `null` |
| `session/set_config_option` | `null` |
| `authenticate` | `null` |
| `session/cancel` | *(notification, no response)* |
| `session/prompt` | `{ "stopReason": "end_turn" }` + optional scenario updates (see below) |

### Agent → Client requests (triggered by prompt scenarios)

| Scenario | Method | Fixture |
|---|---|---|
| `test request_permission` | `session/request_permission` | Golden `request_permission_request.json` |
| `test fs_read` | `fs/read_text_file` | Golden `fs_read_text_file_request.json` |
| `test fs_write` | `fs/write_text_file` | Golden `fs_write_text_file_request.json` |

---

## Session update scenarios

Send a prompt with text `"test <scenario>"` to trigger `session/update` notifications before the response. Use `"test all"` to fire every scenario in sequence.

### `session/update` notifications (golden fixtures)

| Prompt | Type | Fixture |
|---|---|---|
| `test agent_message` | `AgentMessageChunk` | `session_update_agent_message_chunk.json` |
| `test thought` | `AgentThoughtChunk` | `session_update_agent_thought_chunk.json` |
| `test plan` | `AgentPlanUpdate` | `session_update_plan.json` |
| `test tool_call` | `ToolCallStart` → `ToolCallProgress` × 2 | `session_update_tool_call.json`, `…_update_content.json`, `…_update_more_fields.json` |
| `test tool_call_read` | `ToolCallStart` (read) | `session_update_tool_call_read.json` |
| `test tool_call_edit` | `ToolCallStart` (edit) | `session_update_tool_call_edit.json` |
| `test tool_call_locations` | `ToolCallStart` (locations + raw input) | `session_update_tool_call_locations_rawinput.json` |
| `test config_option` | `ConfigOptionUpdate` | `session_update_config_option_update.json` |
| `test user_message` | `UserMessageChunk` | `session_update_user_message_chunk.json` |

### `session/update` notifications (extra fixtures)

| Prompt | Type | Fixture |
|---|---|---|
| `test tool_call_diff` | `ToolCallProgress` (diff content) | `fixtures/session_update_tool_call_update_diff_content.json` |
| `test tool_call_diff_no_old` | `ToolCallProgress` (diff, new only) | `fixtures/session_update_tool_call_update_diff_no_old_content.json` |
| `test tool_call_terminal` | `ToolCallProgress` (terminal ref) | `fixtures/session_update_tool_call_update_terminal_content.json` |
| `test available_commands` | `AvailableCommandsUpdate` | `fixtures/session_update_available_commands.json` |
| `test current_mode` | `CurrentModeUpdate` | `fixtures/session_update_current_mode.json` |
| `test session_info` | `SessionInfoUpdate` | `fixtures/session_update_session_info.json` |
| `test usage` | `UsageUpdate` | `fixtures/session_update_usage.json` |
