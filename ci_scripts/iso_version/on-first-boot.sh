#!/usr/bin/env bash
set -eu

# enable serial console
systemctl enable serial-getty@ttyS0
systemctl start serial-getty@ttyS0

# fix up local to allow things we need
pvesh set /storage/local -content iso,vztmpl,backup,snippets,images,rootdir,import

# set to no-subscription PVE repo
echo 'deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription' > /etc/apt/sources.list.d/pve-no-subscription.list
rm -f /etc/apt/sources.list.d/{pve-enterprise,ceph}.list

# install dnsmasq for SDN
apt update
apt install -y dnsmasq
systemctl disable --now dnsmasq

# shut down to signal to virt-install that installation is complete
poweroff
