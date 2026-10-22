"""Tests: run the MCP tool over stdio against a fake docker, call every tool."""
import asyncio, json, os, shutil, sys, tempfile
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
FAKE = str(ROOT / "tests" / "fake_docker")
RESULTS = []


def check(label, cond, detail=""):
    RESULTS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + label + ("" if cond else f"  -> {str(detail)[:500]}"))


async def call(session, name, args=None):
    r = await session.call_tool(name, args or {})
    return "\n".join(c.text for c in r.content if hasattr(c, "text"))


def calls(logfile):
    if not Path(logfile).exists():
        return []
    return [json.loads(x) for x in Path(logfile).read_text().splitlines() if x.strip()]


def wrote(logfile, word):
    """Did any recorded docker call use this word as an argument?"""
    return any(word in c["args"] for c in calls(logfile))


async def run(env_extra, body):
    with tempfile.TemporaryDirectory() as tmp:
        logfile = os.path.join(tmp, "calls.log")
        stacks = os.path.join(tmp, "stacks")
        os.makedirs(os.path.join(stacks, "arr-apps"))
        Path(stacks, "arr-apps", "compose.yaml").write_text(
            "services:\n  radarr:\n    environment:\n      PUID: ${PUID}\n      OPENVPN_PASSWORD: hunter2\n      PIA_PASSWORD: ${PIA_PASSWORD}\n")
        Path(stacks, "arr-apps", ".env").write_text("PIA_PASSWORD=supersecret\n")
        os.makedirs(os.path.join(stacks, "empty-folder"))
        fake = os.path.join(tmp, "fake_docker")  # copy it, so it can run even if the source folder blocks running files
        shutil.copy(FAKE, fake)
        os.chmod(fake, 0o755)
        env = {**os.environ, "DOCKER_MCP_DOCKER_BIN": fake, "FAKE_DOCKER_LOG": logfile,
               "DOCKER_MCP_HOSTS": "local", "DOCKER_MCP_LOCAL_STACKS": stacks,
               "FAKE_STACK_FILE": os.path.join(stacks, "arr-apps", "compose.yaml").replace("\\", "/"), **env_extra}
        params = StdioServerParameters(command=sys.executable, args=["-m", "docker_mcp"], cwd=str(ROOT), env=env)
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                await body(s, logfile)


async def reads(s, log):
    tools = {t.name for t in (await s.list_tools()).tools}
    check("all tools are listed", {"docker_hosts", "docker_ps", "docker_logs", "docker_inspect", "docker_stats",
          "docker_images", "docker_volumes", "docker_networks", "docker_disk_usage", "docker_stacks",
          "docker_stack_status", "docker_stack_file", "docker_stack_config", "docker_container_action",
          "docker_stack_action", "docker_pull_image", "docker_remove", "docker_prune", "docker_exec",
          "docker_file_list", "docker_file_read", "docker_file_write", "docker_file_edit", "docker_file_mkdir",
          "docker_file_move", "docker_file_delete", "docker_copy", "docker_stack_write", "docker_stack_logs",
          "docker_build", "docker_tag_image", "docker_run", "docker_create", "docker_host_ssh"} <= tools, tools)
    t = await call(s, "docker_hosts")
    check("hosts: shows docker and compose version", "27.3.1" in t and "2.33.0" in t, t)
    t = await call(s, "docker_ps")
    check("ps: lists both containers", "plex" in t and "seerr" in t and "Exited" in t, t)
    t = await call(s, "docker_ps", {"name_contains": "see"})
    check("ps: filter by name", "seerr" in t and "plex" not in t, t)
    t = await call(s, "docker_logs", {"container": "gluetun", "tail": 50})
    check("logs: shows lines", "start ok" in t, t)
    check("logs: password and token hidden", "hunter2" not in t and "abc123" not in t and "hidden" in t, t)
    t = await call(s, "docker_inspect", {"name": "gluetun"})
    check("inspect container: ip and health", "172.16.30.59" in t and "healthy" in t, t)
    check("inspect container: secrets hidden, plain env kept", "hunter2" not in t and "p1234567" not in t and "PUID=1000" in t, t)
    t = await call(s, "docker_inspect", {"name": "audiobookshelf_themedia", "kind": "volume"})
    check("inspect volume: shows nfs options", "nfsvers=3" in t and "172.16.1.11" in t, t)
    for tool, word in [("docker_stats", "300MiB"), ("docker_images", "plexinc"), ("docker_volumes", "audiobookshelf_themedia"),
                       ("docker_networks", "macvlan"), ("docker_disk_usage", "Images")]:
        t = await call(s, tool)
        check(f"{tool} works", word in t, t)
    t = await call(s, "docker_stacks")
    check("stacks: lists folder with compose file, skips empty one", "arr-apps" in t and "empty-folder" not in t and "running(5)" in t, t)
    t = await call(s, "docker_stack_status", {"stack": "arr-apps"})
    check("stack status", "radarr" in t and "7878" in t, t)
    t = await call(s, "docker_stack_file", {"stack": "arr-apps"})
    check("stack file: secret hidden, reference kept", "hunter2" not in t and "${PIA_PASSWORD}" in t and "PUID" in t, t)
    check("stack file: .env never shown", "supersecret" not in t, t)
    t = await call(s, "docker_stack_config", {"stack": "arr-apps"})
    check("stack config: password hidden", "hunter2" not in t and "TZ: America/Los_Angeles" in t, t)
    c = [x for x in calls(log) if x["args"][:2] == ["compose", "config"]]
    check("stack config ran inside the stack folder", c and c[0]["cwd"].endswith("arr-apps"), c)
    t = await call(s, "docker_stack_file", {"stack": "nope"})
    check("unknown stack is refused", "No stack 'nope'" in t, t)
    t = await call(s, "docker_stack_file", {"stack": "../etc"})
    check("bad stack name is refused", "Bad stack name" in t, t)
    t = await call(s, "docker_logs", {"container": "x; rm -rf /"})
    check("bad container name is refused", "Bad container name" in t, t)
    t = await call(s, "docker_logs", {"container": "plex", "since": "1h; ls"})
    check("bad since is refused", "Bad since" in t, t)
    t = await call(s, "docker_inspect", {"name": "x", "kind": "everything"})
    check("bad kind is refused", "kind must be" in t, t)


