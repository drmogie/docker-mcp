# docker-mcp

An MCP tool that lets Claude look at and manage Docker.

It works with containers, images, volumes, networks, and Compose stacks.
It connects to your Docker host over SSH with a key. Nothing is installed on the host.

## What Claude can do

Read (runs right away):

- `docker_hosts`: list hosts and test the connection
- `docker_ps`: list containers
- `docker_logs`: last lines of a container log
- `docker_inspect`: details of a container, volume, network or image
- `docker_stats`: CPU and memory right now
- `docker_images`, `docker_volumes`, `docker_networks`, `docker_disk_usage`
- `docker_stacks`: Compose stacks (one folder each), and whether they run
- `docker_stack_status`: containers of one stack
- `docker_stack_file`: the compose file, secrets hidden
- `docker_stack_config`: the final compose file with the .env filled in. Good for finding a wrong value

Change (needs `confirm=true`, Claude must ask you first):

- `docker_container_action`: start, stop, restart, pause, unpause
- `docker_stack_action`: up, pull, update (pull then up), start, stop, restart
- `docker_pull_image`

Destructive (needs `confirm=true` and a typed phrase):

- `docker_stack_action` with down or down_volumes. Phrase: `<host> stack <stack> down`
- `docker_remove`: container, image, volume, network. Phrase: `<host> remove <kind> <name>`
- `docker_prune`: containers, images, networks, volumes, builder. Phrase: `<host> prune <what>`
- `docker_exec`: run one command inside a container. Phrase: `<host> exec <container>`

## Safety

- Claude cannot run any docker command it likes. Only the tools above exist.
- Every name is checked. No shell tricks get through.
- Remove never forces. A running container is not removed.
- Image prune only removes unused untagged images.
- Secrets (passwords, tokens, keys, usernames) are hidden in compose files, logs and inspect output. A variable reference such as `${PIA_PASSWORD}` is shown as is. This is best effort for free text in logs.
- The `.env` files are never read.
- Set `DOCKER_MCP_READ_ONLY=true` to refuse every change.

## Setup

1. On your PC, make an SSH key if you do not have one:
   `ssh-keygen -t ed25519`
2. Put the key on the Docker host:
   `ssh-copy-id theadmin@themedia`
   On Windows without ssh-copy-id, append the contents of `id_ed25519.pub` to `~/.ssh/authorized_keys` on the host.
3. Log in once by hand, so SSH trusts the host: `ssh theadmin@themedia`
4. Let the user run Docker without sudo, on the host:
   `sudo usermod -aG docker theadmin`
   then log out and back in.
   (Or set `DOCKER_MCP_THEMEDIA_SUDO=true` and allow `sudo` with no password for docker.)
5. Copy the settings from `claude_desktop_config.example.json` into your Claude config. Change the key path.
   `uvx` downloads the tool from GitHub, so no local copy is needed. To get a newer version, run `uvx --refresh --from git+https://github.com/drmogie/docker-mcp docker-mcp` once, or pin a release with `@2026.10.20.01` after the address.
6. Restart Claude. Ask: "list my Docker hosts".

## Settings

Set in the `env` part of the Claude config.

- `DOCKER_MCP_HOSTS`: host names, comma separated. If empty, one host called `local` uses docker on the same machine.
- For each host, with NAME in capitals:
  - `DOCKER_MCP_NAME_SSH`: user@address. Leave empty for local docker.
  - `DOCKER_MCP_NAME_SSH_PORT`: port, default 22
  - `DOCKER_MCP_NAME_SSH_KEY`: path to the private key
  - `DOCKER_MCP_NAME_SUDO`: `true` to run docker with `sudo -n`
  - `DOCKER_MCP_NAME_STACKS`: folder with one sub folder per stack, default `/opt/stacks`
- Shared settings, for many hosts with one key (a host's own setting always wins):
  - `DOCKER_MCP_SSH_USER`: login name. The host name is used as the address (`user@name`)
  - `DOCKER_MCP_SSH_KEY`: one private key for all hosts
  - `DOCKER_MCP_SSH_PORT`, `DOCKER_MCP_SUDO`, `DOCKER_MCP_STACKS`: same idea
- `DOCKER_MCP_READ_ONLY`: `true` refuses every change
- `DOCKER_MCP_TIMEOUT`: seconds for normal commands, default 60
- `DOCKER_MCP_LONG_TIMEOUT`: seconds for pull and up, default 900

Stacks are found as `<stacks folder>/<name>/compose.yaml`. Compose runs inside that folder, so its `.env` file works as normal.

## Tests

The tests use a fake `docker` program. No Docker is needed.

    pip install "mcp>=1.2,<2"
    python tests/test_server.py

## Notes

- Several hosts work. Set `DOCKER_MCP_HOSTS=a,b` and Claude must say which one.
- On Windows, local docker works too (Docker Desktop). Stack folders are found on the local disk.
- Compose needs to be installed on the host (`docker compose version`).
