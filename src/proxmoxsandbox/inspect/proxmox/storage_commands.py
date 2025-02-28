import abc
from logging import getLogger
from typing import Literal


from proxmoxsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from proxmoxsandbox.inspect.proxmox.task_wrapper import TaskWrapper


class StorageCommands(abc.ABC):
    logger = getLogger(__name__)

    TRACE_NAME = "proxmox_storage_commands"

    async_proxmox: AsyncProxmoxAPI
    task_wrapper: TaskWrapper
    node: str
    storage: str

    def __init__(self, async_proxmox: AsyncProxmoxAPI, node: str, storage: str):
        self.async_proxmox = async_proxmox
        self.task_wrapper = TaskWrapper(async_proxmox)
        self.node = node
        self.storage = storage

    async def upload_file_to_storage(
        self,
        content: bytes,
        filename: str,
        file_type: Literal["iso", "vztmpl", "import"],
    ) -> None:
        """
        Uploads a file to Proxmox storage.

        Args:
            storage: The storage name in Proxmox
            content: The binary content of the file
            filename: The filename to use for the file in Proxmox storage
            file_type: One of the file types supported by Proxmox
        """
        import uuid

        boundary = str(uuid.uuid4())

        # Construct the multipart form-data payload
        payload = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="content"\r\n\r\n{file_type}\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="filename"; filename="{filename}"\r\n'
            f"Content-Length: {len(content)}\r\n\r\n"
        ).encode("us-ascii")

        payload += content + f"\r\n--{boundary}--\r\n".encode("us-ascii")

        async def upload_file() -> None:
            await self.async_proxmox.request(
                "POST",
                f"/nodes/{self.node}/storage/{self.storage}/upload",
                content=payload,
                content_type=f"multipart/form-data; boundary={boundary}",
            )

        await self.task_wrapper.do_action_and_wait_for_tasks(upload_file)
