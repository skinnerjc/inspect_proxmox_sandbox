import abc
import tarfile
from logging import getLogger
from pathlib import Path
from typing import Dict, List, Tuple

import tenacity
from inspect_ai.util import trace_action
from pydantic.networks import HttpUrl

from proxmoxsandbox.inspect.proxmox.async_proxmox import (
    AsyncProxmoxAPI,
    ProxmoxJsonDataType,
)
from proxmoxsandbox.inspect.proxmox.storage_commands import StorageCommands
from proxmoxsandbox.inspect.proxmox.task_wrapper import TaskWrapper
from proxmoxsandbox.inspect.schema import (
    VmConfig,
)


class QemuCommands(abc.ABC):
    logger = getLogger(__name__)

    TRACE_NAME = "proxmox_qemu_command"

    async_proxmox: AsyncProxmoxAPI
    task_wrapper: TaskWrapper
    storage: str  # TODO disambiguate that this is for images rather than VM disks which continue to live in local-lvm
    storage_commands: StorageCommands
    node: str

    def __init__(self, async_proxmox: AsyncProxmoxAPI, node: str):
        self.async_proxmox = async_proxmox
        self.task_wrapper = TaskWrapper(async_proxmox)
        self.storage = "local"
        self.storage_commands = StorageCommands(async_proxmox, node, self.storage)
        self.node = node

    async def await_vm(
        self,
        vm_id: int,
        is_sandbox: bool,
        status_for_wait: str = "running",
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

    async def start_and_await(
        self,
        vm_id: int,
        is_sandbox: bool = True,
    ) -> None:
        await self.async_proxmox.request(
            "POST",
            f"/nodes/{self.node}/qemu/{vm_id}/status/start",
        )

        await self.await_vm(
            vm_id=vm_id,
            is_sandbox=is_sandbox,
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

                async def create_from_backup() -> None:
                    await self.async_proxmox.request(
                        "POST",
                        f"/nodes/{self.node}/qemu",
                        json={
                            "vmid": new_vm_id,
                            "node": self.node,
                            "archive": f"/var/lib/vz/dump/{vm_config.vm_source_config.existing_backup_name}",
                        },
                    )
                    # todo other config

                await self.task_wrapper.do_action_and_wait_for_tasks(create_from_backup)

            await self.start_and_await(
                vm_id=new_vm_id,
                is_sandbox=vm_config.is_sandbox,
            )
        elif vm_config.vm_source_config.built_in:
            if vm_config.vm_source_config.built_in in ["ubuntu24.04"]:
                vm_id_to_clone = built_in_vm_ids[vm_config.vm_source_config.built_in]

                if vm_id_to_clone is None:
                    raise ValueError(
                        f"couldn't find template VM for {vm_config.vm_source_config.built_in}"
                    )

                # TODO: check "Import" is enabled for local storage

                new_vm_id = await self.clone_vm_and_start(
                    vm_config, vm_id_to_clone, sdn_vnet_aliases
                )
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

                json_for_create: ProxmoxJsonDataType = {
                    "node": self.node,
                    "cpu": "host",
                    "ostype": "l26",
                    "scsihw": "virtio-scsi-single",
                    "start": False,
                }

                self.other_config_json(vm_config, json_for_create)

                vmdks = []
                with tarfile.open(vm_config.vm_source_config.ova, "r") as tar:
                    # Get the list of member names
                    file_list = tar.getnames()

                    for file_name in file_list:
                        if file_name.endswith(".vmdk"):
                            vmdks.append(file_name)

                for i, vmdk in enumerate(vmdks):
                    json_for_create[f"scsi{i}"] = (
                        f"local-lvm:0,import-from={self.storage}:import/{vm_config.vm_source_config.ova.name}/{vmdk},format=qcow2,cache=writeback"
                    )

                new_vm_id = await self.find_next_available_vm_id()
                json_for_create["vmid"] = new_vm_id

                with trace_action(
                    self.logger,
                    self.TRACE_NAME,
                    f"create VM from OVA {new_vm_id=}",
                ):

                    async def create() -> None:
                        await self.async_proxmox.request(
                            "POST", f"/nodes/{self.node}/qemu", json=json_for_create
                        )

                    await self.task_wrapper.do_action_and_wait_for_tasks(create)

                await self.configure_network(vm_config, sdn_vnet_aliases, new_vm_id)

                await self.start_and_await(
                    vm_id=new_vm_id,
                    is_sandbox=vm_config.is_sandbox,
                )
            else:
                raise NotImplementedError(
                    f"Not supported: {type(vm_config.vm_source_config.ova)}"
                )
        elif vm_config.vm_source_config.existing_vm_template_tag:
            existing_vms = await self.list_vms()

            found_vm = []

            for existing_vm in existing_vms:
                if (
                    "tags" in existing_vm
                    and existing_vm["tags"]
                    == vm_config.vm_source_config.existing_vm_template_tag
                    and "template" in existing_vm
                    and existing_vm["template"] == 1
                ):
                    found_vm.append(existing_vm)
                    break

            if len(found_vm) == 0:
                raise ValueError(
                    f"Couldn't find VM with tag {vm_config.vm_source_config.existing_vm_template_tag}"
                )

            if len(found_vm) > 1:
                raise ValueError(
                    f"Found multiple VMs with tag {vm_config.vm_source_config.existing_vm_template_tag}: {found_vm=}"
                )

            vm_id_to_clone = found_vm[0]["vmid"]

            new_vm_id = await self.clone_vm_and_start(
                vm_config, vm_id_to_clone, sdn_vnet_aliases
            )

        else:
            raise NotImplementedError(f"Not supported: {vm_config.vm_source_config=}")
        if new_vm_id is None:
            raise ValueError("No VM ID?")
        return new_vm_id

    async def configure_network(
        self,
        vm_config: VmConfig,
        sdn_vnet_aliases: List[Tuple[str, str | None]],
        vm_id: int,
    ) -> None:
        async def update_network() -> None:
            network_update_json: ProxmoxJsonDataType = {
                "tags": ""
            }  # remove the tag as that's only for the template TODO - move this
            if vm_config.nics is None:
                # TODO: remove any existing nics
                raise NotImplementedError()
            elif len(vm_config.nics) > 0:
                alias_mapping = self._convert_sdn_vnet_aliases(sdn_vnet_aliases)
                for i, nic in enumerate(vm_config.nics):
                    netx = f"virtio,bridge={alias_mapping[nic.vnet_alias]}"
                    if nic.mac:
                        netx += f",macaddr={nic.mac}"
                    network_update_json[f"net{i}"] = netx

            else:
                first_vnet_id = sdn_vnet_aliases[0][0]
                network_update_json["net0"] = f"virtio,bridge={first_vnet_id}"

            await self.async_proxmox.request(
                "POST",
                f"/nodes/{self.node}/qemu/{vm_id}/config",
                json=network_update_json,
            )

        await self.task_wrapper.do_action_and_wait_for_tasks(update_network)

    async def clone_vm_and_start(
        self,
        vm_config: VmConfig,
        vm_id_to_clone: int,
        sdn_vnet_aliases: List[Tuple[str, str | None]],
    ) -> int:
        new_vm_id = await self.find_next_available_vm_id()

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
                json={"newid": new_vm_id, "full": 0, "name": vm_config.name},
            )

        await create_clone()

        if vm_config.nics != ():
            await self.configure_network(vm_config, sdn_vnet_aliases, new_vm_id)

        other_update_json: ProxmoxJsonDataType = {}
        self.other_config_json(vm_config, other_update_json)

        await self.async_proxmox.request(
            "POST",
            f"/nodes/{self.node}/qemu/{new_vm_id}/config",
            json=other_update_json,
        )

        await self.start_and_await(new_vm_id)
        return new_vm_id

    def other_config_json(
        self, vm_config: VmConfig, json_for_create: ProxmoxJsonDataType
    ) -> None:
        json_for_create["agent"] = f"enabled={1 if vm_config.is_sandbox else 0}"
        json_for_create["memory"] = vm_config.ram_mb
        json_for_create["cores"] = vm_config.vcpus
        if vm_config.name is not None:
            json_for_create["name"] = vm_config.name
        if vm_config.uefi_boot:
            json_for_create["efidisk0"] = "local-lvm:0,efitype=4m,pre-enrolled-keys=0"
            json_for_create["bios"] = "ovmf"
