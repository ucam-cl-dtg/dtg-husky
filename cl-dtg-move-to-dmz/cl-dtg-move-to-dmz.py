#!/usr/bin/env python
# As close to Python3 as 2.7 can get
from __future__ import absolute_import, division, print_function, unicode_literals
from future_builtins import *  # ascii, filter, hex, map, oct, zip

import argparse
from cStringIO import StringIO
from fabric.api import *
import sys
import xenhelpers


DMZ_NETWORK = 'DMZ vlan'


def etc_network_interfaces(args):
    """Returns file contents for /etc/network/interfaces."""
    all_nameservers = ' '.join(args.nameserver)
    return '''
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
address {ip}
netmask {netmask}
gateway {gateway}
dns-nameservers {all_nameservers}
dns-search {domain}
pre-up iptables-restore < /etc/iptables.rules
'''.format(all_nameservers=all_nameservers, **args.__dict__)


@task
def test_ssh(use_sudo=False):
    func = sudo if use_sudo else run
    out = func('uname -a', quiet=True, warn_only=True)
    assert out.succeeded


def test_access_rights(args):
    """Not a fabric task, a simple function."""
    print('Testing access on root@husky0', file=sys.stderr)
    execute(test_ssh, hosts=[xenhelpers.DOM0_HOST])
    print('Access to root@husky0 OK.', file=sys.stderr)
    print('Testing access and sudo rights on ' + args.ssh_address, file=sys.stderr)
    execute(test_ssh, use_sudo=True, hosts=[args.ssh_address])
    print('Access and sudo on %s OK.' % args.ssh_address, file=sys.stderr)


@task
def test_vm_exists(vm):
    uuid, name = xenhelpers.xe_find('vm', vm)  # xe_uuid will fail if there are more than one results.
    print('Found VM "%s" (%s)' % (name, uuid), file=sys.stderr)
    return uuid, name


@task
def test_dmz_exists():
    uuid, name = xenhelpers.xe_find('network', DMZ_NETWORK)  # xe_uuid will fail if there are more than one results.
    print('Found network "%s" (%s)' % (name, uuid), file=sys.stderr)
    return uuid


@task
def test_vifs_exist(vmuuid, vmname):
    vifs = xenhelpers.xe_param('vm-vif-list', 'uuid', vm=vmuuid)
    if not vifs:
        abort('No VIFs found on "%s" (%s). How did you SSH into it then?' % (vmname, vmuuid))


@task
def set_static_network(args):
    put(StringIO(etc_network_interfaces(args)), '/etc/network/interfaces', use_sudo=True, mode=0644)


@task
def remove_vifs(vmuuid):
    for vifuuid in xenhelpers.xe_param('vm-vif-list', 'uuid', vm=vmuuid):
        run('xe vif-unplug uuid=%s' % vifuuid)
        run('xe vif-destroy uuid=%s' % vifuuid)


@task
def create_dmz_vif(vmuuid, networkuuid, mac):
    vifuuid = run('xe vif-create vm-uuid=%s network-uuid=%s mac=%s device=0' % (vmuuid, networkuuid, mac)).strip()
    run('xe vif-plug uuid=%s' % vifuuid)


def main(args):
    test_access_rights(args)
    vmuuid, vmname = xenhelpers.task_retval(execute(test_vm_exists, args.vm, hosts=[xenhelpers.DOM0_HOST]))
    networkuuid = xenhelpers.task_retval(execute(test_dmz_exists, hosts=[xenhelpers.DOM0_HOST]))
    execute(test_vifs_exist, vmuuid, vmname, hosts=[xenhelpers.DOM0_HOST])
    execute(set_static_network, args, hosts=[args.ssh_address])
    prompt('Static config written to /etc/network/interfaces. Replacing VIF.')
    execute(remove_vifs, vmuuid, hosts=[xenhelpers.DOM0_HOST])
    execute(create_dmz_vif, vmuuid, networkuuid, args.mac, hosts=[xenhelpers.DOM0_HOST])
    print('All done. Your server should now exist on public IP %s.' % args.ip)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Moves a VM to the DMZ by changing its network config to static, and switching the VIF to DMZ vlan.')
    # Specify the VM
    parser.add_argument('--vm', required=True, help='Substring of the name-label or uuid of the VM on Xen. Specify enough to make it unambiguous.')
    parser.add_argument('--ssh-address', required=True, help='IP or hostname where to ssh into this VM currently.')
    # New config
    parser.add_argument('--mac', type=xenhelpers.macaddress, required=True, help='MAC address on the DMZ. Get this from the CL sysadmins.')
    parser.add_argument('--ip', type=xenhelpers.ipaddress, required=True, help='IP address on the DMZ. Get this from the CL sysadmins.')
    parser.add_argument('--gateway', type=xenhelpers.ipaddress, required=True, help='Gateway on the DMZ. Get this from the CL sysadmins.')
    parser.add_argument('--netmask', type=xenhelpers.ipaddress, default='255.255.255.0', help='Netmask on the DMZ. Get this from the CL sysadmins.')
    parser.add_argument('--nameserver', type=xenhelpers.ipaddress, action='append', default=xenhelpers.DefaultList(['128.232.1.1', '128.232.1.2', '128.232.1.3']),
                        help='Nameservers on the DMZ. Usually standard CL nameservers.')
    parser.add_argument('--domain', default='dtg.cl.cam.ac.uk', help='DNS domain search suffix. Usually dtg.cl.cam.ac.uk.')
    # Run
    args = parser.parse_args()
    main(args)






