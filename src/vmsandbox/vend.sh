#!/usr/bin/env bash
# NOTE: script requires root for unclear reasons
set -eux

VM_ID=$1
VM_ORIG=proxmox-2000
VM_NEW="proxmox-clone-$VM_ID"

AISI_PROXMOX_EXPOSED_PORT=$(( 11000 + $VM_ID ))


virt-clone --original "$VM_ORIG" \
               --name "$VM_NEW" \
               --file "/var/lib/libvirt/images/$VM_NEW.qcow2" \
                --check disk_size=off


root_password=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | head -c 20)

# for some reason the hostkeys are not regenerated and proxmox complains about missing /etc/ssh/ssh_host_rsa_key.pub
virt-sysprep -d "$VM_NEW" \
    --root-password "password:$root_password" \
    --operations "defaults,-ssh-hostkeys" \


EDITOR="sed -i 's/hostfwd=tcp::[0-9]\+-:8006/hostfwd=tcp::$AISI_PROXMOX_EXPOSED_PORT-:8006/'" virsh edit "$VM_NEW"

echo "Created VM $VM_NEW on port $AISI_PROXMOX_EXPOSED_PORT with root password $root_password"