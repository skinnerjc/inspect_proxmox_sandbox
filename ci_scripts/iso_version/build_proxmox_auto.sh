#!/usr/bin/env bash

apt update
apt install -y libvirt-clients libvirt-daemon-system qemu-system-x86 virtinst

virsh destroy proxmox-auto
virsh undefine --nvram --remove-all-storage proxmox-auto

set -eu

cat << 'EOFANSWERS' > answers.toml
[global]
keyboard = "en-gb"
country = "gb"
fqdn = "proxmox.local"
mailto = "root@localhost"
timezone = "Europe/London"
root_password = "Password2.0"

[network]
source = "from-dhcp"

[disk-setup]
filesystem = "ext4"
disk_list = ["vda"]

[first-boot]
source = "from-iso"
ordering = "fully-up"
EOFANSWERS

cat << 'EOFONFIRSTBOOT' > on-first-boot.sh
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
EOFONFIRSTBOOT

cat << 'EOFDOCKER' > Dockerfile
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
     gnupg \
     wget \
     xorriso \
     && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /iso

RUN wget -O /iso/proxmox.iso https://enterprise.proxmox.com/iso/proxmox-ve_8.3-1.iso

RUN echo "deb http://download.proxmox.com/debian/pve/ bookworm pve-no-subscription" > /etc/apt/sources.list.d/pve.list
RUN wget -O- http://download.proxmox.com/debian/proxmox-release-bookworm.gpg | apt-key add -

RUN apt-get update && apt-get install -y \
     proxmox-auto-install-assistant \
     && rm -rf /var/lib/apt/lists/*

COPY answers.toml /iso/answers.toml
COPY on-first-boot.sh /iso/on-first-boot.sh

RUN cd /iso && proxmox-auto-install-assistant prepare-iso /iso/proxmox.iso --fetch-from iso --answer-file /iso/answers.toml --on-first-boot /iso/on-first-boot.sh
# Set volume to access the ISO
VOLUME /output

# Default command to copy the ISO to the output volume (JSON form)
CMD ["cp", "/iso/proxmox-auto-from-iso.iso", "/output/"]

EOFDOCKER

docker build --debug  -t proxmox-auto-install .
docker run --rm -v $(pwd):/output proxmox-auto-install
sudo cp -v proxmox-auto-from-iso.iso /var/lib/libvirt/images
virt-install --name proxmox-auto --memory 131072 --vcpus 16 --disk size=2000 --cdrom '/var/lib/libvirt/images/proxmox-auto-from-iso.iso' --os-variant debian12 --network none --graphics none --console pty,target_type=serial --boot uefi --cpu host  --qemu-commandline="-device virtio-net,netdev=user.0,addr=8  -netdev user,id=user.0,hostfwd=tcp::10000-:8006" --check disk_size=off 

# remove the CDROM
EDITOR="sed -i '/<disk type=.*device=.cdrom/,/<\/disk>/d'" virsh edit proxmox-auto
