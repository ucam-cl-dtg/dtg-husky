#! /usr/bin/python

from fabric.api import *
from datetime import date
from time import sleep
import sys, subprocess

dhcp = 'husky0.dtg.cl.cam.ac.uk'
dom0 = 'husky0.dtg.cl.cam.ac.uk'

env.user="root"

# OS
TEMPLATE          = '66456203-e601-9bd7-2022-6f2158f375ac'
INSTALLREPO       = 'http://www-uxsup.csx.cam.ac.uk/pub/linux/ubuntu'
PRESEEDLOCATION   = 'http://dhcp.dtg.cl.cam.ac.uk/puppy-preseed.cfg'

# Filesystem
DEFAULTROOTFSSIZE = '4'
DEFAULTDATAFSSIZE = '1'
DEFAULTSR         = 'NFS\ virtual\ disk\ storage'
SR                = 'b1bb7fa6-ca99-c984-4002-940ac6757e3e'

# Networking
NETWORK           = '77922c07-8ea4-abb2-708b-4719f4c6a0f8'
DEVICE            = '0'

# System
DEFAULTVCPUs      = '2'
DEFAULTMEMORY     = '2048'

# Template
TEMPLATENAME      = 'DTG-template'

# SSH
SSHUSER           = 'dtg'

def prepare_vm(ip, mac, uuid, memory, vcpus):

    if ip != "":
        mac = ip_to_mac(ip)
    if mac == "":
        mac = next_mac()

    # Give the VM a VIF
    run('xe vif-create network-uuid=%s mac=%s vm-uuid=%s device=%s' % (NETWORK, mac, uuid, DEVICE))

    # Give the VM enough memory, and VCPU
    run('xe vm-param-set uuid=%s VCPUs-max=%s' % (uuid, vcpus))
    run('xe vm-param-set uuid=%s  VCPUs-at-startup=%s'  % (uuid,vcpus))
    run('xe vm-memory-limits-set uuid=%s dynamic-max=%sMiB static-max=%sMiB static-min=%sMiB dynamic-min=%sMiB' % (uuid, memory, memory, memory, memory))


@hosts(dom0)
def new_vm(name="", ip="", mac="", memory=DEFAULTMEMORY, vcpus=DEFAULTVCPUs, root_fs_size=DEFAULTROOTFSSIZE, fs_location=SR):
    """
    Create a new VM
    """
    if name == "":
        name='DTG-snapshot-' + date.today()

    # Create a VM
    new_vm = run('xe vm-install new-name-label=%s template=%s sr-uuid=%s' % (name, TEMPLATE, fs_location))

    # Point VM at install repo
    run('xe vm-param-set uuid=%s other-config:install-repository=%s' % (new_vm, INSTALLREPO))

    # Remove the first disk. XAPI adds an 8GiB disk to the VM with vm-install
    # and this can't be reduced in size.
    vdi_old_uuid = run('xe vm-disk-list vm=%s |grep uuid | sed -e \'s/.*: //\' | tail -n 1' % name)
    vbd_uuid = run('xe vbd-list params=uuid vm-uuid=%s --minimal' % new_vm)
    run('xe vbd-destroy uuid=%s' % vbd_uuid)
    run('xe vdi-destroy uuid=%s' % vdi_old_uuid)

    # Create new disks
    vdi_a_uuid = run('xe vdi-create sr-uuid=%s virtual-size=%sGiB name-label=%s-os type=user' % (fs_location, root_fs_size, name))
    run('xe vbd-create vm-uuid=%s vdi-uuid=%s device=0 bootable=true' % (new_vm, vdi_a_uuid))

    # Set the preseed file, and pass a hostname, and password hash
    run('xe vm-param-set uuid=%s PV-args=" --quiet console=hvc0 auto=true url=%s netcfg/get_hostname=%s"' % (new_vm, PRESEEDLOCATION, name))

    prepare_vm(ip, mac, new_vm, memory, vcpus)

    # Boot the VM, with an answer file
    run('xe vm-start vm=%s' % name)

    # Start a background script in dom0 that waits for installation to complete, then shuts down the VM, and builds a snapshot
    run('nohup ./capture-vm-snapshot.sh %s &' % name)


@hosts(dom0)
def new_cloned_vm(name, ip="", mac="", memory=DEFAULTMEMORY, vcpus=DEFAULTVCPUs, data_size=DEFAULTDATAFSSIZE, data_SR=SR):
    """
    Build a new VM by cloning the most recent DTG-snapshot.
    This will give a DTG-itised VM, much faster than calling new_vm,
    however the VM uses copy-on-write.
    """

    # Create VM from snapshot
    run('xe vm-install new-name-label=%s template=%s sr-uuid=%s' % (name, TEMPLATENAME, SR))
    new_vm = run('xe vm-list name-label=%s params=uuid --minimal' % name)

    prepare_vm(ip, mac, new_vm, memory, vcpus)

    # Create a /dev/xvdb that can be mounted at /data/local
    if data_size > 0:
        vdi_b_uuid = run('xe vdi-create sr-uuid=%s virtual-size=%sGiB name-label=%s-data type=user' % (data_SR, data_size, name))
        run('xe vbd-create vm-uuid=%s vdi-uuid=%s device=1' % (new_vm, vdi_b_uuid))

    run('xe vm-start vm=%s' % name)

    # SSH into the new machine, and set the hostname. First wait for the m/c to boot

    sleep(10)
    ip = run('xe vm-param-get param-name=networks uuid=%s | sed -e \'s_0/ip: __\' -e \'s/; .*$//\'' % new_vm)
    subprocess.call(['ssh %s@%s "hostname %s"'  % (SSHUSER, ip, name)])
    subprocess.call(['ssh %s@%s "./etc/puppet-bare/hooks/post-update"' % (SSHUSER, ip)])


@hosts(dhcp)
def ip_to_mac(ip):
    """
    Convert an IP address to a MAC address by searching our DHCP config
    """
    if ip == "":
        return "";

    mac = run('grep -B 1 %s /etc/dhcpd.conf | grep ethernet | sed -e \'s/.*net //\' -e \'s/;//\'' % ip)
    return mac

@hosts(dhcp)
def next_mac():
    """
    Finds a MAC address that is not currently assigned to a VM
    """
    dhcp_macs = run('grep "hardware ethernet" /etc/dhcpd.conf | sed -e \'s/.*ethernet //\' -e \'s/;//\'')
    assigned_macs = run('xe vif-list params=MAC | sed -e \'/^$/d\' -e \'s/.*: //\'')
    return (list((set(dhcp_macs.split()) - set(assigned_macs.split())))[0])


if __name__ == '__main__':

    if len(sys.argv) > 1:
        subprocess.call(['fab', '-f', __file__] + sys.argv[1:])
    else:
        subprocess.call(['fab', '-f', __file__, '--list'])
