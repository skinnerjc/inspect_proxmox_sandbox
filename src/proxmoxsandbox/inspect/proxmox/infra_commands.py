import abc
from logging import getLogger
from random import shuffle
from typing import Dict, Tuple

from inspect_ai.util import trace_action

from proxmoxsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from proxmoxsandbox.inspect.proxmox.qemu_commands import QemuCommands
from proxmoxsandbox.inspect.proxmox.sdn_commands import SdnCommands
from proxmoxsandbox.inspect.proxmox.task_wrapper import TaskWrapper
from proxmoxsandbox.inspect.schema import SdnConfig, VmConfig, simple_sdn_config


class InfraCommands(abc.ABC):
    logger = getLogger(__name__)

    TRACE_NAME = "proxmox_infra_command"

    async_proxmox: AsyncProxmoxAPI
    task_wrapper: TaskWrapper
    sdn_commands: SdnCommands
    qemu_commands: QemuCommands
    node: str

    def __init__(self, async_proxmox: AsyncProxmoxAPI, node: str):
        self.async_proxmox = async_proxmox
        self.task_wrapper = TaskWrapper(async_proxmox)
        self.sdn_commands = SdnCommands(async_proxmox, node)
        self.qemu_commands = QemuCommands(async_proxmox, node)
        self.node = node

    async def create_sdn_and_vms(
        self,
        proxmox_ids_start: str,
        sdn_config: SdnConfig,
        vms_config: Tuple[VmConfig, ...],
        known_builtins: Dict[str, int],
    ):
        vm_configs_with_ids = []
        sdn_zone_id = None
        if sdn_config is None:
            raise ValueError("SDN config must be provided")

        sdn_zone_id, vnet_id, subnet_for_vms = await self.sdn_commands.create_sdn(
            proxmox_ids_start, sdn_config
        )

        for vm_config in vms_config:
            with trace_action(self.logger, self.TRACE_NAME, f"create VM {vm_config=}"):
                vm_id = await self.qemu_commands.create_and_start_vm(
                    sdn_zone_id=sdn_zone_id,
                    vnet_id=vnet_id,
                    subnet=subnet_for_vms[0]["subnet"],
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

    async def delete_sdn_and_vms(self, sdn_zone_id: str| None, vm_ids: Tuple[int, ...]):
        for vm_id in vm_ids:
                    await self.qemu_commands.destroy_vm(
                        vm_id=vm_id
                    )
        if sdn_zone_id is not None:
            await self.sdn_commands.tear_down_sdn_zone_and_vnet(
                sdn_zone_id=sdn_zone_id
            )

    async def generate_sdn_config(self) -> SdnConfig:
        sdn_config = None
        try_third_octets = list(range(2, 253))
        # Deliberately randomize the IP address range you get if you don't specify one.
        # This is to avoid brittle evals
        shuffle(try_third_octets)
        for third_octet in try_third_octets:
            try_sdn_config = simple_sdn_config(third_octet)
            try:
                await self.sdn_commands.check_cidrs(sdn_config=try_sdn_config)
                sdn_config = try_sdn_config
                break
            except ValueError:
                continue
        if sdn_config is None:
            raise ValueError("Could not find a suitable IP range for the SDN")
        # There is obviously a race condition here. Another eval could sneak in and create a clashing
        # IP range.
        # We could use a 10.*/24 range instead, which would give us many more ranges and
        # reduce the chance of a collision.
        return sdn_config