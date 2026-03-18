from __future__ import annotations

from pyferox.core import Module, StructQuery, handle, singleton

from app.users import InMemoryUserRepo


class InMemoryBillingRepo:
    def __init__(self) -> None:
        self._balances: dict[int, int] = {}

    async def get_balance_cents(self, user_id: int) -> int:
        return self._balances.get(user_id, 0)


class GetBalance(StructQuery):
    user_id: int


@handle(GetBalance)
async def get_balance(query: GetBalance, users: InMemoryUserRepo, billing: InMemoryBillingRepo) -> dict[str, int]:
    await users.get(query.user_id)
    return {"user_id": query.user_id, "balance_cents": await billing.get_balance_cents(query.user_id)}


billing_module = Module(
    name="billing",
    handlers=[get_balance],
    providers=[singleton(InMemoryBillingRepo())],
)
