import asyncio
import copy
from typing import Any

from acp import run_agent
from acp.exceptions import RequestError
from acp.schema import (
    AgentMessageChunk,
    AgentPlanUpdate,
    AgentThoughtChunk,
    AudioContentBlock,
    AvailableCommandsUpdate,
    ConfigOptionUpdate,
    CurrentModeUpdate,
    EmbeddedResourceContentBlock,
    ImageContentBlock,
    PermissionOption,
    PromptResponse,
    ResourceContentBlock,
    SessionInfoUpdate,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
    ToolCallUpdate,
    UsageUpdate,
    UserMessageChunk,
)

from lib import MockAgent, load_golden, load_extra


SCENARIOS: dict[str, list] = {
    "agent_message": [
        lambda: AgentMessageChunk.model_validate(
            load_golden("session_update_agent_message_chunk")
        )
    ],
    "thought": [
        lambda: AgentThoughtChunk.model_validate(
            load_golden("session_update_agent_thought_chunk")
        )
    ],
    "plan": [
        lambda: AgentPlanUpdate.model_validate(load_golden("session_update_plan")),
        lambda: AgentPlanUpdate.model_validate(
            _complete_plan(load_golden("session_update_plan"))
        ),
    ],
    "tool_call": [
        lambda: ToolCallStart.model_validate(load_golden("session_update_tool_call")),
        lambda: ToolCallProgress.model_validate(
            load_golden("session_update_tool_call_update_content")
        ),
        lambda: ToolCallProgress.model_validate(
            _complete_tool_call(
                load_golden("session_update_tool_call"), "File read successfully."
            )
        ),
    ],
    "tool_call_read": [
        lambda: ToolCallStart.model_validate(
            load_golden("session_update_tool_call_read")
        ),
        lambda: ToolCallProgress.model_validate(
            _complete_tool_call(
                load_golden("session_update_tool_call_read"), "File read successfully."
            )
        ),
    ],
    "tool_call_edit": [
        lambda: ToolCallStart.model_validate(
            load_golden("session_update_tool_call_edit")
        ),
        lambda: ToolCallProgress.model_validate(
            _complete_tool_call(
                load_golden("session_update_tool_call_edit"), "Edit applied successfully."
            )
        ),
    ],
    "tool_call_locations": [
        lambda: ToolCallStart.model_validate(
            load_golden("session_update_tool_call_locations_rawinput")
        ),
        lambda: ToolCallProgress.model_validate(
            _complete_tool_call(
                load_golden("session_update_tool_call_locations_rawinput"),
                "File tracked successfully.",
            )
        ),
    ],
    "tool_call_diff": [
        lambda: ToolCallProgress.model_validate(
            load_extra("session_update_tool_call_update_diff_content")
        ),
        lambda: ToolCallProgress.model_validate(
            _complete_tool_call(
                load_extra("session_update_tool_call_update_diff_content"),
                "Edit with diff applied successfully.",
            )
        ),
    ],
    "tool_call_diff_no_old": [
        lambda: ToolCallProgress.model_validate(
            load_extra("session_update_tool_call_update_diff_no_old_content")
        ),
        lambda: ToolCallProgress.model_validate(
            _complete_tool_call(
                load_extra("session_update_tool_call_update_diff_no_old_content"),
                "New file created successfully.",
            )
        ),
    ],
    "tool_call_terminal": [
        lambda: ToolCallProgress.model_validate(
            load_extra("session_update_tool_call_update_terminal_content")
        ),
        lambda: ToolCallProgress.model_validate(
            _complete_tool_call(
                load_extra("session_update_tool_call_update_terminal_content"),
                "Terminal command completed.\n$ npm install\nadded 42 packages in 2s",
            )
        ),
    ],
    "config_option": [
        lambda: ConfigOptionUpdate.model_validate(
            load_golden("session_update_config_option_update")
        )
    ],
    "user_message": [
        lambda: UserMessageChunk.model_validate(
            load_golden("session_update_user_message_chunk")
        )
    ],
    "available_commands": [
        lambda: AvailableCommandsUpdate.model_validate(
            load_extra("session_update_available_commands")
        )
    ],
    "current_mode": [
        lambda: CurrentModeUpdate.model_validate(
            load_extra("session_update_current_mode")
        )
    ],
    "session_info": [
        lambda: SessionInfoUpdate.model_validate(
            load_extra("session_update_session_info")
        )
    ],
    "usage": [lambda: UsageUpdate.model_validate(load_extra("session_update_usage"))],
    "long_running": [
        lambda: AgentThoughtChunk.model_validate(load_golden("session_update_agent_thought_chunk")),
        lambda: AgentThoughtChunk.model_validate(load_golden("session_update_agent_thought_chunk")),
        lambda: AgentThoughtChunk.model_validate(load_golden("session_update_agent_thought_chunk")),
        lambda: AgentMessageChunk.model_validate(load_golden("session_update_agent_message_chunk")),
        lambda: AgentMessageChunk.model_validate(load_golden("session_update_agent_message_chunk")),
        lambda: AgentMessageChunk.model_validate(load_golden("session_update_agent_message_chunk")),
    ],
}

ALL_SCENARIOS = [step for steps in SCENARIOS.values() for step in steps]

SCENARIO_DELAYS: dict[str, float] = {
    "long_running": 1.5,
}


def _complete_tool_call(base: dict, content_text: str) -> dict:
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
    result = copy.deepcopy(base)
    for entry in result["entries"]:
        entry["status"] = "completed"
    return result


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


class ScenarioAgent(MockAgent):
    async def _test_request_permission(self, session_id: str) -> None:
        options = [
            PermissionOption.model_validate(o)
            for o in load_golden("request_permission_request")["options"]
        ]
        tool_call = ToolCallUpdate(tool_call_id="call_001")
        await self._conn.request_permission(
            options=options, session_id=session_id, tool_call=tool_call
        )

    async def _test_fs_read(self, session_id: str) -> None:
        req = load_golden("fs_read_text_file_request")
        await self._conn.read_text_file(
            path=req["path"],
            session_id=session_id,
            line=req.get("line"),
            limit=req.get("limit"),
        )

    async def _test_fs_write(self, session_id: str) -> None:
        req = load_golden("fs_write_text_file_request")
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
            keyword = text[len("test "):]
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
                delay = SCENARIO_DELAYS.get(keyword, 0.1)
                for factory in steps:
                    await self._conn.session_update(
                        session_id=session_id, update=factory()
                    )
                    await asyncio.sleep(delay)

        return PromptResponse(stop_reason="end_turn", user_message_id=message_id)


async def main() -> None:
    await run_agent(ScenarioAgent())


if __name__ == "__main__":
    asyncio.run(main())
