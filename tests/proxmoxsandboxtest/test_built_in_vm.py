from proxmoxsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from proxmoxsandbox.inspect.proxmox.built_in_vm import BuiltInVM
from proxmoxsandbox.inspect.proxmox.qemu_commands import QemuCommands
from proxmoxsandbox.inspect.schema import VmSourceConfig


async def test_ubuntu(async_proxmox_api: AsyncProxmoxAPI) -> None:
    built_in_vm = BuiltInVM(async_proxmox_api, node="proxmox")
    await built_in_vm.clear_builtins()

    known_builtins = await built_in_vm.known_builtins()

    assert "ubuntu24.04" not in known_builtins

    qemu_commands = QemuCommands(async_proxmox_api, node="proxmox")

    existing_vms = await qemu_commands.list_vms()

    await built_in_vm.ensure_exists(
        vm_source_config=VmSourceConfig(built_in="ubuntu24.04"),
        known_buitins=known_builtins,
    )

    all_vms = await qemu_commands.list_vms()

    existing_vm_ids = [vm["vmid"] for vm in existing_vms]

    assert len(all_vms) == len(existing_vms) + 1

    new_vms = [vm for vm in all_vms if vm["vmid"] not in existing_vm_ids]
    assert len(new_vms) == 1
    assert new_vms[0]["template"] == 1
    assert new_vms[0]["tags"] == "inspect-ubuntu24.04"
