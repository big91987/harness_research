from __future__ import annotations

from dataclasses import dataclass

from harness.schema import Message


@dataclass
class ContextManager:
    max_messages: int = 40
    keep_head: int = 2
    keep_tail: int = 20

    def prepare(self, messages: list[Message]) -> list[Message]:
        if len(messages) <= self.max_messages:
            return list(messages)
        head = messages[: self.keep_head]
        tail = messages[-self.keep_tail :]
        dropped = messages[self.keep_head : len(messages) - self.keep_tail]
        summary_bits = []
        for msg in dropped:
            text = msg.content.replace("\n", " ")
            summary_bits.append(f"{msg.role}: {text[:160]}")
        summary = "Compacted conversation summary:\n" + "\n".join(summary_bits)
        return [*head, Message.system(summary), *tail]

