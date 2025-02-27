import abc
from logging import getLogger
from typing import Dict

import tenacity
from inspect_ai.util import trace_action

from proxmoxsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from proxmoxsandbox.inspect.proxmox.task_wrapper import TaskWrapper
from proxmoxsandbox.inspect.schema import (
    VmConfig,
)


class QemuCommands(abc.ABC):
    logger = getLogger(__name__)

    TRACE_NAME = "proxmox_qemu_command"

    async_proxmox: AsyncProxmoxAPI
    task_wrapper: TaskWrapper
    node: str

    def __init__(self, async_proxmox: AsyncProxmoxAPI, node: str):
        self.async_proxmox = async_proxmox
        self.task_wrapper = TaskWrapper(async_proxmox)
        self.node = node

 

    async def await_vm(
        self, vm_id: int, is_sandbox: bool, status_for_wait: str = "running"
    ) -> None:
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

    async def start_and_await(self, vm_id: int) -> None:
        await self.async_proxmox.request(
            "POST",
            f"/nodes/{self.node}/qemu/{vm_id}/status/start",
        )

        await self.await_vm(
            vm_id=vm_id,
            is_sandbox=True,
        )

    async def create_and_start_vm(
        self,
        sdn_zone_id: str,
        vnet_id: str,
        subnet: str,
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
            if vm_config.vm_source_config.built_in == "ubuntu24.04":
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
                    await self.async_proxmox.request(
                        "POST",
                        f"/nodes/{self.node}/qemu/{new_vm_id}/config",
                        json={
                            "tags": "",  # remove the tag as that's only for the template
                            "net0": f"virtio,bridge={vnet_id}",
                        },
                    )

                await self.task_wrapper.do_action_and_wait_for_tasks(update_network)

                await self.start_and_await(new_vm_id)

        else:
            raise NotImplementedError(f"Not supported: {vm_config.vm_source_config=}")
        if new_vm_id is None:
            raise ValueError("No VM ID?")
        return new_vm_id
