

from proxmoxsandbox.inspect.proxmox.qemu_commands import QemuCommands
from proxmoxsandbox.inspect.proxmox.sdn_commands import SdnCommands


async def test_simple(qemu_commands: QemuCommands, sdn_commands: SdnCommands):
    sdn_commands.create_sdn
    # qemu_commands.create_and_start_vm([], vm_config=)

async def test_none_nic_from_template_tag():
    pass

async def test_none_nic_from_built_in():
    pass

async def test_multiple_nic():
    pass

async def test_empty_nic_from_built_in():
    pass

async def test_uefi():
    pass

async def test_low_ram():
    pass

async def test_is_sandbox():
    pass

async def test_is_not_sandbox():
    pass

async def test_existing_vm_template_tag():
    pass

async def test_from_ova():
    pass

