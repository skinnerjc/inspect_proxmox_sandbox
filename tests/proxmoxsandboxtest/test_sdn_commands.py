import random

from pytest import raises

from proxmoxsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from proxmoxsandbox.inspect.proxmox.infra_commands import InfraCommands
from proxmoxsandbox.inspect.proxmox.sdn_commands import SdnCommands
from proxmoxsandbox.inspect.schema import DhcpRange, SdnConfig, SubnetConfig, VnetConfig


async def test_create_sdn_no_vnets(sdn_commands: SdnCommands) -> None:
    ids_start = f"tsc{random.randint(100, 999)}"

    with raises(ValueError) as e_info:
        await sdn_commands.create_sdn(
            proxmox_ids_start=ids_start,
            sdn_config=SdnConfig(vnet_configs=(), use_pve_ipam_dnsnmasq=False),
        )
    assert "No vnets provided" in str(e_info.value)


async def test_create_sdn_with_vnets(sdn_commands: SdnCommands) -> None:
    ids_start = f"tsc{random.randint(100, 999)}"

    sdn_zone_id, vnet_aliases = await sdn_commands.create_sdn(
        proxmox_ids_start=ids_start,
        sdn_config=SdnConfig(
            vnet_configs=(
                VnetConfig(),
                VnetConfig(alias="test_create_sdn_with_vnets"),
            ),
            use_pve_ipam_dnsnmasq=False,
        ),
    )

    assert sdn_zone_id is not None
    assert len(vnet_aliases) == 2
    assert vnet_aliases[0][1] is None
    assert vnet_aliases[1][1] == "test_create_sdn_with_vnets"

    await sdn_commands.tear_down_sdn_zone_and_vnet(sdn_zone_id)


async def test_create_sdn_with_vnets_and_subnet(sdn_commands: SdnCommands) -> None:
    ids_start = f"tsc{random.randint(100, 999)}"

    # class SubnetConfig(BaseModel, frozen=True):
    #     cidr: IPvAnyNetwork
    #     gateway: IPvAnyAddress
    #     snat: bool
    #     dhcp_ranges: Tuple[DhcpRange, ...]

    sdn_zone_id, vnet_aliases = await sdn_commands.create_sdn(
        proxmox_ids_start=ids_start,
        sdn_config=SdnConfig(
            vnet_configs=(
                VnetConfig(
                    subnets=(
                        SubnetConfig(
                            cidr="10.32.32.0/24",
                            gateway="10.32.32.1",
                            snat=True,
                            dhcp_ranges=(),
                        ),
                    )
                ),
            ),
            use_pve_ipam_dnsnmasq=True,
        ),
    )

    assert sdn_zone_id is not None
    assert len(vnet_aliases) == 1

    await sdn_commands.tear_down_sdn_zone_and_vnet(sdn_zone_id)


async def test_inconsistent_ipam_setting_true_but_no_dhcp(
    sdn_commands: SdnCommands,
) -> None:
    ids_start = f"tsc{random.randint(100, 999)}"
    with raises(ValueError) as e_info:
        await sdn_commands.create_sdn(
            proxmox_ids_start=ids_start,
            sdn_config=SdnConfig(
                vnet_configs=(VnetConfig(),),
                use_pve_ipam_dnsnmasq=True,
            ),
        )
    assert "use_pve_ipam_dnsnmasq" in str(e_info.value)


async def test_inconsistent_ipam_setting_false_but_dhcp(
    sdn_commands: SdnCommands,
) -> None:
    ids_start = f"tsc{random.randint(100, 999)}"
    with raises(ValueError) as e_info:
        await sdn_commands.create_sdn(
            proxmox_ids_start=ids_start,
            sdn_config=SdnConfig(
                vnet_configs=(
                    VnetConfig(
                        subnets=(
                            SubnetConfig(
                                cidr="10.32.32.0/24",
                                gateway="10.32.32.1",
                                snat=False,
                                dhcp_ranges=(
                                    DhcpRange(start="10.32.32.16", end="10.32.32.32"),
                                ),
                            ),
                        )
                    ),
                ),
                use_pve_ipam_dnsnmasq=False,
            ),
        )
    assert "use_pve_ipam_dnsnmasq" in str(e_info.value)


async def test_create_sdn_overlapping(
    sdn_commands: SdnCommands,
) -> None:
    ids_start = f"tsc{random.randint(100, 999)}"
    with raises(ValueError) as e_info:
        await sdn_commands.create_sdn(
            proxmox_ids_start=ids_start,
            sdn_config=SdnConfig(
                vnet_configs=(
                    VnetConfig(
                        subnets=(
                            SubnetConfig(
                                cidr="10.0.0.0/8",
                                gateway="10.0.0.1",
                                snat=False,
                                dhcp_ranges=(
                                    DhcpRange(start="10.0.0.16", end="10.0.0.32"),
                                ),
                            ),
                        )
                    ),
                    VnetConfig(
                        subnets=(
                            SubnetConfig(
                                cidr="10.128.0.0/9",
                                gateway="10.128.0.1",
                                snat=False,
                                dhcp_ranges=(
                                    DhcpRange(start="10.128.0.16", end="10.128.0.32"),
                                ),
                            ),
                        )
                    ),
                ),
                use_pve_ipam_dnsnmasq=True,
            ),
        )
    assert "Duplicate IP ranges" in str(e_info.value)


async def test_create_sdn_auto(proxmox_api: AsyncProxmoxAPI) -> None:
    sdn_commands = SdnCommands(proxmox_api, node="proxmox")

    ids_start = f"tsc{random.randint(100, 999)}"

    __build_class__, vnet_aliases = await sdn_commands.create_sdn(
        proxmox_ids_start=ids_start, sdn_config="auto"
    )

    assert len(vnet_aliases) == 1


async def test_create_sdn_none(proxmox_api: AsyncProxmoxAPI) -> None:
    sdn_commands = SdnCommands(proxmox_api, node="proxmox")

    ids_start = f"tsc{random.randint(100, 999)}"

    sdn_zone_id, vnet_aliases = await sdn_commands.create_sdn(
        proxmox_ids_start=ids_start, sdn_config=None
    )

    assert sdn_zone_id is None
    assert vnet_aliases == []
