#! /usr/bin/env python2.7

from fabric.api import *
import sys, argparse, subprocess, socket
from datetime import date
from time import sleep

dom0 = 'husky0.dtg.cl.cam.ac.uk'

env.user="root"

@hosts(dom0)
def rm_vm(name):
    """
    Destroy an existing VM.
    """

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

