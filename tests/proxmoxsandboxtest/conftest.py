# tests/conftest.py
import random
from typing import AsyncGenerator

import pytest

from proxmoxsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from proxmoxsandbox.inspect.proxmox.qemu_commands import QemuCommands
from proxmoxsandbox.inspect.proxmox.sdn_commands import SdnCommands
from proxmoxsandbox.inspect.proxmox_sandbox_environment import (
    ProxmoxSandboxEnvironmentConfig,
)


@pytest.fixture
async def async_proxmox_api(
    sandbox_env_config: ProxmoxSandboxEnvironmentConfig,
) -> AsyncGenerator[AsyncProxmoxAPI, None]:
    """Provides configured AsyncProxmoxAPI instance"""
    yield AsyncProxmoxAPI(
        host=f"{sandbox_env_config.host}:{sandbox_env_config.port}",
        user=f"{sandbox_env_config.user}@{sandbox_env_config.user_realm}",
        password=sandbox_env_config.password,
        verify_ssl=False,
    )


@pytest.fixture
async def sandbox_env_config() -> ProxmoxSandboxEnvironmentConfig:
    return ProxmoxSandboxEnvironmentConfig()


@pytest.fixture
async def sdn_commands(async_proxmox_api: AsyncProxmoxAPI) -> SdnCommands:
    return SdnCommands(async_proxmox_api, node="proxmox")


@pytest.fixture
async def qemu_commands(async_proxmox_api: AsyncProxmoxAPI) -> SdnCommands:
    return QemuCommands(async_proxmox_api, node="proxmox")


@pytest.fixture(scope="function")
async def ids_start() -> str:
    ids_start = f"cts{random.randint(100, 999)}"
    return ids_start
