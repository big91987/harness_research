from __future__ import annotations

from dataclasses import dataclass

from harness.context import ContextManager
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
    memory: MarkdownMemoryStore | None = None
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_iterations: int = 20

    def run_turn(self, session: Session, user_input: str) -> TurnResult:
        trace = self.trace or TraceRecorder()
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
            trace.record(
                "model_response",
                session_id=session.id,
                iteration=iterations,
                tool_calls=len(response.tool_calls),
                usage=response.usage,
            )

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