async def changes(s, log):
    t = await call(s, "docker_container_action", {"container": "plex", "action": "restart"})
    check("change without confirm: NOT RUN", t.startswith("NOT RUN") and not wrote(log, "restart"), t)
    t = await call(s, "docker_container_action", {"container": "plex", "action": "restart", "confirm": True})
    check("change with confirm: runs", t.startswith("Done") and wrote(log, "restart"), t)
    t = await call(s, "docker_container_action", {"container": "plex", "action": "delete", "confirm": True})
    check("bad action is refused", "action must be" in t, t)
    t = await call(s, "docker_stack_action", {"stack": "arr-apps", "action": "update"})
    check("stack update without confirm: NOT RUN", t.startswith("NOT RUN") and not wrote(log, "pull"), t)
    t = await call(s, "docker_stack_action", {"stack": "arr-apps", "action": "update", "confirm": True})
    pulls = [x for x in calls(log) if x["args"][:2] == ["compose", "pull"]]
    ups = [x for x in calls(log) if x["args"][:3] == ["compose", "up", "-d"]]
    check("stack update runs pull then up in the stack folder", t.startswith("Done") and pulls and ups and ups[0]["cwd"].endswith("arr-apps"), (t, pulls, ups))
    t = await call(s, "docker_pull_image", {"image": "ghcr.io/seerr-team/seerr:latest"})
    check("pull image without confirm: NOT RUN", t.startswith("NOT RUN") and not wrote(log, "pull") or len([x for x in calls(log) if x["args"][:1] == ["pull"]]) == 0, t)
    t = await call(s, "docker_pull_image", {"image": "bad image;"})
    check("bad image name is refused", "Bad image name" in t, t)


