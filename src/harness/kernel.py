from __future__ import annotations

from dataclasses import dataclass

from harness.audit import AuditLog
from harness.context import ContextManager
from harness.cost import ModelPricing, RuntimeBudget, canonical_usage
from harness.memory import MarkdownMemoryStore
from harness.model import ModelClient
from harness.permissions import Policy
from harness.schema import Message, TurnResult
from harness.session import JsonlSessionStore, Session
from harness.tools import ToolRegistry, ToolResult
from harness.trace import TraceRecorder
from harness.workspace import Workspace


DEFAULT_SYSTEM_PROMPT = """You are a local agent harness.
Use tools when they help. Keep all file operations inside the workspace.
When tool results are enough, provide a concise final answer."""


@dataclass
class AgentKernel:
    model: ModelClient
    tools: ToolRegistry
    store: JsonlSessionStore
    workspace: Workspace
    policy: Policy
    context: ContextManager | None = None
    trace: TraceRecorder | None = None
    audit: AuditLog | None = None
    memory: MarkdownMemoryStore | None = None
    pricing: ModelPricing = ModelPricing()
    budget: RuntimeBudget = RuntimeBudget()
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_iterations: int = 20

    def run_turn(self, session: Session, user_input: str) -> TurnResult:
        trace = self.trace or TraceRecorder()
        audit = self.audit or AuditLog()
        context = self.context or ContextManager()
        session.messages.append(Message.user(user_input))
        trace.record("turn_start", session_id=session.id, user_input=user_input)
        final_text = ""
        iterations = 0
        stop_reason = "max_iterations"

        for iterations in range(1, self.max_iterations + 1):
            prompt_messages = [Message.system(self.system_prompt)]
            if self.memory:
                memory_context = self.memory.render_context()
                if memory_context:
                    prompt_messages.append(Message.system(memory_context))
            prompt_messages.extend(context.prepare(session.messages))

            trace.record("model_call", session_id=session.id, iteration=iterations)
            try:
                response = self.model.generate(prompt_messages, self.tools.definitions())
            except Exception as exc:  # noqa: BLE001 - model failures should become turn state.
                final_text = f"Model error: {exc}"
                stop_reason = "model_error"
                trace.record("model_error", session_id=session.id, iteration=iterations, error=str(exc))
                session.messages.append(Message.assistant(final_text))
                break
            cost_usd = self._record_usage(session, response.usage)
            trace.record(
                "model_response",
                session_id=session.id,
                iteration=iterations,
                tool_calls=len(response.tool_calls),
                usage=response.usage,
                cost_usd=cost_usd,
            )
            budget_error = self.budget.check(
                total_tokens=session.usage.get("total_tokens", 0),
                cost_usd=session.cost_usd,
            )
            if budget_error:
                final_text = f"Budget exceeded: {budget_error}"
                stop_reason = "budget_exceeded"
                trace.record(
                    "budget_exceeded",
                    session_id=session.id,
                    iteration=iterations,
                    reason=budget_error,
                    usage=session.usage,
                    cost_usd=session.cost_usd,
                )
                session.messages.append(Message.assistant(final_text))
                break

            session.messages.append(Message.assistant(response.content, response.tool_calls))
            if not response.tool_calls:
                final_text = response.content
                stop_reason = "final_answer"
                break

            for call in response.tool_calls:
                try:
                    tool = self.tools.get(call.name)
                    result = tool.run(call.arguments, self.workspace, self.policy)
                except Exception as exc:  # noqa: BLE001 - tool lookup/runtime errors return to model.
                    result = ToolResult(str(exc), is_error=True)
                trace.record(
                    "tool_call",
                    session_id=session.id,
                    name=call.name,
                    arguments=call.arguments,
                    is_error=result.is_error,
                )
                audit.record(
                    "tool_call",
                    session_id=session.id,
                    actor="agent",
                    action=call.name,
                    allowed=not result.is_error,
                    is_error=result.is_error,
                )
                session.messages.append(Message.tool(call.id, call.name, result.output))
                if result.is_error:
                    trace.record("tool_error", session_id=session.id, name=call.name, output=result.output)

            self.store.save(session)

        self.store.save(session)
        trace.record(
            "turn_end",
            session_id=session.id,
            iterations=iterations,
            stop_reason=stop_reason,
            final_text=final_text,
        )
        return TurnResult(session.id, final_text, iterations, stop_reason)

    def _record_usage(self, session: Session, usage: dict) -> float:
        tokens = canonical_usage(usage)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            session.usage[key] = int(session.usage.get(key, 0)) + int(tokens.get(key, 0) or 0)
        cost_usd = self.pricing.estimate(usage)
        session.cost_usd += cost_usd
        return cost_usd
