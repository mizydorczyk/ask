## Fine-tune a language model for `ask`

This document defines a supervised fine-tuning task for `ask`, the Zsh and Terminal.app assistant. The target model is [gemma-4-26b-a4b-it](https://ai.google.dev/gemma/docs/core/model_card_4): the Gemma 4 instruction-tuned mixture-of-experts model.

#### Conversational task: Which task should the model perform?

The model acts as `ask`, a concise Zsh-terminal assistant, and uses the relevant terminal scrollback as context. For each request, it must either:

- propose one shell command for the user to review, or
- answer concisely in plain text when the user asks for an explanation or a command would not help.

A command proposal is exactly one `shell` function call containing the command and its working directory, followed by a short explanation.

#### Conversational goals: What interactions will the model support?

The model will handle the interactions documented in [examples.md](../docs/examples.md): creating, finding, compressing, fixing, explaining, and improving shell commands; common Git workflows; and project-aware requests such as running tests or locating an environment variable. It should use the supplied terminal history and conversation to infer the working directory, the previous command, errors, and relevant project context.

For a command request, output exactly one structured `shell` tool call, followed by a short user-facing explanation. For explanation-only requests, output text only. Requests to edit source code, write documentation, or engage in general-purpose chat are outside the product scope; the model should say so briefly rather than fabricate a shell action.

The model must also support follow-up turns. When the user asks to fix or explain the previous command, it should use the prior command and its result. When the user adds a constraint to a canceled proposal, it should revise that proposal directly rather than ask for information already present in the conversation. A canceled proposal must never be treated as executed.

#### Data source and preparation: From where will conversational examples come?

Build examples from the documented `ask` use cases, and reviewed, synthetic terminal scenarios. Do not train on
a user's raw terminal history unless it has explicit permission, has been scrubbed of credentials and personal data, and is appropriate to retain.

Convert each example to the Gemma 4 chat template with a consistent system instruction, one or more user-assistant turns, and optional structured terminal-history tool-call/tool-result context. The target for each assistant turn is either a single `shell` function call plus a concise explanation, or a concise text-only answer. Include the command's expected working directory, realistic stdout/stderr, and exit status where context is necessary. Include multi-turn examples for previous-command questions and canceled-proposal revisions. Validate every JSON/tool-call payload and remove secrets, access tokens, hostnames, and private paths before splitting the data into train, validation, and held-out test sets by scenario family.

#### Success criteria: How will quality be measured?

Compare the tuned model with the untuned `gemma-4-26b-a4b-it` baseline on the held-out set and through human review. A response succeeds when it:

- selects text-only output versus a command proposal correctly;
- emits exactly one valid `shell` call when a command is needed;
- supplies a syntactically valid command and the correct working directory;
- respects terminal context and constraints such as macOS compatibility; and
- is concise, helpful, and safe to present for review.

Record tool-call validity, command correctness under isolated test fixtures, relevance, and reviewer-rated helpfulness. Track unsafe or destructive proposals, leaked sensitive data, and scope violations as separate failure categories.

#### Use case: How will the tuned model be used?

`ask` will call the model when a user types `?` followed by a request in Zsh. The application supplies the relevant terminal context, renders a command proposal with run, edit, and cancel controls, and executes nothing until the user chooses run. Text-only explanations are displayed directly. The model is therefore an intent-to-proposal component, not an autonomous shell agent.

It is recommended that you aim for 100 to 200 conversational pairs for initial testing, and scale up to 1000+ examples for a more robust training if possible.
