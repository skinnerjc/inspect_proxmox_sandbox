import abc
from ipaddress import ip_address, ip_network
from logging import getLogger
from typing import Tuple, Callable, Awaitable

import tenacity
from inspect_ai.util import trace_action
import asyncio

from vmsandbox.inspect.proxmox.agent_commands import AgentCommands
from vmsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from vmsandbox.inspect.schema import (
    DhcpRange,
    SdnConfig,
    SubnetConfig,
    VmConfig,
    VnetConfig,
)


class InfraCommands(abc.ABC):
    logger = getLogger(__name__)

    TRACE_NAME = "proxmox_infra_command"

    async_proxmox: AsyncProxmoxAPI

    def __init__(self, async_proxmox: AsyncProxmoxAPI):
        self.async_proxmox = async_proxmox

    async def do_action_and_wait_for_tasks(
        self, the_action: Callable[[], Awaitable[None]], async_wait_seconds: int = 2
    ) -> None:
        incomplete_tasks_pre_action = await self.new_incomplete_tasks(
            pre_existing_incomplete_tasks=[]
        )

        await the_action()

        # Regrettably, sometimes the resulting server-side tasks don't turn up immediately
        await asyncio.sleep(async_wait_seconds)

        @tenacity.retry(
            wait=tenacity.wait_exponential(min=0.1, exp_base=1.3),
            stop=tenacity.stop_after_delay(300),
            retry=tenacity.retry_if_result(lambda x: x is False),
        )
        async def new_tasks_are_complete() -> bool:
            post_action_current_tasks = await self.new_incomplete_tasks(
                pre_existing_incomplete_tasks=incomplete_tasks_pre_action
            )
            return not post_action_current_tasks

        await new_tasks_are_complete()

    async def create_and_upload_cloudinit_iso(
        self,
        node: str,
        storage: str,
        vm_id: int,
        meta_data: str = """instance-id: proxmox\n""",  # TODO sort this
        user_data: str = """#cloud-config
package_update: true
packages:
  - qemu-guest-agent
users:
  - name: ubuntu
    passwd: $6$rounds=4096$6ZjLzzWD9RGieC1y$8R5a/3Vwp3xr9ae9GVlCH0xGGofhp8xlKdddWRugOPhj3frUMr5g57x8t28JRFdS/scPl5AUwrTjah/BVe8dY1
    lock_passwd: false
    sudo: ALL=(ALL) NOPASSWD:ALL
    groups: sudo

runcmd:
  - [ systemctl, enable, qemu-guest-agent ]
  - [ systemctl, start, qemu-guest-agent ]
""",
        network_config: str = """network:
  version: 2
  ethernets:
    default:
      match:
        name: e*
      dhcp4: true
      dhcp6: false
""",
    ) -> None:
        """
        Creates a cloud-init ISO and uploads it to Proxmox storage.

        The ISO is created in memory and uploaded directly without writing to disk.
        """
        from io import BytesIO

        import pycdlib

        iso = pycdlib.PyCdlib()
        iso.new(interchange_level=3, joliet=3, rock_ridge="1.12", vol_ident="CIDATA")

        # Add cloud-init files to ISO
        for filename, content in [
            ("META_DATA", meta_data),
            ("USER_DATA", user_data),
            ("NETWORK", network_config),
        ]:
            if content:
                content_bytes = content.encode("utf-8")
                buffer = BytesIO(content_bytes)

                iso_path = f"/{filename}"
                proper_name = {
                    "META_DATA": "meta-data",
                    "USER_DATA": "user-data",
                    "NETWORK": "network-config",
                }[filename]

                iso.add_fp(
                    buffer,
                    len(content_bytes),
                    iso_path,
                    joliet_path=f"/{proper_name}",
                    rr_name=proper_name,
                )

        # Write ISO to memory
        iso_buffer = BytesIO()
        iso.write_fp(iso_buffer)
        iso.close()

        iso_data = iso_buffer.getvalue()
        filename = f"vm-{vm_id}-cl00udinit.iso"

        # Create the multipart form-data manually
        import uuid

        boundary = str(uuid.uuid4())

        # Construct the multipart form-data payload
        payload = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="content"\r\n\r\niso\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="filename"; filename="{filename}"\r\n'
            # f"Content-Type: application/x-iso9660-image\r\n"
            f"Content-Length: {len(iso_data)}\r\n\r\n"
        ).encode("us-ascii")

        payload += iso_data + f"\r\n--{boundary}--\r\n".encode("us-ascii")

        await self.async_proxmox.request(
            "POST",
            f"/nodes/{node}/storage/{storage}/upload",
            content=payload,
            content_type=f"multipart/form-data; boundary={boundary}",
        )

        @tenacity.retry(
            wait=tenacity.wait_exponential(min=1, exp_base=1.3),
            stop=tenacity.stop_after_delay(30),
        )
        async def attach_to_vm() -> None:
            await self.async_proxmox.request(
                "POST",
                f"/nodes/{node}/qemu/{vm_id}/config",
                json={"ide2": f"{storage}:iso/{filename},media=cdrom"},
            )

        await attach_to_vm()

    async def create_sdn_and_vms(
        self,
        proxmox_ids_start: str,
        sdn_config: SdnConfig | None,
        vms_config: Tuple[VmConfig, ...],
    ):
        vm_configs_with_ids = []
        sdn_zone_id = None
        if sdn_config is None:
            raise NotImplementedError()
        else:
            sdn_zone_id, vnet_id, subnet_for_vms = await self.create_sdn(
                proxmox_ids_start, sdn_config
            )

            for vm_config in vms_config:
                with trace_action(
                    self.logger, self.TRACE_NAME, f"create VM {vm_config=}"
                ):
                    vm_id = await self.create_and_start_vm(
                        node="proxmox",
                        sdn_zone_id=sdn_zone_id,
                        vnet_id=vnet_id,
                        subnet=subnet_for_vms[0]["subnet"],
                        vm_config=vm_config,
                    )
                    vm_configs_with_ids.append((vm_id, vm_config))

            # TODO check for failed starts in the log somehow

        for vm_configs_with_id in vm_configs_with_ids:
            await self.await_vm(
                "proxmox", vm_configs_with_id[0], vm_configs_with_id[1].is_sandbox
            )

        return vm_configs_with_ids, sdn_zone_id

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

        with trace_action(self.logger, self.TRACE_NAME, "update all SDN"):
            await self.async_proxmox.request("PUT", "/cluster/sdn")

            # TODO await network having restarted

        with trace_action(self.logger, self.TRACE_NAME, "get subnets"):
            subnet_for_vms = await self.async_proxmox.request(
                "GET", f"/cluster/sdn/vnets/{vnet_id}/subnets"
            )

        return sdn_zone_id, vnet_id, subnet_for_vms

    async def await_vm(
        self, node: str, vm_id: int, is_sandbox: bool, status_for_wait: str = "running"
    ) -> None:
        @tenacity.retry(
            wait=tenacity.wait_exponential(min=0.1, exp_base=1.3),
            stop=tenacity.stop_after_delay(300),
        )
        async def is_in_status() -> None:
            vm_status = await self.async_proxmox.request(
                "GET", f"/nodes/{node}/qemu/{vm_id}/status/current"
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
                await self.async_proxmox.ping_qemu_agent(node, vm_id)

            with trace_action(
                self.logger, self.TRACE_NAME, f"await VM {vm_id} QEMU agent"
            ):
                await qemu_agent_reachable()

    async def list_sdn_zones(self):
        with trace_action(self.logger, self.TRACE_NAME, "get SDN zones"):
            return await self.async_proxmox.request("GET", "/cluster/sdn/zones")

    async def destroy_vm(self, node: str, vm_id: int) -> None:
        with trace_action(self.logger, self.TRACE_NAME, f"stop VM {vm_id}"):
            await self.async_proxmox.request(
                "POST", f"/nodes/{node}/qemu/{vm_id}/status/stop"
            )

        @tenacity.retry(
            wait=tenacity.wait_exponential(min=0.1, exp_base=1.3),
            stop=tenacity.stop_after_delay(300),
        )
        async def is_not_running() -> None:
            vm_status = await self.async_proxmox.request(
                "GET", f"/nodes/{node}/qemu/{vm_id}/status/current"
            )
            if vm_status["status"] != "stopped":
                raise ValueError(f"vm {vm_id} still running")

        with trace_action(self.logger, self.TRACE_NAME, f"await VM {vm_id} stopped"):
            await is_not_running()

        with trace_action(self.logger, self.TRACE_NAME, f"delete VM {vm_id}"):
            await self.async_proxmox.request("DELETE", f"/nodes/{node}/qemu/{vm_id}")

        @tenacity.retry(
            wait=tenacity.wait_exponential(min=0.1, exp_base=1.3),
            stop=tenacity.stop_after_delay(30),
        )
        async def vm_deleted() -> None:
            current = await self.async_proxmox.request(
                method="GET",
                path=f"/nodes/{node}/qemu/{vm_id}/status/current",
                raise_errors=False,
            )
            if "vmid" in current:
                raise ValueError(f"vm {vm_id} still exists")

        with trace_action(self.logger, self.TRACE_NAME, f"await VM {vm_id} deleted"):
            await vm_deleted()

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

        with trace_action(self.logger, self.TRACE_NAME, "update all SDN"):
            await self.async_proxmox.request("PUT", "/cluster/sdn")

    async def list_vms(self, node: str):
        with trace_action(self.logger, self.TRACE_NAME, "list all VMs"):
            return await self.async_proxmox.request("GET", f"/nodes/{node}/qemu")

    async def find_next_available_vm_id(self, node) -> int:
        existing_vms = await self.list_vms(node=node)
        if existing_vms:
            next_available_vm_id = (
                max(list(int(existing["vmid"]) for existing in existing_vms)) + 1
            )
        else:
            next_available_vm_id = 100
        return next_available_vm_id

    async def start_and_await(self, node: str, vm_id: int) -> None:
        await self.async_proxmox.request(
            "POST",
            f"/nodes/{node}/qemu/{vm_id}/status/start",
        )

        await self.await_vm(
            node=node,
            vm_id=vm_id,
            is_sandbox=True,
        )

    async def create_builtin(self, node: str, vm_config: VmConfig):
        next_available_vm_id = await self.find_next_available_vm_id(node)

        # TODO: allow storage to be configurable
        storage = "local"

        async def content_exists(content_name_end: str) -> bool:
            existing_content = await self.async_proxmox.request(
                "GET",
                f"/nodes/{node}/storage/{storage}/content",
            )
            return any(
                content["volid"] and content["volid"].endswith(content_name_end)
                for content in existing_content
            )

        if await content_exists("/ubuntu24.04.ova"):
            self.logger.debug(
                f"OVA {vm_config.vm_source_config.built_in} already uploaded"
            )
        else:
            with trace_action(
                self.logger,
                self.TRACE_NAME,
                f"upload OVA {vm_config.vm_source_config.built_in=} ",
            ):
                await self.async_proxmox.request(
                    "POST",
                    f"/nodes/{node}/storage/{storage}/download-url",
                    json={
                        "content": "import",
                        "filename": "ubuntu24.04.ova",
                        "url": "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.ova",
                    },
                )

                @tenacity.retry(
                    wait=tenacity.wait_exponential(min=0.1, exp_base=1.3),
                    stop=tenacity.stop_after_delay(300),
                )
                async def upload_complete() -> None:
                    if not await content_exists("/ubuntu24.04.ova"):
                        raise ValueError("OVA upload not yet complete")

                await upload_complete()

        existing_zones = await self.list_sdn_zones()

        exists_already = any(
            zone_info["zone"] and zone_info["zone"] == "inspvmz"
            for zone_info in existing_zones
        )

        if exists_already:
            sdn_zone_id = "inspvmz"
            vnet_id = "inspvmv0"
        else:
            _, vnet_id, _ = await self.create_sdn(
                proxmox_ids_start="inspvm",
                sdn_config=SdnConfig(
                    vnet_configs=(
                        VnetConfig(
                            subnets=(
                                SubnetConfig(
                                    cidr=ip_network("192.168.99.0/24"),
                                    gateway=ip_address("192.168.99.1"),
                                    snat=True,
                                    dhcp_ranges=(
                                        DhcpRange(
                                            start=ip_address("192.168.99.50"),
                                            end=ip_address("192.168.99.100"),
                                        ),
                                    ),
                                ),
                            )
                        ),
                    )
                ),
            )

        with trace_action(
            self.logger,
            self.TRACE_NAME,
            f"create VM from OVA {next_available_vm_id=}",
        ):
            await self.async_proxmox.request(
                "POST",
                f"/nodes/{node}/qemu",
                json={
                    "vmid": next_available_vm_id,
                    "name": f"inspect-{vm_config.vm_source_config.built_in}",
                    "node": node,
                    "cpu": "host",
                    "memory": 2048,
                    "cores": 2,
                    "ostype": "l26",
                    "scsi0": "local-lvm:0,import-from=local:import/ubuntu24.04.ova/ubuntu-noble-24.04-cloudimg.vmdk,format=qcow2,cache=writeback",
                    "scsihw": "virtio-scsi-single",
                    "net0": f"virtio,bridge={vnet_id}",
                    "start": False,
                    "agent": f"enabled={1 if vm_config.is_sandbox else 0}",
                },
            )
            await self.await_vm(
                node=node,
                vm_id=next_available_vm_id,
                is_sandbox=False,
                status_for_wait="stopped",
            )

            # @tenacity.retry(
            #     wait=tenacity.wait_exponential(min=0.1, exp_base=1.3),
            #     stop=tenacity.stop_after_delay(120),
            # )
            # async def add_cloudinit_drive() -> None:
            #     # this fails while the VM is creating. It would be better to wait until the VM is finished, but
            #     # it seems the VM is always in the status "stopped" until creation is finished
            #     await self.async_proxmox.request(
            #         "POST",
            #         f"/nodes/{node}/qemu/{next_available_vm_id}/config",
            #         json={"ide3": "local-lvm:cloudinit"},
            #     )

            # await add_cloudinit_drive()

            await self.create_and_upload_cloudinit_iso(
                node=node,
                storage="local",
                vm_id=next_available_vm_id,
            )

            # TODO: rather than these two retried calls, we should wait until the VM is definitely not locked, then go
            @tenacity.retry(
                wait=tenacity.wait_exponential(min=0.1, exp_base=1.3),
                stop=tenacity.stop_after_delay(120),
            )
            async def update_tags() -> None:
                await self.async_proxmox.request(
                    "POST",
                    f"/nodes/{node}/qemu/{next_available_vm_id}/config",
                    json={
                        "tags": f"inspect-{vm_config.vm_source_config.built_in}",
                    },
                )

            await update_tags()

            await self.start_and_await(node, next_available_vm_id)

            # now wait for cloud-init to finish

            agent_commands = AgentCommands(self.async_proxmox)
            res = await agent_commands.exec_command(
                node=node,
                vm_id=next_available_vm_id,
                command=["cloud-init", "status", "--wait"],
            )

            @tenacity.retry(
                wait=tenacity.wait_exponential(min=0.1, exp_base=1.3),
                stop=tenacity.stop_after_delay(300),
                retry=tenacity.retry_if_result(lambda x: x is False),
            )
            async def wait_for_cloud_init() -> bool:
                exec_status = await agent_commands.get_agent_exec_status(
                    node=node, vm_id=next_available_vm_id, pid=res["pid"]
                )
                print(f"wait_for_exec; {exec_status=}")
                if exec_status["exited"] == 1:
                    print(f"wait_for_exec exited = 1; {exec_status=}")
                    if exec_status["out-data"].strip() == "status: done":
                        return True
                    else:
                        raise ValueError(
                            f"cloud-init failed: {exec_status['out-data']}"
                        )
                else:
                    return False

            await wait_for_cloud_init()

            res_sync = await agent_commands.exec_command(
                node=node,
                vm_id=next_available_vm_id,
                command=["sync"],
            )

            @tenacity.retry(
                wait=tenacity.wait_exponential(min=0.1, exp_base=1.3),
                stop=tenacity.stop_after_delay(300),
                retry=tenacity.retry_if_result(lambda x: x is False),
            )
            async def wait_for_sync() -> bool:
                exec_status = await agent_commands.get_agent_exec_status(
                    node=node, vm_id=next_available_vm_id, pid=res_sync["pid"]
                )
                print(f"wait_for_exec; {exec_status=}")
                return exec_status["exited"] == 1

            await wait_for_sync()

            await self.async_proxmox.request(
                "POST",
                f"/nodes/{node}/qemu/{next_available_vm_id}/status/shutdown",
            )

            await self.await_vm(
                node=node,
                vm_id=next_available_vm_id,
                is_sandbox=True,
                status_for_wait="stopped",
            )

            await self.async_proxmox.request(
                "POST",
                f"/nodes/{node}/qemu/{next_available_vm_id}/template",
            )

            @tenacity.retry(
                wait=tenacity.wait_exponential(min=0.1, exp_base=1.3),
                stop=tenacity.stop_after_delay(300),
                retry=tenacity.retry_if_result(lambda x: x is False),
            )
            async def is_template() -> bool:
                current_config = await self.async_proxmox.request(
                    "GET",
                    f"/nodes/{node}/qemu/{next_available_vm_id}/config?current=1",
                )
                return current_config["template"] == 1

            await is_template()

            return next_available_vm_id
            # TODO tear down SDN zone and vnet
            # TODO remove CDROM drive
            # TODO delete cloudinit ISO

    async def create_and_start_vm(
        self,
        node: str,
        sdn_zone_id: str,
        vnet_id: str,
        subnet: str,
        vm_config: VmConfig,
    ) -> int:
        new_vm_id: int | None = None

        if vm_config.vm_source_config.existing_backup_name:
            new_vm_id = await self.find_next_available_vm_id(node)
            with trace_action(
                self.logger,
                self.TRACE_NAME,
                f"create VM from backup {new_vm_id=}",
            ):
                await self.async_proxmox.request(
                    "POST",
                    f"/nodes/{node}/qemu",
                    json={
                        "vmid": new_vm_id,
                        "node": node,
                        "archive": f"/var/lib/vz/dump/{vm_config.vm_source_config.existing_backup_name}",
                        "net0": f"virtio,bridge={vnet_id}",
                        "start": True,
                    },
                )
        elif vm_config.vm_source_config.built_in:
            if vm_config.vm_source_config.built_in == "ubuntu24.04":
                # TODO: check for existing template VM

                existing_vms = await self.list_vms(node=node)

                vm_id_to_clone = None

                for existing_vm in existing_vms:
                    if (
                        "tags" in existing_vm
                        and existing_vm["tags"]
                        == f"inspect-{vm_config.vm_source_config.built_in}"
                    ):
                        vm_id_to_clone = int(existing_vm["vmid"])
                        break

                # TODO: check "Import" is enabled for local storage

                if vm_id_to_clone is None:
                    vm_id_to_clone = await self.create_builtin(node, vm_config)

                new_vm_id = await self.find_next_available_vm_id(node)

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
                        f"/nodes/{node}/qemu/{vm_id_to_clone}/clone",
                        json={"newid": new_vm_id, "full": 0},
                    )

                await create_clone()

                async def update_network() -> None:
                    await self.async_proxmox.request(
                        "POST",
                        f"/nodes/{node}/qemu/{new_vm_id}/config",
                        json={
                            "tags": "",  # remove the tag as that's only for the template
                            "net0": f"virtio,bridge={vnet_id}",
                        },
                    )

                await self.do_action_and_wait_for_tasks(update_network)

                await self.start_and_await(node, new_vm_id)

        else:
            raise NotImplementedError(f"Not supported: {vm_config.vm_source_config=}")
        if new_vm_id is None:
            raise ValueError("No VM ID?")
        return new_vm_id

    async def new_incomplete_tasks(self, pre_existing_incomplete_tasks):
        current_tasks = await self.async_proxmox.request("GET", "/cluster/tasks")

        current_incomplete_tasks = [
            current_task
            for current_task in current_tasks
            if (
                ("status" in current_task and current_task["status"] != "OK")
                or "status" not in current_task
            )
        ]

        new_tasks = [
            current_incomplete_task
            for current_incomplete_task in current_incomplete_tasks
            if not any(
                pre_existing_task["upid"] == current_incomplete_task["upid"]
                for pre_existing_task in pre_existing_incomplete_tasks
            )
        ]
        return new_tasks
