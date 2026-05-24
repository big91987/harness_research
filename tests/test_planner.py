from __future__ import annotations

import json
import subprocess
import sys

from harness.planner import PlanStore, TaskPlanner


def test_task_planner_creates_steps_from_prompt() -> None:
    planner = TaskPlanner()

    plan = planner.plan("Inspect repo, run tests, summarize results")

    assert [step.title for step in plan.steps] == ["Inspect repo", "run tests", "summarize results"]
    assert plan.status == "pending"


def test_plan_store_persists_and_updates_steps(tmp_path) -> None:  # noqa: ANN001
    store = PlanStore(tmp_path)
    plan = TaskPlanner().plan("Inspect repo, run tests")

    saved = store.save(plan)
    updated = store.update_step(saved.id, 1, status="completed")

    loaded = store.load(saved.id)
    assert loaded is not None
    assert updated.steps[0].status == "completed"
    assert loaded.steps[0].status == "completed"
    assert store.list()[0].id == saved.id


def test_cli_plans_create_show_and_update(tmp_path) -> None:  # noqa: ANN001
    create = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "plans",
            "--plan-dir",
            str(tmp_path),
            "--create",
            "Inspect repo, run tests",
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={"PYTHONPATH": "src"},
    )
    plan_id = json.loads(create.stdout)["id"]
    update = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "plans",
            "--plan-dir",
            str(tmp_path),
            "--update",
            plan_id,
            "--step",
            "1",
            "--status",
            "completed",
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={"PYTHONPATH": "src"},
    )

    assert json.loads(update.stdout)["steps"][0]["status"] == "completed"
