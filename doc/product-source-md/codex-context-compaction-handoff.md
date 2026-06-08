# Codex context compaction handoff

Date: 2026-06-08

This handoff records the current investigation into Codex context compaction. It focuses on source-backed facts, real request captures, and the open questions that remain.

## Current conclusion

Codex has two compaction implementations:

1. Remote compact: OpenAI / Azure providers call the service endpoint `/v1/responses/compact`.
2. Local compact: non-remote providers use the normal `/v1/responses` path with Codex's local compact prompt.

The two implementations share the same runtime purpose: replace an oversized conversation history with a compacted replacement history, then continue the same thread/turn from that replacement.

Remote compact is opaque to the local client. It returns a `ResponseItem::Compaction { encrypted_content }` item. Codex stores and replays that item, but does not decrypt it or read a plaintext summary.

Local compact is transparent. It appends the local compact prompt to history, gets a plaintext assistant summary, wraps it with `SUMMARY_PREFIX`, and stores that summary as a user-message-like history item.

This compact work sits on top of the context assembly mechanism already verified earlier:

- First turn writes full initial context into history.
- Later turns do not append a second full initial context when nothing changed.
- Later turns can append targeted context update items, for example `<model_switch>`, when the turn context differs from the previous reference context item.
- The old initial context still appears in model input because it is part of history; the important point is that Codex does not duplicate it every turn.

## Where compaction can happen

| Entry | Runtime location | Trigger condition | Phase |
|---|---|---|---|
| Manual compact | `Op::Compact` -> `CompactTask` | Client/user explicitly submits compact | Standalone turn |
| Pre-turn auto compact | Start of `run_turn`, before recording new input | Previous history already exceeds auto compact budget or usable context window | PreTurn |
| Mid-turn auto compact | After a sample, before the next follow-up sample | `token_limit_reached && needs_follow_up` | MidTurn |
| Model downshift compact | Start of `run_turn` | Switching to a smaller context-window model and old history no longer fits | PreTurn |

Important distinction:

- Pre-turn compact uses `InitialContextInjection::DoNotInject`. After compaction, `run_turn` records context updates and new user input in the normal path.
- Mid-turn compact uses `InitialContextInjection::BeforeLastUserMessage`, because the same turn must continue sampling immediately after history replacement.

## Trigger logic

Automatic compaction is driven by `auto_compact_token_status`, not by model choice.

The effective predicate is whether the current token usage exceeds either:

- the configured/model auto compact budget;
- the usable context-window limit.

In the run-turn loop:

```text
pre-turn:
  run_turn
    -> run_pre_sampling_compact
    -> auto_compact_token_status
    -> if token_limit_reached: run_auto_compact(... PreTurn)

mid-turn:
  sample
    -> model_needs_follow_up || has_pending_input
    -> if token_limit_reached && needs_follow_up:
         run_auto_compact(... MidTurn)
```

## Remote compact behavior

Remote compact request body shape is defined by `CompactionInput`:

```rust
pub struct CompactionInput<'a> {
    pub model: &'a str,
    pub input: &'a [ResponseItem],
    pub instructions: &'a str,
    pub tools: Vec<Value>,
    pub parallel_tool_calls: bool,
    pub reasoning: Option<Reasoning>,
    pub service_tier: Option<&'a str>,
    pub prompt_cache_key: Option<&'a str>,
    pub text: Option<TextControls>,
}
```

The response schema is:

```rust
struct CompactHistoryResponse {
    output: Vec<ResponseItem>,
}
```

The actual remote capture showed no local compact prompt in the request input. The service endpoint itself encodes the compaction task:

```text
POST /v1/responses/compact
body = { model, instructions, input: history, tools, reasoning, ... }
```

Observed remote output item:

```json
{
  "type": "compaction",
  "encrypted_content": "..."
}
```

Interpretation:

- `encrypted_content` is an opaque service-side checkpoint.
- Codex local client has no decryption key.
- The service can consume it later when Codex sends it back in `/v1/responses`.
- The server likely binds this to auth/account plus `session-id` / `thread-id` headers, but the exact key management is not visible in the open-source client.

## Local compact behavior

Local compact uses the default prompt:

```text
You are performing a CONTEXT CHECKPOINT COMPACTION. Create a handoff summary for another LLM that will resume the task.

Include:
- Current progress and key decisions made
- Important context, constraints, or user preferences
- What remains to be done (clear next steps)
- Any critical data, examples, or references needed to continue

Be concise, structured, and focused on helping the next LLM seamlessly continue the work.
```

Source path:

```text
codex-rs/core/templates/compact/prompt.md
```

All local compact entry points use the same `turn_context.compact_prompt()` unless overridden by config:

```toml
compact_prompt = "..."
experimental_compact_prompt_file = "..."
```

Local compact request shape from real capture:

```text
history
assistant final from previous turn
user compact prompt
```

Local compact follow-up request shape:

```text
previous real user message
plaintext handoff summary
current developer/context items
new user message
```

The plaintext summary begins with Codex's summary prefix:

```text
Another language model started to solve this problem and produced a summary of its thinking process...
```

## Real experiments

### Context diff experiment

Script:

```text
tmp/codex-full-turn-mock/run_diff_context_turns.ts
```

Method:

- Used a controlled Responses mock server.
- Ran three turns against the same resumed session.
- Turn 1: `gpt-5`.
- Turn 2: same model and same config.
- Turn 3: changed model to `gpt-5.1`.

Observed:

