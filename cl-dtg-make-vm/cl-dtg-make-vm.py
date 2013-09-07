#! /usr/bin/env python2.7

from fabric.api import *
import sys, argparse, subprocess, socket, getpass
from datetime import date
from time import sleep

dhcp = env.user + '@dhcp.dtg.cl.cam.ac.uk'
dom0 = 'root@husky0.dtg.cl.cam.ac.uk'

# OS
TEMPLATE          = '115a8d15-a73d-85bb-09df-103768ed36ee'
INSTALLREPO       = 'http://www-uxsup.csx.cam.ac.uk/pub/linux/ubuntu'
PRESEEDLOCATION   = 'http://git.dtg.cl.cam.ac.uk/?p=husky/preseed.git;a=blob_plain;f=puppy-preseed.cfg;hb=HEAD'

# Filesystem
DEFAULTROOTFSSIZE = '8'
DEFAULTDATAFSSIZE = '1'
DEFAULTSR         = 'NFS\ virtual\ disk\ storage'
SR                = '53a849fd-d3a0-7857-bb9c-302871a45127'

# Networking
NETWORK           = '77922c07-8ea4-abb2-708b-4719f4c6a0f8'
DEVICE            = '0'

# System
DEFAULTVCPUs      = '1'
DEFAULTMINMEMORY  = '256'
DEFAULTMAXMEMORY  = '512'

# Template
TEMPLATENAME      = 'DTG-template'

# SSH
SSHUSER           = 'root'

def validIP(address):
    parts = address.split(".")
    if len(parts) != 4:
        return False
    for item in parts:
        if not 0 <= int(item) <= 255:
            return False
    return True

def check_name(name):
    duplicate_name = run('xe vm-list name-label=%s' % name).strip()
    if duplicate_name:
        sys.stderr.write('Duplicate VM name: %s. You might wish to use cl-dtg-rm-vm.' % name)
        sys.exit(1)

def prepare_vm(ip, mac, uuid, memory, vcpus):
    """
    Assigns a mac address, memory and vcpus to a VM.
    """
    if ip != "":
        mac = ip_to_mac(ip)
    if mac == "":
        mac = next_mac()

    # Give the VM a VIF
    run('xe vif-create network-uuid=%s mac=%s vm-uuid=%s device=%s' % (NETWORK, mac, uuid, DEVICE))

    # Give the VM enough memory, and VCPU
    run('xe vm-param-set uuid=%s VCPUs-max=%s' % (uuid, vcpus))
    run('xe vm-param-set uuid=%s  VCPUs-at-startup=%s'  % (uuid,vcpus))

    run('xe vm-memory-limits-set uuid=%s dynamic-max=%sMiB static-max=%sMiB static-min=%sMiB dynamic-min=%sMiB' % (uuid, memory, memory, DEFAULTMINMEMORY, DEFAULTMINMEMORY))


