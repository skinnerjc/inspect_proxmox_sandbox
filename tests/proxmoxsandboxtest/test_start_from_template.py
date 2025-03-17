import pytest
from proxmoxsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from proxmoxsandbox.inspect.proxmox.built_in_vm import BuiltInVM
from proxmoxsandbox.inspect.proxmox_sandbox_environment import ProxmoxSandboxEnvironment
from proxmoxsandbox.inspect.schema import (
    ProxmoxSandboxEnvironmentConfig,
    VmConfig,
    VmSourceConfig,
)
from tests.proxmoxsandboxtest.proxmox_sandbox_utils import setup_sandbox


async def test_start_from_template(proxmox_api: AsyncProxmoxAPI) -> None:
    built_in_vm = BuiltInVM(proxmox_api, node="proxmox")
    await built_in_vm.ensure_exists(
        vm_source_config=VmSourceConfig(built_in="ubuntu24.04"),
    )

    envs_dict = {}
    sandbox_env_config = ProxmoxSandboxEnvironmentConfig(
        vms_config=(
            VmConfig(
                vm_source_config=VmSourceConfig(
                    existing_vm_template_tag="inspect-ubuntu24.04"  # coupling ourselves to the implementation of built_in_vm, naughty
                )
            ),
        )
    )
    try:
        task_name = "sandbox_test_restore"
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