```text
Call 1 input=3
  full initial context + turn1 input

Call 2 input=5
  same initial context from history + turn1 assistant + turn2 input
  no duplicate full context item

Call 3 input=8
  history + <model_switch> developer update + turn3 input
```

Capture files:

```text
/private/tmp/codex-diff-context-turns/parsed-summary.md
/private/tmp/codex-diff-context-turns/request-01.json
/private/tmp/codex-diff-context-turns/request-02.json
/private/tmp/codex-diff-context-turns/request-03.json
```

### Remote compact experiment

Script:

```text
tmp/codex-full-turn-mock/run_real_pre_turn_compact_case.ts
```

Method:

- Used real Codex/OpenAI provider.
- Set `model_auto_compact_token_limit=200`.
- Ran two short `codex exec` turns in the same session.
- First turn consumed enough injected context to exceed the low threshold.
- Second turn triggered pre-turn auto compact.

Observed:

```text
context compacted
```

Capture files:

```text
/private/tmp/codex-real-pre-turn-compact-case/real-request-04.json
/private/tmp/codex-real-pre-turn-compact-case/real-request-05.json
/private/tmp/codex-real-pre-turn-compact-case/remote-compact-input-call04.json
/private/tmp/codex-real-pre-turn-compact-case/remote-compact-output-observed-call05.json
```

Key shape:

```text
Call 4: remote compact input
  developer context
  AGENTS/environment context
  turn1 user input
  assistant response

Call 5: next sample after compaction
  turn1 user input
  encrypted compaction item
  current developer context
  AGENTS/environment context
  turn2 user input
```

### Local compact experiment

Script:

```text
tmp/codex-full-turn-mock/run_real_local_compact_case.ts
```

Method:

- Still used the real Codex/OpenAI backend.
- Defined a custom provider with non-OpenAI name and `requires_openai_auth=true`.
- Did not set `base_url`, so Codex used the ChatGPT/Codex backend auth path.
- Because provider name was not OpenAI/Azure, `supports_remote_compaction=false`.
- Set `model_auto_compact_token_limit=200`.

Observed:

```text
context compacted
```

Capture files:

```text
/private/tmp/codex-real-local-compact-case/local-request-02.json
/private/tmp/codex-real-local-compact-case/local-request-03.json
/private/tmp/codex-real-local-compact-case/parsed-summary.md
```

Key shape:

```text
Call 2: local compact
  developer context
  AGENTS/environment context
  turn1 user input
  assistant response
  local compact prompt

Call 3: next sample after compaction
  turn1 user input
  plaintext handoff summary
  current developer context
  AGENTS/environment context
  turn2 user input
```

## Source evidence map

| Concern | Source |
|---|---|
| Remote vs local selection | `codex-rs/core/src/compact.rs::should_use_remote_compact_task` |
| OpenAI/Azure remote support | `codex-rs/model-provider-info/src/lib.rs::supports_remote_compaction` |
| Pre-turn compact | `codex-rs/core/src/session/turn.rs::run_pre_sampling_compact` |
| Model downshift compact | `codex-rs/core/src/session/turn.rs::maybe_run_previous_model_inline_compact` |
| Mid-turn compact | `codex-rs/core/src/session/turn.rs` branch around `token_limit_reached && needs_follow_up` |
| Manual compact task | `codex-rs/core/src/tasks/compact.rs::CompactTask` |
| Local compact prompt | `codex-rs/core/templates/compact/prompt.md` |
| Local compact implementation | `codex-rs/core/src/compact.rs::run_compact_task_inner_impl` |
| Remote compact implementation | `codex-rs/core/src/compact_remote.rs::run_remote_compact_task_inner_impl` |
| Compact endpoint client | `codex-rs/core/src/client.rs::compact_conversation_history` |
| Compact input schema | `codex-rs/codex-api/src/common.rs::CompactionInput` |
| Compact response schema | `codex-rs/codex-api/src/endpoint/compact.rs::CompactHistoryResponse` |
| History replacement | `codex-rs/core/src/session/mod.rs::replace_compacted_history` |
| Initial context reinjection | `codex-rs/core/src/compact_remote.rs::process_compacted_history` and `codex-rs/core/src/compact.rs::insert_initial_context_before_last_real_user_or_summary` |

## Current status

What is confirmed:

- Remote compact does not send the local compact prompt in the client-visible request JSON.
- Remote compact returns an encrypted compaction item.
- The encrypted item is replayed into the next `/v1/responses` request and is understood by the service.
- Local compact sends the local prompt as a normal user message and produces a plaintext handoff summary.
- The three compact entry points share the same local compact prompt when local compact is used.
- The difference between pre-turn and mid-turn is mostly the phase, trigger timing, and initial context reinjection behavior.

What remains unclear:

- Server-side key management for `encrypted_content`.
- Whether remote compact uses a prompt internally, a separate compression model, or a specialized service policy.
- Whether remote compact v2 is enabled in current production paths for this account. Source shows a feature flag, but the real capture matched the legacy `/responses/compact` opaque output path.
- Exact failure behavior if a remote compaction item is replayed under a different thread/account; source strongly suggests auth/session/thread binding, but this was not tested.

## Recommended next step

For documentation/PPT, explain compact in two layers:

1. Runtime mechanism: when compaction triggers, how history is replaced, how future sampling continues.
2. Implementation strategy: remote opaque checkpoint vs local plaintext handoff summary.

Avoid saying "remote compact has no prompt" too broadly. The precise wording should be:

```text
Remote compact has no client-visible local compact prompt in the request body.
The compaction instruction is represented by the service endpoint semantics and server-side policy.
```
