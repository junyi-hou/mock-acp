import asyncio
from typing import Any

from acp import run_agent
from acp.exceptions import RequestError
from acp.schema import AuthenticateResponse

from lib import MockAgent


class AuthErrorAgent(MockAgent):
    async def authenticate(
        self, method_id: str, **kwargs: Any
    ) -> AuthenticateResponse | None:
        raise RequestError.auth_required(
            {"details": "Intentionally triggered authentication error for testing."}
        )


async def main() -> None:
    await run_agent(AuthErrorAgent())


if __name__ == "__main__":
    asyncio.run(main())
