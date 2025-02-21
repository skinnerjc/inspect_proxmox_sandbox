from logging import getLogger
from typing import Optional

import httpx
from inspect_ai.util import (
    OutputLimitExceededError,
    SandboxEnvironmentLimits,
    trace_action,
)
from pydantic_core import from_json


class AsyncProxmoxAPI:
    logger = getLogger(__name__)

    TRACE_NAME = "async_proxmox"

    base_url: str
    username: str
    password: str
    verify_ssl: bool
    ticket: Optional[str] = None
    csrf_token: Optional[str] = None

    def __init__(self, host: str, user: str, password: str, verify_ssl: bool = True):
        self.base_url = f"https://{host}/api2/json"
        self.username = user
        self.password = password
        self.verify_ssl = verify_ssl

    def __hash__(self):
        return hash((self.base_url, self.username, self.password, self.verify_ssl))

    async def _login(self, client: httpx.AsyncClient):
        """Get new authentication ticket and CSRF token."""
        with trace_action(self.logger, self.TRACE_NAME, "login"):
            response = await client.post(
                f"{self.base_url}/access/ticket",
                data={"username": self.username, "password": self.password},
            )
            response.raise_for_status()

            data = response.json()["data"]
            self.ticket = data["ticket"]
            self.csrf_token = data["CSRFPreventionToken"]

    async def request(
        self,
        method: str,
        path: str,
        raise_errors: bool = True,
        content_type: str | None = None,
        json: dict | None = None,
        **kwargs,
    ):
        if json is not None:
            content_type = "application/json"
        async with httpx.AsyncClient(
            verify=self.verify_ssl,
            timeout=httpx.Timeout(connect=5, read=60, write=60, pool=60),
        ) as client:
            # Always get a fresh ticket if we don't have one
            if not self.ticket:
                await self._login(client)

            if self.csrf_token is None:
                raise ValueError("CSRF token was not set by login")

            headers = self._prepare_headers(method, content_type)

            response = await client.request(
                method, f"{self.base_url}{path}", headers=headers, json=json, **kwargs
            )

            # If we get a 401, our ticket might have expired (2 hour lifetime)
            # Try to login once and retry the request
            if response.status_code == 401:
                await self._login(client)
                headers = self._prepare_headers(method, content_type)

                response = await client.request(
                    method, f"{self.base_url}{path}", headers=headers, **kwargs
                )

            if response.is_error and raise_errors:
                response.raise_for_status()
            else:
                if response.is_error:
                    return response.json()
            return response.json()["data"]

    def _prepare_headers(self, method: str, content_type: str | None):
        headers = {
            "Cookie": f"PVEAuthCookie={self.ticket}",
        }

        if content_type is not None:
            headers["Content-Type"] = content_type

        # Add CSRF token for write operations
        if method.upper() in ["POST", "PUT", "DELETE"]:
            headers["CSRFPreventionToken"] = self.csrf_token
        return headers

    async def ping_qemu_agent(self, node: str, vm_id: int):
        await self.request("POST", f"/nodes/{node}/qemu/{vm_id}/agent/ping")

    # TODO split this method and push most of it down into agent_commands, it's too coupled
    async def read_file(self, node: str, vm_id: int, filepath: str, max_size: int):
        """Read a file from the VM using QEMU agent with optional size limit.

        Args:
            node (str): The node name
            vm_id (int): The VM ID
            filepath (str): Path to the file to read
            max_size (int, optional): Maximum number of bytes to read. None means no limit.

        Returns:
            dict: The file contents and metadata

        Raises:
            FileTooLargeError: If the file size exceeds max_size
        """
        path = f"/nodes/{node}/qemu/{vm_id}/agent/file-read"

        # this is a hack; it would be better to use a type here with e.g. size_bytes and friendly_name
        max_size_str = (
            SandboxEnvironmentLimits.MAX_READ_FILE_SIZE_STR
            if max_size == SandboxEnvironmentLimits.MAX_READ_FILE_SIZE
            else SandboxEnvironmentLimits.MAX_EXEC_OUTPUT_SIZE_STR
        )

        async with httpx.AsyncClient(
            verify=self.verify_ssl,
            timeout=httpx.Timeout(connect=5, read=60, write=60, pool=60),
        ) as client:
            # ping to refresh token if needed, so we don't have to do it in the stream
            await self.ping_qemu_agent(node, vm_id)

            async with client.stream(
                "GET",
                f"{self.base_url}{path}",
                headers={
                    "Cookie": f"PVEAuthCookie={self.ticket}",
                },
                params={"file": filepath},
            ) as response:
                response.raise_for_status()

                # Check Content-Length if available
                content_length = response.headers.get("content-length")
                if content_length and max_size:
                    if int(content_length) > max_size:
                        await response.aclose()
                        raise OutputLimitExceededError(max_size_str, None)

                # Read the response in chunks
                chunks = []
                total_size = 0

                async for chunk in response.aiter_bytes(chunk_size=8192):
                    chunks.append(chunk)
                    total_size += len(chunk)

                    if max_size and total_size > max_size:
                        await response.aclose()

                        truncated_json = from_json(
                            b"".join(chunks) + b'"', allow_partial=True
                        )
                        truncated_content = truncated_json.get(
                            "data", {"content": ""}
                        ).get(
                            "content",
                            "",
                        )
                        raise OutputLimitExceededError(max_size_str, truncated_content)

                # Combine chunks and parse JSON
                full_response = b"".join(chunks)
                return httpx.Response(200, content=full_response).json()["data"]
