import http.client as http_client
import logging
from typing import Dict, Tuple

from inspect_ai.util import SandboxEnvironment

from proxmoxsandbox._proxmox_sandbox_environment import (
    ProxmoxSandboxEnvironment,
    ProxmoxSandboxEnvironmentConfig,
)


def setup_requests_logging() -> None:
    http_client.HTTPConnection.debuglevel = 1
    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True


async def setup_sandbox(
    task_name: str, config: ProxmoxSandboxEnvironmentConfig
) -> Tuple[str, Dict[str, SandboxEnvironment]]:
    await ProxmoxSandboxEnvironment.task_init(task_name=task_name, config=config)
    envs_dict = await ProxmoxSandboxEnvironment.sample_init(
        task_name=task_name,
        config=config,
        metadata={},
    )
    return task_name, envs_dict
