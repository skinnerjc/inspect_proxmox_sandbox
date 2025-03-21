import json
from logging import getLogger
from typing import Dict, List, Optional, Union

import aiohttp
from inspect_ai.util import (
    OutputLimitExceededError,
    trace_action,
)
from pydantic_core import from_json

ProxmoxJsonDataType = Dict[str, Union[str, List[str], int, bool, None]]


class AsyncProxmoxAPI:
    logger = getLogger(__name__)

    TRACE_NAME = "async_proxmox"

    base_url: str
    api_base_url: str
    username: str
    password: str
    verify_ssl: bool
    ticket: Optional[str] = None
    csrf_token: Optional[str] = None

    # note: host *includes* :port
    def __init__(self, host: str, user: str, password: str, verify_ssl: bool = True):
        self.base_url = f"https://{host}"
        self.api_base_url = f"{self.base_url}/api2/json"
        self.username = user
        self.password = password
        self.verify_ssl = verify_ssl

    def __hash__(self):
        return hash((self.api_base_url, self.username, self.password, self.verify_ssl))

    async def _login(self, session: aiohttp.ClientSession):
        """Get new authentication ticket and CSRF token."""
        with trace_action(self.logger, self.TRACE_NAME, "login"):
            async with session.post(
                f"{self.api_base_url}/access/ticket",
                data={"username": self.username, "password": self.password},
                ssl=False,
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    response.raise_for_status()

                response_data = await response.json()
                data = response_data["data"]
                self.ticket = data["ticket"]
                self.csrf_token = data["CSRFPreventionToken"]

    async def request(
        self,
        method: str,
        path: str,
        raise_errors: bool = True,
        content_type: str | None = None,
        json: Optional[ProxmoxJsonDataType] = None,
        body_content: Optional[str|bytes] = None,
    ):
        if json is not None:
            content_type = "application/json"

        ssl = None if self.verify_ssl else False
        timeout = aiohttp.ClientTimeout(
            total=60, connect=5, sock_connect=5, sock_read=60
        )

        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Always get a fresh ticket if we don't have one
            if not self.ticket:
                await self._login(session)

            if self.csrf_token is None:
                raise ValueError("CSRF token was not set by login")

            headers = self._prepare_headers(method, content_type)

            async with session.request(
                method,
                f"{self.api_base_url}{path}",
                headers=headers,
                json=json,
                ssl=ssl,
                data=body_content,
            ) as response:
                # If we get a 401, our ticket might have expired (2 hour lifetime)
                # Try to login once and retry the request
                if response.status == 401:
                    await self._login(session)
                    headers = self._prepare_headers(method, content_type)

                    async with session.request(
                        method,
                        f"{self.api_base_url}{path}",
                        headers=headers,
                        ssl=ssl,
                    ) as retry_response:
                        response = retry_response

                if response.status >= 400 and raise_errors:
                    # Include response text in the error message
                    text = await response.text()
                    message = f"HTTP response error: {response.status} {response.reason}: {text}"
                    raise aiohttp.ClientResponseError(
                        response.request_info,
                        response.history,
                        status=response.status,
                        message=message,
                        headers=response.headers,
                    )

                response_json = await response.json()
                if response.status >= 400:
                    return response_json

                return response_json["data"]

    def _prepare_headers(self, method: str, content_type: str | None):
        headers = {
            "Cookie": f"PVEAuthCookie={self.ticket}",
        }

        if content_type is not None:
            headers["Content-Type"] = content_type

        # Add CSRF token for write operations
        if method.upper() in ["POST", "PUT", "DELETE"]:
            if self.csrf_token is None:
                raise ValueError("CSRF token was not set; login first")
            headers["CSRFPreventionToken"] = self.csrf_token
        return headers

    # this more naturally belongs in qemu_commands but it's copied here because of read_file
    async def _ping_qemu_agent(self, node: str, vm_id: int):
        await self.request("POST", f"/nodes/{node}/qemu/{vm_id}/agent/ping")

    async def read_file(
        self, node: str, vm_id: int, filepath: str, max_size: int, max_size_str: str
    ):
        """Read a file from the VM using QEMU agent with optional size limit.

        Args:
            node (str): The node name
            vm_id (int): The VM ID
            filepath (str): Path to the file to read
            max_size (int, optional): Maximum number of bytes to read. None means no limit.
            max_size_str (str): Human-readable string of the max_size

        Returns:
            dict: The file contents and metadata

        Raises:
            FileTooLargeError: If the file size exceeds max_size
        """
        path = f"/nodes/{node}/qemu/{vm_id}/agent/file-read"

        ssl = None if self.verify_ssl else False
        timeout = aiohttp.ClientTimeout(
            total=60, connect=5, sock_connect=5, sock_read=60
        )

        async with aiohttp.ClientSession(timeout=timeout) as session:
            # ping to refresh token if needed, so we don't have to do it in the stream
            await self._ping_qemu_agent(node, vm_id)

            headers = {
                "Cookie": f"PVEAuthCookie={self.ticket}",
            }

            async with session.get(
                f"{self.api_base_url}{path}",
                headers=headers,
                params={"file": filepath},
                ssl=ssl,
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    raise aiohttp.ClientResponseError(
                        response.request_info,
                        response.history,
                        status=response.status,
                        message=f"HTTP response error: {response.status} {response.reason}: {text}",
                        headers=response.headers,
                    )

                # Check Content-Length if available
                content_length = response.headers.get("Content-Length")
                if content_length and max_size:
                    if int(content_length) > max_size:
                        raise OutputLimitExceededError(max_size_str, None)

                # Read the response in chunks
                chunks = []
                total_size = 0

                async for chunk, _ in response.content.iter_chunks():
                    chunks.append(chunk)
                    total_size += len(chunk)

                    if max_size and total_size > max_size:
                        # Close the response
                        response.close()

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
                response_json = json.loads(full_response)
                return response_json["data"]
