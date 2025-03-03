from pathlib import Path

from proxmoxsandboxtest.proxmox_sandbox_utils import (
    setup_sandbox,
)

from proxmoxsandbox.inspect.proxmox.infra_commands import InfraCommands
from proxmoxsandbox.inspect.schema import (
    ProxmoxSandboxEnvironmentConfig,
    SdnConfig,
    VmConfig,
    VmNicConfig,
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

    # class VmNicConfig(BaseModel, frozen=True):
    #     vnet_alias: str # TODO consider allowing this to be None, hence connecting to first VNet
    #     mac: Optional[MacAddress]

    crystal_peak_vms = (
        VmConfig(
            vm_source_config=VmSourceConfig(built_in="ubuntu24.04"),
            name="sneak",
            nics=(VmNicConfig(vnet_alias="with_ip"),),
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path("/home/ubuntu/img/cpeak-pt-isp-gateway-10.ova")
            ),
            name="isp-gateway",
            nics=(
                VmNicConfig(vnet_alias="isp-link-0", mac="00:16:3d:1d:eb:a0"),
                VmNicConfig(vnet_alias="isp-link-1", mac="00:16:3d:1d:eb:a1"),
                VmNicConfig(vnet_alias="isp-link-2", mac="00:16:3d:1d:eb:a2"),
                VmNicConfig(vnet_alias="isp-link-3", mac="00:16:3d:1d:eb:a3"),
            ),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path("/home/ubuntu/img/cpeak-pt-local-agent-10.ova")
            ),
            name="local-agent",
            nics=(VmNicConfig(vnet_alias="lan-local", mac="00:16:3d:1d:eb:03"),),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path("/home/ubuntu/img/cpeak-pt-local-gateway.ova")
            ),
            name="local-gateway",
            nics=(
                VmNicConfig(vnet_alias="isp-link-0", mac="00:16:3d:1d:eb:01"),
                VmNicConfig(vnet_alias="lan-local", mac="00:16:3d:1d:eb:02"),
            ),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path("/home/ubuntu/img/cpeak-pt-acmenet-gateway.ova")
            ),
            name="acmenet-gateway",
            nics=(
                VmNicConfig(vnet_alias="isp-link-1", mac="00:16:3d:1d:eb:b0"),
                VmNicConfig(vnet_alias="lan-acmenet-ext", mac="00:16:3d:1d:eb:b1"),
                VmNicConfig(vnet_alias="lan-acmenet-int", mac="00:16:3d:1d:eb:b2"),
            ),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path("/home/ubuntu/img/cpeak-pt-acmenet-api.ova")
            ),
            name="acmenet-api",
            nics=(VmNicConfig(vnet_alias="lan-acmenet-ext", mac="00:16:3d:1d:eb:b3"),),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path("/home/ubuntu/img/cpeak-pt-acmenet-db.ova")
            ),
            name="cpeak-pt-acmenet-db",
            nics=(VmNicConfig(vnet_alias="lan-acmenet-ext", mac="00:16:3d:1d:eb:b4"),),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path("/home/ubuntu/img/cpeak-pt-acmenet-jump.ova")
            ),
            name="acmenet-jump",
            nics=(VmNicConfig(vnet_alias="lan-acmenet-ext", mac="00:16:3d:1d:eb:b5"),),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path("/home/ubuntu/img/cpeak-pt-acmenet-nfs.ova")
            ),
            name="acmenet-nfs",
            nics=(VmNicConfig(vnet_alias="lan-acmenet-int", mac="00:16:3d:1d:eb:b6"),),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path("/home/ubuntu/img/cpeak-pt-acmenet-alice.ova")
            ),
            name="acmenet-alice",
            nics=(VmNicConfig(vnet_alias="lan-acmenet-int", mac="00:16:3d:1d:eb:b7"),),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path("/home/ubuntu/img/cpeak-pt-acmenet-bob-10.ova")
            ),
            name="acmenet-bob",
            nics=(VmNicConfig(vnet_alias="lan-acmenet-int", mac="00:16:3d:1d:eb:b8"),),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path("/home/ubuntu/img/cpeak-pt-devcorp-gateway.ova")
            ),
            name="devcorp-gateway",
            nics=(
                VmNicConfig(vnet_alias="isp-link-2", mac="00:16:3d:1d:eb:c0"),
                VmNicConfig(vnet_alias="lan-devcorp", mac="00:16:3d:1d:eb:c1"),
            ),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path("/home/ubuntu/img/cpeak-pt-devcorp-registry.ova")
            ),
            name="devcorp-registry",
            nics=(VmNicConfig(vnet_alias="lan-devcorp", mac="00:16:3d:1d:eb:c2"),),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path("/home/ubuntu/img/cpeak-pt-devcorp-git.ova")
            ),
            name="devcorp-git",
            nics=(VmNicConfig(vnet_alias="lan-devcorp", mac="00:16:3d:1d:eb:c3"),),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path("/home/ubuntu/img/cpeak-pt-cloudnet-gateway.ova")
            ),
            name="cloudnet-gateway",
            nics=(
                VmNicConfig(vnet_alias="isp-link-3", mac="00:16:3d:1d:eb:d1"),
                VmNicConfig(vnet_alias="lan-cloudnet", mac="00:16:3d:1d:eb:d2"),
            ),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path("/home/ubuntu/img/cpeak-pt-cloudnet-dns.ova")
            ),
            name="cloudnet-dns",
            nics=(VmNicConfig(vnet_alias="lan-cloudnet", mac="00:16:3d:1d:eb:d5"),),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path("/home/ubuntu/img/cpeak-pt-cloudnet-vps1.ova")
            ),
            name="cloudnet-vps1",
            nics=(VmNicConfig(vnet_alias="lan-cloudnet", mac="00:16:3d:1d:eb:d4"),),
            is_sandbox=False,
            uefi_boot=True,
        ),
        VmConfig(
            vm_source_config=VmSourceConfig(
                ova=Path("/home/ubuntu/img/cpeak-pt-cloudnet-vps2-10.ova")
            ),
            name="cloudnet-vps2",
            nics=(VmNicConfig(vnet_alias="lan-cloudnet", mac="00:16:3d:1d:eb:d3"),),
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
