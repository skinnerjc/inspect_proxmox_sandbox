#!/bin/bash
# note: the uefi param doesn't actually work in proxmox, though it seems fine in VirtualBox
# this script has a bunch of problems with idempotency TODO fix them

if [ -z "$1" ]; then
    echo "Usage: $0 <source_directory> [uefi]"
    echo "Add 'uefi' as second parameter to enable UEFI boot mode"
    exit 1
fi

SOURCE_DIR="$1"
TEMP_DIR="/tmp/qcow2_to_ova_conversion"
OUTPUT_DIR="$SOURCE_DIR/converted_ovas"
UEFI_MODE=0

# Check if UEFI mode is requested
if [ "$2" = "uefi" ]; then
    UEFI_MODE=1
    echo "UEFI boot mode enabled"
fi

set -eu

mkdir -p "$TEMP_DIR" "$OUTPUT_DIR"

for qcow2_file in "$SOURCE_DIR"/*.qcow2; do
    if [ ! -f "$qcow2_file" ]; then
        echo "No qcow2 files found in $SOURCE_DIR"
        exit 1
    fi

    filename=$(basename "$qcow2_file" .qcow2)
    echo "Processing: $filename"

    # Convert qcow2 to VDI
    qemu-img convert -f qcow2 -O vdi "$qcow2_file" "$TEMP_DIR/$filename.vdi"

    # Create and configure VM
    VBoxManage createvm --name "$filename" --ostype Linux26_64 --register
    
    # Configure basic VM settings
    VBoxManage modifyvm "$filename" --memory 2048 --cpus 2 --acpi on --boot1 disk
    
    # Configure UEFI if requested
    if [ $UEFI_MODE -eq 1 ]; then
        VBoxManage modifyvm "$filename" --firmware efi
    fi
    
    # Configure storage
    VBoxManage storagectl "$filename" --name "SATA Controller" --add sata --controller IntelAhci
    VBoxManage storageattach "$filename" --storagectl "SATA Controller" --port 0 --device 0 --type hdd --medium "$TEMP_DIR/$filename.vdi"

    # Export to OVA
    VBoxManage export "$filename" --output "$OUTPUT_DIR/$filename.ova"

    # Cleanup - VBoxManage unregistervm --delete also removes the VDI
    VBoxManage unregistervm "$filename" --delete

    echo "Converted: $OUTPUT_DIR/$filename.ova"
done

rm -rf "$TEMP_DIR"
echo "All conversions completed!"