async def destructive(s, log):
    t = await call(s, "docker_stack_action", {"stack": "arr-apps", "action": "down", "confirm": True})
    check("down with confirm but no phrase: NOT RUN", t.startswith("NOT RUN") and "local stack arr-apps down" in t and not wrote(log, "down"), t)
    t = await call(s, "docker_stack_action", {"stack": "arr-apps", "action": "down", "confirm": True, "confirm_phrase": "local stack arr-apps up"})
    check("down with wrong phrase: NOT RUN", t.startswith("NOT RUN") and not wrote(log, "down"), t)
    t = await call(s, "docker_stack_action", {"stack": "arr-apps", "action": "down", "confirm": True, "confirm_phrase": "local stack arr-apps down"})
    check("down with right phrase: runs", t.startswith("Done") and wrote(log, "down"), t)
    t = await call(s, "docker_stack_action", {"stack": "arr-apps", "action": "down_volumes", "confirm": True, "confirm_phrase": "local stack arr-apps down_volumes"})
    check("down_volumes with right phrase: runs with --volumes", t.startswith("Done") and wrote(log, "--volumes"), t)
    t = await call(s, "docker_remove", {"kind": "volume", "name": "audiobookshelf_themedia"})
    check("remove without confirm: NOT RUN", t.startswith("NOT RUN") and not wrote(log, "rm"), t)
    t = await call(s, "docker_remove", {"kind": "volume", "name": "audiobookshelf_themedia", "confirm": True,
                                        "confirm_phrase": "local remove volume audiobookshelf_themedia"})
    rm = [x for x in calls(log) if x["args"][:3] == ["volume", "rm", "audiobookshelf_themedia"]]
    check("remove volume with phrase: runs", t.startswith("Done") and rm, t)
    t = await call(s, "docker_remove", {"kind": "container", "name": "plex", "confirm": True, "confirm_phrase": "local remove container plex"})
    rm = [x for x in calls(log) if x["args"] == ["rm", "plex"]]
    check("remove container never uses force", rm and "-f" not in rm[0]["args"], t)
    t = await call(s, "docker_prune", {"what": "volumes"})
    check("prune without confirm: NOT RUN", t.startswith("NOT RUN") and not wrote(log, "prune"), t)
    t = await call(s, "docker_prune", {"what": "images", "confirm": True, "confirm_phrase": "local prune images"})
    prune = [x for x in calls(log) if x["args"][:2] == ["image", "prune"]]
    check("prune images: only unused untagged (no -a)", t.startswith("Done") and prune and "-a" not in prune[0]["args"], t)
    t = await call(s, "docker_prune", {"what": "everything"})
    check("bad prune target is refused", "what must be" in t, t)
    t = await call(s, "docker_exec", {"container": "plex", "command": "ls -la /config"})
    check("exec without confirm: NOT RUN", t.startswith("NOT RUN") and not wrote(log, "exec"), t)
    t = await call(s, "docker_exec", {"container": "plex", "command": "ls -la /config", "confirm": True, "confirm_phrase": "local exec plex"})
    ex = [x for x in calls(log) if x["args"][:1] == ["exec"]]
    check("exec with phrase: runs, no shell, no tty", "ran: ls -la /config" in t and ex and "-it" not in ex[0]["args"] and "-t" not in ex[0]["args"], t)


