from proxmoxsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from proxmoxsandbox.inspect.proxmox.infra_commands import InfraCommands

import pytest

# not actually a test; just a convenience for tearing down leftover stuff when testing
@pytest.mark.skip
async def test_teardown(proxmox_api: AsyncProxmoxAPI):
    test_zone_starts = ["san", "hel", "try", "tes", "ctf", "ins"]
    infra_commands = InfraCommands(async_proxmox=proxmox_api, node="proxmox")


    zone_ids_to_delete = []
    for zone in await infra_commands.list_sdn_zones():
        if zone["zone"][:3] in test_zone_starts:
            zone_ids_to_delete.append(zone["zone"])

    await infra_commands.tear_down_sdn_zones_and_vnets(zone_ids_to_delete)
