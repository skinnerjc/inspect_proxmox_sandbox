import os
from ipaddress import ip_address, ip_network
from typing import Literal, Tuple

from pydantic import BaseModel, Field, model_validator
from pydantic.networks import IPvAnyAddress, IPvAnyNetwork


class DhcpRange(BaseModel, frozen=True):
    start: IPvAnyAddress
    end: IPvAnyAddress

    def to_proxmox_format(self) -> str:
        return f"start-address={self.start},end-address={self.end}"


class SubnetConfig(BaseModel, frozen=True):
    cidr: IPvAnyNetwork
    gateway: IPvAnyAddress
    snat: bool
    dhcp_ranges: Tuple[DhcpRange, ...]


class VnetConfig(BaseModel, frozen=True):
    subnets: Tuple[SubnetConfig, ...]


class SdnConfig(BaseModel, frozen=True):
    vnet_configs: Tuple[VnetConfig, ...]
    # Set this to False if you want to use your own pfsense instance to handle IPAM (recommended)
    use_pve_ipam_dnsnmasq: bool = True


def simple_sdn_config(third_octet: int = 16) -> SdnConfig:
    return SdnConfig(
        vnet_configs=(
            VnetConfig(
                subnets=(
                    SubnetConfig(
                        cidr=ip_network(f"192.168.{third_octet}.0/24"),
                        gateway=ip_address(f"192.168.{third_octet}.1"),
                        snat=True,
                        dhcp_ranges=(
                            DhcpRange(
                                start=ip_address(f"192.168.{third_octet}.50"),
                                end=ip_address(f"192.168.{third_octet}.100"),
                            ),
                        ),
                    ),
                )
            ),
        )
    )


class VmSourceConfig(BaseModel, frozen=True):
    existing_vm_template_tag: str | None = (
        None  # if the VM exists as a template with this tag, clone it from that - TODO, not yet implemented
    )
    existing_ova_name: str | None = (
        None  # otherwise, the VM will be created from this OVA - TODO, not yet implemented
    )
    existing_backup_name: str | None = (
        None  # otherwise, the VM will be created from this backup
    )
    built_in: Literal["ubuntu24.04", "debian12"] | None = (
        None  # otherwise, the provider will attempt to create a VM suitable for a sandbox
    )

    @model_validator(mode="after")
    def validate_single_source(self) -> "VmSourceConfig":
        set_sources = [
            name
            for name, value in {
                "existing_vm_template_tag": self.existing_vm_template_tag,
                "existing_ova_name": self.existing_ova_name,
                "existing_backup_name": self.existing_backup_name,
                "built_in": self.built_in,
            }.items()
            if value is not None
        ]

        if len(set_sources) != 1:
            raise ValueError(
                f"Exactly one source must be set. Found {len(set_sources)}: {', '.join(set_sources) or 'none'}"
            )

        return self


class VmConfig(BaseModel, frozen=True):
    vm_source_config: VmSourceConfig
    is_sandbox: bool = True  # if so, the VM will show up as a sandbox. It must have the qemu-guest-agent installed


def get_env(env_var: str) -> str:
    return os.environ[env_var]

class ProxmoxSandboxEnvironmentConfig(BaseModel, frozen=True):
    host: str = Field(default_factory=lambda: get_env("PROXMOX_HOST"))
    port: int = Field(default_factory=lambda: int(get_env("PROXMOX_PORT")))
    user: str = Field(default_factory=lambda: get_env("PROXMOX_USER"))
    user_realm: str = Field(default_factory=lambda: get_env("PROXMOX_REALM"))
    password: str = Field(default_factory=lambda: get_env("PROXMOX_PASSWORD"))
 
    # If not set, you will get a simple SDN with a single subnet. The IP addresses
    # will not be predictable as it depends on what subnets already exist.
    sdn_config: SdnConfig | None = None
    vms_config: Tuple[VmConfig, ...] = (
        VmConfig(vm_source_config=VmSourceConfig(built_in="ubuntu24.04")),
    )
