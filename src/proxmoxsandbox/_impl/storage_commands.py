import abc
from logging import getLogger
from pathlib import Path
from typing import Literal, Optional

from proxmoxsandbox._impl.async_proxmox import AsyncProxmoxAPI
from proxmoxsandbox._impl.task_wrapper import TaskWrapper


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
        file: Path,
        content_type: Literal["iso", "vztmpl", "import"],
        filename: Optional[str] = None,
        overwrite: bool = False,
    ) -> None:
        """
        Uploads a file to Proxmox storage.

        Args:
            storage: The storage name in Proxmox
            file: Path to the file
            content_type: One of the file types supported by Proxmox
            filename: The filename to use for the file in Proxmox storage.
                If not provided, the filename of the file will be used.
            overwrite: Whether to overwrite the file if it already exists.
                If False, this function will return immediately
                if the file already exists.
        """
        if not isinstance(file, Path):
            raise ValueError(f"{file=} must be a Path; got {type(file)}")

        if filename is None:
            filename = file.name
        if not overwrite:
            existing_content = await self.async_proxmox.request(
                "GET",
                f"/nodes/{self.node}/storage/{self.storage}/content?content={content_type}",
            )
            for existing_file in existing_content:
                if "volid" in existing_file and existing_file["volid"].endswith(
                    filename
                ):
                    self.logger.debug(
                        f"File {filename} already exists in storage {self.storage}"
                        + f" on node {self.node} at {existing_file['volid']}"
                    )
                    return

        async def do_upload():
            await self.async_proxmox.upload_file_with_curl(
                self.node, self.storage, file, content_type, filename=filename
            )

        await self.task_wrapper.do_action_and_wait_for_tasks(do_upload)
