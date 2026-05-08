from __future__ import annotations

import os
import posixpath
import secrets
import time
from dataclasses import dataclass
from typing import Callable, Optional

import paramiko


SPLUNK_TGZ_URL = "https://download.splunk.com/products/splunk/releases/10.0.0/linux/splunk-10.0.0-e8eb0c4654f8-linux-amd64.tgz"
REMOTE_TGZ_PATH = "/opt/splunk-10.0.0-linux-amd64.tgz"
SPLUNK_HOME = "/opt/splunk"


@dataclass(frozen=True)
class Host:
    name: str
    hostname: str
    username: str
    ssh_port: int = 22


class DeployError(RuntimeError):
    pass


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def connect(host: Host, pem_path: str, timeout_s: int = 30) -> paramiko.SSHClient:
    key = None
    key_errors: list[str] = []
    for key_cls in (paramiko.RSAKey, paramiko.ECDSAKey, paramiko.Ed25519Key):
        try:
            key = key_cls.from_private_key_file(pem_path)
            break
        except Exception as e:  # noqa: BLE001
            key_errors.append(f"{key_cls.__name__}: {e}")
    if key is None:
        raise DeployError("Unable to load PEM key. Tried: " + "; ".join(key_errors))

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host.hostname,
        port=host.ssh_port,
        username=host.username,
        pkey=key,
        timeout=timeout_s,
        banner_timeout=timeout_s,
        auth_timeout=timeout_s,
    )
    return client


def run(
    ssh: paramiko.SSHClient,
    cmd: str,
    *,
    sudo: bool = False,
    timeout_s: int = 600,
    log: Optional[Callable[[str], None]] = None,
) -> str:
    full = cmd if not sudo else f"sudo -n bash -lc {sh_quote(cmd)}"
    if log:
        log(f"[{_now()}] $ {full}")
    stdin, stdout, stderr = ssh.exec_command(full, timeout=timeout_s)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    if code != 0:
        raise DeployError(f"Command failed (exit {code}): {full}\nSTDOUT:\n{out}\nSTDERR:\n{err}")
    return out.strip()


def sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def ensure_splunk_installed(
    ssh: paramiko.SSHClient,
    *,
    splunk_admin_password: str,
    log: Optional[Callable[[str], None]] = None,
) -> None:
    run(ssh, "mkdir -p /opt", sudo=True, log=log)
    run(
        ssh,
        f"test -d {SPLUNK_HOME} || (wget -q -O {REMOTE_TGZ_PATH} {sh_quote(SPLUNK_TGZ_URL)} && tar -xzf {REMOTE_TGZ_PATH} -C /opt)",
        sudo=True,
        log=log,
        timeout_s=1200,
    )

    seed = f"{SPLUNK_HOME}/etc/system/local/user-seed.conf"
    run(
        ssh,
        f"if [ ! -f {seed} ]; then "
        f"mkdir -p {posixpath.dirname(seed)} && "
        f"printf '%s\\n' "
        f"'[user_info]' "
        f"'USERNAME = admin' "
        f"'PASSWORD = {splunk_admin_password}' "
        f"> {seed}; "
        f"fi",
        sudo=True,
        log=log,
    )

    run(ssh, f"{SPLUNK_HOME}/bin/splunk enable boot-start -systemd-managed 0 --accept-license --answer-yes --no-prompt", sudo=True, log=log)
    run(ssh, f"{SPLUNK_HOME}/bin/splunk start --accept-license --answer-yes --no-prompt", sudo=True, log=log)


def set_servername(ssh: paramiko.SSHClient, name: str, *, log: Optional[Callable[[str], None]] = None) -> None:
    run(ssh, f"{SPLUNK_HOME}/bin/splunk set servername {sh_quote(name)} -auth admin:changeme || true", sudo=True, log=log)


def configure_deployer(
    deployer: paramiko.SSHClient,
    *,
    shc_secret: str,
    splunk_admin_password: str,
    log: Optional[Callable[[str], None]] = None,
) -> None:
    run(
        deployer,
        f"{SPLUNK_HOME}/bin/splunk edit shcluster-config -mode deployer -secret {sh_quote(shc_secret)} "
        f"-auth admin:{sh_quote(splunk_admin_password)}",
        sudo=True,
        log=log,
    )
    run(deployer, f"{SPLUNK_HOME}/bin/splunk restart -auth admin:{sh_quote(splunk_admin_password)}", sudo=True, log=log)


def configure_sh_member(
    sh: paramiko.SSHClient,
    *,
    mgmt_uri_host: str,
    replication_port: int,
    shc_secret: str,
    deployer_mgmt_uri: str,
    splunk_admin_password: str,
    log: Optional[Callable[[str], None]] = None,
) -> None:
    run(
        sh,
        f"{SPLUNK_HOME}/bin/splunk edit shcluster-config "
        f"-mode member "
        f"-mgmt_uri https://{mgmt_uri_host}:8089 "
        f"-replication_port {replication_port} "
        f"-secret {sh_quote(shc_secret)} "
        f"-shcluster_label shcluster1 "
        f"-conf_deploy_fetch_url {sh_quote(deployer_mgmt_uri)} "
        f"-auth admin:{sh_quote(splunk_admin_password)}",
        sudo=True,
        log=log,
    )
    run(sh, f"{SPLUNK_HOME}/bin/splunk restart -auth admin:{sh_quote(splunk_admin_password)}", sudo=True, log=log)


