"""Lightweight workflow orchestration runtime."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Awaitable, Callable, Generic, TypeVar
from uuid import uuid4

from pyferox.reliability import RetryClassifier, RetryPolicy, default_retry_classifier

TState = TypeVar("TState")

StepFn = Callable[[TState], Awaitable[TState | None] | TState | None]
CompensateFn = Callable[[TState], Awaitable[None] | None]


class WorkflowStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    COMPENSATED = "compensated"


@dataclass(slots=True)
class WorkflowStep(Generic[TState]):
    name: str
    run: StepFn[TState]
    compensate: CompensateFn[TState] | None = None
    retry_policy: RetryPolicy | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WorkflowContext:
    workflow_id: str = field(default_factory=lambda: str(uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WorkflowExecutionResult(Generic[TState]):
    status: WorkflowStatus
    state: TState
    completed_steps: list[str] = field(default_factory=list)
    compensated_steps: list[str] = field(default_factory=list)
    failed_step: str | None = None
    error: str | None = None


class Workflow(Generic[TState]):
    def __init__(
        self,
        name: str,
        *,
        steps: list[WorkflowStep[TState]] | None = None,
        retry_classifier: RetryClassifier | None = None,
    ) -> None:
        self.name = name
        self.steps = steps or []
        self.retry_classifier = retry_classifier or default_retry_classifier

    def add_step(self, step: WorkflowStep[TState]) -> None:
        self.steps.append(step)

    async def run(self, state: TState, *, context: WorkflowContext | None = None) -> WorkflowExecutionResult[TState]:
        _ = context or WorkflowContext()
        completed: list[WorkflowStep[TState]] = []
        completed_names: list[str] = []
        current = state

        for step in self.steps:
            ok, current, error = await self._run_step(step, current)
            if ok:
                completed.append(step)
                completed_names.append(step.name)
                continue

            compensated = await self._compensate(completed, current)
            status = WorkflowStatus.COMPENSATED if compensated else WorkflowStatus.FAILED
            compensated_names = [item.name for item in completed if item.compensate is not None]
            return WorkflowExecutionResult(
                status=status,
                state=current,
                completed_steps=completed_names,
                compensated_steps=compensated_names if compensated else [],
                failed_step=step.name,
                error=error,
            )

        return WorkflowExecutionResult(
            status=WorkflowStatus.SUCCESS,
            state=current,
            completed_steps=completed_names,
        )

    async def _run_step(self, step: WorkflowStep[TState], state: TState) -> tuple[bool, TState, str | None]:
        attempt = 1
        policy = step.retry_policy or RetryPolicy(max_attempts=1, base_delay_seconds=0.0)
        while True:
            try:
                maybe_state = step.run(state)
                if asyncio.iscoroutine(maybe_state):
                    maybe_state = await maybe_state
                if maybe_state is not None:
                    state = maybe_state
                return True, state, None
            except Exception as exc:
                decision = self.retry_classifier(exc)
                if policy.should_retry(attempt=attempt, decision=decision):
                    await asyncio.sleep(policy.next_delay_seconds(attempt=attempt))
                    attempt += 1
                    continue
                return False, state, str(exc)

    async def _compensate(self, completed: list[WorkflowStep[TState]], state: TState) -> bool:
        compensated_any = False
        for step in reversed(completed):
            if step.compensate is None:
                continue
            compensated_any = True
            try:
                result = step.compensate(state)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                return False
        return compensated_any