async def newtools(s, log):
    # find the stacks folder the harness made
    t = await call(s, "docker_file_list", {"depth": 2})
    check("file list: shows stack and compose file", "arr-apps" in t and "compose.yaml" in t, t)
    root = next(x.split(" ", 5)[5] for x in t.splitlines() if x.endswith("/arr-apps/compose.yaml")).rsplit("/arr-apps", 1)[0]
    t = await call(s, "docker_file_list", {"path": "/etc"})
    check("file list: outside folder refused", "outside the allowed folders" in t, t)
    t = await call(s, "docker_file_read", {"path": "arr-apps/../../etc/passwd"})
    check("file read: .. escape refused", "outside the allowed folders" in t, t)
    t = await call(s, "docker_file_read", {"path": "arr-apps/compose.yaml"})
    check("file read: secret hidden, reference kept", "hunter2" not in t and "${PIA_PASSWORD}" in t, t)
    t = await call(s, "docker_file_read", {"path": "arr-apps/.env"})
    check("file read: .env refused", "holds secrets" in t and "supersecret" not in t, t)
    t = await call(s, "docker_file_write", {"path": "app/data/hello.txt", "content": "hi\r\nthere\n"})
    check("file write without confirm: NOT RUN", t.startswith("NOT RUN") and not Path(root, "app").exists(), t)
    t = await call(s, "docker_file_write", {"path": "app/data/hello.txt", "content": "hi\r\nthere\n", "confirm": True})
    f = Path(root, "app", "data", "hello.txt")
    check("file write: creates folders and keeps exact bytes", t.startswith("Done") and f.read_bytes() == b"hi\r\nthere\n", t)
    t = await call(s, "docker_file_write", {"path": "app/run.sh", "content": "#!/bin/sh\n", "mode": "755", "confirm": True})
    check("file write: mode applied", oct(Path(root, "app", "run.sh").stat().st_mode & 0o777) == "0o755", t)
    t = await call(s, "docker_file_write", {"path": "app/data/hello.txt", "content": "x ***hidden*** y", "confirm": True})
    check("file write: hidden placeholder refused", "Refusing" in t and f.read_bytes() == b"hi\r\nthere\n", t)
    t = await call(s, "docker_file_write", {"path": "../x.txt", "content": "x", "confirm": True})
    check("file write: escape refused", "outside the allowed folders" in t, t)
    t = await call(s, "docker_file_write", {"path": "app/data/hello.txt", "content": "new\n", "confirm": True})
    check("file write: replaces and keeps a .bak", t.startswith("Done") and f.read_text() == "new\n" and Path(str(f) + ".bak").read_bytes() == b"hi\r\nthere\n", t)
    link = Path(root, "app", "evil")
    link.symlink_to("/etc")
    t = await call(s, "docker_file_read", {"path": "app/evil/passwd"})
    check("file read: symlink out of the folder refused", "symlink" in t, t)
    link.unlink()
    f.write_text("a=1\nb=2\na=1\n")
    t = await call(s, "docker_file_edit", {"path": "app/data/hello.txt", "old_string": "b=2", "new_string": "b=3"})
    check("file edit without confirm: NOT RUN", t.startswith("NOT RUN") and "b=2" in f.read_text(), t)
    t = await call(s, "docker_file_edit", {"path": "app/data/hello.txt", "old_string": "b=2", "new_string": "b=3", "confirm": True})
    check("file edit: one change", t.startswith("Done") and f.read_text() == "a=1\nb=3\na=1\n", t)
    t = await call(s, "docker_file_edit", {"path": "app/data/hello.txt", "old_string": "a=1", "new_string": "a=9", "confirm": True})
    check("file edit: not unique is refused", "2 times" in t and "a=9" not in f.read_text(), t)
    t = await call(s, "docker_file_edit", {"path": "app/data/hello.txt", "old_string": "a=1", "new_string": "a=9", "replace_all": True, "confirm": True})
    check("file edit: replace_all", f.read_text() == "a=9\nb=3\na=9\n", t)
    t = await call(s, "docker_file_edit", {"path": "app/data/hello.txt", "old_string": "zzz", "new_string": "y", "confirm": True})
    check("file edit: missing text reported", "not found" in t, t)
    t = await call(s, "docker_file_edit", {"path": "arr-apps/.env", "old_string": "a", "new_string": "b", "confirm": True})
    check("file edit: .env refused", "holds secrets" in t, t)
    t = await call(s, "docker_file_write", {"path": "arr-apps/.env", "content": "PIA_PASSWORD=new\n", "confirm": True})
    check("file write: .env can be written", t.startswith("Done") and Path(root, "arr-apps", ".env").read_text() == "PIA_PASSWORD=new\n", t)
    t = await call(s, "docker_file_mkdir", {"path": "app/logs", "confirm": True})
    check("mkdir", t.startswith("Done") and Path(root, "app", "logs").is_dir(), t)
    t = await call(s, "docker_file_move", {"source": "app/data/hello.txt", "destination": "app/logs/hello.txt", "confirm": True})
    check("move", t.startswith("Done") and Path(root, "app", "logs", "hello.txt").exists() and not f.exists(), t)
    t = await call(s, "docker_file_move", {"source": ".", "destination": "app/x", "confirm": True})
    check("move of the root folder refused", "root folder" in t, t)
    t = await call(s, "docker_file_delete", {"path": "app/logs/hello.txt", "confirm": True})
    check("delete without phrase: NOT RUN", t.startswith("NOT RUN") and Path(root, "app", "logs", "hello.txt").exists(), t)
    t = await call(s, "docker_file_delete", {"path": "app/logs/hello.txt", "confirm": True, "confirm_phrase": f"local delete {root}/app/logs/hello.txt"})
    check("delete with phrase", t.startswith("Done") and not Path(root, "app", "logs", "hello.txt").exists(), t)
    t = await call(s, "docker_file_delete", {"path": "app", "confirm": True, "confirm_phrase": f"local delete {root}/app"})
    check("delete non-empty folder needs recursive", t.startswith("ERROR") and Path(root, "app").exists(), t)
    t = await call(s, "docker_file_delete", {"path": "app", "recursive": True, "confirm": True, "confirm_phrase": f"local delete {root}/app"})
    check("delete recursive", t.startswith("Done") and not Path(root, "app").exists(), t)
    t = await call(s, "docker_file_delete", {"path": ".", "confirm": True, "confirm_phrase": f"local delete {root}"})
    check("delete of the root folder refused", "root folder" in t, t)

    # stack write: the fake `compose config -q` passes; a bad one is rolled back below
    t = await call(s, "docker_stack_write", {"stack": "newapp", "content": "services:\n  a:\n    image: nginx\n"})
    check("stack write without confirm: NOT RUN", t.startswith("NOT RUN") and not Path(root, "newapp").exists(), t)
    t = await call(s, "docker_stack_write", {"stack": "newapp", "content": "services:\n  a:\n    image: nginx\n", "confirm": True})
    check("stack write: creates and checks", t.startswith("Done") and Path(root, "newapp", "compose.yaml").exists() and wrote(log, "-q"), t)
    t = await call(s, "docker_stack_write", {"stack": "arr-apps", "content": "services: FAIL_CONFIG\n", "confirm": True})
    check("stack write: failed check puts the old file back",
          "did not pass" in t and "OPENVPN_PASSWORD: hunter2" in Path(root, "arr-apps", "compose.yaml").read_text(), t)
    t = await call(s, "docker_stack_logs", {"stack": "arr-apps", "service": "radarr", "tail": 5})
    lg = [x for x in calls(log) if x["args"][:2] == ["compose", "logs"]]
    check("stack logs runs in the stack folder", lg and lg[0]["cwd"].endswith("arr-apps") and "radarr" in lg[0]["args"], (t, lg))

    # copy
    t = await call(s, "docker_copy", {"container": "plex", "container_path": "/config/a.txt", "host_path": "arr-apps/compose.yaml", "direction": "to_container"})
    check("copy without confirm: NOT RUN", t.startswith("NOT RUN") and not wrote(log, "cp"), t)
    t = await call(s, "docker_copy", {"container": "plex", "container_path": "/config/a.txt", "host_path": "arr-apps/compose.yaml", "direction": "to_container", "confirm": True})
    cp = [x for x in calls(log) if x["args"][:1] == ["cp"]]
    check("copy to container", t.startswith("Done") and cp and cp[0]["args"][1].endswith("compose.yaml") and cp[0]["args"][2] == "plex:/config/a.txt", (t, cp))
    t = await call(s, "docker_copy", {"container": "plex", "container_path": "/config/../etc/x", "host_path": "arr-apps/x", "direction": "from_container", "confirm": True})
    check("copy: .. in container path refused", "Bad container_path" in t, t)
    t = await call(s, "docker_copy", {"container": "plex", "container_path": "/a", "host_path": "/etc/passwd", "direction": "from_container", "confirm": True})
    check("copy: host path outside refused", "outside the allowed folders" in t, t)

    # build
    t = await call(s, "docker_build", {"context": "arr-apps", "tag": "myapp:1", "build_args": {"VERSION": "1", "API_TOKEN": "tok999"}})
    check("build without confirm: NOT RUN and secret arg hidden", t.startswith("NOT RUN") and "tok999" not in t and not wrote(log, "build"), t)
    t = await call(s, "docker_build", {"context": "arr-apps", "tag": "myapp:1", "dockerfile": "Dockerfile.dev", "build_args": {"VERSION": "1"}, "no_cache": True, "confirm": True})
    b = [x for x in calls(log) if x["args"][:1] == ["build"]]
    check("build runs with tag, file, args, no-cache", t.startswith("Done") and b and "myapp:1" in b[0]["args"] and "--no-cache" in b[0]["args"] and "VERSION=1" in b[0]["args"] and b[0]["args"][-1].endswith("arr-apps"), (t, b))
    t = await call(s, "docker_build", {"context": "https://github.com/drmogie/docker-mcp.git#main", "tag": "x:1", "confirm": True})
    check("build from a git URL", t.startswith("Done"), t)
    t = await call(s, "docker_build", {"context": "http://evil.example/x", "tag": "x:1", "confirm": True})
    check("build: non-https URL refused", "Bad context" in t, t)
    t = await call(s, "docker_build", {"context": "arr-apps", "tag": "x:1", "dockerfile": "../../etc/x", "confirm": True})
    check("build: bad dockerfile refused", "Bad dockerfile" in t, t)
    t = await call(s, "docker_build", {"context": "arr-apps", "tag": "x:1", "build_args": {"BAD KEY": "1"}, "confirm": True})
    check("build: bad arg name refused", "Bad build arg" in t, t)
    t = await call(s, "docker_stack_action", {"stack": "arr-apps", "action": "up_build", "confirm": True})
    check("stack up_build", t.startswith("Done") and wrote(log, "--build"), t)
    t = await call(s, "docker_stack_action", {"stack": "arr-apps", "action": "build_no_cache", "confirm": True})
    check("stack build_no_cache", t.startswith("Done") and wrote(log, "--no-cache"), t)

    # tag, run, create
    t = await call(s, "docker_tag_image", {"source": "myapp:1", "target": "myapp:latest", "confirm": True})
    check("tag image", t.startswith("Done") and wrote(log, "tag"), t)
    t = await call(s, "docker_run", {"image": "nginx:latest", "name": "web", "ports": ["8080:80"], "env": {"TZ": "UTC", "DB_PASSWORD": "pw777"},
                                    "volumes": [f"{root}/newapp:/data:ro", "named:/x"], "network": "THEDMZ"})
    check("run without confirm: NOT RUN and secret hidden", t.startswith("NOT RUN") and "pw777" not in t, t)
    t = await call(s, "docker_run", {"image": "nginx:latest", "name": "web", "ports": ["8080:80"], "env": {"TZ": "UTC"},
                                    "volumes": [f"{root}/newapp:/data:ro", "named:/x"], "network": "THEDMZ", "command": "nginx -g 'daemon off;'", "confirm": True})
    r = [x for x in calls(log) if x["args"][:2] == ["run", "-d"]]
    check("run: builds the right command", t.startswith("Done") and r and "--restart" in r[0]["args"] and "8080:80" in r[0]["args"] and f"{root}/newapp:/data:ro" in r[0]["args"] and r[0]["args"][-3:] == ["nginx", "-g", "daemon off;"] and "--privileged" not in r[0]["args"], (t, r))
    for bad, why in [({"volumes": ["/var/run/docker.sock:/s"]}, "docker socket"), ({"volumes": ["/etc:/e"]}, "host /etc"), ({"ports": ["80;ls"]}, "bad port"), ({"restart": "always; ls"}, "bad restart"), ({"env": {"A B": "1"}}, "bad env")]:
        t = await call(s, "docker_run", {"image": "nginx", "confirm": True, **bad})
        check(f"run: {why} refused", "NOT RUN" not in t and t.startswith(("Bad", "Path", "restart", "ERROR")) , t)
    t = await call(s, "docker_create", {"kind": "network", "name": "THEX", "driver": "macvlan", "subnet": "172.16.40.0/24", "gateway": "172.16.40.1", "parent": "eth0.40", "confirm": True})
    n = [x for x in calls(log) if x["args"][:2] == ["network", "create"]]
    check("create macvlan network", t.startswith("Done") and n and "parent=eth0.40" in n[0]["args"] and "--subnet" in n[0]["args"] and n[0]["args"][-1] == "THEX", (t, n))
    t = await call(s, "docker_create", {"kind": "volume", "name": "nfsvol", "options": {"type": "nfs", "o": "addr=1.2.3.4,nfsvers=3", "device": ":/x"}, "confirm": True})
    v = [x for x in calls(log) if x["args"][:2] == ["volume", "create"]]
    check("create nfs volume", t.startswith("Done") and v and "type=nfs" in v[0]["args"] and "--opt" in v[0]["args"], (t, v))
    t = await call(s, "docker_create", {"kind": "network", "name": "N", "subnet": "not-a-subnet", "confirm": True})
    check("create: bad subnet refused", "Bad address" in t, t)

    # exec upgrades and host command
    t = await call(s, "docker_exec", {"container": "plex", "command": "ls | wc -l", "shell": True, "workdir": "/config", "user": "abc", "confirm": True, "confirm_phrase": "local exec plex"})
    ex = [x for x in calls(log) if x["args"][:1] == ["exec"] and "-w" in x["args"]]
    check("exec: shell, workdir and user", ex and ex[0]["args"][1:5] == ["-w", "/config", "-u", "abc"] and ex[0]["args"][-3:] == ["sh", "-c", "ls | wc -l"], (t, ex))
    t = await call(s, "docker_host_ssh", {"command": "ls -la | head -5"})
    check("host command: safe read runs right away", not t.startswith("NOT RUN") and "ERROR" not in t, t)
    t = await call(s, "docker_host_ssh", {"command": "touch x.txt"})
    check("host command: change needs confirm", t.startswith("NOT RUN") and not Path(root, "x.txt").exists(), t)
    t = await call(s, "docker_host_ssh", {"command": "touch x.txt", "confirm": True})
    check("host command: runs with confirm in the stacks folder", Path(root, "x.txt").exists(), t)
    t = await call(s, "docker_host_ssh", {"command": "rm x.txt", "confirm": True})
    check("host command: rm needs the phrase", t.startswith("NOT RUN") and Path(root, "x.txt").exists() and "local ssh rm" in t, t)
    t = await call(s, "docker_host_ssh", {"command": "rm x.txt", "confirm": True, "confirm_phrase": "local ssh rm"})
    check("host command: rm with phrase", not Path(root, "x.txt").exists(), t)
    t = await call(s, "docker_host_ssh", {"command": "cat arr-apps/.env"})
    check("host command: .env blocked", "blocked" in t and "supersecret" not in t, t)


