from __future__ import annotations

import asyncio

from pyferox.workflow import Workflow, WorkflowStatus, WorkflowStep


def test_workflow_add_step_and_async_none_result_branch() -> None:
    workflow = Workflow[dict[str, int]]("w")

    async def step(_: dict[str, int]) -> None:
        return None

    workflow.add_step(WorkflowStep(name="s1", run=step))
    result = asyncio.run(workflow.run({"v": 1}))
    assert result.status == WorkflowStatus.SUCCESS
    assert result.state["v"] == 1


def test_workflow_compensation_failure_path() -> None:
    async def bad_compensate(_: dict[str, int]) -> None:
        raise RuntimeError("compensate failed")

    def explode(_: dict[str, int]) -> None:
        raise ValueError("boom")

    workflow = Workflow[dict[str, int]](
        "w2",
        steps=[
            WorkflowStep(name="a", run=lambda state: state, compensate=None),
            WorkflowStep(name="b", run=lambda state: state, compensate=bad_compensate),
            WorkflowStep(name="c", run=explode),
        ],
    )

    result = asyncio.run(workflow.run({"v": 0}))
    assert result.status == WorkflowStatus.FAILED
    assert result.failed_step == "c"


def test_workflow_compensation_skips_none_and_handles_sync_compensate() -> None:
    seen: list[int] = []

    def sync_compensate(state: dict[str, int]) -> None:
        seen.append(state["v"])

    workflow = Workflow[dict[str, int]]("w3")
    steps = [
        WorkflowStep(name="none", run=lambda state: state, compensate=None),
        WorkflowStep(name="sync", run=lambda state: state, compensate=sync_compensate),
    ]

    compensated = asyncio.run(workflow._compensate(steps, {"v": 5}))
    assert compensated is True
    assert seen == [5]
