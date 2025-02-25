# tests/conftest.py
from typing import AsyncGenerator

import pytest

from proxmoxsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from proxmoxsandbox.inspect.proxmox_sandbox_environment import ProxmoxSandboxEnvironmentConfig


@pytest.fixture
async def proxmox_api(
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
