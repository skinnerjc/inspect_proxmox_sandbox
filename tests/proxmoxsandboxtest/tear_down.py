from proxmoxsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from proxmoxsandbox.inspect.proxmox.infra_commands import InfraCommands

import pytest


# not actually a test; just a convenience for tearing down leftover stuff when testing
@pytest.mark.skip
async def test_teardown(async_proxmox_api: AsyncProxmoxAPI, node: str) -> None:
    test_zone_starts = ["san", "hel", "try", "tes", "ctf", "san", "kal", "tco", "cts"]
    infra_commands = InfraCommands(async_proxmox=async_proxmox_api, node=node)

    zone_ids_to_delete = []
    for zone in await infra_commands.sdn_commands.list_sdn_zones():
        if zone["zone"][:3] in test_zone_starts:
            zone_ids_to_delete.append(zone["zone"])

    await infra_commands.sdn_commands.tear_down_sdn_zones_and_vnets(zone_ids_to_delete)
