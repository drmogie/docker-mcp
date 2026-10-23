# Changelog

## 2026.10.23.01

- SSH passwords: set `DOCKER_MCP_<NAME>_SSH_PASSWORD` for one host, or `DOCKER_MCP_SSH_PASSWORD` for all. Works like the Pi 5 tool. Uses `paramiko`, a new dependency.
- Sudo passwords: `DOCKER_MCP_<NAME>_SUDO_PASSWORD` or `DOCKER_MCP_SUDO_PASSWORD`. Default is the SSH password.
- A host's own key or password wins over the shared one. Hosts with keys work as before.
- Passwords are removed from all output. `docker_hosts` shows the login type (key or password), never the password.

## 2026.10.22.02

- Fix: `DOCKER_MCP_HOSTS_NAME` with `ip=name` pairs now works on its own. In `.01` the setting `DOCKER_MCP_HOSTS` was still needed.

## 2026.10.22.01

- Files on the host: `docker_file_list`, `docker_file_read`, `docker_file_write`, `docker_file_edit`, `docker_file_mkdir`, `docker_file_move`, `docker_file_delete`. They only work inside the stacks folder and folders listed in `DOCKER_MCP_FILE_ROOTS`. Symlinks and `..` cannot escape.
- Secret files (.env, keys, credentials) are never shown or edited, but `.env` can be written. Text with a hidden secret placeholder is refused, so a real secret cannot be overwritten by mistake. Writes keep the old file as `.bak`.
- `docker_copy`: copy files into or out of a container (docker cp).
- `docker_build`: build an image from a host folder or an https git URL. `docker_tag_image`.
- `docker_stack_write`: create a stack or replace its compose file, then check it. A failed check puts the old file back. `docker_stack_logs`.
- `docker_stack_action` has new actions: build, build_no_cache, up_build, recreate.
- `docker_run`: start a container (ports, env, volumes, network, restart). No privileged mode, devices, or docker socket.
- `docker_create`: make a network (macvlan, subnet, gateway, parent) or a volume (NFS options).
- `docker_host_ssh`: run one shell command on the host. Safe reads run right away, others need confirm, risky ones need a typed phrase. Same idea as `pikvm_ssh`.
- `docker_exec` can now use `shell=true`, `workdir` and `user`.
- New settings: `DOCKER_MCP_FILE_ROOTS`, `DOCKER_MCP_<NAME>_FILE_ROOTS`, `DOCKER_MCP_MAX_FILE_KB`, `DOCKER_MCP_BUILD_TIMEOUT`.
- New `DOCKER_MCP_HOSTS_NAME`: friendly names for the hosts (a list in the same order as `DOCKER_MCP_HOSTS`, or `ip=name` pairs). Hosts can now be listed by IP. Names and IPs both work in every tool, and `docker_hosts` shows both. Old configs work unchanged.
- File tools need a Linux host (they use find, head, realpath).

## 2026.10.20.01

- Many hosts with one key: new shared settings DOCKER_MCP_SSH_USER, DOCKER_MCP_SSH_KEY, DOCKER_MCP_SSH_PORT, DOCKER_MCP_SUDO and DOCKER_MCP_STACKS.
- With DOCKER_MCP_SSH_USER set, the host name is the address, so DOCKER_MCP_HOSTS="themedia,thedns01" is enough.
- A host's own setting still wins over the shared one. Old configs work unchanged.

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
