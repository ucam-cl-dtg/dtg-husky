#! /usr/bin/python

from fabric.api import *
import sys, subprocess, argparse

dhcp = 'husky0.dtg.cl.cam.ac.uk'
dom0 = 'husky0.dtg.cl.cam.ac.uk'

env.user="root"

# OS
TEMPLATE          = '66456203-e601-9bd7-2022-6f2158f375ac'
INSTALLREPO       = 'http://www-uxsup.csx.cam.ac.uk/pub/linux/ubuntu'
PRESEEDLOCATION   = 'http://puppy8.dtg.cl.cam.ac.uk/alloptions.cfg'

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


@hosts(dom0)
def new_vm(name, ip="", mac="", memory=DEFAULTMEMORY, vcpus=DEFAULTVCPUs, root_fs_size=DEFAULTROOTFSSIZE, data_size=DEFAULTDATAFSSIZE, fs_location=SR):
    """
    Create a new VM
    """
    if ip != "":
        mac = ip_to_mac(ip)
    if mac == "":
        mac = next_mac()

    # Create a VM
    new_vm = run('xe vm-install new-name-label=%s template=%s sr-uuid=%s' % (name, TEMPLATE, fs_location))

    # Point VM at install repo
    run('xe vm-param-set uuid=%s other-config:install-repository=%s' % (new_vm, INSTALLREPO))

    # Give the VM a VIF
    run('xe vif-create network-uuid=%s mac=%s vm-uuid=%s device=%s' % (NETWORK, mac, new_vm, DEVICE))

    # Remove the first disk. XAPI adds an 8GiB disk to the VM with vm-install
    # and this can't be reduced in size.
    vdi_old_uuid = run('xe vm-disk-list vm=%s |grep uuid | sed -e \'s/.*: //\' | tail -n 1' % name)
    vbd_uuid = run('xe vbd-list params=uuid vm-uuid=%s --minimal' % new_vm)
    run('xe vbd-destroy uuid=%s' % vbd_uuid)
    run('xe vdi-destroy uuid=%s' % vdi_old_uuid)

    # Create new disks
    vdi_a_uuid = run('xe vdi-create sr-uuid=%s virtual-size=%sGiB name-label=%s-os type=user' % (fs_location, root_fs_size, name))
    run('xe vbd-create vm-uuid=%s vdi-uuid=%s device=0 bootable=true' % (new_vm, vdi_a_uuid))
    vdi_b_uuid = run('xe vdi-create sr-uuid=%s virtual-size=%sGiB name-label=%s-data type=user' % (fs_location, data_size, name))
    run('xe vbd-create vm-uuid=%s vdi-uuid=%s device=1' % (new_vm, vdi_b_uuid))

    # Give the VM enough memory, and VCPU
    run('xe vm-param-set uuid=%s VCPUs-max=%s' % (new_vm, vcpus))
    run('xe vm-param-set uuid=%s  VCPUs-at-startup=%s'  % (new_vm,vcpus))
    run('xe vm-memory-limits-set uuid=%s dynamic-max=%sMiB static-max=%sMiB static-min=%sMiB dynamic-min=%sMiB' % (new_vm, memory, memory, memory, memory))

    # Set the preseed file, and pass a hostname, and password hash
    run('xe vm-param-set uuid=%s PV-args=" --quiet console=hvc0 auto=true url=%s netcfg/get_hostname=%s"' % (new_vm, PRESEEDLOCATION, name))

    # Boot the VM, with an answer file
    run('xe vm-start vm=%s' % name)

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

    parser = argparse.ArgumentParser(description='Make a VM on the DTG husky cluster. The resulting VM will, by the magic of drt24\'s puppet, contain much DTG goodness')

    parser.add_argument('--new-template', action='store_true', help='Build a new template from the Ubuntu repos, and apply DTG customisations. The result is stored as a template, rather than creating a VM')

    # We don't want both an IP address and MAC
    ip_mac_group = parser.add_mutually_exclusive_group()
    ip_mac_group.add_argument('-i', '--ip', help='The created VM will be given a MAC address that will be offered this value by DHCP')
    ip_mac_group.add_argument('-M', '--mac', help='MAC address to assign the VM\s VIF')

    # Optional args
    parser.add_argument('-m', '--memory', type=int, help='memory (in GB) assigned to VM')
    parser.add_argument('-v', '--vcpus', type=int, help='Number of VCPUs')
    parser.add_argument('-r', '--rootfs', dest='root_fs_size', type=int, help='Size of /dev/xvda, the root filesystem')
    parser.add_argument('-d', '--datafs', dest='data_size', type=int, help='Size of /dev/xvdb, the data partition, mounted on /data/local')
    parser.add_argument('-l', '--dataloc', help='Storage repository to use for the data partition')

    # Name is required
    parser.add_argument('name', help='The hostname of the VM')

    parsed_args = vars(parser.parse_args())
    argstring = ""
    for param in parsed_args.keys():
        if parsed_args[param] != None and param != 'new_template':
            argstring = '%s%s=%s,' % (argstring, param, parsed_args[param])

    argstring = argstring[:-1]

    subprocess.call(['fab', '-f', __file__] + ['new_vm:' + argstring])
