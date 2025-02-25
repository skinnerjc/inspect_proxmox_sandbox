import logging
from typing import Dict, Tuple

from vmsandbox.inspect.vm_sandbox_environment import (
    VmSandboxEnvironment,
    VmSandboxEnvironmentConfig,
)


def setup_requests_logging() -> None:
    # These two lines enable debugging at httplib level (requests->urllib3->http.client)
    # You will see the REQUEST, including HEADERS and DATA, and RESPONSE with HEADERS but without DATA.
    # The only thing missing will be the response.body which is not logged.

    import http.client as http_client

    http_client.HTTPConnection.debuglevel = 1

    # You must initialize logging, otherwise you'll not see debug output.
    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True

async def setup_sandbox(
    task_name: str,
    config: VmSandboxEnvironmentConfig
) -> Tuple[str, Dict[str, VmSandboxEnvironment]]:
    """Setup sandbox environment with given configuration"""
    await VmSandboxEnvironment.task_init(task_name=task_name, config=None)
    envs_dict = await VmSandboxEnvironment.sample_init(
        task_name=task_name,
        config=config,
        metadata={},
    )
    return task_name, envs_dict