def bootstrap_captain(
    sh1: paramiko.SSHClient,
    *,
    sh1_mgmt_uri: str,
    splunk_admin_password: str,
    log: Optional[Callable[[str], None]] = None,
) -> None:
    run(
        sh1,
        f"{SPLUNK_HOME}/bin/splunk bootstrap shcluster-captain -servers_list {sh_quote(sh1_mgmt_uri)} "
        f"-auth admin:{sh_quote(splunk_admin_password)}",
        sudo=True,
        log=log,
    )


def push_bundle(
    deployer: paramiko.SSHClient,
    *,
    captain_mgmt_uri: str,
    splunk_admin_password: str,
    log: Optional[Callable[[str], None]] = None,
) -> None:
    run(
        deployer,
        f"{SPLUNK_HOME}/bin/splunk apply shcluster-bundle -target {sh_quote(captain_mgmt_uri)} "
        f"-auth admin:{sh_quote(splunk_admin_password)} -preserve-lookups true",
        sudo=True,
        log=log,
        timeout_s=1800,
    )


def ensure_app_on_deployer(
    deployer: paramiko.SSHClient,
    app_folder_name: str,
    *,
    log: Optional[Callable[[str], None]] = None,
) -> str:
    if "/" in app_folder_name or "\\" in app_folder_name or app_folder_name.strip() == "":
        raise DeployError("App folder name must be a simple folder name (no slashes).")
    app_path = f"{SPLUNK_HOME}/etc/shcluster/apps/{app_folder_name}"
    run(deployer, f"mkdir -p {app_path}/default", sudo=True, log=log)
    run(
        deployer,
        f"test -f {app_path}/default/app.conf || printf '%s\\n' '[install]' 'is_configured = 1' > {app_path}/default/app.conf",
        sudo=True,
        log=log,
    )
    return app_path


def deploy_shc(
    *,
    pem_path: str,
    deployer_host: Host,
    sh_hosts: list[Host],
    splunk_admin_password: str,
    shc_secret: Optional[str] = None,
    replication_port_start: int = 9887,
    force_sh1_captain: bool = True,
    log: Optional[Callable[[str], None]] = None,
) -> dict:
    if len(sh_hosts) != 3:
        raise DeployError("Expected exactly 3 search head members (sh1, sh2, sh3).")
    if shc_secret is None or shc_secret.strip() == "":
        shc_secret = secrets.token_urlsafe(24)

    def _log(msg: str) -> None:
        if log:
            log(msg)

    _log(f"[{_now()}] Connecting to deployer {deployer_host.hostname}")
    dep = connect(deployer_host, pem_path)
    try:
        ensure_splunk_installed(dep, splunk_admin_password=splunk_admin_password, log=_log)
        set_servername(dep, deployer_host.name, log=_log)
        configure_deployer(dep, shc_secret=shc_secret, splunk_admin_password=splunk_admin_password, log=_log)

        deployer_mgmt_uri = f"https://{deployer_host.hostname}:8089"

        sh_sessions: list[tuple[Host, paramiko.SSHClient]] = []
        try:
            for idx, h in enumerate(sh_hosts):
                _log(f"[{_now()}] Connecting to {h.name} {h.hostname}")
                ssh = connect(h, pem_path)
                sh_sessions.append((h, ssh))
                ensure_splunk_installed(ssh, splunk_admin_password=splunk_admin_password, log=_log)
                set_servername(ssh, h.name, log=_log)
                configure_sh_member(
                    ssh,
                    mgmt_uri_host=h.hostname,
                    replication_port=replication_port_start + idx,
                    shc_secret=shc_secret,
                    deployer_mgmt_uri=deployer_mgmt_uri,
                    splunk_admin_password=splunk_admin_password,
                    log=_log,
                )

            sh1 = sh_sessions[0][1]
            sh1_mgmt_uri = f"https://{sh_hosts[0].hostname}:8089"
            if force_sh1_captain:
                bootstrap_captain(sh1, sh1_mgmt_uri=sh1_mgmt_uri, splunk_admin_password=splunk_admin_password, log=_log)

            return {
                "shc_secret": shc_secret,
                "deployer_mgmt_uri": deployer_mgmt_uri,
                "captain_mgmt_uri": sh1_mgmt_uri,
            }
        finally:
            for _, s in sh_sessions:
                try:
                    s.close()
                except Exception:
                    pass
    finally:
        try:
            dep.close()
        except Exception:
            pass


def deploy_app_to_shc(
    *,
    pem_path: str,
    deployer_host: Host,
    captain_host: Host,
    splunk_admin_password: str,
    app_folder_name: str,
    log: Optional[Callable[[str], None]] = None,
) -> dict:
    dep = connect(deployer_host, pem_path)
    try:
        ensure_app_on_deployer(dep, app_folder_name, log=log)
        captain_mgmt_uri = f"https://{captain_host.hostname}:8089"
        push_bundle(dep, captain_mgmt_uri=captain_mgmt_uri, splunk_admin_password=splunk_admin_password, log=log)
        return {"app": app_folder_name, "captain_mgmt_uri": captain_mgmt_uri}
    finally:
        try:
            dep.close()
        except Exception:
            pass
