from proxmoxsandbox.inspect.proxmox.built_in_vm import BuiltInVM
from proxmoxsandbox.inspect.proxmox.qemu_commands import QemuCommands
from proxmoxsandbox.inspect.proxmox.sdn_commands import SdnCommands
from proxmoxsandbox.inspect.schema import VmConfig, VmSourceConfig


async def test_simple_vm_non_sandbox(
    qemu_commands: QemuCommands,
    sdn_commands: SdnCommands,
    built_in_vm: BuiltInVM,
    ids_start: str,
):
    sdn_zone_id, vnet_aliases = await sdn_commands.create_sdn(ids_start, "auto")

    built_in_ubuntu = VmSourceConfig(built_in="ubuntu24.04")

    await built_in_vm.ensure_exists(built_in_ubuntu)

    new_vm_id = await qemu_commands.create_and_start_vm(
        sdn_vnet_aliases=vnet_aliases,
        vm_config=VmConfig(
            vm_source_config=built_in_ubuntu,
            ram_mb=768,
            vcpus=3,
            is_sandbox=False,
            uefi_boot=False,
        ),
        built_in_vm_ids=await built_in_vm.known_builtins(),
    )

    new_vm = await qemu_commands.read_vm(new_vm_id)
    assert new_vm["memory"] == "768"
    assert new_vm["cores"] == 3
    assert new_vm["agent"] == "enabled=0"
    assert "net0" in new_vm

    qemu_commands.destroy_vm(new_vm_id)
    sdn_commands.tear_down_sdn_zone_and_vnet(sdn_zone_id)

    # new_vm = {'tags': 'inspect-ubuntu24.04', 'cpu': 'host', 'ide2': 'none,media=cdrom', 'digest': '1b06374b6cfb9b411e0216fbb8f1509e9c237a9a', 'cores': 2, 'name': 'Copy-of-VM-inspect-ubuntu24.04', 'memory': '2048', 'meta': 'creation-qemu=9.0.2,ctime=1742225637', 'net0': 'virtio=BC:24:11:57:75:05,bridge=inspvmv0', 'agent': 'enabled=1', 'boot': 'order=scsi0;net0;ide2', 'ostype': 'l26', 'smbios1': 'uuid=a3700e1c-4a46-417c-bdc8-3f4b33495b10', 'scsi0': 'local-lvm:vm-102-disk-0,cache=writeback,size=10G', 'scsihw': 'virtio-scsi-single', 'vmgenid': 'ce6dc26c-e973-4a98-8d7b-226b3b374a03'}


async def test_none_nic_from_template_tag():
    pass


async def test_none_nic_from_built_in(
    qemu_commands: QemuCommands,
    sdn_commands: SdnCommands,
    built_in_vm: BuiltInVM,
    ids_start: str,
):
    sdn_zone_id, vnet_aliases = await sdn_commands.create_sdn(ids_start, "auto")

    built_in_ubuntu = VmSourceConfig(built_in="ubuntu24.04")

    await built_in_vm.ensure_exists(built_in_ubuntu)

    new_vm_id = await qemu_commands.create_and_start_vm(
        sdn_vnet_aliases=vnet_aliases,
        vm_config=VmConfig(
            vm_source_config=built_in_ubuntu,
            nics=None,
        ),
        built_in_vm_ids=await built_in_vm.known_builtins(),
    )

    new_vm = await qemu_commands.read_vm(new_vm_id)
    assert "net0" in new_vm
    assert vnet_aliases[0][0] in new_vm["net0"]

    qemu_commands.destroy_vm(new_vm_id)
    sdn_commands.tear_down_sdn_zone_and_vnet(sdn_zone_id)


async def test_multiple_nic():
    pass


async def test_empty_nic_from_built_in(
    qemu_commands: QemuCommands,
    sdn_commands: SdnCommands,
    built_in_vm: BuiltInVM,
    ids_start: str,
):
    sdn_zone_id, vnet_aliases = await sdn_commands.create_sdn(ids_start, "auto")

    built_in_ubuntu = VmSourceConfig(built_in="ubuntu24.04")

    await built_in_vm.ensure_exists(built_in_ubuntu)

    new_vm_id = await qemu_commands.create_and_start_vm(
        sdn_vnet_aliases=vnet_aliases,
        vm_config=VmConfig(
            vm_source_config=built_in_ubuntu,
            nics=(),
        ),
        built_in_vm_ids=await built_in_vm.known_builtins(),
    )

    new_vm = await qemu_commands.read_vm(new_vm_id)
    assert "net0" not in new_vm

    qemu_commands.destroy_vm(new_vm_id)
    sdn_commands.tear_down_sdn_zone_and_vnet(sdn_zone_id)


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
