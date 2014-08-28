#!/usr/bin/env python
# As close to Python3 as 2.7 can get
from __future__ import absolute_import, division, print_function, unicode_literals
from future_builtins import *  # ascii, filter, hex, map, oct, zip

import argparse

def ip_to_mac(ip):
    split_ip = ip.split('.')
    mac = '00:16:3e'
    for group in split_ip[1:]:
        mac += ':{:02X}'.format(int(group))
    return mac.upper()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--ip')
    results = parser.parse_args()

    print(ip_to_mac(results.ip))
