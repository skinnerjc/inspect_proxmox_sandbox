import abc
from ipaddress import ip_network
from logging import getLogger
from typing import List, Tuple, Dict

from inspect_ai.util import trace_action

from proxmoxsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from proxmoxsandbox.inspect.proxmox.task_wrapper import TaskWrapper
from proxmoxsandbox.inspect.schema import (
    SdnConfig,
)


class SdnCommands(abc.ABC):
    logger = getLogger(__name__)

    TRACE_NAME = "proxmox_sdn_command"

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
        await self.check_cidrs(sdn_config)

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

            await self.async_proxmox.request(
                "POST",
                "/cluster/sdn/zones",
                json=zone_create_json,
            )

        if len(sdn_config.vnet_configs) > 10:
            raise ValueError(
                f"Too many vnets; max 10, got {len(sdn_config.vnet_configs)}"
            )

        vnet_aliases: Dict[str,str] = {}

        for idx, vnet_config in enumerate(sdn_config.vnet_configs):
            vnet_id = f"{proxmox_ids_start}v{idx}"

            with trace_action(self.logger, self.TRACE_NAME, f"create vnet {vnet_id=}"):
                vnet_json = {"vnet": vnet_id, "zone": sdn_zone_id}
                if vnet_config.alias is not None:
                    vnet_json["alias"] = vnet_config.alias
                    vnet_aliases[vnet_config.alias] = vnet_id
                await self.async_proxmox.request(
                    "POST",
                    "/cluster/sdn/vnets",
                    json=vnet_json,
                )

            for subnet in vnet_config.subnets:
                with trace_action(
                    self.logger,
                    self.TRACE_NAME,
                    f"create subnet {vnet_id=} {subnet.cidr=}",
                ):
                    await self.async_proxmox.request(
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

            # TODO firewall to block access to proxmox?

        await self.do_update_all_sdn()

        return sdn_zone_id, vnet_id, vnet_aliases

    async def do_update_all_sdn(self) -> None:
        async def update_all_sdn() -> None:
            with trace_action(self.logger, self.TRACE_NAME, "update all SDN"):
                await self.async_proxmox.request("PUT", "/cluster/sdn")

        await self.task_wrapper.do_action_and_wait_for_tasks(update_all_sdn)

    async def list_sdn_zones(self):
        with trace_action(self.logger, self.TRACE_NAME, "get SDN zones"):
            return await self.async_proxmox.request("GET", "/cluster/sdn/zones")

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
        await self.tear_down_sdn_zones_and_vnets([sdn_zone_id])

    async def tear_down_sdn_zones_and_vnets(self, sdn_zone_ids: List[str]) -> None:
        for sdn_zone_id in sdn_zone_ids:
            all_vnets = await self.async_proxmox.request("GET", "/cluster/sdn/vnets")
            relevant_vnets = list(
                vnet for vnet in all_vnets if vnet["zone"] == sdn_zone_id
            )
            for vnet_details in relevant_vnets:
                vnet = vnet_details["vnet"]
                with trace_action(
                    self.logger, self.TRACE_NAME, f"get subnets for {vnet=}"
                ):
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
                    await self.async_proxmox.request(
                        "DELETE", f"/cluster/sdn/vnets/{vnet}"
                    )

            with trace_action(
                self.logger, self.TRACE_NAME, f"delete zone {sdn_zone_id=}"
            ):
                await self.async_proxmox.request(
                    "DELETE", f"/cluster/sdn/zones/{sdn_zone_id}"
                )

        await self.do_update_all_sdn()
