# ElevenLabs voice-agent client-tool boundary

FreshCtx protects consequential ElevenLabs Python client tools immediately
inside their registered handler. Evidence is revalidated before the booking,
payment, or account-update function starts.

## Install

```console
python -m pip install 'freshctx[elevenlabs]'
```

## Configure ElevenLabs

In the ElevenLabs agent dashboard, create a **Client** tool whose name and
parameters match the Python handler. Enable **Wait for response** so the agent
receives the tool result before continuing the conversation.

```python
from elevenlabs import ElevenLabs
from elevenlabs.conversational_ai.conversation import ClientTools, Conversation

from freshctx.integrations.elevenlabs import register_elevenlabs_client_tool

client_tools = ClientTools()
register_elevenlabs_client_tool(
    client_tools,
    "confirm_booking",
    confirm_booking,
    depends_on=[customer_decision],
    store=store,
)

conversation = Conversation(
    client=ElevenLabs(api_key=api_key),
    agent_id=agent_id,
    requires_auth=True,
    client_tools=client_tools,
)
```

Use `is_async=True` when the registered application handler is asynchronous.
The application remains responsible for the event-loop lifecycle required by
the ElevenLabs SDK.

## Expected outcomes

| Situation | Tool result | Application handler |
| --- | --- | --- |
| Declared customer record remains current | Application result | Executes once |
| Declared customer record changes | Structured FreshCtx block | Does not execute |
| Speech-to-record match is unresolved | `UNVERIFIABLE` FreshCtx block | Does not execute |

Run all three outcomes without an API key or microphone:

```console
python examples/elevenlabs_voice_customer_guard.py
```

Expected output:

```text
current_match: confirmed (CURRENT), executions=1
record_changed: blocked (STALE_REASONING), executions=0
unresolved_mismatch: blocked (UNVERIFIABLE), executions=0
```

## Product boundary

FreshCtx does not transcribe audio, resolve customer identity, or decide
whether two names are semantically equivalent. The application performs that
matching and declares only the evidence used by its decision. If the
application cannot defend the match, it should supply an unresolved dependency
so FreshCtx fails closed as `UNVERIFIABLE`.

Tool parameters remain in the ElevenLabs SDK and application handler. FreshCtx
records only the integration contract, runtime name, and protected action name.
It does not copy transcripts, customer details, booking IDs, credentials, or
other tool parameters into its objects or JSONL audit records.

This bridge covers registered Python client tools. For ElevenLabs webhook
tools, place an equivalent FreshCtx protected-action boundary inside the
receiving application endpoint. ElevenLabs system tools do not execute through
the Python client-tool registry and are not protected by this bridge.
