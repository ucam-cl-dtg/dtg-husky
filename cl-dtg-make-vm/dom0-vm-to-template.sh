#! /bin/bash

guest_user="root"

if [ $# -lt 1 ]; then
    echo "Usage: capture-vm-snapshot name"
    exit 1
fi

vm=$1

no_vms_same_name="$(xe vm-list name-label=$vm --minimal | wc -l)"

if [ $no_vms_same_name -ne 1 ]; then
    echo "Ambiguous, or non-existent VM: $vm"
    exit 1
fi

vm_uuid="$(xe vm-list name-label=$vm params=uuid --minimal)"
ip="$(xe vm-param-get param-name=networks uuid=$vm_uuid | sed -e 's_0/ip: __' -e 's/; .*$//')"

RET=1
until [ $RET -eq 0 ]; do
    # We cannot verify the fingerprint of the host. We have just built it from
    # a fresh install, and so have no previous value to compare it with.
    # Therefore we don't check host keys
    ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=7200 -o PreferredAuthentications=publickey ${guest_user}@${ip} <<ESSH
	  while [ $(pgrep puppet) ] || [ ! -d /etc/puppet ]; do
	    sleep 2
	  done
ESSH
    RET=$?
    sleep 5
done

echo "SSH-ed into VM, and detected a valid puppet setup. Proceeding."
echo "Shutting down"

xe vm-shutdown name-label=$vm
# wait until we have shutdown
while [ $( xe vm-list params=power-state name-label=$vm | grep running ) ]; do
    sleep 1
done


vif_uuid=$(xe vif-list vm-name-label=$vm --minimal)
if [ -n "$vif_uuid" ]; then
    echo "Destroying VIF"
    xe vif-destroy uuid=$vif_uuid
fi

xe template-param-set is-a-template=true uuid=$vm_uuid
xe template-param-set other-config:install-methods=http,ftp,nfs uuid=$vm_uuid
