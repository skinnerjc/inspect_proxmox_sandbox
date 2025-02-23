from ipaddress import ip_address, ip_network

from vmsandboxtest.vmsandbox_utils import setup_sandbox

from vmsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from vmsandbox.inspect.proxmox.infra_commands import InfraCommands
from vmsandbox.inspect.schema import (
    DhcpRange,
    SdnConfig,
    SubnetConfig,
    VmConfig,
    VmSourceConfig,
    VnetConfig,
)
from vmsandbox.inspect.vm_sandbox_environment import (
    VmSandboxEnvironmentConfig,
)

import random


async def test_create_sdn(request) -> None:
    third = "21"
    # setup_requests_logging()
    task_name, envs_dict = await setup_sandbox(
        request=request,
        vm_sandbox_environment_config=VmSandboxEnvironmentConfig(
            host="proxmox-9.ai-taskforce.reference.build",
            port=443,
            user="root",
            user_realm="pam",
            password="LgLWXOrsy3Y4YEATjx9m",
            sdn_config=SdnConfig(
                vnet_configs=(
                    VnetConfig(
                        subnets=(
                            SubnetConfig(
                                cidr=ip_network(f"192.168.{third}.0/24"),
                                gateway=ip_address(f"192.168.{third}.1"),
                                snat=True,
                                dhcp_ranges=(
                                    DhcpRange(
                                        start=ip_address(f"192.168.{third}.50"),
                                        end=ip_address(f"192.168.{third}.100"),
                                    ),
                                ),
                            ),
                        )
                    ),
                ),
            ),
        ),
    )


async def test_create_vm_built_in_ova() -> None:
    infra_config = InfraCommands(
        async_proxmox=AsyncProxmoxAPI(
            host="172.31.29.151:11002",
            user="root@pam",
            password="something",
            verify_ssl=False,
        )
    )

    ids_start = f"hel{random.randint(100, 999)}"

    await infra_config.create_sdn_and_vms(
        proxmox_ids_start=ids_start,
        sdn_config=VmSandboxEnvironmentConfig(
            host="", port=0, user="", user_realm="", password=""
        ).sdn_config,
        vms_config=(),
    )
    await infra_config.create_and_start_vm(
        node="proxmox",
        sdn_zone_id=f"{ids_start}z",
        vnet_id=f"{ids_start}v0",
        subnet="192.168.21.0/24",
        vm_config=VmConfig(
            vm_source_config=VmSourceConfig(built_in="ubuntu24.04"), is_sandbox=True
        ),
    )
