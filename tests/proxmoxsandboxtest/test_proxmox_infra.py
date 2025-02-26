import random

from pytest import raises

from proxmoxsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from proxmoxsandbox.inspect.proxmox.infra_commands import InfraCommands
from proxmoxsandbox.inspect.schema import (
    simple_sdn_config,
)


async def test_create_sdn(proxmox_api: AsyncProxmoxAPI) -> None:
    infra_config = InfraCommands(proxmox_api, node="proxmox")

    ids_start = f"hel{random.randint(100, 999)}"

    sdn_zone_id = None

    try:
        __name__, sdn_zone_id = await infra_config.create_sdn_and_vms(
            proxmox_ids_start=ids_start,
            sdn_config=simple_sdn_config(22),
            vms_config=(),
            known_builtins={},
        )

    finally:
        if sdn_zone_id is not None:
            await infra_config.tear_down_sdn_zone_and_vnet(sdn_zone_id)


async def test_create_sdn_duplicate(proxmox_api: AsyncProxmoxAPI) -> None:
    infra_config = InfraCommands(proxmox_api, node="proxmox")

    sdn_zone_ids = []

    try:
        z1_ids_start = f"hel{random.randint(100, 999)}"

        __name__, sdn_zone_id_1 = await infra_config.create_sdn_and_vms(
            proxmox_ids_start=z1_ids_start,
            sdn_config=simple_sdn_config(22),
            vms_config=(),
            known_builtins={},
        )
        sdn_zone_ids.append(sdn_zone_id_1)

        with raises(ValueError) as e_info:
            z2_ids_start = f"hel{random.randint(100, 999)}"
            __name__, sdn_zone_id_1 = await infra_config.create_sdn_and_vms(
                proxmox_ids_start=z2_ids_start,
                sdn_config=simple_sdn_config(22),
                vms_config=(),
                known_builtins={},
            )
            sdn_zone_ids.append(sdn_zone_id_1)
        assert "Duplicate IP" in str(e_info.value)
        assert "22" in str(e_info.value)
    finally:
        for sdn_zone_id in sdn_zone_ids:
            await infra_config.tear_down_sdn_zone_and_vnet(sdn_zone_id)