async def newtools_readonly(s, log):
    for tool, args in [("docker_file_write", {"path": "a.txt", "content": "x"}), ("docker_build", {"context": "arr-apps", "tag": "x:1"}),
                       ("docker_run", {"image": "nginx"}), ("docker_create", {"kind": "volume", "name": "v"}),
                       ("docker_stack_write", {"stack": "z", "content": "services: {}"}), ("docker_host_ssh", {"command": "touch x"})]:
        t = await call(s, tool, {**args, "confirm": True})
        check(f"read-only: {tool} refused", t.startswith("NOT RUN") and "Read-only" in t, t)
    t = await call(s, "docker_file_list")
    check("read-only: file list still works", "arr-apps" in t, t)


async def readonly(s, log):
    t = await call(s, "docker_container_action", {"container": "plex", "action": "restart", "confirm": True})
    check("read-only mode refuses even with confirm", t.startswith("NOT RUN") and "Read-only" in t and not wrote(log, "restart"), t)
    t = await call(s, "docker_ps")
    check("read-only mode still reads", "plex" in t, t)


async def errors(s, log):
    t = await call(s, "docker_hosts")
    check("a broken docker shows an error, not a crash", "error" in t.lower(), t)


async def multi(s, log):
    t = await call(s, "docker_ps")
    check("two hosts: must pick one", t.startswith("Which host?") and "a" in t and "b" in t, t)
    t = await call(s, "docker_ps", {"host": "zzz"})
    check("unknown host is refused", "Unknown host" in t, t)
    t = await call(s, "docker_ps", {"host": "a"})
    check("named host works", "plex" in t, t)


