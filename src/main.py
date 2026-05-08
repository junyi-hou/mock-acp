import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from acp import run_agent
from acp.interfaces import Client
from acp.schema import (
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
    AvailableCommand,
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


def _available_commands_update() -> AvailableCommandsUpdate:
    return AvailableCommandsUpdate(
        session_update="available_commands_update",
        available_commands=[
            AvailableCommand(
                name="create_plan", description="Create a plan for the current task"
            ),
            AvailableCommand(
                name="research_codebase", description="Research the codebase"
            ),
        ],
    )


def _current_mode_update() -> CurrentModeUpdate:
    return CurrentModeUpdate(
        session_update="current_mode_update", current_mode_id="default"
    )


def _session_info_update() -> SessionInfoUpdate:
    return SessionInfoUpdate(
        session_update="session_info_update",
        title="Mock session",
        updated_at="2026-01-01T00:00:00Z",
    )


def _usage_update() -> UsageUpdate:
    return UsageUpdate(session_update="usage_update", size=4096, used=512)


# Each scenario is an ordered list of callables returning a session update object.
SCENARIOS: dict[str, list] = {
    "agent_message": [
        lambda: AgentMessageChunk.model_validate(
            _load("session_update_agent_message_chunk")
        )
    ],
    "thought": [
        lambda: AgentThoughtChunk.model_validate(
            _load("session_update_agent_thought_chunk")
        )
    ],
    "plan": [lambda: AgentPlanUpdate.model_validate(_load("session_update_plan"))],
    "tool_call": [
        lambda: ToolCallStart.model_validate(_load("session_update_tool_call")),
        lambda: ToolCallProgress.model_validate(
            _load("session_update_tool_call_update_content")
        ),
        lambda: ToolCallProgress.model_validate(
            _load("session_update_tool_call_update_more_fields")
        ),
    ],
    "tool_call_read": [
        lambda: ToolCallStart.model_validate(_load("session_update_tool_call_read"))
    ],
    "tool_call_edit": [
        lambda: ToolCallStart.model_validate(_load("session_update_tool_call_edit"))
    ],
    "tool_call_locations": [
        lambda: ToolCallStart.model_validate(
            _load("session_update_tool_call_locations_rawinput")
        )
    ],
    "config_option": [
        lambda: ConfigOptionUpdate.model_validate(
            _load("session_update_config_option_update")
        )
    ],
    "user_message": [
        lambda: UserMessageChunk.model_validate(
            _load("session_update_user_message_chunk")
        )
    ],
    "available_commands": [_available_commands_update],
    "current_mode": [_current_mode_update],
    "session_info": [_session_info_update],
    "usage": [_usage_update],
}

ALL_SCENARIOS = [step for steps in SCENARIOS.values() for step in steps]


def _load(name: str) -> dict:
    return json.loads((GOLDEN / f"{name}.json").read_text())


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
        return InitializeResponse.model_validate(_load("initialize_response"))

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        **kwargs: Any,
    ) -> NewSessionResponse:
        data = _load("new_session_response")
        data["sessionId"] = uuid4().hex
        return NewSessionResponse.model_validate(data)

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
            steps = ALL_SCENARIOS if keyword == "all" else SCENARIOS.get(keyword, [])
            for factory in steps:
                await self._conn.session_update(session_id=session_id, update=factory())

        return PromptResponse(stop_reason="end_turn", user_message_id=message_id)


async def main() -> None:
    await run_agent(MockAgent())


if __name__ == "__main__":
    asyncio.run(main())
