import asyncio

from vmsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from vmsandbox.inspect.proxmox.infra_commands import InfraCommands

proxmox = AsyncProxmoxAPI(
            host="proxmox-9.ai-taskforce.reference.build:443",
            user="root@pam",
            password="LgLWXOrsy3Y4YEATjx9m",
            verify_ssl=False,
        )


async def main():
    # await proxmox.create_vm(
    #     node="proxmox",
    #     zone="simplez",
    #     vnet="vnetz0",
    #     subnet="10.0.13.0/24",
    #     vm_config=VmConfig(backup_name="vzdump-qemu-101-2025_02_10-15_00_13.vma.zst"),
    # )
    # res= await proxmox.exec_command("proxmox", 103, ["ls", "/"])
    # print(f"{res=}")
    infra_commands = InfraCommands(async_proxmox=proxmox)
    for zone in await infra_commands.list_sdn_zones():
        if zone["zone"][:3] == "ctf" or zone["zone"][:3] == "hel":
            await infra_commands.tear_down_sdn_zone_and_vnet(zone["zone"])


asyncio.run(main())
