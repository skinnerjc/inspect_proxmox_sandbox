import abc
from logging import getLogger
from typing import Dict, Tuple, List

import tenacity
from inspect_ai.util import trace_action

from proxmoxsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from proxmoxsandbox.inspect.proxmox.storage_commands import StorageCommands
from proxmoxsandbox.inspect.proxmox.task_wrapper import TaskWrapper
from proxmoxsandbox.inspect.schema import (
    VmConfig,
)


from pydantic.networks import HttpUrl
from pathlib import Path


class QemuCommands(abc.ABC):
    logger = getLogger(__name__)

    TRACE_NAME = "proxmox_qemu_command"

    async_proxmox: AsyncProxmoxAPI
    task_wrapper: TaskWrapper
    storage_commands: StorageCommands
    node: str

    def __init__(self, async_proxmox: AsyncProxmoxAPI, node: str):
        self.async_proxmox = async_proxmox
        self.task_wrapper = TaskWrapper(async_proxmox)
        self.storage_commands = StorageCommands(async_proxmox, node, "local")
        self.node = node

    async def await_vm(
        self,
        vm_id: int,
        is_sandbox: bool,
        status_for_wait: str = "running",
        press_enter_at_grub: bool = False,
    ) -> None:
        if press_enter_at_grub and (not status_for_wait == "running" or not is_sandbox):
            raise ValueError(
                f"It makes no sense to have {press_enter_at_grub=} unless you are waiting for the VM to be running and it's a sandbox"
            )

        @tenacity.retry(
            wait=tenacity.wait_exponential(min=0.1, exp_base=1.3),
            stop=tenacity.stop_after_delay(300),
        )
        async def is_in_status() -> None:
            vm_status = await self.async_proxmox.request(
                "GET", f"/nodes/{self.node}/qemu/{vm_id}/status/current"
            )
            if vm_status["status"] != status_for_wait:
                raise ValueError(f"vm {vm_id} not {status_for_wait}")

        with trace_action(
            self.logger,
            self.TRACE_NAME,
            f"await VM {vm_id} to be in status {status_for_wait}",
        ):
            await is_in_status()

        if is_sandbox and status_for_wait == "running":

            @tenacity.retry(
                wait=tenacity.wait_exponential(min=0.1, exp_base=1.3),
                stop=tenacity.stop_after_delay(300),
            )
            async def qemu_agent_reachable() -> None:
                if press_enter_at_grub:
                    await self.async_proxmox.request(
                        "PUT",
                        f"/nodes/{self.node}/qemu/{vm_id}/sendkey",
                        json={"key": "ret"},
                    )
                await self.async_proxmox.ping_qemu_agent(self.node, vm_id)

            with trace_action(
                self.logger, self.TRACE_NAME, f"await VM {vm_id} QEMU agent"
            ):
                await qemu_agent_reachable()

    async def destroy_vm(self, vm_id: int) -> None:
        with trace_action(self.logger, self.TRACE_NAME, f"stop VM {vm_id}"):
            await self.async_proxmox.request(
                "POST", f"/nodes/{self.node}/qemu/{vm_id}/status/stop"
            )

        @tenacity.retry(
            wait=tenacity.wait_exponential(min=0.1, exp_base=1.3),
            stop=tenacity.stop_after_delay(300),
        )
        async def is_not_running() -> None:
            vm_status = await self.async_proxmox.request(
                "GET", f"/nodes/{self.node}/qemu/{vm_id}/status/current"
            )
            if vm_status["status"] != "stopped":
                raise ValueError(f"vm {vm_id} still running")

        with trace_action(self.logger, self.TRACE_NAME, f"await VM {vm_id} stopped"):
            await is_not_running()

        with trace_action(self.logger, self.TRACE_NAME, f"delete VM {vm_id}"):
            await self.async_proxmox.request(
                "DELETE", f"/nodes/{self.node}/qemu/{vm_id}"
            )

        @tenacity.retry(
            wait=tenacity.wait_exponential(min=0.1, exp_base=1.3),
            stop=tenacity.stop_after_delay(30),
        )
        async def vm_deleted() -> None:
            current = await self.async_proxmox.request(
                method="GET",
                path=f"/nodes/{self.node}/qemu/{vm_id}/status/current",
                raise_errors=False,
            )
            if "vmid" in current:
                raise ValueError(f"vm {vm_id} still exists")

        with trace_action(self.logger, self.TRACE_NAME, f"await VM {vm_id} deleted"):
            await vm_deleted()

    async def list_vms(self):
        with trace_action(self.logger, self.TRACE_NAME, "list all VMs"):
            return await self.async_proxmox.request("GET", f"/nodes/{self.node}/qemu")

    async def find_next_available_vm_id(self) -> int:
        existing_vms = await self.list_vms()
        if existing_vms:
            next_available_vm_id = (
                max(list(int(existing["vmid"]) for existing in existing_vms)) + 1
            )
        else:
            next_available_vm_id = 100
        return next_available_vm_id

    async def start_and_await(
        self, vm_id: int, press_enter_at_grub: bool = False
    ) -> None:
        await self.async_proxmox.request(
            "POST",
            f"/nodes/{self.node}/qemu/{vm_id}/status/start",
        )

        await self.await_vm(
            vm_id=vm_id,
            is_sandbox=True,
            press_enter_at_grub=press_enter_at_grub,
        )

    def _convert_sdn_vnet_aliases(
        self, sdn_vnet_aliases: List[Tuple[str, str | None]]
    ) -> Dict[str, str]:
        """Convert list of (vnet_id, vnet_alias) tuples to alias->id mapping, skipping None aliases."""
        return {
            alias: vnet_id for vnet_id, alias in sdn_vnet_aliases if alias is not None
        }

    async def create_and_start_vm(
        self,
        sdn_vnet_aliases: List[
            Tuple[str, str | None]
        ],  # a List tuples of [vnet ID, vnet alias], for the particular sdn_zone_id. The vnet alias may be None.
        vm_config: VmConfig,
        built_in_vm_ids: Dict[str, int],
    ) -> int:
        new_vm_id: int | None = None

        if vm_config.vm_source_config.existing_backup_name:
            new_vm_id = await self.find_next_available_vm_id()
            with trace_action(
                self.logger,
                self.TRACE_NAME,
                f"create VM from backup {new_vm_id=}",
            ):
                await self.async_proxmox.request(
                    "POST",
                    f"/nodes/{self.node}/qemu",
                    json={
                        "vmid": new_vm_id,
                        "node": self.node,
                        "archive": f"/var/lib/vz/dump/{vm_config.vm_source_config.existing_backup_name}",
                        "net0": f"virtio,bridge={vnet_id}",
                        "start": True,
                    },
                )
        elif vm_config.vm_source_config.built_in:
            if vm_config.vm_source_config.built_in in ["ubuntu24.04", "kali"]:
                vm_id_to_clone = built_in_vm_ids[vm_config.vm_source_config.built_in]

                if vm_id_to_clone is None:
                    raise ValueError(
                        f"couldn't find template VM for {vm_config.vm_source_config.built_in}"
                    )

                # TODO: check "Import" is enabled for local storage

                new_vm_id = await self.find_next_available_vm_id()

                # now clone
                @tenacity.retry(
                    wait=tenacity.wait_exponential(min=1, exp_base=2),
                    stop=tenacity.stop_after_attempt(4),
                )
                # Sometimes fails with '500 Linked clone feature is not supported for 'local-lvm:vm-101-disk-0' (scsi0)'
                # hence the retry decorator
                async def create_clone() -> None:
                    await self.async_proxmox.request(
                        "POST",
                        f"/nodes/{self.node}/qemu/{vm_id_to_clone}/clone",
                        json={"newid": new_vm_id, "full": 0},
                    )

                await create_clone()

                async def update_network() -> None:
                    network_update_json = {
                        "tags": ""
                    }  # remove the tag as that's only for the template
                    if len(vm_config.vnet_aliases) > 0:
                        alias_mapping = self._convert_sdn_vnet_aliases(sdn_vnet_aliases)
                        for i, vnet_alias in enumerate(vm_config.vnet_aliases):
                            network_update_json[f"net{i}"] = (
                                f"virtio,bridge={alias_mapping[vnet_alias]}"
                            )
                    else:
                        first_vnet_id = sdn_vnet_aliases[0][0]
                        network_update_json["net0"] = f"virtio,bridge={first_vnet_id}"

                    await self.async_proxmox.request(
                        "POST",
                        f"/nodes/{self.node}/qemu/{new_vm_id}/config",
                        json=network_update_json,
                    )

                await self.task_wrapper.do_action_and_wait_for_tasks(update_network)

                press_enter_at_grub = vm_config.vm_source_config.built_in == "kali"
                await self.start_and_await(new_vm_id, press_enter_at_grub)
            else:
                raise NotImplementedError(
                    f"Not supported: {vm_config.vm_source_config.built_in=}"
                )
        elif vm_config.vm_source_config.ova is not None:
            if isinstance(vm_config.vm_source_config.ova, HttpUrl):
                raise NotImplementedError(
                    f"Not supported: {type(vm_config.vm_source_config.ova)}"
                )
            if isinstance(vm_config.vm_source_config.ova, Path):
                await self.storage_commands.upload_file_to_storage(
                    content=vm_config.vm_source_config.ova.read_bytes(),
                    filename=vm_config.vm_source_config.ova.name,
                    file_type="import",
                )
            else:
                raise NotImplementedError(
                    f"Not supported: {type(vm_config.vm_source_config.ova)}"
                )               
        if new_vm_id is None:
            raise ValueError("No VM ID?")
        return new_vm_id
