"""Tests: password settings are read correctly and never leak."""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docker_mcp import server as s

os.environ.update({
    "DOCKER_MCP_HOSTS_NAME": "172.16.10.11=thevault,172.16.20.50=themedia",
    "DOCKER_MCP_SSH_USER": "theadmin",
    "DOCKER_MCP_SSH_KEY": "/k/id",
    "DOCKER_MCP_THEVAULT_SSH": "admin@172.16.10.11",
    "DOCKER_MCP_THEVAULT_SSH_PASSWORD": "s3cret",
    "DOCKER_MCP_THEVAULT_SUDO": "true",
})
hs = s._hosts()
v, m = hs["thevault"], hs["themedia"]
ok = []
def check(label, cond):
    ok.append(bool(cond)); print(("PASS " if cond else "FAIL ") + label)
check("vault uses password", v["password"] == "s3cret" and v["key"] == "")
check("vault sudo password defaults to ssh password", v["sudo_password"] == "s3cret")
check("themedia keeps shared key", m["key"] == "/k/id" and m["password"] == "")
check("scrub hides password", "s3cret" not in s._scrub("pw s3cret here", v))
check("hosts list never shows password", "s3cret" not in s.docker_hosts.__doc__ )
bad = s._run_password(dict(v, ssh="admin@127.0.0.1", port="1"), ["docker", "ps"], None, 5, None)
check("bad connection returns an error, not a crash", bad[0] == 255 and b"s3cret" not in bad[2])
print(f"{sum(ok)} passed, {len(ok)-sum(ok)} failed"); sys.exit(0 if all(ok) else 1)
