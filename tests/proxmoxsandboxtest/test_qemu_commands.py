from pathlib import Path

import pytest

from proxmoxsandbox.inspect.proxmox.built_in_vm import BuiltInVM
from proxmoxsandbox.inspect.proxmox.qemu_commands import QemuCommands, VnetAliases
from proxmoxsandbox.inspect.proxmox.sdn_commands import SdnCommands
from proxmoxsandbox.inspect.schema import (
    SdnConfig,
    VmConfig,
    VmNicConfig,
    VmSourceConfig,
    VnetConfig,
)

CURRENT_DIR = Path(__file__).parent  # noqa: F821


async def test_simple_vm_non_sandbox(
    qemu_commands: QemuCommands,
    auto_sdn_vnet_aliases: VnetAliases,
    built_in_vm: BuiltInVM,
):
    built_in_ubuntu = VmSourceConfig(built_in="ubuntu24.04")

    await built_in_vm.ensure_exists(built_in_ubuntu)

    new_vm_id = await qemu_commands.create_and_start_vm(
        sdn_vnet_aliases=auto_sdn_vnet_aliases,
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

    await qemu_commands.destroy_vm(new_vm_id)
    # new_vm = {'tags': 'inspect-ubuntu24.04', 'cpu': 'host', 'ide2': 'none,media=cdrom', 'digest': '1b06374b6cfb9b411e0216fbb8f1509e9c237a9a', 'cores': 2, 'name': 'Copy-of-VM-inspect-ubuntu24.04', 'memory': '2048', 'meta': 'creation-qemu=9.0.2,ctime=1742225637', 'net0': 'virtio=BC:24:11:57:75:05,bridge=inspvmv0', 'agent': 'enabled=1', 'boot': 'order=scsi0;net0;ide2', 'ostype': 'l26', 'smbios1': 'uuid=a3700e1c-4a46-417c-bdc8-3f4b33495b10', 'scsi0': 'local-lvm:vm-102-disk-0,cache=writeback,size=10G', 'scsihw': 'virtio-scsi-single', 'vmgenid': 'ce6dc26c-e973-4a98-8d7b-226b3b374a03'}


async def test_none_nic_from_template_tag(
    qemu_commands: QemuCommands,
    auto_sdn_vnet_aliases: VnetAliases,
    built_in_vm: BuiltInVM,
):
    built_in_ubuntu = VmSourceConfig(built_in="ubuntu24.04")

    await built_in_vm.ensure_exists(built_in_ubuntu)

    new_vm_id = await qemu_commands.create_and_start_vm(
        sdn_vnet_aliases=auto_sdn_vnet_aliases,
        vm_config=VmConfig(
            vm_source_config=VmSourceConfig(
                existing_vm_template_tag="inspect-ubuntu24.04"
            ),  # coupling ourselves to the implementation of built_in_vm, naughty
            nics=None,
        ),
        built_in_vm_ids=await built_in_vm.known_builtins(),
    )

    new_vm = await qemu_commands.read_vm(new_vm_id)
    assert "net0" in new_vm
    assert BuiltInVM.STATIC_SDN_START in new_vm["net0"]

    qemu_commands.destroy_vm(new_vm_id)


async def test_empty_nic_from_template_tag(
    qemu_commands: QemuCommands,
    auto_sdn_vnet_aliases: VnetAliases,
    built_in_vm: BuiltInVM,
):
    built_in_ubuntu = VmSourceConfig(built_in="ubuntu24.04")

    await built_in_vm.ensure_exists(built_in_ubuntu)

    new_vm_id = await qemu_commands.create_and_start_vm(
        sdn_vnet_aliases=auto_sdn_vnet_aliases,
        vm_config=VmConfig(
            vm_source_config=VmSourceConfig(
                existing_vm_template_tag="inspect-ubuntu24.04"
            ),
            nics=(),
        ),
        built_in_vm_ids=await built_in_vm.known_builtins(),
    )

    new_vm = await qemu_commands.read_vm(new_vm_id)
    assert "net0" not in new_vm

    await qemu_commands.destroy_vm(new_vm_id)


async def test_none_nic_from_built_in(
    qemu_commands: QemuCommands,
    auto_sdn_vnet_aliases: VnetAliases,
    built_in_vm: BuiltInVM,
):
    built_in_ubuntu = VmSourceConfig(built_in="ubuntu24.04")

    await built_in_vm.ensure_exists(built_in_ubuntu)

    new_vm_id = await qemu_commands.create_and_start_vm(
        sdn_vnet_aliases=auto_sdn_vnet_aliases,
        vm_config=VmConfig(
            vm_source_config=built_in_ubuntu,
            nics=None,
        ),
        built_in_vm_ids=await built_in_vm.known_builtins(),
    )

    new_vm = await qemu_commands.read_vm(new_vm_id)
    assert "net0" in new_vm
    assert auto_sdn_vnet_aliases[0][0] in new_vm["net0"]

    await qemu_commands.destroy_vm(new_vm_id)


async def test_multiple_nic(
    qemu_commands: QemuCommands,
    built_in_vm: BuiltInVM,
    sdn_commands: SdnCommands,
    ids_start: str,
):
    built_in_ubuntu = VmSourceConfig(built_in="ubuntu24.04")

    await built_in_vm.ensure_exists(built_in_ubuntu)

    sdn_zone_id, vnet_aliases = await sdn_commands.create_sdn(
        ids_start,
        sdn_config=SdnConfig(
            vnet_configs=(
                VnetConfig(alias="vnetA"),
                VnetConfig(alias="vnetB"),
            ),
            use_pve_ipam_dnsnmasq=False,
        ),
    )

    new_vm_id = await qemu_commands.create_and_start_vm(
        sdn_vnet_aliases=vnet_aliases,
        vm_config=VmConfig(
            vm_source_config=built_in_ubuntu,
            nics=(VmNicConfig(vnet_alias="vnetB"), VmNicConfig(vnet_alias="vnetA")),
        ),
        built_in_vm_ids=await built_in_vm.known_builtins(),
    )

    new_vm = await qemu_commands.read_vm(new_vm_id)
    assert "net0" in new_vm
    assert vnet_aliases[1][0] in new_vm["net0"]
    assert vnet_aliases[1][1] == "vnetB"
    assert "net1" in new_vm
    assert vnet_aliases[0][0] in new_vm["net1"]
    assert vnet_aliases[0][1] == "vnetA"

    await qemu_commands.destroy_vm(new_vm_id)
    await sdn_commands.tear_down_sdn_zone_and_vnet(sdn_zone_id)


async def test_empty_nic_from_built_in(
    qemu_commands: QemuCommands,
    auto_sdn_vnet_aliases: VnetAliases,
    built_in_vm: BuiltInVM,
):
    built_in_ubuntu = VmSourceConfig(built_in="ubuntu24.04")

    await built_in_vm.ensure_exists(built_in_ubuntu)

    new_vm_id = await qemu_commands.create_and_start_vm(
        sdn_vnet_aliases=auto_sdn_vnet_aliases,
        vm_config=VmConfig(
            vm_source_config=built_in_ubuntu,
            nics=(),
        ),
        built_in_vm_ids=await built_in_vm.known_builtins(),
    )

    new_vm = await qemu_commands.read_vm(new_vm_id)
    assert "net0" not in new_vm

    await qemu_commands.destroy_vm(new_vm_id)


async def test_from_ova_local(qemu_commands: QemuCommands):
    new_vm_id = await qemu_commands.create_and_start_vm(
        sdn_vnet_aliases=[],
        vm_config=VmConfig(
            vm_source_config=VmSourceConfig(
                # This is originally from a release in https://github.com/oVirt/ovirt-tinycore-linux
                # but converted to OVA and checked in here
                ova=CURRENT_DIR / ".." / "oVirtTinyCore64-13.11.ova"
            ),
            nics=(),
            uefi_boot=False,
            is_sandbox=True,
        ),
        built_in_vm_ids={},
    )

    await qemu_commands.ping_qemu_agent("proxmox", new_vm_id)

    await qemu_commands.destroy_vm(new_vm_id)


# test disabled - you need a publicly available OVA that has both:
# 1. UEFI boot enabled
# 2. qemu-guest-agent installed
# AISI has one internally which can be provided on request, but it is
# nearly 1GB in size and hence not checked in to this repo.
@pytest.mark.skip
async def test_from_ova_uefi_sandbox(qemu_commands: QemuCommands):
    new_vm_id = await qemu_commands.create_and_start_vm(
        sdn_vnet_aliases=[],
        vm_config=VmConfig(
            vm_source_config=VmSourceConfig(ova=Path("ubu.ova")),
            nics=(),
            uefi_boot=True,
            is_sandbox=True,
        ),
        built_in_vm_ids={},
    )

    await qemu_commands.ping_qemu_agent("proxmox", new_vm_id)

    await qemu_commands.destroy_vm(new_vm_id)


async def test_uefi(
    qemu_commands: QemuCommands,
    auto_sdn_vnet_aliases: VnetAliases,
    built_in_vm: BuiltInVM,
):
    built_in_ubuntu = VmSourceConfig(built_in="ubuntu24.04")

    await built_in_vm.ensure_exists(built_in_ubuntu)

    new_vm_id = await qemu_commands.create_and_start_vm(
        sdn_vnet_aliases=auto_sdn_vnet_aliases,
        vm_config=VmConfig(
            vm_source_config=built_in_ubuntu,
            is_sandbox=True,
            uefi_boot=True,
        ),
        built_in_vm_ids=await built_in_vm.known_builtins(),
    )

    new_vm = await qemu_commands.read_vm(new_vm_id)
    assert new_vm["agent"] == "enabled=1"
    assert new_vm["bios"] == "ovmf"

    await qemu_commands.ping_qemu_agent("proxmox", new_vm_id)

    await qemu_commands.destroy_vm(new_vm_id)


async def test_restore_from_backup(
    qemu_commands: QemuCommands,
    built_in_vm: BuiltInVM,
    sdn_commands: SdnCommands,
    ids_start: str,
) -> None:
    await built_in_vm.ensure_exists(VmSourceConfig(built_in="ubuntu24.04"))

    vm_id_for_backup_source = await qemu_commands.create_and_start_vm(
        sdn_vnet_aliases=[],
        vm_config=VmConfig(
            vm_source_config=VmSourceConfig(
                ova=CURRENT_DIR / ".." / "oVirtTinyCore64-13.11.ova"
            ),
            nics=(),
            is_sandbox=True,
        ),
        built_in_vm_ids=await built_in_vm.known_builtins(),
    )

    backup = await qemu_commands.create_backup(vm_id_for_backup_source)

    sdn_zone_id, vnet_aliases = await sdn_commands.create_sdn(
        ids_start,
        sdn_config=SdnConfig(
            vnet_configs=(
                VnetConfig(alias="vnetC"),
                VnetConfig(alias="vnetD"),
            ),
            use_pve_ipam_dnsnmasq=False,
        ),
    )

    new_vm_id = await qemu_commands.create_and_start_vm(
        sdn_vnet_aliases=vnet_aliases,
        vm_config=VmConfig(
            vm_source_config=VmSourceConfig(
                # volid looks like:
                # 'local:backup/vzdump-qemu-103-2025_03_18-15_34_14.vma.zst'
                existing_backup_name=backup["volid"].split("/")[-1]
            ),
            nics=(VmNicConfig(vnet_alias="vnetC"), VmNicConfig(vnet_alias="vnetD")),
            is_sandbox=True,
        ),
        built_in_vm_ids={},
    )

    await qemu_commands.ping_qemu_agent("proxmox", new_vm_id)

    new_vm = await qemu_commands.read_vm(new_vm_id)
    assert "net0" in new_vm
    assert vnet_aliases[0][0] in new_vm["net0"]
    assert vnet_aliases[0][1] == "vnetC"
    assert "net1" in new_vm
    assert vnet_aliases[1][0] in new_vm["net1"]
    assert vnet_aliases[1][1] == "vnetD"

    await qemu_commands.destroy_vm(new_vm_id)
    await qemu_commands.destroy_vm(vm_id_for_backup_source)
    await sdn_commands.tear_down_sdn_zone_and_vnet(sdn_zone_id)
