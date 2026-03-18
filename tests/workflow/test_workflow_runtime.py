from __future__ import annotations

import asyncio

from pyferox.reliability import RetryDisposition, RetryPolicy
from pyferox.workflow import Workflow, WorkflowStatus, WorkflowStep


def test_workflow_success_path() -> None:
    workflow = Workflow[dict[str, int]](
        "ok",
        steps=[
            WorkflowStep(name="inc1", run=lambda state: {"value": state["value"] + 1}),
            WorkflowStep(name="inc2", run=lambda state: {"value": state["value"] + 1}),
        ],
    )
    result = asyncio.run(workflow.run({"value": 0}))
    assert result.status == WorkflowStatus.SUCCESS
    assert result.state["value"] == 2
    assert result.completed_steps == ["inc1", "inc2"]


def test_workflow_compensation_path() -> None:
    compensated: list[str] = []

    async def compensate(_: dict[str, int]) -> None:
        compensated.append("inc")

    def fail(_: dict[str, int]) -> dict[str, int]:
        raise ValueError("boom")

    workflow = Workflow[dict[str, int]](
        "compensate",
        steps=[
            WorkflowStep(
                name="inc",
                run=lambda state: {"value": state["value"] + 1},
                compensate=compensate,
            ),
            WorkflowStep(name="fail", run=fail),
        ],
    )

    result = asyncio.run(workflow.run({"value": 0}))
    assert result.status == WorkflowStatus.COMPENSATED
    assert result.failed_step == "fail"
    assert compensated == ["inc"]


def test_workflow_retry_step_then_success() -> None:
    attempts = {"count": 0}

    def flaky(state: dict[str, int]) -> dict[str, int]:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary")
        return {"value": state["value"] + 1}

    workflow = Workflow[dict[str, int]](
        "retry",
        steps=[
            WorkflowStep(
                name="flaky",
                run=flaky,
                retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.0),
            ),
        ],
    )

    result = asyncio.run(workflow.run({"value": 1}))
    assert result.status == WorkflowStatus.SUCCESS
    assert result.state["value"] == 2
    assert attempts["count"] == 2


def test_workflow_custom_retry_classifier_marks_permanent() -> None:
    def classify(_: Exception):
        from pyferox.reliability import RetryDecision

        return RetryDecision(RetryDisposition.PERMANENT, reason="permanent")

    workflow = Workflow[dict[str, int]](
        "permanent",
        steps=[
            WorkflowStep(
                name="fail",
                run=lambda _: (_ for _ in ()).throw(RuntimeError("x")),
                retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.0),
            ),
        ],
        retry_classifier=classify,
    )
    result = asyncio.run(workflow.run({"value": 0}))
    assert result.status == WorkflowStatus.FAILED
