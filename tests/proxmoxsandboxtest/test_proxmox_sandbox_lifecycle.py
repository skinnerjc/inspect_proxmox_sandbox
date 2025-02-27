from proxmoxsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from proxmoxsandbox.inspect.proxmox.infra_commands import InfraCommands
from proxmoxsandbox.inspect.schema import (
    ProxmoxSandboxEnvironmentConfig,
)
from proxmoxsandboxtest.proxmox_sandbox_utils import (
    setup_requests_logging,
    setup_sandbox,
)

from proxmoxsandbox.inspect.proxmox_sandbox_environment import ProxmoxSandboxEnvironment


async def test_smoke() -> None:
    envs_dict = {}
    sandbox_env_config = ProxmoxSandboxEnvironmentConfig()
    try:
        task_name = "sandbox_test_smoketask"
        task_name, envs_dict = await setup_sandbox(task_name, sandbox_env_config)
        uname_result = await envs_dict["default"].exec(
            [
                "uname",
                "-a",
            ]
        )
        assert uname_result.success, f"Failed to run uname: {uname_result=}"
        assert "Ubuntu" in uname_result.stdout, (
            f"Unexpected result of uname: {uname_result.stdout=}"
        )
    finally:
        await ProxmoxSandboxEnvironment.sample_cleanup(
            task_name="unused",
            config=sandbox_env_config,
            environments=envs_dict,
            interrupted=False,
        )


async def test_multiple_sandboxes(sandbox_env_config) -> None:
    setup_requests_logging()

    sandboxes = {}

    try:
        task_name = "sandbox_1_task"
        task_name, envs_dict = await setup_sandbox(task_name, sandbox_env_config)
        sandboxes["first"] = envs_dict["default"]

        # Second time round, the sandbox should get a different SDN IP range
        task_name = "sandbox_2_task"
        task_name, envs_dict = await setup_sandbox(task_name, sandbox_env_config)
        sandboxes["second"] = envs_dict["default"]

        second_ip = (
            await sandboxes["second"].exec(
                [
                    "bash",
                    "-c",
                    'ip a | grep -oP "(?<=inet\s)\d+(\.\d+){3}" | grep -v "127\.0" ',
                ]
            )
        ).stdout.splitlines()
        if len(second_ip) != 1:
            raise Exception(f"Expected exactly one IP address, got {second_ip}")

        ping_result = await sandboxes["first"].exec(
            ["ping", "-c", "1", second_ip[0]], timeout=3
        )

        assert not ping_result.success, (
            f"Should not be able to ping between sandboxes; {ping_result=}"
        )
    finally:
        await ProxmoxSandboxEnvironment.sample_cleanup(
            task_name="unused",
            config=sandbox_env_config,
            environments=sandboxes,
            interrupted=False,
        )


async def test_multiple_vnets(proxmox_api: AsyncProxmoxAPI) -> None:
    envs_dict = {}
    sdn_config = await InfraCommands(proxmox_api, node="proxmox").generate_sdn_config(
        alias="interesting alias with ( . _ 0 and -"
    )
    sandbox_env_config = ProxmoxSandboxEnvironmentConfig(sdn_config=sdn_config)
    try:
        task_name = "sandbox_test_smoketask"
        task_name, envs_dict = await setup_sandbox(task_name, sandbox_env_config)
    finally:
        await ProxmoxSandboxEnvironment.sample_cleanup(
            task_name="unused",
            config=sandbox_env_config,
            environments=envs_dict,
            interrupted=False,
        )
