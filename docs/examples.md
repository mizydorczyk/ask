## Use ask to...

### Create commands

```zsh
? create a Rust project in the parent directory
? find all PDF files modified in the last 7 days
? compress this folder into a tar.gz archive
```

`ask` displays its proposed command with controls to run it, place it in the
prompt for editing, or cancel it. The command is not executed until you choose
**run**.

### Fix commands

```zsh
? fix the previous command
? why did this fail?
? make this command work on macOS
```

### Explain commands

```zsh
? explain the previous command
? what does this awk command do?
? explain this git error
```

Explanation requests return text directly and do not show a command review.

### Improve commands

```zsh
? make this command faster
? simplify this pipeline
? make this command recursive
```

### Git workflows

```zsh
? undo my last commit but keep the changes
? squash the last 3 commits
? delete merged branches
```

### Project-aware tasks

```zsh
? run the test suite
? create a new feature branch
? find where this environment variable is used
```

## Don't use ask for...

- Editing source code
- Writing documentation
- General-purpose chat
