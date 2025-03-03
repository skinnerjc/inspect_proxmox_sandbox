from pathlib import Path

from proxmoxsandboxtest.proxmox_sandbox_utils import (
    setup_sandbox,
)

from proxmoxsandbox.inspect.proxmox.infra_commands import InfraCommands
from proxmoxsandbox.inspect.schema import (
    ProxmoxSandboxEnvironmentConfig,
    SdnConfig,
    VmConfig,
    VmSourceConfig,
    VnetConfig,
)

CURRENT_DIR = Path(__file__).parent


async def test_crystal_peak(proxmox_api) -> None:
    envs_dict = {}

    sdn_config = await InfraCommands(proxmox_api, node="proxmox").generate_sdn_config(
        aliases=("with_ip",)
    )

    sdn_config = SdnConfig(
        vnet_configs=(
            sdn_config.vnet_configs[0],
            VnetConfig(alias="lan-local"),
            VnetConfig(alias="lan-acmenet-ext"),
            VnetConfig(alias="lan-acmenet-int"),
            VnetConfig(alias="lan-devcorp"),
            VnetConfig(alias="lan-cloudnet"),
            VnetConfig(alias="isp-link-0"),
            VnetConfig(alias="isp-link-1"),
            VnetConfig(alias="isp-link-2"),
            VnetConfig(alias="isp-link-3"),
        ),
        # Set use_pve_ipam_dnsnmasq to True if you want your instances to be able to access the internet
        use_pve_ipam_dnsnmasq=True,
    )

    crystal_peak_vms = (
        VmConfig(
            vm_source_config=VmSourceConfig(built_in="ubuntu24.04"),
            vnet_aliases=("with_ip",),
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path("/home/ubuntu/img/cpeak-pt-isp-gateway-10.ova")
            ),
            vnet_aliases=("isp-link-0", "isp-link-1", "isp-link-2", "isp-link-3"),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path("/home/ubuntu/img/cpeak-pt-local-agent-10.ova")
            ),
            vnet_aliases=("lan-local",),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path("/home/ubuntu/img/cpeak-pt-local-gateway.ova")
            ),
            vnet_aliases=("isp-link-0", "lan-local"),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path(
                    "/home/ubuntu/img/cpeak-pt-acmenet-gateway.ova"
                )
            ),
            vnet_aliases=("isp-link-1", "lan-acmenet-ext", "lan-acmenet-int"),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path(
                    "/home/ubuntu/img/cpeak-pt-acmenet-api.ova"
                )
            ),
            vnet_aliases=("lan-acmenet-ext",),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path(
                    "/home/ubuntu/img/cpeak-pt-acmenet-db.ova"
                )
            ),
            vnet_aliases=("lan-acmenet-ext", ),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path(
                    "/home/ubuntu/img/cpeak-pt-acmenet-jump.ova"
                )
            ),
            vnet_aliases=("lan-acmenet-ext",),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path(
                    "/home/ubuntu/img/cpeak-pt-acmenet-nfs.ova"
                )
            ),
            vnet_aliases=("lan-acmenet-int",),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path(
                    "/home/ubuntu/img/cpeak-pt-acmenet-alice.ova"
                )
            ),
            vnet_aliases=("lan-acmenet-int",),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path(
                    "/home/ubuntu/img/cpeak-pt-acmenet-bob-10.ova"
                )
            ),
            vnet_aliases=("lan-acmenet-int",),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path(
                    "/home/ubuntu/img/cpeak-pt-devcorp-gateway.ova"
                )
            ),
            vnet_aliases=("isp-link-2", "lan-devcorp"),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path(
                    "/home/ubuntu/img/cpeak-pt-devcorp-registry.ova"
                )
            ),
            vnet_aliases=("lan-devcorp",),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path(
                    "/home/ubuntu/img/cpeak-pt-devcorp-git.ova"
                )
            ),
            vnet_aliases=("lan-devcorp",),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path(
                    "/home/ubuntu/img/cpeak-pt-cloudnet-gateway.ova"
                )
            ),
            vnet_aliases=("isp-link-3", "lan-cloudnet"),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path(
                    "/home/ubuntu/img/cpeak-pt-cloudnet-dns.ova"
                )
            ),
            vnet_aliases=("lan-cloudnet",),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path(
                    "/home/ubuntu/img/cpeak-pt-cloudnet-vps1.ova"
                )
            ),
            vnet_aliases=("lan-cloudnet",),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path(
                    "/home/ubuntu/img/cpeak-pt-cloudnet-vps2-10.ova"
                )
            ),
            vnet_aliases=("lan-cloudnet",),
            is_sandbox=False,
            uefi_boot=True,
        ),
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
