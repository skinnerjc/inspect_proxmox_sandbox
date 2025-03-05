import pytest
from proxmoxsandbox.inspect.proxmox_sandbox_environment import ProxmoxSandboxEnvironment
from proxmoxsandbox.inspect.schema import (
    ProxmoxSandboxEnvironmentConfig,
    VmConfig,
    VmSourceConfig,
)
from tests.proxmoxsandboxtest.proxmox_sandbox_utils import setup_sandbox

# Skipped because this is coupled to my range
@pytest.mark.skip
async def test_restore() -> None:
    envs_dict = {}
    sandbox_env_config = ProxmoxSandboxEnvironmentConfig(
        vms_config=(
            VmConfig(
                vm_source_config=VmSourceConfig(
                    existing_backup_name="vzdump-qemu-113-2025_03_05-12_35_48.vma.zst"
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

