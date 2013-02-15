#!/usr/bin/env python
# As close to Python3 as 2.7 can get
from __future__ import absolute_import, division, print_function, unicode_literals
from future_builtins import *  # ascii, filter, hex, map, oct, zip

import argparse
from fabric.api import *
import re
import sys

DOM0_HOST = 'root@husky0.dtg.cl.cam.ac.uk'


class DefaultList(list):
    """Default argument list for action='append' arguments. Use as parser.add_argument(default=DefaultList([yourlist])).

    If using action='append' and default=[...] together, any extra arguments on the command line get ADDED to the default.
    Using the DefaultList wrapper erases the default if anything is passed on the command line.
    """
    def __copy__(self):
        return []


def ipaddress(string):
    """IP address validator for argparse. Use as parser.add_argument(type=ipaddress)."""
    err = argparse.ArgumentTypeError('An IP address must be four 0-255 separated by dots, for example 1.2.100.200')
    m = re.match(r'^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$', string)
    if not m:
        raise err
    for g in m.groups():
        try:
            if not (0 <= int(g) <= 255):
                raise err
        except TypeError:
            raise err
    return string


def macaddress(string):
    """MAC address validator for argparse. Use as parser.add_argument(type=macaddress)."""
    err = argparse.ArgumentTypeError('A MAC address must be six [0-9a-f]{2} separated by colons, for example 00:11:22:aa:bb:cc')
    string = string.lower()
    m = re.match(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$', string)
    if not m:
        raise err
    return string


def task_retval(execute_dict):
    """Returns the return value of a fabric task run on a single host as a simple value.

    Usage:
    asd = task_return(execute(fabric_task, hosts=[...]))

    Normally, execute() returns a dictionary of {host, return value} items for each host the task is run on.
    This is annoying if tasks are run on a single host. The task_return() wrapper returns the return value,
    or error if there are 0 or 2+.
    """
    assert len(execute_dict) == 1
    return execute_dict.values()[0]


def xe_exists(object_type, uuid):
    """Returns true if "xe x-list uuid=..." has any results.

    For example, use object_type 'vm', 'network' or 'template'.
    Can be used from tasks on host husky0.
    """
    return bool(run('xe %s-list uuid=%s' % (object_type, uuid)).strip())


def xe_find(object_type, name_or_uuid_substring):
    """Returns the uuid of an object based on part of a name or uuid.

    Fails if there are 0 or 2+ matches: specify just enough to get 1 match.
    Can be used from tasks on host husky0.
    """
    out = unicode(run('xe %s-list params=uuid,name-label' % object_type, quiet=True))
    objects = []
    for obj in out.split('\r\n\r\n\r\n'):  # xe output objects are separated by 1 newline + 2 blank lines
        lines = list(map(unicode.strip, obj.strip().split('\r\n')))
        assert len(lines) == 2, 'Expecting two lines, uuid and name-label'
        uuid, name = lines
        assert uuid.startswith('uuid')
        assert uuid.count(':') >= 1
        assert name.startswith('name-label')
        assert name.count(':') >= 1
        uuid = uuid.split(':', 1)[1].strip()
        name = name.split(':', 1)[1].strip()
        if name_or_uuid_substring in name or name_or_uuid_substring in uuid:
            objects.append((uuid, name))
    assert len(objects) > 0, 'Found no matches for name %r.' % name_or_uuid_substring
    assert len(objects) < 2, 'Found 2+ matches for name %r, ambiguous.' % name_or_uuid_substring
    return objects[0]  # Return first and only item


def xe_param(command, output_param_name, **selectors):
    """Returns a list of parameters of objects found by the xe command.

    Selectors are passed to the xe command as key=value.
    For example, xe_param('vm-vif-list', 'uuid', vm='some-vm-uuid') returns a list of uuids of VIFs attached to a vm.
    May return an empty list.
    """
    out = unicode(run('xe %s params=%s %s' % (command, output_param_name, ' '.join(key + '=' + value for (key, value) in selectors.iteritems())), quiet=True))
    objects = []
    for line in out.split('\r\n\r\n\r\n'):  # xe output objects are separated by 1 newline + 2 blank lines
        key, value = line.strip().split(':', 1)
        assert key.startswith(output_param_name)
        objects.append(value.strip())
    return objects
