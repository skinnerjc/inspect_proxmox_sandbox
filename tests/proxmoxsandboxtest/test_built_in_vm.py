from proxmoxsandbox.inspect.proxmox.async_proxmox import AsyncProxmoxAPI
from proxmoxsandbox.inspect.proxmox.built_in_vm import BuiltInVM
from proxmoxsandbox.inspect.schema import VmSourceConfig


async def test_ubuntu(proxmox_api: AsyncProxmoxAPI) -> None:
    built_in_vm = BuiltInVM(proxmox_api, node="proxmox")
    await built_in_vm.clear_builtins()

    known_builtins = await built_in_vm.known_builtins()

    assert "ubuntu24.04" not in known_builtins

    await built_in_vm.ensure_exists(
        vm_source_config=VmSourceConfig(built_in="ubuntu24.04"),
        known_buitins=known_builtins,
    )
