# tests/conftest.py
import random
from typing import AsyncGenerator

import pytest

from proxmoxsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from proxmoxsandbox.inspect.proxmox.built_in_vm import BuiltInVM
from proxmoxsandbox.inspect.proxmox.qemu_commands import QemuCommands, VnetAliases
from proxmoxsandbox.inspect.proxmox.sdn_commands import SdnCommands
from proxmoxsandbox.inspect.proxmox_sandbox_environment import (
    ProxmoxSandboxEnvironment,
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
async def node(
    sandbox_env_config: ProxmoxSandboxEnvironmentConfig,
) -> str:
    return sandbox_env_config.node


@pytest.fixture
async def sandbox_env_config() -> ProxmoxSandboxEnvironmentConfig:
    return ProxmoxSandboxEnvironmentConfig()


@pytest.fixture
async def sdn_commands(async_proxmox_api: AsyncProxmoxAPI) -> SdnCommands:
    return SdnCommands(async_proxmox_api)


@pytest.fixture
async def qemu_commands(async_proxmox_api: AsyncProxmoxAPI, node: str) -> SdnCommands:
    return QemuCommands(async_proxmox_api, node=node)


@pytest.fixture
async def built_in_vm(async_proxmox_api: AsyncProxmoxAPI, node: str) -> SdnCommands:
    return BuiltInVM(async_proxmox_api, node=node)


@pytest.fixture(scope="function")
async def ids_start() -> str:
    ids_start = f"cts{random.randint(100, 999)}"
    return ids_start


@pytest.fixture
async def auto_sdn_vnet_aliases(
    ids_start: str, sdn_commands: SdnCommands
) -> AsyncGenerator[VnetAliases, None]:
    sdn_zone_id, vnet_aliases = await sdn_commands.create_sdn(ids_start, "auto")
    yield vnet_aliases
    await sdn_commands.tear_down_sdn_zone_and_vnet(sdn_zone_id)


@pytest.fixture(scope="function")
async def proxmox_sandbox_environment(
    sandbox_env_config: ProxmoxSandboxEnvironmentConfig,
) -> AsyncGenerator[ProxmoxSandboxEnvironment, None]:
    task_name = "from_conftest"
    await ProxmoxSandboxEnvironment.task_init(task_name=task_name, config=None)
    envs_dict = await ProxmoxSandboxEnvironment.sample_init(
        task_name=task_name,
        config=sandbox_env_config,
        metadata={},
    )
    yield envs_dict["default"]
    await ProxmoxSandboxEnvironment.sample_cleanup(
        task_name=task_name,
        config=sandbox_env_config,
        environments=envs_dict,
        interrupted=False,
    )
