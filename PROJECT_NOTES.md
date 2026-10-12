# Project notes: docker-mcp

- Version format: YYYY.MM.DD.## (daily counter always two digits). Current: 2026.10.11.01. Python package version: 2026.10.11.1.
- Same design as arr-mcp: three tiers (read, change, destructive), confirm flag, typed phrase for destructive.
- Built for: themedia (Linux Docker host, arr stack, stacks at /opt/stacks, settings at /opt/docker/<service>).
- Not done: a second host (Synology), Docker events, Compose file editing, a container-only guard list.
- Ideas: protect list (containers that can never be stopped, such as gluetun), stack file editing with a diff preview, log search.
- Tests: `python tests/test_server.py` (needs `mcp>=1.2,<2`). The fake docker is copied to a temp folder, because some mounts do not allow running files.
