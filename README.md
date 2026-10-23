# docker-mcp

An MCP tool that lets Claude look at and manage Docker.

It works with containers, images, volumes, networks, and Compose stacks.
It connects to your Docker host over SSH with a key or a password. Nothing is installed on the host.

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

- `docker_file_list`, `docker_file_read`: look at files on the host (secret files never shown)
- `docker_stack_logs`: log lines of a whole stack or one service

Change (needs `confirm=true`, Claude must ask you first):

- `docker_container_action`: start, stop, restart, pause, unpause
- `docker_stack_action`: up, pull, update (pull then up), start, stop, restart, build, build_no_cache, up_build, recreate
- `docker_pull_image`, `docker_tag_image`
- `docker_build`: build an image from a host folder or an https git URL
- `docker_file_write`: create or replace a file (old one kept as `.bak`)
- `docker_file_edit`: replace some text in a file
- `docker_file_mkdir`, `docker_file_move`
- `docker_copy`: copy files into or out of a container
- `docker_stack_write`: create a stack or replace its compose file, then check it (rolled back if the check fails)
- `docker_run`: start a container (no privileged mode, no devices, no docker socket)
- `docker_create`: make a network (macvlan too) or a volume (NFS too)
- `docker_host_ssh`: one shell command on the host. Safe reads run right away. Others need confirm. Risky ones (rm, mv, chmod, systemctl, apt, reboot, sudo ...) also need the phrase `<host> ssh <first word>`

Destructive (needs `confirm=true` and a typed phrase):

- `docker_stack_action` with down or down_volumes. Phrase: `<host> stack <stack> down`
- `docker_remove`: container, image, volume, network. Phrase: `<host> remove <kind> <name>`
- `docker_prune`: containers, images, networks, volumes, builder. Phrase: `<host> prune <what>`
- `docker_exec`: run one command inside a container (`shell=true` for pipes, plus `workdir` and `user`). Phrase: `<host> exec <container>`
- `docker_file_delete`: delete a file or folder (`recursive=true` for a full folder). Phrase: `<host> delete <path>`

## Safety

- Claude cannot run any docker command it likes. Only the tools above exist.
- Every name is checked. No shell tricks get through.
- File tools only touch the stacks folder and folders in `DOCKER_MCP_FILE_ROOTS`. `..` and symlinks that leave those folders are refused. The roots themselves cannot be moved or deleted.
- Text containing `***hidden***` is refused when writing, so a hidden secret is never overwritten. Put secrets in `.env` and use `${VAR}` in compose files.
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

### Using a password instead of a key

Good for a NAS such as a Synology that rejects keys.

- Set `DOCKER_MCP_THEVAULT_SSH=user@172.16.10.11` and `DOCKER_MCP_THEVAULT_SSH_PASSWORD=your-password`.
- If docker needs sudo, also set `DOCKER_MCP_THEVAULT_SUDO=true`. The SSH password is used for sudo too, unless you set `DOCKER_MCP_THEVAULT_SUDO_PASSWORD`.
- The password lives only in your Claude config. It is hidden from all output.
- Other hosts can keep using the shared key.

## Settings

Set in the `env` part of the Claude config.

- `DOCKER_MCP_HOSTS`: hosts, comma separated. Each one is a name or an IP address. If empty, one host called `local` uses docker on the same machine.
- `DOCKER_MCP_HOSTS_NAME`: (easiest: just this one, as `ip=name` pairs, and `DOCKER_MCP_HOSTS` can be left out) friendly names for the hosts, so you can say "themedia" and Claude knows the IP. Optional. Two ways (a blank slot, like `themedia,,thedmz`, skips a host):
  - a list in the same order: `DOCKER_MCP_HOSTS=172.16.20.50,172.16.20.40` and `DOCKER_MCP_HOSTS_NAME=themedia,thedmz`
  - pairs: `DOCKER_MCP_HOSTS_NAME=172.16.20.50=themedia,172.16.20.40=thedmz`

  SSH still connects to the IP. Claude can use the name or the IP, and the tool lists both. In the per-host settings below, NAME can be the friendly name or the IP with dots as underscores.
- For each host, with NAME in capitals:
  - `DOCKER_MCP_NAME_SSH`: user@address. Leave empty for local docker.
  - `DOCKER_MCP_NAME_SSH_PORT`: port, default 22
  - `DOCKER_MCP_NAME_SSH_KEY`: path to the private key
  - `DOCKER_MCP_NAME_SSH_PASSWORD`: SSH password, instead of a key
  - `DOCKER_MCP_NAME_SUDO`: `true` to run docker with sudo (`sudo -n` with no password set)
  - `DOCKER_MCP_NAME_SUDO_PASSWORD`: sudo password. Default: the SSH password
  - `DOCKER_MCP_NAME_STACKS`: folder with one sub folder per stack, default `/opt/stacks`
- Shared settings, for many hosts with one key (a host's own setting always wins):
  - `DOCKER_MCP_SSH_USER`: login name. The host name is used as the address (`user@name`)
  - `DOCKER_MCP_SSH_KEY`: one private key for all hosts
  - `DOCKER_MCP_SSH_PASSWORD`: one SSH password for all hosts. A host's own key or password wins
  - `DOCKER_MCP_SUDO_PASSWORD`: one sudo password for all hosts
  - `DOCKER_MCP_SSH_PORT`, `DOCKER_MCP_SUDO`, `DOCKER_MCP_STACKS`: same idea
- `DOCKER_MCP_FILE_ROOTS`: extra host folders the file, copy and build tools may use, comma separated (the stacks folder is always allowed). Per host: `DOCKER_MCP_NAME_FILE_ROOTS`
- `DOCKER_MCP_MAX_FILE_KB`: biggest file to read or write, default 1024
- `DOCKER_MCP_BUILD_TIMEOUT`: seconds for docker build, default 1800
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
- The file tools need a Linux host (they use `find`, `head`, `realpath`). Write access depends on the SSH user: files that containers made as root may not be writable.
- Compose needs to be installed on the host (`docker compose version`).
