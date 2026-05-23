from __future__ import annotations

from dataclasses import dataclass

from harness.schema import Message


@dataclass(frozen=True)
class CompactionResult:
    messages: list[Message]
    original_count: int
    dropped_count: int


@dataclass
class ContextManager:
    max_messages: int = 40
    keep_head: int = 2
    keep_tail: int = 20

    def prepare(self, messages: list[Message]) -> list[Message]:
        return self.compact(messages).messages

    def compact(self, messages: list[Message]) -> CompactionResult:
        if self.keep_head < 0 or self.keep_tail < 0:
            raise ValueError("keep_head and keep_tail must be non-negative")
        if self.max_messages < 1:
            raise ValueError("max_messages must be greater than 0")
        if len(messages) <= self.max_messages:
            return CompactionResult(list(messages), original_count=len(messages), dropped_count=0)
        head = messages[: self.keep_head]
        tail = messages[-self.keep_tail :]
        dropped = messages[self.keep_head : len(messages) - self.keep_tail]
        summary_bits = []
        for msg in dropped:
            text = msg.content.replace("\n", " ")
            summary_bits.append(f"{msg.role}: {text[:160]}")
        summary = "Compacted conversation summary:\n" + "\n".join(summary_bits)
        summary_message = Message(
            role="system",
            content=summary,
            metadata={
                "kind": "compaction_summary",
                "dropped_messages": len(dropped),
                "original_messages": len(messages),
            },
        )
        return CompactionResult(
            [*head, summary_message, *tail],
            original_count=len(messages),
            dropped_count=len(dropped),
        )
