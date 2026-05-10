import asyncio
from typing import Any

from acp import run_agent
from acp.exceptions import RequestError
from acp.schema import ClientCapabilities, Implementation, InitializeResponse

from lib import MockAgent


class InitErrorAgent(MockAgent):
    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        raise RequestError.internal_error(
            {"details": "Intentionally triggered initialization error for testing."}
        )


async def main() -> None:
    await run_agent(InitErrorAgent())


if __name__ == "__main__":
    asyncio.run(main())
