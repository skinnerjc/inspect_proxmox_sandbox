import abc
from logging import getLogger
from typing import List, Set, Tuple

from inspect_ai.util import trace_action

from proxmoxsandbox._impl.async_proxmox import AsyncProxmoxAPI
from proxmoxsandbox._impl.built_in_vm import BuiltInVM
from proxmoxsandbox._impl.qemu_commands import QemuCommands
from proxmoxsandbox._impl.sdn_commands import SdnCommands
from proxmoxsandbox._impl.task_wrapper import TaskWrapper
from proxmoxsandbox.schema import (
    SdnConfigType,
    VmConfig,
)


class InfraCommands(abc.ABC):
    logger = getLogger(__name__)

    TRACE_NAME = "proxmox_infra_command"

    async_proxmox: AsyncProxmoxAPI
    task_wrapper: TaskWrapper
    sdn_commands: SdnCommands
    qemu_commands: QemuCommands
    built_in_vm: BuiltInVM
    node: str

    def __init__(self, async_proxmox: AsyncProxmoxAPI, node: str):
        self.async_proxmox = async_proxmox
        self.task_wrapper = TaskWrapper(async_proxmox)
        self.sdn_commands = SdnCommands(async_proxmox)
        self.qemu_commands = QemuCommands(async_proxmox, node)
        self.built_in_vm = BuiltInVM(async_proxmox, node)
        self.node = node

    async def create_sdn_and_vms(
        self,
        proxmox_ids_start: str,
        sdn_config: SdnConfigType,
        vms_config: Tuple[VmConfig, ...],
    ):
        vm_configs_with_ids = []
        sdn_zone_id, vnet_aliases = await self.sdn_commands.create_sdn(
            proxmox_ids_start, sdn_config
        )

        known_builtins = await self.built_in_vm.known_builtins()

        for vm_config in vms_config:
            with trace_action(self.logger, self.TRACE_NAME, f"create VM {vm_config=}"):
                vm_id = await self.qemu_commands.create_and_start_vm(
                    sdn_vnet_aliases=vnet_aliases,
                    vm_config=vm_config,
                    built_in_vm_ids=known_builtins,
                )
                vm_configs_with_ids.append((vm_id, vm_config))

        # TODO check for failed starts in the log somehow

        for vm_configs_with_id in vm_configs_with_ids:
            await self.qemu_commands.await_vm(
                vm_configs_with_id[0], vm_configs_with_id[1].is_sandbox
            )

        # TODO types here
        return vm_configs_with_ids, sdn_zone_id

    async def delete_sdn_and_vms(
        self, sdn_zone_id: str | None, vm_ids: Tuple[int, ...]
    ):
        for vm_id in vm_ids:
            await self.qemu_commands.destroy_vm(vm_id=vm_id)
        if sdn_zone_id is not None:
            await self.sdn_commands.tear_down_sdn_zone_and_vnet(sdn_zone_id=sdn_zone_id)

    async def find_all_zones(self, vnet_ids: List[str]) -> Set[str]:
        return set(
            [
                vnet["zone"]
                for vnet in await self.sdn_commands.read_all_vnets()
                if vnet["vnet"] in vnet_ids
            ]
        )

    async def cleanup(self) -> None:
        await self.qemu_commands.cleanup()
        await self.sdn_commands.cleanup()

    async def cleanup_no_id(self) -> None:
        noticed_vnets = []

        for vm in await self.qemu_commands.list_vms():
            if "inspect" in vm["tags"].split(";") and (
                ("template" in vm and vm["template"] == 0) or ("template" not in vm)
            ):
                existing_vm = await self.qemu_commands.read_vm(vm["vmid"])
                for key in existing_vm.keys():
                    if key.startswith("net"):
                        # 'virtio=BC:24:11:3E:C3:BA,bridge=tcc919v0'
                        bridge = existing_vm[key].split(",")[1].split("=")[1]
                        noticed_vnets.append(bridge)
                await self.qemu_commands.destroy_vm(vm["vmid"])

        zones_to_delete = await self.find_all_zones(noticed_vnets)
        await self.sdn_commands.tear_down_sdn_zones_and_vnets(zones_to_delete)
