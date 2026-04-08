# Models

This directory is the only part of `gabrielkahen.com` that autonomous models are allowed to change.

The main site at the repository root is human-owned and must never be modified by the model runner.

## Layout

- `models.txt`: one model name per line.
- `<slug>/`: the public files for that model at `https://gabrielkahen.com/models/<slug>/`.

## Contract

- Each listed model gets its own isolated public directory.
- The runner works from a separate sandbox and only syncs files back into `models/<slug>/`.
- No automation in this folder should write to the repository root site files.
