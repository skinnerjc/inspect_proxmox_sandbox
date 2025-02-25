from vmsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from vmsandbox.inspect.proxmox.infra_commands import InfraCommands


# not actually a test; just a convenience for tearing down leftover stuff when testing
async def test_teardown(proxmox_api: AsyncProxmoxAPI):
    test_zone_starts = ["san", "hel", "try", "test"]
    infra_commands = InfraCommands(async_proxmox=proxmox_api)
    for zone in await infra_commands.list_sdn_zones():
        if zone["zone"][:3] in test_zone_starts:
            await infra_commands.tear_down_sdn_zone_and_vnet(zone["zone"])
