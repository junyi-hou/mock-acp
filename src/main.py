import asyncio
import copy
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from acp import run_agent
from acp.exceptions import RequestError
from acp.interfaces import Client
from acp.schema import (
    PermissionOption,
    ToolCallUpdate,
    AuthenticateResponse,
    CloseSessionResponse,
    ForkSessionResponse,
    LoadSessionResponse,
    ResumeSessionResponse,
    SetSessionConfigOptionResponse,
    SetSessionModelResponse,
    SetSessionModeResponse,
    AgentMessageChunk,
    AgentPlanUpdate,
    AgentThoughtChunk,
    AudioContentBlock,
    AvailableCommandsUpdate,
    ClientCapabilities,
    ConfigOptionUpdate,
    CurrentModeUpdate,
    EmbeddedResourceContentBlock,
    HttpMcpServer,
    ImageContentBlock,
    Implementation,
    InitializeResponse,
    ListSessionsResponse,
    McpServerStdio,
    NewSessionResponse,
    PromptResponse,
    ResourceContentBlock,
    SessionInfoUpdate,
    SseMcpServer,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
    UsageUpdate,
    UserMessageChunk,
)

GOLDEN = Path(__file__).parent.parent / "vendor" / "acp-sdk" / "tests" / "golden"
FIXTURES = Path(__file__).parent.parent / "fixtures"


# Each scenario is an ordered list of callables returning a session update object.
SCENARIOS: dict[str, list] = {
    "agent_message": [
        lambda: AgentMessageChunk.model_validate(
            _load_golden("session_update_agent_message_chunk")
        )
    ],
    "thought": [
        lambda: AgentThoughtChunk.model_validate(
            _load_golden("session_update_agent_thought_chunk")
        )
    ],
    "plan": [
        lambda: AgentPlanUpdate.model_validate(_load_golden("session_update_plan")),
        lambda: AgentPlanUpdate.model_validate(
            _complete_plan(_load_golden("session_update_plan"))
        ),
    ],
    "tool_call": [
        lambda: ToolCallStart.model_validate(_load_golden("session_update_tool_call")),
        lambda: ToolCallProgress.model_validate(
            _load_golden("session_update_tool_call_update_content")
        ),
        lambda: ToolCallProgress.model_validate(
            _complete_tool_call(
                _load_golden("session_update_tool_call"), "File read successfully."
            )
        ),
    ],
    "tool_call_read": [
        lambda: ToolCallStart.model_validate(
            _load_golden("session_update_tool_call_read")
        ),
        lambda: ToolCallProgress.model_validate(
            _complete_tool_call(
                _load_golden("session_update_tool_call_read"), "File read successfully."
            )
        ),
    ],
    "tool_call_edit": [
        lambda: ToolCallStart.model_validate(
            _load_golden("session_update_tool_call_edit")
        ),
        lambda: ToolCallProgress.model_validate(
            _complete_tool_call(
                _load_golden("session_update_tool_call_edit"), "Edit applied successfully."
            )
        ),
    ],
    "tool_call_locations": [
        lambda: ToolCallStart.model_validate(
            _load_golden("session_update_tool_call_locations_rawinput")
        ),
        lambda: ToolCallProgress.model_validate(
            _complete_tool_call(
                _load_golden("session_update_tool_call_locations_rawinput"),
                "File tracked successfully.",
            )
        ),
    ],
    "tool_call_diff": [
        lambda: ToolCallProgress.model_validate(
            _load_extra("session_update_tool_call_update_diff_content")
        ),
        lambda: ToolCallProgress.model_validate(
            _complete_tool_call(
                _load_extra("session_update_tool_call_update_diff_content"),
                "Edit with diff applied successfully.",
            )
        ),
    ],
    "tool_call_diff_no_old": [
        lambda: ToolCallProgress.model_validate(
            _load_extra("session_update_tool_call_update_diff_no_old_content")
        ),
        lambda: ToolCallProgress.model_validate(
            _complete_tool_call(
                _load_extra("session_update_tool_call_update_diff_no_old_content"),
                "New file created successfully.",
            )
        ),
    ],
    "tool_call_terminal": [
        lambda: ToolCallProgress.model_validate(
            _load_extra("session_update_tool_call_update_terminal_content")
        ),
        lambda: ToolCallProgress.model_validate(
            _complete_tool_call(
                _load_extra("session_update_tool_call_update_terminal_content"),
                "Terminal command completed.\n$ npm install\nadded 42 packages in 2s",
            )
        ),
    ],
    "config_option": [
        lambda: ConfigOptionUpdate.model_validate(
            _load_golden("session_update_config_option_update")
        )
    ],
    "user_message": [
        lambda: UserMessageChunk.model_validate(
            _load_golden("session_update_user_message_chunk")
        )
    ],
    "available_commands": [
        lambda: AvailableCommandsUpdate.model_validate(
            _load_extra("session_update_available_commands")
        )
    ],
    "current_mode": [
        lambda: CurrentModeUpdate.model_validate(
            _load_extra("session_update_current_mode")
        )
    ],
    "session_info": [
        lambda: SessionInfoUpdate.model_validate(
            _load_extra("session_update_session_info")
        )
    ],
    "usage": [lambda: UsageUpdate.model_validate(_load_extra("session_update_usage"))],
}

