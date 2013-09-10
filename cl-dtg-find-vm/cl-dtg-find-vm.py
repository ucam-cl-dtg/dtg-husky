#! /usr/bin/env python2.7

from fabric.api import *
from fabric.utils import *
import argparse
import re

dhcp = 'husky0.dtg.cl.cam.ac.uk'
dom0 = 'husky0.dtg.cl.cam.ac.uk'

env.user = "root"

@hosts(dom0)
def find_vm(name):
    """
    Find the dns name for an existing VM.
    """

    macs = run('xe vm-vif-list vm="%s" --minimal params=MAC' % (name)).strip()
    if not macs:
        abort("No network interfaces found for %s" % (name))

    macs = macs.split(",")
    if len(macs) > 1:
        warn("Multiple interfaces found.  Using the first one")

    ip = mac_to_ip(macs[0])

    dnsname = local('dig -x %s +short' % (ip),capture=True)
    print dnsname

@hosts(dhcp)
def mac_to_ip(mac):
    """
    Convert a MAC address to an IP address by searching our DHCP config.
    """
    if mac == "":
        abort("MAC not set")

    ip = run('grep -A 1 %s /etc/dhcpd.conf | grep fixed-address | sed -e \'s/.*fixed-address //\' -e \'s/;//\'' % mac)
    return ip
                       

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Find the DNS name for a VM')

    parser.add_argument('name', help='The name of the VM')

    parsed_args = vars(parser.parse_args())
    execute(find_vm, **parsed_args)
