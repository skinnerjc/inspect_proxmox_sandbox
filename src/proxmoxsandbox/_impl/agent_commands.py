import base64
from logging import getLogger
from typing import List

import httpx
from inspect_ai.util import (
    SandboxEnvironmentLimits,
    trace_action,
)

from proxmoxsandbox._impl.async_proxmox import (
    AsyncProxmoxAPI,
    ProxmoxJsonDataType,
)


class AgentCommands:
    logger = getLogger(__name__)

    TRACE_NAME = "proxmox_agent_command"

    async_proxmox: AsyncProxmoxAPI
    node: str

    def __init__(self, async_proxmox: AsyncProxmoxAPI, node: str):
        self.async_proxmox = async_proxmox
        self.node = node

    async def get_agent_exec_status(self, vm_id: int, pid: int):
        path = f"/nodes/{self.node}/qemu/{vm_id}/agent/exec-status?pid={pid}"
        return await self.async_proxmox.request("GET", path)

    async def write_file(self, vm_id: int, content: bytes, filepath: str):
        """Write a file to the VM using QEMU agent."""
        path = f"/nodes/{self.node}/qemu/{vm_id}/agent/file-write"
        data: ProxmoxJsonDataType = {
            # It's necessary to encode the content as base-64 ourselves,
            # otherwise a string with non-ASCII characters gets mangled
            # You see the following:
            # ERROR: ResourceException('500 Internal Server Error: Wide character in subroutine entry at /usr/share/perl5/PVE/API2/Qemu/Agent.pm line 491.')  # noqa: E501
            "content": base64.b64encode(content).decode(),
            "file": filepath,
            # encode=0 instead of encode=False is surprising as it's a binary,
            # but encode=False doesn't work, nor does encode="false"
            "encode": 0,
        }
        with trace_action(
            self.logger,
            self.TRACE_NAME,
            f"write_file {vm_id=} {filepath=} {len(content)=}",
        ):
            return await self.async_proxmox.request("POST", path, json=data)

    async def exec_command(self, vm_id: int, command: List[str]):
        """Execute a command in the VM using QEMU agent."""
        with trace_action(
            self.logger, self.TRACE_NAME, f"exec_command {vm_id=} {command=}"
        ):
            path = f"/nodes/{self.node}/qemu/{vm_id}/agent/exec"
            data: ProxmoxJsonDataType = {"command": command}
            return await self.async_proxmox.request("POST", path, json=data)

    async def read_file_or_blank(
        self,
        vm_id: int,
        filepath: str,
        max_size: int = SandboxEnvironmentLimits.MAX_READ_FILE_SIZE,
    ):
        with trace_action(
            self.logger,
            self.TRACE_NAME,
            f"read_file_or_blank {vm_id=} {filepath=} {max_size=}",
        ):
            try:
                return await self.read_file(vm_id, filepath, max_size)
            except httpx.HTTPStatusError as e:
                if (
                    e.response.status_code == 500
                    and "no such file" in e.response.reason_phrase.casefold()
                ):
                    return {"content": ""}
                else:
                    raise e

    async def read_file(
        self,
        vm_id: int,
        filepath: str,
        max_size: int = SandboxEnvironmentLimits.MAX_READ_FILE_SIZE,
    ):
        # this is a hack; it would be better to use a type here with
        # e.g. size_bytes and friendly_name
        max_size_str = (
            SandboxEnvironmentLimits.MAX_READ_FILE_SIZE_STR
            if max_size == SandboxEnvironmentLimits.MAX_READ_FILE_SIZE
            else SandboxEnvironmentLimits.MAX_EXEC_OUTPUT_SIZE_STR
        )
        return await self.async_proxmox.read_file(
            self.node, vm_id, filepath, max_size, max_size_str
        )

    async def create_snapshot(self, vm_id: int, snapshot_name: str) -> None:
        path = f"/nodes/{self.node}/qemu/{vm_id}/snapshot"
        data: ProxmoxJsonDataType = {"snapname": snapshot_name, "vmstate": 1}
        await self.async_proxmox.request("POST", path, json=data)

    async def rollback_to_snapshot(self, vm_id: int, snapshot_name: str) -> None:
        path = f"/nodes/{self.node}/qemu/{vm_id}/snapshot/{snapshot_name}/rollback"
        await self.async_proxmox.request("POST", path)