ALL_SCENARIOS = [step for steps in SCENARIOS.values() for step in steps]


def _load_golden(name: str) -> dict:
    return json.loads((GOLDEN / f"{name}.json").read_text())


def _load_extra(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _extract_text(prompt: list) -> str:
    for block in prompt:
        text = (
            block.get("text")
            if isinstance(block, dict)
            else getattr(block, "text", None)
        )
        if text:
            return text
    return ""


def _complete_tool_call(base: dict, content_text: str) -> dict:
    """Build a completed ToolCallProgress dict from a start or progress fixture."""
    result = {
        "sessionUpdate": "tool_call_update",
        "toolCallId": base["toolCallId"],
        "status": "completed",
        "content": [
            {"type": "content", "content": {"type": "text", "text": content_text}}
        ],
    }
    for field in ("title", "kind", "locations"):
        if field in base:
            result[field] = base[field]
    return result


def _complete_plan(base: dict) -> dict:
    """Deep-copy a plan fixture and mark every entry completed."""
    result = copy.deepcopy(base)
    for entry in result["entries"]:
        entry["status"] = "completed"
    return result


class MockAgent:
    _conn: Client

    def on_connect(self, conn: Client) -> None:
        self._conn = conn

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        return InitializeResponse.model_validate(_load_golden("initialize_response"))

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        **kwargs: Any,
    ) -> NewSessionResponse:
        return NewSessionResponse.model_validate(_load_golden("new_session_response"))

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        pass

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        pass

    async def authenticate(
        self, method_id: str, **kwargs: Any
    ) -> AuthenticateResponse | None:
        return None

    async def load_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        **kwargs: Any,
    ) -> LoadSessionResponse | None:
        return None

    async def close_session(
        self, session_id: str, **kwargs: Any
    ) -> CloseSessionResponse | None:
        return None

    async def set_session_mode(
        self, mode_id: str, session_id: str, **kwargs: Any
    ) -> SetSessionModeResponse | None:
        return None

    async def set_session_model(
        self, model_id: str, session_id: str, **kwargs: Any
    ) -> SetSessionModelResponse | None:
        return None

    async def set_config_option(
        self,
        config_id: str,
        session_id: str,
        value: str | bool,
        **kwargs: Any,
    ) -> SetSessionConfigOptionResponse | None:
        return None

    async def fork_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        **kwargs: Any,
    ) -> ForkSessionResponse:
        return ForkSessionResponse(session_id=uuid4().hex)

    async def resume_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        **kwargs: Any,
    ) -> ResumeSessionResponse:
        return ResumeSessionResponse()

    async def list_sessions(
        self, cursor: str | None = None, cwd: str | None = None, **_kwargs: Any
    ) -> ListSessionsResponse:
        return ListSessionsResponse(sessions=[])

    async def _test_request_permission(self, session_id: str) -> None:
        options = [
            PermissionOption.model_validate(o)
            for o in _load_golden("request_permission_request")["options"]
        ]
        tool_call = ToolCallUpdate(tool_call_id="call_001")
        await self._conn.request_permission(
            options=options, session_id=session_id, tool_call=tool_call
        )

    async def _test_fs_read(self, session_id: str) -> None:
        req = _load_golden("fs_read_text_file_request")
        await self._conn.read_text_file(
            path=req["path"],
            session_id=session_id,
            line=req.get("line"),
            limit=req.get("limit"),
        )

    async def _test_fs_write(self, session_id: str) -> None:
        req = _load_golden("fs_write_text_file_request")
        await self._conn.write_text_file(
            content=req["content"], path=req["path"], session_id=session_id
        )

    async def prompt(
        self,
        prompt: list[
            TextContentBlock
            | ImageContentBlock
            | AudioContentBlock
            | ResourceContentBlock
            | EmbeddedResourceContentBlock
        ],
        session_id: str,
        message_id: str | None = None,
        **_kwargs: Any,
    ) -> PromptResponse:
        text = _extract_text(prompt).strip().lower()

        if text.startswith("test "):
            keyword = text[len("test ") :]
            if keyword == "all":
                for factory in ALL_SCENARIOS:
                    await self._conn.session_update(
                        session_id=session_id, update=factory()
                    )
                    await asyncio.sleep(0.1)
                await self._test_request_permission(session_id)
                await self._test_fs_read(session_id)
                await self._test_fs_write(session_id)
            elif keyword == "request_permission":
                await self._test_request_permission(session_id)
            elif keyword == "fs_read":
                await self._test_fs_read(session_id)
            elif keyword == "fs_write":
                await self._test_fs_write(session_id)
            elif keyword == "error":
                raise RequestError.internal_error(
                    {"details": "Intentionally triggered error for testing."}
                )
            else:
                steps = SCENARIOS.get(keyword, [])
                for factory in steps:
                    await self._conn.session_update(
                        session_id=session_id, update=factory()
                    )
                    await asyncio.sleep(0.1)

        return PromptResponse(stop_reason="end_turn", user_message_id=message_id)


async def main() -> None:
    await run_agent(MockAgent())


if __name__ == "__main__":
    asyncio.run(main())