@hosts(dom0)
def new_vm(name, ip="", mac="", memory=DEFAULTMAXMEMORY, vcpus=DEFAULTVCPUs, root_fs_size=DEFAULTROOTFSSIZE, fs_location=SR):
    """
    Create a new VM.
    """

    check_name(name)

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
def new_cloned_vm(name, ip="", mac="", memory=DEFAULTMAXMEMORY, vcpus=DEFAULTVCPUs, root_fs_size=DEFAULTROOTFSSIZE, data_size=DEFAULTDATAFSSIZE, data_SR=SR):
    """
    Build a new VM by cloning the most recent DTG-snapshot.
    This will give a DTG-itised VM, much faster than calling new_vm,
    however the VM uses copy-on-write.
    """

    check_name(name)

    # Create VM from snapshot
    run('xe vm-clone new-name-label=%s vm=%s' % (name, TEMPLATENAME))
    new_vm = run('xe template-list name-label=%s params=uuid --minimal' % name)
    run('xe template-param-set is-a-template=false uuid=%s' % new_vm)

    prepare_vm(ip, mac, new_vm, memory, vcpus)

    # Create a /dev/xvdb that can be mounted at /data/local
    if data_size > 0:
        vdi_b_uuid = run('xe vdi-create sr-uuid=%s virtual-size=%sGiB name-label=%s-data type=user' % (data_SR, data_size, name))
        run('xe vbd-create vm-uuid=%s vdi-uuid=%s device=1' % (new_vm, vdi_b_uuid))

    run('xe vm-start vm=%s' % name)

    # SSH into the new machine, and set the hostname. First wait for the m/c to boot

    while not validIP(ip):
        ip = run('xe vm-param-get param-name=networks uuid=%s | sed -e \'s_0/ip: __\' -e \'s/; .*$//\'' % new_vm)
        sleep(1)

    dns_name = socket.gethostbyaddr(ip)[0]
    print dns_name

    run('xe vm-param-set name-description="%s" uuid=%s' % (dns_name, new_vm))
    run('xe vm-param-set other-config:XenCenter.CustomFields.owner="%s" uuid=%s' % (getpass.getuser(), new_vm))
    run('xe vm-param-set other-config:XenCenter.CustomFields.deletable-by="owner" uuid=%s' % (new_vm))

    with settings(warn_only=True):
        while run('ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no  %s@%s "sudo sh -c \'echo %s > /etc/hostname ; sudo start hostname \'"'  % (SSHUSER, dns_name, name)) == '1':
            sleep(1)
    run('nohup ssh -n -f -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no %s@%s "/etc/rc2.d/S76vm-boot; sudo apt-get update; cd /etc/puppet-bare; sudo git fetch -f git://github.com/ucam-cl-dtg/dtg-puppet.git master:master; nohup sudo bash /etc/puppet-bare/hooks/post-update >/var/log/puppet/install-log 2>&1"' % (SSHUSER, dns_name))


@hosts(dhcp)
def ip_to_mac(ip):
    """
    Convert an IP address to a MAC address by searching our DHCP config.
    """
    if ip == "":
        return "";

    mac = run('grep -B 1 %s /etc/dhcpd.conf | grep ethernet | sed -e \'s/.*net //\' -e \'s/;//\'' % ip)
    return mac

@hosts(dhcp)
def next_mac():
    """
    Finds a MAC address that is not currently assigned to a VM.
    """
    dhcp_macs = run('grep "hardware ethernet" /etc/dhcpd.conf | sed -e \'s/.*ethernet //\' -e \'s/;//\'').upper()
    assigned_macs = run('xe vif-list params=MAC | sed -e \'/^$/d\' -e \'s/.*: //\'').upper()
    return (list((set(dhcp_macs.split()) - set(assigned_macs.split())))[0])


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Make a VM on the DTG husky cluster. The resulting VM will, by the magic of drt24\'s puppet, contain much DTG goodness')

    parser.add_argument('--new-template', action='store_true', help='Build a new template from the Ubuntu repos, and apply DTG customisations. The result is stored as a template, rather than creating a VM')

    # We don't want both an IP address and MAC
    ip_mac_group = parser.add_mutually_exclusive_group()
    ip_mac_group.add_argument('-i', '--ip', help='The created VM will be given a MAC address that will be offered this value by DHCP')
    ip_mac_group.add_argument('-M', '--mac', help='MAC address to assign the VM\s VIF')

    # Optional args
    parser.add_argument('-m', '--memory', type=int, help='memory (in MB) assigned to VM')
    parser.add_argument('-v', '--vcpus', type=int, help='Number of VCPUs')
    parser.add_argument('-r', '--rootfs', dest='root_fs_size', type=int, help='Size of /dev/xvda, the root filesystem (in GB)')
    parser.add_argument('-d', '--datafs', dest='data_size', type=int, help='Size of /dev/xvdb, the data partition, mounted on /data/local (in GB)')
    parser.add_argument('-l', '--dataloc', help='Storage repository to use for the data partition')

    # Name is required
    parser.add_argument('name', help='The hostname of the VM')

    parsed_args = vars(parser.parse_args())
    argstring = ""
    for param in parsed_args.keys():
        if parsed_args[param] != None and param != 'new_template':
            argstring = '%s%s=%s,' % (argstring, param, parsed_args[param])

    argstring = argstring[:-1]

    command = 'new_vm' if parsed_args['new_template'] else 'new_cloned_vm'
    subprocess.call(['fab', '--hide=output,running', '-f', __file__] + [command + ':' + argstring])
