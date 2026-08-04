# ask — ask the Zsh shell

Turn natural language into shell commands.

```zsh
? create a Rust project in the parent directory
? explain the previous command
? fix this git error
```

Type `?` followed by your request. `ask` understands your terminal context and turns your intent into shell commands you can review before running.

## Install

From this repository:

```sh
uv tool install .
```

This installs the `ask` executable. `uv` is not needed after installation.

Enable the Zsh integration in the current shell:

```zsh
eval "$(ask initialize)"
```

To enable it for new shells, add that line to `~/.zshrc` after your `PATH`
setup.

The first request may cause macOS to ask for permission to automate
Terminal.app. Allow it so `ask` can read scrollback for the invoking terminal
tab.

See `docs/examples.md` for examples.

## Development

```sh
uv tool install --editable .
uv run python -m unittest discover -s tests -v
```

An editable installation runs directly from this working directory, so source
changes take effect without reinstalling.
