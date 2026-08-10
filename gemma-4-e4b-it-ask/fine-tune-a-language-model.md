## Fine-tune `gemma-4-E4B-it` for `ask`

This runbook fine-tunes [`google/gemma-4-E4B-it`](https://huggingface.co/google/gemma-4-E4B-it) for `ask`, the concise Zsh and tmux assistant.

## Reproducible Colab workflow

The source-controlled notebooks define a two-stage, training workflow. First run [`prepare-a-dataset.ipynb`](prepare-a-dataset.ipynb) from a checkout containing the example scenarios. It writes the 150-example `train` and 27-example `evaluate` JSONL files, then publishes the prepared splits and their split-declaring card to the private `$HF_NAMESPACE/gemma-4-e4b-it-ask-dataset` dataset repository.

Then open [`fine-tune-on-colab.ipynb`](fine-tune-on-colab.ipynb) in Google Colab, select an A100 GPU runtime, and store `HF_TOKEN` as a Colab Secret. The token needs read access to Gemma plus private dataset/model read and write access. The notebook clones the source repository and loads the [training template](chat_template_training.jinja) from its file before it pulls the latest prepared dataset revision directly from the Hub, verifies its common tool declaration and the resulting assistant-only loss masks, and trains the LoRA adapter in the Colab kernel. The preparation notebook validates the complete `messages`/`tools` schema and template before publication.

The notebook generates and parses a manually entered validation prompt, then publishes the summaries and private LoRA adapter.

#### Conversational task: Which task should the model perform?

The model acts as `ask`, a concise Zsh-terminal assistant, and uses the relevant terminal scrollback as context. For each request, it must either:

- propose one shell command for the user to review, or
- answer concisely in plain text when the user asks for an explanation or a command would not help.

A command proposal is exactly one `shell` function call containing only the command, followed by a short explanation.

#### Conversational goals: What interactions will the model support?

The model will handle the interactions documented in [examples.md](../docs/examples.md): creating, finding, compressing, fixing, explaining, and improving shell commands; common Git workflows; and project-aware requests such as running tests or locating an environment variable. It should use the supplied terminal history and conversation for the previous command, errors, and relevant project context.

For a command request, output exactly one structured `shell` tool call, followed by a short user-facing explanation. For explanation-only requests, output text only. Requests to edit source code, write documentation, or engage in general-purpose chat are outside the product scope; the model should say so briefly rather than fabricate a shell action.

The model must also support follow-up turns. When the user asks to fix or explain the previous command, it should use the prior command and its result. When the user adds a constraint to a canceled proposal, it should revise that proposal directly rather than ask for information already present in the conversation. A canceled proposal must never be treated as executed.

#### Data source and preparation: From where will conversational examples come?

Build examples from the documented `ask` use cases, and reviewed, synthetic terminal scenarios. Do not train on a user's raw terminal history unless it has explicit permission, has been scrubbed of credentials and personal data, and is appropriate to retain.

#### Success criteria: How will quality be measured?

Compare the tuned model with the untuned `google/gemma-4-E4B-it` baseline on the out-of-sample set and through human review. A response succeeds when it:

- selects text-only output versus a command proposal correctly;
- emits exactly one valid `shell` call when a command is needed;
- supplies a syntactically valid command that works in the supplied live directory;
- respects terminal context and constraints such as macOS compatibility; and
- is concise, helpful, and safe to present for review.

Record tool-call validity, command correctness under isolated test fixtures, relevance, and reviewer-rated helpfulness. Track unsafe or destructive proposals, leaked sensitive data, and scope violations as separate failure categories.

#### Use case: How will the tuned model be used?

`ask` will call the model when a user types `?` followed by a request in Zsh. The application supplies the relevant terminal context, renders a command proposal with run, edit, and cancel controls, and executes nothing until the user chooses run. Text-only explanations are displayed directly. The model is therefore an intent-to-proposal component, not an autonomous shell agent.

It is recommended that you aim for 100 to 200 conversational pairs for initial testing, and scale up to 1000+ examples for a more robust training if possible.
