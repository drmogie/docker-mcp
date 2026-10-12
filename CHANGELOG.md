# Changelog

## 2026.10.12.01

- First GitHub release. No code change.
- The example config installs the tool from GitHub (`git+https://github.com/drmogie/docker-mcp`) instead of a local folder.

## 2026.10.11.01

- First build.
- Read tools: hosts, ps, logs, inspect (container, volume, network, image), stats, images, volumes, networks, disk usage, stacks, stack status, stack file, stack config.
- Change tools (need confirm): container start, stop, restart, pause, unpause. Stack up, pull, update, start, stop, restart. Pull image.
- Destructive tools (need confirm and a typed phrase): remove container, image, volume, network. Prune. Exec in a container. Stack down and down with volumes.
- Connects over SSH with a key. Local docker also works. Read-only mode.
- Secrets are hidden in compose files, logs, inspect output. The .env files are never read.
