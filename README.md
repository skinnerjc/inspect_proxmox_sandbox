# Inspect Proxmox Sandbox

## Purpose

This plugin for Inspect allows you to use virtual machines, running within a Proxmox instance, as sandboxes.

## Installing

Add this using Poetry

```
poetry add git+ssh://git@github.com/AI-Safety-Institute/inspect-vm-sandbox.git
```

or in uv,

```
uv add git+ssh://git@github.com/AI-Safety-Institute/inspect-vm-sandbox.git
```

## Requirements

This plugin assumes you already have a Proxmox instance set up, and that you have admin access to it.

Create a .env file with the following

```
PROXMOX_HOST=[IP address or domain name of the host]
PROXMOX_PORT=[port, e.g 8006]
PROXMOX_USER=[user, usually 'root']
PROXMOX_REALM=[authentication realm, usually 'pam' unless you have configured custom auth]
PROXMOX_PASSWORD=[password]
PROXMOX_NODE=[node name, usually 'proxmox']
```

## Configuring

Here is a full example sandbox configuration. 

Note that some of the fields (e.g. subnets) are tuples, so the trailing comma is vital 
if there is only a single item in the tuple.

Most tools use only the first sandbox, so you should list the one you want the agent to operate from first.

Virtual machines must have the qemu-guest-agent installed, unless they are not sandboxes. 
At least one VM in the configuration must be a sandbox.

```python
sandbox=SandboxEnvironmentSpec(
    "proxmox",
    ProxmoxSandboxEnvironmentConfig(
        # These config items will be taken from environment variables, if not specified here
        host=[IP address or domain name of the host]
        port=[port, e.g 8006]
        user=[user, usually 'root']
        user_realm=[authentication realm, 'pam' unless you have configured custom auth]
        password=[password]
        node=[node name, usually 'proxmox']
        # End config from environment

        vms_config=(
            VmConfig(
                # A virtual machine that this provider will install and configure automatically.
                vm_source_config=VmSourceConfig(
                    built_in="ubuntu24.04" # currently supported: "ubuntu24.04"; see schema.py
                ),
                name="romeo", # name is optional, but recommended - it will be shown in the Proxmox GUI
                ram_mb=512, # optional, default is 2048 MB
                vcpus=4, # optional, default is 2. No attempt is made to check that this will fit in the Proxmox host.
                uefi_boot=True, # optional, default is False. Generally only needed for Windows VMs.
                is_sandbox=False, # optional, default is True. A virtual machine that is not a sandbox; the qemu-guest-agent need not be installed.
                # If you have more than one VNet, assign the VM to the VNet via nics.
                # You can assign more than one, to give the VM more than one network interface.
                # If you leave this blank, your VM will be assigned to the first VNet.
                nics=(
                    VmNicConfig(
                        # This alias *must* match the alias in one of the VnetConfigs
                        vnet_alias="my special vnet",
                        # Specifying a MAC address is optional - only needed if you
                        # are doing fancy things with DHCP in your eval
                        mac="00:16:3d:1d:eb:a0"
                    ),
                )
                # extra_proxmox_native_config = dict() TODO
            ),
            # A virtual machine from a local OVA, which will be uploaded from here to the Proxmox server.
            VmConfig(
                vm_source_config=VmSourceConfig(
                    ova=Path("./tests/oVirtTinyCore64-13.11.ova")
                ),
            ),
            # A virtual machine to clone from an existing template VM.
            # This is *not recommended* since it is dependent on configuring a 
            # customised Proxmox instance that contains the template VM before
            # the eval start.
            VmConfig(
                vm_source_config=VmSourceConfig(
                    existing_vm_template_tag="java_server"
                ),
            ),
            # A virtual machine to restore from backup.
            # This is *not recommended* since it is dependent on configuring a 
            # customised Proxmox instance that contains the backup file before
            # the eval start.
            VmConfig(
                vm_source_config=VmSourceConfig(
                    existing_backup_name="vzdump-qemu-[vm id]-[datestamp of backup].vma.zst"
                ),
            ),
            # A virtual machine with no network access.
            VmConfig(
                # ... snip ...           
                nics=()
            ),
        ),
        # You will need a separate SDN per sample, or the VMs will be able to see each other
        # IP ranges *must* be distinct, unfortunately.
        # If you don't care about any of this, you can set this field to the string "auto"
        # and you will get an IP range somewhere in 192.168.[2 - 253].0/24
        sdn_config=SdnConfig(
            vnet_configs=(
                VnetConfig(
                    # You can leave subnets blank if you are handling IPAM yourself (e.g. with your own pfsense instance as a VM)
                    subnets=(
                        SubnetConfig(
                            cidr=ip_network("192.168.20.0/24"),
                            gateway=ip_address("192.168.20.1"),
                            # If you set snat=False, VMs will see each other but not the wider Internet.
                            snat=True,
                            dhcp_ranges=(
                                DhcpRange(
                                    start=ip_address("192.168.20.50"),
                                    end=ip_address("192.168.20.100"),
                                ),
                            ),
                        ),
                    ),
                    alias="my special vnet"
                ),
            ),
            # Set use_pve_ipam_dnsnmasq to True if you want your instances to be able to access the Internet
            use_pve_ipam_dnsnmasq=True,
        ),
    ),
)
```

## Using backup files

Proxmox's HTTP API will not let you upload a .zst backup file.

Instead:

1. Upload your zst backups to S3 or a web server.
2. Connect to the web frontend (see section Observing the VMs).
3. Open Datacenter -> Proxmox node -> Shell.
4. (If using S3) Paste in temporary AWS S3 credentials.
5. Download the zst backups into /var/lib/vz/dump using the AWS S3 CLI or wget.

![Demo of zst upload](docs/proxmox_shell.png "Getting a shell on Proxmox server")

## Observing the VMs

Note, if you are having problems, then setting Inspect's sandbox_cleanup=False will be helpful.

To access the Proxmox UI, at the moment you need to forward the port as follows.

Suppose your developer VM is called `my-dev-vm`, and assuming you copy your `.env` file onto your Mac, you can run on your Mac:

`set -a; source .env; set +a`

Then you can ssh as follows

`ssh -L "localhost:8006:$PROXMOX_HOST:$PROXMOX_PORT" my-dev-vm`

Then open the page https://locahost:8006, accept the certificate warning, and log in with the username and password from the .env flile

## Snapshot

QEMU, the virtualization library used by Proxmox, allows you to snapshot a running virtual machine, 
including the running processes. See [snapshots.py](./src/proxmoxsandbox/experimental/snapshots.py) for example tools that use this.

## Feature Roadmap

- Proxmox server health and config check
- Demo evals
- Normalize having a pfSense VM as the default route for networking
- Firewall off the SDN from the Proxmox server and from other SDNs
- Add more built-in VMs (Debian, Kali)
- Support cloud-init for VM definition
- Cache VM definition as tagged template VMs

## Tech debt

- instructions on how to run tests
- validate there is at least one sandbox
- add escape hatch for proxmox API
- pydocs instead of inline comments on fields etc
- Does not work with Inspect's post-hoc CLI sandbox cleanup feature
- instructions on how to change the password on an agent VM
- Large OVA uploads use PycURL, because neither aiohttp nor httpx worked with large uploads

## Developing

See [CONTRIBUTING.md]