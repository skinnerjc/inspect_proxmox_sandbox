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
)

CURRENT_DIR = Path(__file__).parent


async def test_crystal_peak(proxmox_api) -> None:
    envs_dict = {}

    sdn_config = await InfraCommands(proxmox_api, node="proxmox").generate_sdn_config(
        aliases=("alias1", "alias2", None)
    )

    crystal_peak_vms = ( 
        VmConfig(
                vm_source_config=VmSourceConfig(built_in="ubuntu24.04"),
                vnet_aliases=("alias1", "alias2"),
            ),
        VmConfig(vm_source_config=VmSourceConfig(ova=Path("/home/ubuntu/src/AISI_CPEAK_ctf-evals-crystal-peak/vm_images/converted_ovas/cpeak-pt-isp-gateway-10.ova")), vnet_aliases=("alias1", "alias2"), is_sandbox=False, uefi_boot=True),
        VmConfig(vm_source_config=VmSourceConfig(ova=Path("/home/ubuntu/src/AISI_CPEAK_ctf-evals-crystal-peak/vm_images/converted_ovas/cpeak-pt-local-agent-10.ova")), vnet_aliases=("alias1", "alias2"), is_sandbox=False, uefi_boot=True),
        VmConfig(vm_source_config=VmSourceConfig(ova=Path("/home/ubuntu/src/AISI_CPEAK_ctf-evals-crystal-peak/vm_images/converted_ovas/cpeak-pt-local-gateway.ova")), vnet_aliases=("alias1", "alias2"), is_sandbox=False, uefi_boot=True),
        VmConfig(vm_source_config=VmSourceConfig(ova=Path("/home/ubuntu/src/AISI_CPEAK_ctf-evals-crystal-peak/vm_images/converted_ovas/cpeak-pt-acmenet-gateway.ova")), vnet_aliases=("alias1", "alias2"), is_sandbox=False, uefi_boot=True),
        VmConfig(vm_source_config=VmSourceConfig(ova=Path("/home/ubuntu/src/AISI_CPEAK_ctf-evals-crystal-peak/vm_images/converted_ovas/cpeak-pt-acmenet-api.ova")), vnet_aliases=("alias1", "alias2"), is_sandbox=False, uefi_boot=True),
        VmConfig(vm_source_config=VmSourceConfig(ova=Path("/home/ubuntu/src/AISI_CPEAK_ctf-evals-crystal-peak/vm_images/converted_ovas/cpeak-pt-acmenet-db.ova")), vnet_aliases=("alias1", "alias2"), is_sandbox=False, uefi_boot=True),
        VmConfig(vm_source_config=VmSourceConfig(ova=Path("/home/ubuntu/src/AISI_CPEAK_ctf-evals-crystal-peak/vm_images/converted_ovas/cpeak-pt-acmenet-jump.ova")), vnet_aliases=("alias1", "alias2"), is_sandbox=False, uefi_boot=True),
        VmConfig(vm_source_config=VmSourceConfig(ova=Path("/home/ubuntu/src/AISI_CPEAK_ctf-evals-crystal-peak/vm_images/converted_ovas/cpeak-pt-acmenet-nfs.ova")), vnet_aliases=("alias1", "alias2"), is_sandbox=False, uefi_boot=True),
        VmConfig(vm_source_config=VmSourceConfig(ova=Path("/home/ubuntu/src/AISI_CPEAK_ctf-evals-crystal-peak/vm_images/converted_ovas/cpeak-pt-acmenet-alice.ova")), vnet_aliases=("alias1", "alias2"), is_sandbox=False, uefi_boot=True),
        VmConfig(vm_source_config=VmSourceConfig(ova=Path("/home/ubuntu/src/AISI_CPEAK_ctf-evals-crystal-peak/vm_images/converted_ovas/cpeak-pt-acmenet-bob-10.ova")), vnet_aliases=("alias1", "alias2"), is_sandbox=False, uefi_boot=True),
        VmConfig(vm_source_config=VmSourceConfig(ova=Path("/home/ubuntu/src/AISI_CPEAK_ctf-evals-crystal-peak/vm_images/converted_ovas/cpeak-pt-devcorp-gateway.ova")), vnet_aliases=("alias1", "alias2"), is_sandbox=False, uefi_boot=True),
        VmConfig(vm_source_config=VmSourceConfig(ova=Path("/home/ubuntu/src/AISI_CPEAK_ctf-evals-crystal-peak/vm_images/converted_ovas/cpeak-pt-devcorp-registry.ova")), vnet_aliases=("alias1", "alias2"), is_sandbox=False, uefi_boot=True),
        VmConfig(vm_source_config=VmSourceConfig(ova=Path("/home/ubuntu/src/AISI_CPEAK_ctf-evals-crystal-peak/vm_images/converted_ovas/cpeak-pt-devcorp-git.ova")), vnet_aliases=("alias1", "alias2"), is_sandbox=False, uefi_boot=True),
        VmConfig(vm_source_config=VmSourceConfig(ova=Path("/home/ubuntu/src/AISI_CPEAK_ctf-evals-crystal-peak/vm_images/converted_ovas/cpeak-pt-cloudnet-gateway.ova")), vnet_aliases=("alias1", "alias2"), is_sandbox=False, uefi_boot=True),
        VmConfig(vm_source_config=VmSourceConfig(ova=Path("/home/ubuntu/src/AISI_CPEAK_ctf-evals-crystal-peak/vm_images/converted_ovas/cpeak-pt-cloudnet-dns.ova")), vnet_aliases=("alias1", "alias2"), is_sandbox=False, uefi_boot=True),
        VmConfig(vm_source_config=VmSourceConfig(ova=Path("/home/ubuntu/src/AISI_CPEAK_ctf-evals-crystal-peak/vm_images/converted_ovas/cpeak-pt-cloudnet-vps1.ova")), vnet_aliases=("alias1", "alias2"), is_sandbox=False, uefi_boot=True),
        VmConfig(vm_source_config=VmSourceConfig(ova=Path("/home/ubuntu/src/AISI_CPEAK_ctf-evals-crystal-peak/vm_images/converted_ovas/cpeak-pt-cloudnet-vps2-10.ova")), vnet_aliases=("alias1", "alias2"), is_sandbox=False, uefi_boot=True),
    )



    sandbox_env_config = ProxmoxSandboxEnvironmentConfig(
        vms_config=crystal_peak_vms,
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
        # await ProxmoxSandboxEnvironment.sample_cleanup(
        #     task_name="unused",
        #     config=sandbox_env_config,
        #     environments=envs_dict,
        #     interrupted=False,
        # )
