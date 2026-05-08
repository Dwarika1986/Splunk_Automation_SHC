from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from deploy_engine import DeployError, Host, deploy_app_to_shc, deploy_shc


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"  # queued|running|success|error
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    logs: list[str] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def log(self, msg: str) -> None:
        self.logs.append(msg)
        self.updated_at = time.time()


_JOBS: dict[str, Job] = {}
_LOCK = threading.Lock()


def create_job(kind: str) -> Job:
    job = Job(id=str(uuid.uuid4()), kind=kind)
    with _LOCK:
        _JOBS[job.id] = job
    return job


def get_job(job_id: str) -> Optional[Job]:
    with _LOCK:
        return _JOBS.get(job_id)


def start_deploy_job(
    *,
    pem_path: str,
    username: str,
    deployer_ip: str,
    sh1_ip: str,
    sh2_ip: str,
    sh3_ip: str,
    splunk_admin_password: str,
    shc_secret: str,
    force_sh1_captain: bool,
) -> Job:
    job = create_job("deploy_shc")

    def runner() -> None:
        job.status = "running"
        job.updated_at = time.time()
        try:
            result = deploy_shc(
                pem_path=pem_path,
                deployer_host=Host(name="deployer", hostname=deployer_ip, username=username),
                sh_hosts=[
                    Host(name="sh1", hostname=sh1_ip, username=username),
                    Host(name="sh2", hostname=sh2_ip, username=username),
                    Host(name="sh3", hostname=sh3_ip, username=username),
                ],
                splunk_admin_password=splunk_admin_password,
                shc_secret=shc_secret or None,
                force_sh1_captain=force_sh1_captain,
                log=job.log,
            )
            job.result = result
            job.status = "success"
        except DeployError as e:
            job.error = str(e)
            job.status = "error"
        except Exception as e:  # noqa: BLE001
            job.error = f"Unexpected error: {e}"
            job.status = "error"
        finally:
            job.updated_at = time.time()

    threading.Thread(target=runner, daemon=True).start()
    return job


def start_deploy_app_job(
    *,
    pem_path: str,
    username: str,
    deployer_ip: str,
    captain_ip: str,
    splunk_admin_password: str,
    app_folder_name: str,
) -> Job:
    job = create_job("deploy_app")

    def runner() -> None:
        job.status = "running"
        job.updated_at = time.time()
        try:
            result = deploy_app_to_shc(
                pem_path=pem_path,
                deployer_host=Host(name="deployer", hostname=deployer_ip, username=username),
                captain_host=Host(name="sh1", hostname=captain_ip, username=username),
                splunk_admin_password=splunk_admin_password,
                app_folder_name=app_folder_name,
                log=job.log,
            )
            job.result = result
            job.status = "success"
        except DeployError as e:
            job.error = str(e)
            job.status = "error"
        except Exception as e:  # noqa: BLE001
            job.error = f"Unexpected error: {e}"
            job.status = "error"
        finally:
            job.updated_at = time.time()

    threading.Thread(target=runner, daemon=True).start()
    return job


def ensure_upload_dir() -> str:
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "uploads"))
    os.makedirs(path, exist_ok=True)
    return path