def unit_tests():
    sys.path.insert(0, str(ROOT))
    from docker_mcp import server as sv
    h = {"name": "t", "ssh": "theadmin@themedia", "port": "2222", "key": "C:\\keys\\id", "sudo": False, "stacks": "/opt/stacks"}
    cmd = sv._ssh_cmd(h, ["docker", "logs", "a b; rm -rf /"], cwd="/opt/stacks/arr apps")
    check("ssh: batch mode, port, key, and `--` before the target", "BatchMode=yes" in cmd and "-p" in cmd and "2222" in cmd and "-i" in cmd and cmd[-3] == "--", cmd)
    check("ssh: remote command is quoted", "'a b; rm -rf /'" in cmd[-1] and cmd[-1].startswith("cd '/opt/stacks/arr apps' && docker logs"), cmd[-1])
    try:
        sv._ssh_cmd({**h, "ssh": "-oProxyCommand=evil"}, ["docker", "ps"])
        check("ssh: target starting with - is refused", False)
    except ValueError:
        check("ssh: target starting with - is refused", True)
    check("redact: yaml line", sv._redact_text("    API_TOKEN: abc") == "    API_TOKEN: ***hidden***", sv._redact_text("    API_TOKEN: abc"))
    check("redact: list style env", sv._redact_text("      - PIA_PASSWORD=pw").endswith("***hidden***"), sv._redact_text("      - PIA_PASSWORD=pw"))
    check("redact: variable reference kept", sv._redact_text("  PIA_PASSWORD: ${PIA_PASSWORD}") == "  PIA_PASSWORD: ${PIA_PASSWORD}")
    check("redact: bearer token in a log line", "abc123" not in sv._redact_text("10:00 request Bearer abc123xyz ok"), sv._redact_text("10:00 request Bearer abc123xyz ok"))
    check("redact: normal lines kept", sv._redact_text("  TZ: America/Los_Angeles") == "  TZ: America/Los_Angeles")

    # shared settings: many hosts, one key
    import os
    keep = {k: v for k, v in os.environ.items() if k.startswith("DOCKER_MCP_")}
    for k in keep:
        del os.environ[k]
    os.environ.update({"DOCKER_MCP_HOSTS": "a,b,local", "DOCKER_MCP_SSH_USER": "theadmin", "DOCKER_MCP_SSH_KEY": "/k/id", "DOCKER_MCP_STACKS": "/srv/stacks", "DOCKER_MCP_B_SSH": "root@10.0.0.9", "DOCKER_MCP_B_STACKS": "/opt/b"})
    hh = sv._hosts()
    check("shared: host name becomes the address", hh["a"]["ssh"] == "theadmin@a", hh["a"])
    check("shared: one key and stacks folder for every host", hh["a"]["key"] == "/k/id" and hh["a"]["stacks"] == "/srv/stacks", hh["a"])
    check("shared: a host's own setting wins", hh["b"]["ssh"] == "root@10.0.0.9" and hh["b"]["stacks"] == "/opt/b" and hh["b"]["key"] == "/k/id", hh["b"])
    check("shared: host called local stays local", hh["local"]["ssh"] == "", hh["local"])
    for k in [k for k in os.environ if k.startswith("DOCKER_MCP_")]:
        del os.environ[k]
    os.environ.update({"DOCKER_MCP_HOSTS": "themedia", "DOCKER_MCP_THEMEDIA_SSH": "theadmin@themedia", "DOCKER_MCP_THEMEDIA_SSH_KEY": "/k/old"})
    old = sv._hosts()["themedia"]
    check("old per-host config still works", old["ssh"] == "theadmin@themedia" and old["key"] == "/k/old" and old["stacks"] == "/opt/stacks", old)
    for k in [k for k in os.environ if k.startswith("DOCKER_MCP_")]:
        del os.environ[k]
    # friendly names: pairs and positional list
    os.environ.update({"DOCKER_MCP_HOSTS": "172.16.20.50,172.16.20.40,172.16.20.11", "DOCKER_MCP_SSH_USER": "theadmin",
                       "DOCKER_MCP_HOSTS_NAME": "172.16.20.40=thedmz,172.16.20.50=themedia", "DOCKER_MCP_THEMEDIA_SUDO": "true",
                       "DOCKER_MCP_172_16_20_40_STACKS": "/srv/dmz"})
    nh = sv._hosts()
    check("names (pairs): friendly name, IP kept for ssh", nh["themedia"]["ssh"] == "theadmin@172.16.20.50" and nh["thedmz"]["address"] == "172.16.20.40", list(nh))
    check("names (pairs): unnamed host keeps its IP as name", "172.16.20.11" in nh, list(nh))
    check("names: settings by friendly name or by IP", nh["themedia"]["sudo"] and nh["thedmz"]["stacks"] == "/srv/dmz", nh)
    check("names: pick by name, by IP, and case", sv._pick("themedia")[0]["name"] == "themedia" and sv._pick("172.16.20.40")[0]["name"] == "thedmz" and sv._pick("TheDMZ")[0] is not None)
    check("names: unknown host lists names with IPs", "themedia (172.16.20.50)" in sv._pick("zzz")[1], sv._pick("zzz")[1])
    os.environ["DOCKER_MCP_HOSTS_NAME"] = "themedia,thedmz"
    nl = sv._hosts()
    check("names (list): same order as hosts", nl["themedia"]["address"] == "172.16.20.50" and nl["thedmz"]["address"] == "172.16.20.40" and "172.16.20.11" in nl, list(nl))
    os.environ["DOCKER_MCP_HOSTS_NAME"] = ",,thedns"
    ns = sv._hosts()
    check("names (list): empty slot keeps the IP, others still named", "172.16.20.50" in ns and "172.16.20.40" in ns and ns["thedns"]["address"] == "172.16.20.11", list(ns))
    del os.environ["DOCKER_MCP_HOSTS_NAME"]
    check("names are optional", list(sv._hosts()) == ["172.16.20.50", "172.16.20.40", "172.16.20.11"], list(sv._hosts()))
    for k in [k for k in os.environ if k.startswith("DOCKER_MCP_")]:
        del os.environ[k]
    os.environ.update(keep)


async def main():
    unit_tests()
    await run({}, reads)
    await run({}, changes)
    await run({}, destructive)
    await run({}, newtools)
    await run({"DOCKER_MCP_READ_ONLY": "true"}, newtools_readonly)
    await run({"DOCKER_MCP_READ_ONLY": "true"}, readonly)
    await run({"DOCKER_MCP_DOCKER_BIN": "/nonexistent/docker"}, errors)
    await run({"DOCKER_MCP_HOSTS": "a,b"}, multi)
    bad = RESULTS.count(False)
    print(f"\n{len(RESULTS) - bad} passed, {bad} failed")
    sys.exit(1 if bad else 0)


asyncio.run(main())
