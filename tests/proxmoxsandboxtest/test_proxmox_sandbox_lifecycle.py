from pathlib import Path

from proxmoxsandboxtest.proxmox_sandbox_utils import (
    setup_requests_logging,
    setup_sandbox,
)

from proxmoxsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from proxmoxsandbox.inspect.proxmox.infra_commands import InfraCommands
from proxmoxsandbox.inspect.proxmox_sandbox_environment import ProxmoxSandboxEnvironment
from proxmoxsandbox.inspect.schema import (
    ProxmoxSandboxEnvironmentConfig,
    VmConfig,
    VmSourceConfig,
    VmNicConfig
)

CURRENT_DIR = Path(__file__).parent


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

        # this is known to fail as you need to use the Proxmox firewall
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
    # TODO rewrite this to check VmConfig.nics
    pass

async def test_vnet_mix_alias_or_not(proxmox_api: AsyncProxmoxAPI) -> None:
    # TODO rewrite this to check VmConfig.nics
    pass



async def test_ova() -> None:
    envs_dict = {}
    sandbox_env_config = ProxmoxSandboxEnvironmentConfig(
        vms_config=(
            VmConfig(
                vm_source_config=VmSourceConfig(
                    ova=CURRENT_DIR / ".." / "oVirtTinyCore64-13.11.ova"
                ),
                ram_mb=512,
                vcpus=3
            ),
        )
    )
    try:
        task_name, envs_dict = await setup_sandbox("tcova", sandbox_env_config)
        uname_result = await envs_dict["default"].exec(
            [
                "uname",
                "-a",
            ]
        )
        assert uname_result.success, f"Failed to run uname: {uname_result=}"
        assert "tinycore" in uname_result.stdout, (
            f"Unexpected result of uname: {uname_result.stdout=}"
        )
    finally:
        await ProxmoxSandboxEnvironment.sample_cleanup(
            task_name="unused",
            config=sandbox_env_config,
            environments=envs_dict,
            interrupted=False,
        )


async def test_everything(proxmox_api) -> None:
    envs_dict = {}

    sdn_config = await InfraCommands(proxmox_api, node="proxmox").generate_sdn_config(
        aliases=("alias1", "alias2", None)
    )

    sandbox_env_config = ProxmoxSandboxEnvironmentConfig(
        vms_config=(
            VmConfig(
                vm_source_config=VmSourceConfig(built_in="ubuntu24.04"),
                nics=(VmNicConfig(vnet_alias="alias1"), VmNicConfig(vnet_alias="alias2")),
            ),
            VmConfig(
                vm_source_config=VmSourceConfig(built_in="ubuntu24.04"),
                nics=(VmNicConfig(vnet_alias="alias1"),),
            ),
            VmConfig(
                vm_source_config=VmSourceConfig(
                    ova=Path("./tests/oVirtTinyCore64-13.11.ova")
                ),
                nics=(VmNicConfig(vnet_alias="alias1"), VmNicConfig(vnet_alias="alias2")),
                is_sandbox=True,
            ),
            VmConfig(
                vm_source_config=VmSourceConfig(
                    ova=Path("./tests/oVirtTinyCore64-13.11.ova")
                ),
                is_sandbox=False,
            ),
        ),
        sdn_config=sdn_config,
    )
    try:
        task_name, envs_dict = await setup_sandbox("tcova", sandbox_env_config)
        uname_result = await envs_dict["default"].exec(
            [
                "uname",
                "-a",
            ]
        )
        assert uname_result.success, f"Failed to run uname: {uname_result=}"
        assert "ubuntu" in uname_result.stdout, (
            f"Unexpected result of uname: {uname_result.stdout=}"
        )
    finally:
        pass
        await ProxmoxSandboxEnvironment.sample_cleanup(
            task_name="unused",
            config=sandbox_env_config,
            environments=envs_dict,
            interrupted=False,
        )
