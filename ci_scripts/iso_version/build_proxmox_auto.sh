#!/usr/bin/env bash
# Monolithic script to install proxmox on a bare-metal EC2 instance.
# It's all in one file so that you can run it with the --script option of aisi create-instance.
#
# What it does:
# Using docker, builds a Proxmox auto-install ISO per https://pve.proxmox.com/wiki/Automated_Installation
# Using virt-manager, installs a template Proxmox VM using that auto-install ISO.
# Leaves you with a script vend.sh which you can use to create up to 10 clones of the template VM when you need a Proxmox instance.
# e.g. 
# sudo ./vend.sh 1
# The clones will be accessible on the host at ports 11001, 11002, etc.
# Each clone will have a different root password, which is printed out by vend.sh.

sudo apt update
sudo apt install -y virt-manager libvirt-clients libvirt-daemon-system qemu-system-x86 virtinst guestfs-tools
sudo usermod --append --groups libvirt $(whoami)

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

RUN wget -q -O /iso/proxmox.iso https://enterprise.proxmox.com/iso/proxmox-ve_8.3-1.iso

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

# Previously there were loads of problems with permissions here when attempting to use the ubuntu user.
# Something to do with running in cloud-init; it worked fine when logged in with ubuntu in a normal termainl.
# I gave up and just used sudo.
cat << 'EOFVIRTINST' > virt-inst-proxmox.sh
virt-install --name proxmox-auto \
    --memory 131072 \
    --vcpus 16 \
    --disk size=2000 \
    --cdrom '/var/lib/libvirt/images/proxmox-auto-from-iso.iso' \
    --os-variant debian12 \
    --network none \
    --graphics none \
    --console pty,target_type=serial \
    --boot uefi \
    --cpu host \
    --qemu-commandline='-device virtio-net,netdev=user.0,addr=8 -netdev user,id=user.0,hostfwd=tcp::10000-:8006' \
    --check disk_size=off
EDITOR="sed -i '/<disk type=.*device=.cdrom/,/<\/disk>/d'" virsh edit proxmox-auto
EOFVIRTINST

chmod +x virt-inst-proxmox.sh
sudo tmux new-session -d -s virt-inst-proxmox  ./virt-inst-proxmox.sh

cat << 'EOFVEND' > vend.sh
#!/usr/bin/env bash
set -eux

VM_ID=$1
VM_ORIG=proxmox-auto
VM_NEW="proxmox-clone-$VM_ID"
VM_NEW_DISK="/var/lib/libvirt/images/$VM_NEW.qcow2"
AISI_PROXMOX_EXPOSED_PORT=$(( 11000 + $VM_ID ))

virt-clone --original "$VM_ORIG" \
               --name "$VM_NEW" \
               --file "$VM_NEW_DISK" \
              --check disk_size=off

root_password=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | head -c 20)

# for some reason the hostkeys are not regenerated and proxmox complains about missing /etc/ssh/ssh_host_rsa_key.pub
# virt-sysprep needs root to be able to access the kernel so we need sudo; see https://bugs.launchpad.net/ubuntu/+source/linux/+bug/759725
sudo virt-sysprep -d "$VM_NEW" \
    --root-password "password:$root_password" \
    --operations "defaults,-ssh-hostkeys" \

EDITOR="sed -i 's/hostfwd=tcp::[0-9]\+-:8006/hostfwd=tcp::$AISI_PROXMOX_EXPOSED_PORT-:8006/'" virsh edit "$VM_NEW"

echo "Created VM $VM_NEW on port $AISI_PROXMOX_EXPOSED_PORT with root password $root_password"
EOFVEND
chmod +x ./vend.sh
