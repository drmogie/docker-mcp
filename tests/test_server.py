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
          "docker_stack_action", "docker_pull_image", "docker_remove", "docker_prune", "docker_exec"} <= tools, tools)
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


async def main():
    unit_tests()
    await run({}, reads)
    await run({}, changes)
    await run({}, destructive)
    await run({"DOCKER_MCP_READ_ONLY": "true"}, readonly)
    await run({"DOCKER_MCP_DOCKER_BIN": "/nonexistent/docker"}, errors)
    await run({"DOCKER_MCP_HOSTS": "a,b"}, multi)
    bad = RESULTS.count(False)
    print(f"\n{len(RESULTS) - bad} passed, {bad} failed")
    sys.exit(1 if bad else 0)


asyncio.run(main())
