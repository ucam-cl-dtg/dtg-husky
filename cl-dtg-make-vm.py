#! /usr/bin/python

from fabric.api import *
import sys, subprocess

dhcp = 'husky0.dtg.cl.cam.ac.uk'
dom0 = 'husky0.dtg.cl.cam.ac.uk'

env.user="root"

# OS
OS                = 'Ubuntu 12.04 server edition'
TEMPLATE          = '66456203-e601-9bd7-2022-6f2158f375ac'
INSTALLREPO       = 'http://www-uxsup.csx.cam.ac.uk/pub/linux/ubuntu'
PRESEEDLOCATION   = 'http://puppy8.dtg.cl.cam.ac.uk/alloptions.cfg'

# Filesystem
DEFAULTROOTFSSIZE = 15
DEFAULTSR         = 'NFS\ virtual\ disk\ storage'

# Networking
NETWORK           = '77922c07-8ea4-abb2-708b-4719f4c6a0f8'
DEVICE            = '0'

# System
DEFAULTVCPUs      = '2'
DEFAULTMEMORY     = '2048'


@hosts(dom0)
def new_vm(name, ip="", mac="", memory=DEFAULTMEMORY, vcpus=DEFAULTVCPUs, root_fs_size=DEFAULTROOTFSSIZE, fs_location=DEFAULTSR):
    """ Create a new VM """
    if ip != "":
        mac = ip_to_mac(ip)
    if mac == "":
        mac = next_mac()

    # Create a VM
    new_vm = run('xe vm-install new-name-label=' + name + ' template=' + TEMPLATE + ' sr-name-label=' + fs_location)

    # Point VM at install repo
    run('xe vm-param-set uuid=' + new_vm + ' other-config:install-repository=' + INSTALLREPO)

    # Give the VM a VIF
    run('xe vif-create network-uuid=' + NETWORK + ' mac=' + mac + ' vm-uuid=' + new_vm + ' device=' + DEVICE)

    # Set the disk size
    vdi_uuid = run('xe vm-disk-list vm=' + name + ' |grep uuid | sed -e \'s/.*: //\' | tail -n 1')
    run('xe vdi-resize uuid=' + vdi_uuid + ' disk-size=' + root_fs_size + 'GiB')

    # Give the VM enough memory, and VCPU
    run('xe vm-param-set uuid=' + new_vm + ' VCPUs-max=' + vcpus)
    run('xe vm-param-set uuid=' + new_vm + ' VCPUs-at-startup=' + vcpus)
    run('xe vm-memory-limits-set uuid=' + new_vm + ' dynamic-max=' + memory + 'MiB static-max=' + memory + 'MiB static-min=' + memory + 'MiB dynamic-min=' + memory + 'MiB')

    # Set the preseed file, and pass a hostname, and password hash
    run('xe vm-param-set uuid=' + new_vm + ' PV-args=" --quiet console=hvc0 auto=true url=' + PRESEEDLOCATION  + ' netcfg/get_hostname=' + name + '"')

    # Boot the VM, with an answer file
    run('xe vm-start vm=' + name)

@hosts(dhcp)
def ip_to_mac(ip):
    """ Convert an IP address to a MAC address by searching our DHCP config """
    if ip == "":
        return "";

    mac = run('grep -B 1 ' + ip + ' /etc/dhcpd.conf   | grep ethernet | sed -e \'s/.*net //\' -e \'s/;//\'')
    return mac

@hosts(dhcp)
def next_mac():
    ''' Finds a MAC address that is not currently assigned to a VM '''
    dhcp_macs = run('grep "hardware ethernet" /etc/dhcpd.conf | sed -e \'s/.*ethernet //\' -e \'s/;//\'')
    assigned_macs = run('xe vif-list params=MAC | sed  -e \'/^$/d\' -e \'s/.*: //\'')
    return (list((set(dhcp_macs.split()) - set(assigned_macs.split())))[0])


if __name__ == '__main__':

    if len(sys.argv) > 1:
        subprocess.call(['fab', '-f', __file__] + sys.argv[1:])
    else:
        subprocess.call(['fab', '-f', __file__, '--list'])
