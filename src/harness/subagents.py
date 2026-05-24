from __future__ import annotations

import json
from dataclasses import dataclass

from harness.audit import AuditLog
from harness.kernel import AgentKernel, TurnResult
from harness.memory import MarkdownMemoryStore
from harness.model import ModelClient
from harness.permissions import PermissionMode, Policy
from harness.session import JsonlSessionStore, Session
from harness.skills import SkillStore
from harness.tools import Tool, ToolRegistry, ToolResult
from harness.trace import TraceRecorder
from harness.workspace import Workspace


@dataclass(frozen=True)
class SubagentSpec:
    name: str
    permission: PermissionMode = PermissionMode.READ_ONLY
    max_iterations: int = 5


@dataclass(frozen=True)
class SubagentResult:
    name: str
    session_id: str
    turn_id: str
    final_text: str
    stop_reason: str
    iterations: int

    @classmethod
    def from_turn(cls, name: str, turn: TurnResult) -> "SubagentResult":
        return cls(
            name=name,
            session_id=turn.session_id,
            turn_id=turn.turn_id,
            final_text=turn.final_text,
            stop_reason=turn.stop_reason,
            iterations=turn.iterations,
        )


class SubagentRunner:
    def __init__(
        self,
        *,
        spec: SubagentSpec,
        model: ModelClient,
        tools: ToolRegistry,
        store: JsonlSessionStore,
        workspace: Workspace,
        trace: TraceRecorder | None = None,
        audit: AuditLog | None = None,
        memory: MarkdownMemoryStore | None = None,
        skills: SkillStore | None = None,
    ) -> None:
        self.spec = spec
        self.model = model
        self.tools = tools
        self.store = store
        self.workspace = workspace
        self.trace = trace
        self.audit = audit
        self.memory = memory
        self.skills = skills

    def delegate(self, prompt: str, *, parent_session_id: str | None = None) -> SubagentResult:
        session = Session.new(workspace=str(self.workspace.root))
        session.metadata["subagent_name"] = self.spec.name
        if parent_session_id:
            session.metadata["parent_session_id"] = parent_session_id
        self.store.save(session)
        trace = self.trace
        if trace:
            trace.record(
                "subagent_start",
                name=self.spec.name,
                parent_session_id=parent_session_id,
                child_session_id=session.id,
                permission=self.spec.permission.value,
                prompt=prompt,
            )

        kernel = AgentKernel(
            model=self.model,
            tools=self.tools,
            store=self.store,
            workspace=self.workspace,
            policy=Policy(self.spec.permission, audit=self.audit),
            trace=trace,
            audit=self.audit,
            memory=self.memory,
            skills=self.skills,
            max_iterations=self.spec.max_iterations,
        )
        turn = kernel.run_turn(session, prompt)
        result = SubagentResult.from_turn(self.spec.name, turn)
        if trace:
            trace.record(
                "subagent_end",
                name=self.spec.name,
                parent_session_id=parent_session_id,
                child_session_id=result.session_id,
                turn_id=result.turn_id,
                stop_reason=result.stop_reason,
                final_text=result.final_text,
            )
        return result


class SubagentRegistry:
    def __init__(self) -> None:
        self._runners: dict[str, SubagentRunner] = {}

    def register(
        self,
        spec: SubagentSpec,
        *,
        model: ModelClient,
        tools: ToolRegistry,
        store: JsonlSessionStore,
        workspace: Workspace,
        trace: TraceRecorder | None = None,
        audit: AuditLog | None = None,
        memory: MarkdownMemoryStore | None = None,
        skills: SkillStore | None = None,
    ) -> None:
        if spec.name in self._runners:
            raise ValueError(f"subagent already registered: {spec.name}")
        self._runners[spec.name] = SubagentRunner(
            spec=spec,
            model=model,
            tools=tools,
            store=store,
            workspace=workspace,
            trace=trace,
            audit=audit,
            memory=memory,
            skills=skills,
        )

    def names(self) -> list[str]:
        return sorted(self._runners)

    def delegate(self, agent: str, prompt: str, *, parent_session_id: str | None = None) -> SubagentResult:
        runner = self._runners.get(agent)
        if runner is None:
            raise KeyError(f"unknown subagent: {agent}")
        return runner.delegate(prompt, parent_session_id=parent_session_id)

    def delegate_task_tool(self, *, parent_session_id: str | None = None) -> Tool:
        return Tool(
            name="delegate_task",
            description="Delegate a prompt to a named local subagent and return its result.",
            parameters={
                "type": "object",
                "properties": {
                    "agent": {"type": "string"},
                    "prompt": {"type": "string"},
                },
                "required": ["agent", "prompt"],
            },
            handler=self._delegate_task_handler(parent_session_id=parent_session_id),
            required_permission=PermissionMode.READ_ONLY,
            category="subagent",
        )

    def _delegate_task_handler(self, *, parent_session_id: str | None = None):
        def handler(arguments: dict[str, object], _workspace: Workspace) -> ToolResult:
            agent = str(arguments["agent"])
            prompt = str(arguments["prompt"])
            try:
                result = self.delegate(agent, prompt, parent_session_id=parent_session_id)
            except KeyError as exc:
                return ToolResult(str(exc), is_error=True)
            return ToolResult(
                json.dumps(
                    {
                        "agent": result.name,
                        "session_id": result.session_id,
                        "turn_id": result.turn_id,
                        "stop_reason": result.stop_reason,
                        "iterations": result.iterations,
                        "final_text": result.final_text,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )

        return handler
