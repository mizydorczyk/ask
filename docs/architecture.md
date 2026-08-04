# Architecture

`ask` turns a natural-language request into a reviewed command for the user's
existing Zsh process. `ask initialize` prints the interception function that
the user evaluates in Zsh.

```text
Zsh --> CLI --> App --> Model --> Proposal --> TTY review --> Zsh
                 |
                 v
                 Terminal transcript --> Conversation
```

## Boundaries

- `cli.py` parses commands, prints the Zsh interceptor, and emits the small
  run/edit/cancel protocol.
- `app.py` coordinates one request.
- `conversation.py` contains neutral user messages, assistant messages, tool
  calls, and tool results.
- `model.py` defines the provider-neutral model interface and proposal.
- `development.py` provides the deterministic local model used for now.
- `openai/` implements OpenAI-specific request and response mapping only.
- `terminal/transcript.py` captures Terminal.app scrollback and reconstructs
  conversation history; `terminal/review.py` owns TTY review.
- `intercept.zsh` is the Zsh interception template. It invokes the installed
  `ask` executable directly and does not require Python or uv at runtime.
- `tools.py` defines available tools independently of any provider.

Dependency direction is inward: terminals, shells, and OpenAI adapt to neutral
conversation, tool, and model types. OpenAI never knows about Terminal.app or
Zsh.
