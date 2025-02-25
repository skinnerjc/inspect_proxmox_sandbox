import abc
from ipaddress import ip_network
from logging import getLogger
from typing import Dict, List, Tuple

import tenacity
from inspect_ai.util import trace_action

from vmsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from vmsandbox.inspect.proxmox.task_wrapper import TaskWrapper
from vmsandbox.inspect.schema import (
    SdnConfig,
    VmConfig,
)


class InfraCommands(abc.ABC):
    logger = getLogger(__name__)

    TRACE_NAME = "proxmox_infra_command"

    async_proxmox: AsyncProxmoxAPI
    task_wrapper: TaskWrapper
    node: str

    def __init__(self, async_proxmox: AsyncProxmoxAPI, node: str):
        self.async_proxmox = async_proxmox
        self.task_wrapper = TaskWrapper(async_proxmox)
        self.node = node

    def find_cidr_overlaps(
        self, list1: List[str], list2: List[str]
    ) -> List[Tuple[str, str]]:
        overlaps = []
        networks1 = [ip_network(cidr) for cidr in list1]
        networks2 = [ip_network(cidr) for cidr in list2]

        for i, net1 in enumerate(networks1):
            for j, net2 in enumerate(networks2):
                if net1.overlaps(net2):
                    overlaps.append((list1[i], list2[j]))

        return overlaps

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

        await self.check_cidrs(sdn_config)

        sdn_zone_id, vnet_id, subnet_for_vms = await self.create_sdn(
            proxmox_ids_start, sdn_config
        )

        for vm_config in vms_config:
            with trace_action(self.logger, self.TRACE_NAME, f"create VM {vm_config=}"):
                vm_id = await self.create_and_start_vm(
                    sdn_zone_id=sdn_zone_id,
                    vnet_id=vnet_id,
                    subnet=subnet_for_vms[0]["subnet"],
                    vm_config=vm_config,
                    built_in_vm_ids=known_builtins,
                )
                vm_configs_with_ids.append((vm_id, vm_config))

        # TODO check for failed starts in the log somehow

        for vm_configs_with_id in vm_configs_with_ids:
            await self.await_vm(vm_configs_with_id[0], vm_configs_with_id[1].is_sandbox)

        # TODO types here
        return vm_configs_with_ids, sdn_zone_id

    async def check_cidrs(self, sdn_config):
        existing_cidrs = await self.read_all_simple_zone_cidrs()

        new_cidrs = []
        for vnet_config in sdn_config.vnet_configs:
            for subnet in vnet_config.subnets:
                new_cidrs.append(str(subnet.cidr))

        # See https://forum.proxmox.com/threads/sdn-simple-zones-and-overlapping-ip-ranges.162739/
        if overlaps := self.find_cidr_overlaps(existing_cidrs, new_cidrs):
            raise ValueError(f"Duplicate IP ranges found: {overlaps}")

    async def create_sdn(self, proxmox_ids_start: str, sdn_config: SdnConfig):
        sdn_zone_id = f"{proxmox_ids_start}z"

        with trace_action(
            self.logger, self.TRACE_NAME, f"create sdn zone {sdn_zone_id=}"
        ):
            zone_create_json = {
                "type": "simple",
                "zone": sdn_zone_id,
            }
            if sdn_config.use_pve_ipam_dnsnmasq:
                zone_create_json["ipam"] = "pve"
                zone_create_json["dhcp"] = "dnsmasq"

            zone_create_response = await self.async_proxmox.request(
                "POST",
                "/cluster/sdn/zones",
                json=zone_create_json,
            )
            # TODO check response

        if len(sdn_config.vnet_configs) > 10:
            raise ValueError(
                f"Too many vnets; max 10, got {len(sdn_config.vnet_configs)}"
            )

        for idx, vnet_config in enumerate(sdn_config.vnet_configs):
            vnet_id = f"{proxmox_ids_start}v{idx}"

            with trace_action(self.logger, self.TRACE_NAME, f"create vnet {vnet_id=}"):
                vnet_create_response = await self.async_proxmox.request(
                    "POST",
                    "/cluster/sdn/vnets",
                    json={"vnet": vnet_id, "zone": sdn_zone_id},
                )
                # TODO check response

            for subnet in vnet_config.subnets:
                with trace_action(
                    self.logger,
                    self.TRACE_NAME,
                    f"create subnet {vnet_id=} {subnet.cidr=}",
                ):
                    subnet_create_response = await self.async_proxmox.request(
                        "POST",
                        f"/cluster/sdn/vnets/{vnet_id}/subnets",
                        json={
                            "subnet": str(subnet.cidr),
                            "type": "subnet",
                            "vnet": vnet_id,
                            "gateway": str(subnet.gateway),
                            "snat": subnet.snat,
                            "dhcp-range": list(
                                dhcp_range.to_proxmox_format()
                                for dhcp_range in subnet.dhcp_ranges
                            ),
                        },
                    )

                    # TODO check response

            # TODO firewall to block access to proxmox?

        await self.do_update_all_sdn()

        with trace_action(self.logger, self.TRACE_NAME, "get subnets"):
            subnet_for_vms = await self.async_proxmox.request(
                "GET", f"/cluster/sdn/vnets/{vnet_id}/subnets"
            )

        return sdn_zone_id, vnet_id, subnet_for_vms

    async def do_update_all_sdn(self) -> None:
        async def update_all_sdn() -> None:
            with trace_action(self.logger, self.TRACE_NAME, "update all SDN"):
                await self.async_proxmox.request("PUT", "/cluster/sdn")

        await self.task_wrapper.do_action_and_wait_for_tasks(update_all_sdn)

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

    async def list_sdn_zones(self):
        with trace_action(self.logger, self.TRACE_NAME, "get SDN zones"):
            return await self.async_proxmox.request("GET", "/cluster/sdn/zones")

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

    async def read_all_simple_zone_cidrs(self) -> List[str]:
        existing_zones = await self.list_sdn_zones()
        simple_zone_names = list(
            zone["zone"] for zone in existing_zones if zone["type"] == "simple"
        )
        all_vnets = await self.async_proxmox.request("GET", "/cluster/sdn/vnets")
        relevant_vnets = list(
            vnet for vnet in all_vnets if vnet["zone"] in simple_zone_names
        )
        relevant_subnet_cidrs = []
        for relevant_vnet in relevant_vnets:
            vnet = relevant_vnet["vnet"]
            vnet_subnets = await self.async_proxmox.request(
                "GET", f"/cluster/sdn/vnets/{vnet}/subnets"
            )
            cidrs = list(subnet["cidr"] for subnet in vnet_subnets)
            relevant_subnet_cidrs += cidrs
        return relevant_subnet_cidrs

    async def tear_down_sdn_zone_and_vnet(self, sdn_zone_id: str) -> None:
        all_vnets = await self.async_proxmox.request("GET", "/cluster/sdn/vnets")
        relevant_vnets = list(vnet for vnet in all_vnets if vnet["zone"] == sdn_zone_id)
        for vnet_details in relevant_vnets:
            vnet = vnet_details["vnet"]
            with trace_action(self.logger, self.TRACE_NAME, f"get subnets for {vnet=}"):
                subnets = await self.async_proxmox.request(
                    "GET", f"/cluster/sdn/vnets/{vnet}/subnets"
                )
            for subnet_details in subnets:
                subnet_id = subnet_details["id"]
                with trace_action(
                    self.logger, self.TRACE_NAME, f"delete subnet {subnet_id=}"
                ):
                    await self.async_proxmox.request(
                        "DELETE",
                        f"/cluster/sdn/vnets/{vnet}/subnets/{subnet_id}",
                    )

            with trace_action(self.logger, self.TRACE_NAME, f"delete vnet {vnet=}"):
                await self.async_proxmox.request("DELETE", f"/cluster/sdn/vnets/{vnet}")

        with trace_action(self.logger, self.TRACE_NAME, f"delete zone {sdn_zone_id=}"):
            await self.async_proxmox.request(
                "DELETE", f"/cluster/sdn/zones/{sdn_zone_id}"
            )

        await self.do_update_all_sdn()

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
