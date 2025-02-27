import abc
from ipaddress import ip_address, ip_network
from logging import getLogger
from typing import Dict, get_args

import tenacity
from inspect_ai.util import trace_action

from proxmoxsandbox.inspect.proxmox.agent_commands import AgentCommands
from proxmoxsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from proxmoxsandbox.inspect.proxmox.infra_commands import InfraCommands
from proxmoxsandbox.inspect.proxmox.qemu_commands import QemuCommands
from proxmoxsandbox.inspect.proxmox.sdn_commands import SdnCommands
from proxmoxsandbox.inspect.proxmox.task_wrapper import TaskWrapper
from proxmoxsandbox.inspect.schema import (
    DhcpRange,
    SdnConfig,
    SubnetConfig,
    VmSourceConfig,
    VnetConfig,
)


class BuiltInVM(abc.ABC):
    logger = getLogger(__name__)

    TRACE_NAME = "proxmox_built_in_vm"
    STATIC_SDN_START = "inspvm"

    async_proxmox: AsyncProxmoxAPI
    qemu_commands: QemuCommands
    sdn_commands: SdnCommands
    task_wrapper: TaskWrapper
    node: str

    def __init__(self, async_proxmox: AsyncProxmoxAPI, node: str):
        self.async_proxmox = async_proxmox
        self.task_wrapper = TaskWrapper(async_proxmox)
        self.qemu_commands = QemuCommands(async_proxmox, node)
        self.sdn_commands = SdnCommands(async_proxmox, node)
        self.node = node

    async def create_and_upload_cloudinit_iso(
        self,
        storage: str,
        vm_id: int,
        meta_data: str = """instance-id: proxmox\n""",  # TODO sort this
        user_data: str = """#cloud-config
package_update: true
packages:
  - qemu-guest-agent
# from buildpack-deps Dockerfile
  - autoconf
  - automake
  - bzip2
  - default-libmysqlclient-dev
  - dpkg-dev
  - file
  - g++
  - gcc
  - imagemagick
  - libbz2-dev
  - libc6-dev
  - libcurl4-openssl-dev
  - libdb-dev
  - libevent-dev
  - libffi-dev
  - libgdbm-dev
  - libglib2.0-dev
  - libgmp-dev
  - libjpeg-dev
  - libkrb5-dev
  - liblzma-dev
  - libmagickcore-dev
  - libmagickwand-dev
  - libmaxminddb-dev
  - libncurses-dev # changed from libncurses5-dev
#   - libncursesw5-dev # not available (possibly related discussion https://github.com/cardano-foundation/developer-portal/issues/1364)
  - libpng-dev
  - libpq-dev
  - libreadline-dev
  - libsqlite3-dev
  - libssl-dev
  - libtool
  - libwebp-dev
  - libxml2-dev
  - libxslt1-dev # changed from libxslt-dev
  - libyaml-dev
  - make
  - patch
  - unzip
  - xz-utils
  - zlib1g-dev
# equivalent of python3.12-bookworm Dockerfile
  - python3
  - python3-pip
  - python3-venv
  - python-is-python3
users:
  - name: ubuntu
    passwd: $6$rounds=4096$6ZjLzzWD9RGieC1y$8R5a/3Vwp3xr9ae9GVlCH0xGGofhp8xlKdddWRugOPhj3frUMr5g57x8t28JRFdS/scPl5AUwrTjah/BVe8dY1
    lock_passwd: false
    sudo: ALL=(ALL) NOPASSWD:ALL
    groups: sudo

runcmd:
  - [ systemctl, enable, qemu-guest-agent ]
  - [ systemctl, start, qemu-guest-agent ]
  - [ systemctl, mask, systemd-networkd-wait-online.service ] # this causes startup delays and makes it annoying to debug network issues
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

        async def upload_cloudinit_iso() -> None:
            await self.async_proxmox.request(
                "POST",
                f"/nodes/{self.node}/storage/{storage}/upload",
                content=payload,
                content_type=f"multipart/form-data; boundary={boundary}",
            )

        await self.task_wrapper.do_action_and_wait_for_tasks(upload_cloudinit_iso)

        @tenacity.retry(
            wait=tenacity.wait_exponential(min=1, exp_base=1.3),
            stop=tenacity.stop_after_delay(30),
        )
        async def attach_to_vm() -> None:
            await self.async_proxmox.request(
                "POST",
                f"/nodes/{self.node}/qemu/{vm_id}/config",
                json={"ide2": f"{storage}:iso/{filename},media=cdrom"},
            )

        await attach_to_vm()

    async def known_builtins(self) -> Dict[str, int]:
        existing_vms = await self.qemu_commands.list_vms()

        found_builtins = {}

        for existing_vm_name in list(
            get_args(get_args(VmSourceConfig.model_fields["built_in"].annotation)[0])
        ):
            for existing_vm in existing_vms:
                if (
                    "tags" in existing_vm
                    and existing_vm["tags"] == f"inspect-{existing_vm_name}"
                ):
                    found_builtins[existing_vm_name] = existing_vm["vmid"]
                    break
        return found_builtins

    async def content_exists(self, storage: str, content_name_end: str) -> bool:
        existing_content = await self.async_proxmox.request(
            "GET",
            f"/nodes/{self.node}/storage/{storage}/content",
        )
        return any(
            content["volid"] and content["volid"].endswith(content_name_end)
            for content in existing_content
        )

    async def ensure_exists(
        self, vm_source_config: VmSourceConfig, known_buitins: Dict[str, int]
    ) -> None:
        if vm_source_config.built_in is None:
            raise ValueError("built_in must be set")

        if vm_source_config.built_in in known_buitins:
            return

        next_available_vm_id = await self.qemu_commands.find_next_available_vm_id()

        # TODO: allow storage to be configurable
        storage = "local"

        if vm_source_config.built_in == "ubuntu24.04":
            await self.ensure_exists_ubuntu_24_04(
                storage=storage, next_available_vm_id=next_available_vm_id
            )
        elif vm_source_config.built_in == "kali":
            await self.ensure_exists_kali(
                storage=storage, next_available_vm_id=next_available_vm_id
            )
        else:
            raise ValueError(f"Unknown built-in {vm_source_config.built_in}")

    async def ensure_exists_ubuntu_24_04(
        self, storage: str, next_available_vm_id: int
    ) -> None:
        built_in = "ubuntu24.04"

        if await self.content_exists(storage, "/ubuntu24.04.ova"):
            self.logger.debug(f"OVA {built_in} already uploaded")
        else:
            with trace_action(
                self.logger,
                self.TRACE_NAME,
                f"upload OVA {built_in=} ",
            ):
                await self.async_proxmox.request(
                    "POST",
                    f"/nodes/{self.node}/storage/{storage}/download-url",
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
                    if not await self.content_exists(storage, "/ubuntu24.04.ova"):
                        raise ValueError("OVA upload not yet complete")

                await upload_complete()

        existing_zones = await self.sdn_commands.list_sdn_zones()

        exists_already = any(
            zone_info["zone"] and zone_info["zone"] == f"{self.STATIC_SDN_START}z"
            for zone_info in existing_zones
        )

        if exists_already:
            vnet_id = f"{self.STATIC_SDN_START}v0"
        else:
            _, vnet_id, _ = await self.sdn_commands.create_sdn(
                proxmox_ids_start=self.STATIC_SDN_START,
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

            async def do_create() -> None:
                await self.async_proxmox.request(
                    "POST",
                    f"/nodes/{self.node}/qemu",
                    json={
                        "vmid": next_available_vm_id,
                        "name": f"inspect-{built_in}",
                        "node": self.node,
                        "cpu": "host",
                        "memory": 2048,
                        "cores": 2,
                        "ostype": "l26",
                        "scsi0": "local-lvm:0,import-from=local:import/ubuntu24.04.ova/ubuntu-noble-24.04-cloudimg.vmdk,format=qcow2,cache=writeback",
                        "scsihw": "virtio-scsi-single",
                        "net0": f"virtio,bridge={vnet_id}",
                        "start": False,
                        "agent": "enabled=1",
                    },
                )

            await self.task_wrapper.do_action_and_wait_for_tasks(do_create)

            await self.create_and_upload_cloudinit_iso(
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
                    f"/nodes/{self.node}/qemu/{next_available_vm_id}/config",
                    json={
                        "tags": f"inspect-{built_in}",
                    },
                )

            await update_tags()

            await self.qemu_commands.start_and_await(next_available_vm_id)

            # now wait for cloud-init to finish

            agent_commands = AgentCommands(self.async_proxmox, self.node)
            res = await agent_commands.exec_command(
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
                    vm_id=next_available_vm_id, pid=res["pid"]
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

            await self.async_proxmox.request(
                "POST",
                f"/nodes/{self.node}/qemu/{next_available_vm_id}/status/shutdown",
            )

            await self.qemu_commands.await_vm(
                vm_id=next_available_vm_id,
                is_sandbox=True,
                status_for_wait="stopped",
            )

            await self.async_proxmox.request(
                "POST",
                f"/nodes/{self.node}/qemu/{next_available_vm_id}/template",
            )

            @tenacity.retry(
                wait=tenacity.wait_exponential(min=0.1, exp_base=1.3),
                stop=tenacity.stop_after_delay(300),
                retry=tenacity.retry_if_result(lambda x: x is False),
            )
            async def is_template() -> bool:
                current_config = await self.async_proxmox.request(
                    "GET",
                    f"/nodes/{self.node}/qemu/{next_available_vm_id}/config?current=1",
                )
                return current_config["template"] == 1

            await is_template()

            @tenacity.retry(
                wait=tenacity.wait_exponential(min=1, exp_base=1.3),
                stop=tenacity.stop_after_delay(30),
            )
            async def remove_cdrom() -> None:
                await self.async_proxmox.request(
                    "POST",
                    f"/nodes/{self.node}/qemu/{next_available_vm_id}/config",
                    json={"ide2": "none,media=cdrom"},
                )

            await remove_cdrom()

            # TODO tear down SDN zone and vnet
            # TODO delete cloudinit ISO

    async def ensure_exists_kali(self, storage: str, next_available_vm_id: int) -> None:
        built_in = "kali"

        filename = "kali-linux-2024.4-live-everything-amd64.iso"

        if await self.content_exists(storage, filename):
            self.logger.debug("Kali ISO already uploaded")
        else:
            with trace_action(
                self.logger,
                self.TRACE_NAME,
                f"upload OVA {built_in=} ",
            ):
                await self.async_proxmox.request(
                    "POST",
                    f"/nodes/{self.node}/storage/{storage}/download-url",
                    json={
                        "content": "iso",
                        "filename": filename,
                        "url": f"http://10.0.2.2:8000/{filename}",
                    },
                )

                @tenacity.retry(
                    wait=tenacity.wait_exponential(min=0.1, exp_base=1.3),
                    stop=tenacity.stop_after_delay(300),
                )
                async def upload_complete() -> None:
                    if not await self.content_exists(filename):
                        raise ValueError("ISO upload not yet complete")

                await upload_complete()

        with trace_action(
            self.logger,
            self.TRACE_NAME,
            f"create VM from ISO {next_available_vm_id=}",
        ):

            async def do_create() -> None:
                await self.async_proxmox.request(
                    "POST",
                    f"/nodes/{self.node}/qemu",
                    json={
                        "vmid": next_available_vm_id,
                        "name": f"inspect-{built_in}",
                        "node": self.node,
                        "cpu": "host",
                        "memory": 2048,
                        "cores": 2,
                        "ostype": "l26",
                        "ide2": f"{storage}:iso/{filename},media=cdrom",
                        "scsihw": "virtio-scsi-single",
                        "start": False,
                        "agent": "enabled=1",
                    },
                )

            await self.task_wrapper.do_action_and_wait_for_tasks(do_create)

            # TODO: rather than these two retried calls, we should wait until the VM is definitely not locked, then go
            @tenacity.retry(
                wait=tenacity.wait_exponential(min=0.1, exp_base=1.3),
                stop=tenacity.stop_after_delay(120),
            )
            async def update_tags() -> None:
                await self.async_proxmox.request(
                    "POST",
                    f"/nodes/{self.node}/qemu/{next_available_vm_id}/config",
                    json={
                        "tags": f"inspect-{built_in}",
                    },
                )

            await update_tags()

            await self.async_proxmox.request(
                "POST",
                f"/nodes/{self.node}/qemu/{next_available_vm_id}/template",
            )

            @tenacity.retry(
                wait=tenacity.wait_exponential(min=0.1, exp_base=1.3),
                stop=tenacity.stop_after_delay(300),
                retry=tenacity.retry_if_result(lambda x: x is False),
            )
            async def is_template() -> bool:
                current_config = await self.async_proxmox.request(
                    "GET",
                    f"/nodes/{self.node}/qemu/{next_available_vm_id}/config?current=1",
                )
                return current_config["template"] == 1

            await is_template()
