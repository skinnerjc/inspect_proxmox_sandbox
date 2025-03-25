from proxmoxsandbox._impl.built_in_vm import BuiltInVM
from proxmoxsandbox._impl.qemu_commands import QemuCommands


async def test_ubuntu(qemu_commands: QemuCommands, built_in_vm: BuiltInVM) -> None:
    await built_in_vm.clear_builtins()

    known_builtins = await built_in_vm.known_builtins()

    assert "ubuntu24.04" not in known_builtins

    existing_vms = await qemu_commands.list_vms()

    await built_in_vm.ensure_exists("ubuntu24.04")

    all_vms = await qemu_commands.list_vms()

    existing_vm_ids = [vm["vmid"] for vm in existing_vms]

    assert len(all_vms) == len(existing_vms) + 1

    new_vms = [vm for vm in all_vms if vm["vmid"] not in existing_vm_ids]
    assert len(new_vms) == 1
    assert new_vms[0]["template"] == 1
    assert new_vms[0]["tags"]
    tags = new_vms[0]["tags"].split(";")
    assert "inspect" in tags
    assert "builtin-ubuntu24.04" in tags
