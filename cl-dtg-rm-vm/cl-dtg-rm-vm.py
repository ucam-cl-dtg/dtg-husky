#! /usr/bin/env python2.7

from fabric.api import *
from fabric.utils import *
import argparse, subprocess, getpass, re

dom0 = 'husky0.dtg.cl.cam.ac.uk'

env.user = "root"

@hosts(dom0)
def rm_vm(name):
    """
    Destroy an existing VM.
    """

    # Find the uuid of the VM and abort if we don't find exactly 1 result
    uuid = run('xe vm-list name-label=%s --minimal params=uuid' % (name)).strip()
    if not uuid:
        abort("Failed to find VM with name-label=%s" % (name))
    uuids = uuid.split(",")
    if len(uuids) != 1:
        abort("Found %d VMs with name-label=%s" % (len(uuids),name))
    uuid = uuids[0]

    # Find out the owner of the VM by reading the name-description parameter from xe
    owner = run('xe vm-param-get uuid=%s param-name=other-config param-key=XenCenter.CustomFields.owner' % (uuid)).strip()
    if not owner:
        abort("Failed to find owner parameter (other-config:XenCenter.CustomFields.owner) for this VM")

    # Ensure that the owner of the VM matches the user running this script
    if getpass.getuser() != owner:
        abort("This VM is owned by a different user %s" % (owner))

    vdi_uuids = run('xe vbd-list vm-name-label=%s --minimal params=vdi-uuid' % (name))

    run('xe vm-uninstall vm=%s force=true' % (name))

    for uuid in vdi_uuids.strip().split(","):
        vdi_check = run('xe vdi-list uuid=%s' % (uuid)).strip()
        if (vdi_check == uuid):
            run('xe vdi-destroy uuid=%s' % (uuid))

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Destroy a VM on the DTG husky cluster. This script removes the VM and deletes all its storage devices')

    parser.add_argument('name', help='The name of the VM')

    parsed_args = vars(parser.parse_args())
    argstring = ""
    for param in parsed_args.keys():
        if parsed_args[param] != None:
            argstring = '%s%s=%s,' % (argstring, param, parsed_args[param])

    argstring = argstring[:-1]
    command = 'rm_vm'
    subprocess.call(['fab', '--hide=output,running', '-f', __file__] + [command + ':' + argstring])

