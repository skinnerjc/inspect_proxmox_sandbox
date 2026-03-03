# Issue: Broken Pipe on Proxmox When Reading Large Files (~15MB)

## Problem

Another project that depends on `inspect-proxmox-sandbox` hits a "broken pipe" error
on Proxmox when writing a ~15MB file via `write_file` and then reading it back with
`read_file`. This is reproducible on Proxmox but we need a minimal test case in this
repo to investigate.

## Root Cause Hypothesis

The `read_file` path streams the response from the Proxmox QEMU guest agent API
(`/nodes/{node}/qemu/{vmid}/agent/file-read`) using httpx. The Proxmox API has a
hard 16 MiB limit on file reads. At ~15MB we're close to that limit, and the
connection may be getting closed before the full response is transferred — either
due to buffering issues in the QEMU guest agent, or timeouts during the large
streaming response.

The relevant code path is:

- `_proxmox_sandbox_environment.py:534-574` — `read_file()` method
- `async_proxmox.py:139-208` — streaming GET with 8KB chunks
- `agent_commands.py:85-100` — delegates to `async_proxmox.read_file()`

The `write_file` path for large files splits into 40KB chunks and reassembles on
the VM (see `_proxmox_sandbox_environment.py:484-532`), so the write itself may
also be involved.

## Minimal Repro Test

A test has been added at:
`tests/proxmoxsandboxtest/test_proxmox_sandbox_agent_commands.py::test_write_and_read_15mb`

It does exactly:
1. Generate 15MB of data
2. `write_file` it to the VM
3. `read_file` it back
4. Assert the content matches

This uses the same `proxmox_sandbox_environment` fixture as the existing tests,
which provisions a vanilla Ubuntu 24.04 VM with qemu-guest-agent via the built-in
template mechanism (downloads from Ubuntu cloud images, no external qcow2 needed).

## How the Test Infrastructure Works

### VM Provisioning (No External Images Needed)

The tests use `VmSourceConfig(built_in="ubuntu24.04")`. On first run:

1. Proxmox downloads the official Ubuntu cloud OVA from
   `https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.ova`
   directly onto its own storage (server-side download).
2. A VM is created from the OVA, a cloud-init ISO is attached that installs
   `qemu-guest-agent` and dev tools.
3. The VM boots, cloud-init runs, then it's shut down and converted to a
   **read-only template** tagged `inspect,builtin-ubuntu24.04`.

Each test then **clones** this template into a fresh VM, creates an isolated SDN
network, boots it, and waits for the QEMU guest agent. After the test, the clone
and SDN are destroyed. The template persists for reuse.

### Proxmox Itself

Proxmox is run as a **VM inside the metal host** using libvirt/KVM (nested
virtualization). The `build_proxmox_auto.sh` script handles this:

```
Metal instance (Ubuntu 24.04)
  -> libvirt/KVM
       -> "proxmox-auto" VM (Proxmox VE from ISO)
            -> Test VMs (Ubuntu 24.04 clones)
```

## Instructions: Setting Up on a Metal Instance

### Prerequisites

- An AWS metal instance (or any host with nested virtualization support)
- Ubuntu 24.04
- Docker installed (`sudo apt install docker.io && sudo usermod -aG docker $USER`)
  — log out and back in after adding yourself to the docker group

### Step-by-Step

```bash
# 1. Clone the repo (use the branch with the repro test)
git clone <repo-url> inspect-proxmox-sandbox
cd inspect-proxmox-sandbox
git checkout joe/broken-pipe-repro

# 2. Build the virtualized Proxmox instance (~15-20 min)
#    This downloads the Proxmox ISO, builds an auto-install ISO,
#    and installs Proxmox into a libvirt VM.
./scripts/virtualized_proxmox/build_proxmox_auto.sh

# 3. Wait for the script to complete, then vend a Proxmox clone.
#    vend.sh prints the credentials you need.
./vend.sh 1

# 4. Create .env from the vend.sh output. It prints lines like:
#      PROXMOX_HOST=<ip>
#      PROXMOX_PORT=11001
#      PROXMOX_USER=root
#      PROXMOX_REALM=pam
#      PROXMOX_PASSWORD=<random>
#      PROXMOX_NODE=proxmox
#      PROXMOX_VERIFY_TLS=0
#    Copy those into a .env file:
cat > .env << 'EOF'
PROXMOX_HOST=<ip from vend.sh output>
PROXMOX_PORT=11001
PROXMOX_USER=root
PROXMOX_REALM=pam
PROXMOX_PASSWORD=<password from vend.sh output>
PROXMOX_NODE=proxmox
PROXMOX_VERIFY_TLS=0
EOF

# 5. Install Python dependencies
uv sync

# 6. Load env vars and run JUST the repro test
set -a; source .env; set +a
uv run pytest tests/proxmoxsandboxtest/test_proxmox_sandbox_agent_commands.py::test_write_and_read_15mb -v

# The first run will be slow (~5-10 min) because it downloads the Ubuntu
# cloud image and runs cloud-init to create the template. Subsequent runs
# reuse the cached template and just clone + boot (~1-2 min).
```

### Running the Existing Large File Test for Comparison

The existing test writes a ~20MB OVA file and checks its MD5 (but does NOT
read it back via `read_file` — it uses `exec(["md5sum", ...])` instead):

```bash
uv run pytest tests/proxmoxsandboxtest/test_proxmox_sandbox_agent_commands.py::test_write_file_large -v
```

### Running All Tests

```bash
uv run pytest -v
```

Requires at least 3 vCPUs available on the Proxmox node.

### Troubleshooting

- If `build_proxmox_auto.sh` fails on Docker: make sure Docker is installed and
  your user is in the `docker` group.
- If tests can't connect: check `virsh list --all` to see if the Proxmox VM is
  running. Try `curl -k https://localhost:11001` to check the API.
- If the first test run is very slow: the Ubuntu cloud image download (~700MB)
  and cloud-init (package installation) happen on first run only. Be patient.
- If you get authentication errors: Proxmox auth tickets expire after 2 hours.
  The code handles this automatically, but if your Proxmox VM was restarted you
  may need to re-check the credentials.

## Decisions Made

- Use the simplest possible setup: built-in Ubuntu 24.04 VM (no external qcow2/S3).
- Run everything on one metal instance (repo, Proxmox, tests).
- The repro test generates synthetic data rather than using an existing file,
  to make the test self-contained and the size easily adjustable.
- Test is placed alongside the existing agent command tests since it exercises
  the same `write_file`/`read_file` code path.
