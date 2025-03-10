#!/usr/bin/env bash

virsh destroy proxmox-auto
virsh undefine --nvram --remove-all-storage proxmox-auto

set -eu
docker build --debug  -t proxmox-auto-install .
docker run --rm -v $(pwd):/output proxmox-auto-install
sudo cp -v proxmox-auto-from-iso.iso /var/lib/libvirt/images
virt-install --name proxmox-auto --memory 131072 --vcpus 16 --disk size=2000 --cdrom '/var/lib/libvirt/images/proxmox-auto-from-iso.iso' --os-variant debian12 --network none --graphics none --console pty,target_type=serial --boot uefi --cpu host  --qemu-commandline="-device virtio-net,netdev=user.0,addr=8  -netdev user,id=user.0,hostfwd=tcp::10000-:8006" --check disk_size=off 

EDITOR="sed -i '/<disk type=.*device=.cdrom/,/<\/disk>/d'" virsh edit proxmox-auto
