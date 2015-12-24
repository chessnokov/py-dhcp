#
# Copyright 2015 iXsystems, Inc.
# All rights reserved
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted providing that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
# IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
# STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING
# IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
#####################################################################

import enum
import ipaddress
import struct


MAGIC_COOKIE = b'\x63\x82\x53\x63'


class PacketType(enum.IntEnum):
    BOOTREQUEST = 1
    BOOTREPLY = 2


class HardwareAddressType(enum.IntEnum):
    ETHERNET = 1
    IEEE802 = 6


class MessageType(enum.IntEnum):
    DHCPDISCOVER = 1
    DHCPOFFER = 2
    DHCPREQUEST = 3
    DHCPDECLINE = 4
    DHCPACK = 5
    DHCPNAK = 6
    DHCPRELEASE = 7


class PacketOption(enum.IntEnum):
    SUBNET_MASK = 1
    ROUTER = 3
    TIME_SERVER = 4
    NAME_SERVER = 5
    DOMAIN_NAME_SERVER = 6
    LOG_SERVER = 7
    HOST_NAME = 12
    DOMAIN_NAME = 15
    ROOT_PATH = 17
    EXTENSIONS_PATH = 18
    REQUESTED_IP = 50
    LEASE_TIME = 51
    MESSAGE_TYPE = 53
    SERVER_IDENT = 54
    PARAMETER_REQUEST_LIST = 55
    CLASS_IDENT = 60
    CLIENT_IDENT = 61


class Packet(object):
    def __init__(self):
        self.op = None
        self.htype = None
        self.hlen = None
        self.hops = None
        self.secs = None
        self.flags = None
        self.xid = None
        self.ciaddr = ipaddress.ip_address('0.0.0.0')
        self.yiaddr = ipaddress.ip_address('0.0.0.0')
        self.siaddr = ipaddress.ip_address('0.0.0.0')
        self.giaddr = ipaddress.ip_address('0.0.0.0')
        self.chaddr = bytes(b'\x00\x00\x00\x00\x00\x00')
        self.sname = ''
        self.cookie = None
        self.options = {}

    def clone_from(self, other):
        self.htype = other.htype
        self.hlen = other.hlen
        self.hops = other.hops
        self.xid = other.xid
        self.secs = other.secs
        self.flags = other.flags
        self.chaddr = other.chaddr

    def unpack(self, payload):
        self.op, self.htype, self.hlen, self.hops = struct.unpack_from('BBBB', payload, 0)
        self.xid = struct.unpack_from('!I', payload, 4)[0]
        self.secs, self.flags = struct.unpack_from('HH', payload, 8)
        self.ciaddr = ipaddress.ip_address(struct.unpack_from('!I', payload, 12)[0])
        self.yiaddr = ipaddress.ip_address(struct.unpack_from('!I', payload, 16)[0])
        self.siaddr = ipaddress.ip_address(struct.unpack_from('!I', payload, 20)[0])
        self.giaddr = ipaddress.ip_address(struct.unpack_from('!I', payload, 24)[0])
        self.chaddr = struct.unpack_from('12s', payload, 28)[0]
        self.sname = struct.unpack_from('64s', payload, 44)[0].decode('ascii')

        self.op = PacketType(self.op)
        self.cookie = struct.unpack_from('4s', payload, 236)[0]

        offset = 240
        while offset < len(payload):
            code = struct.unpack_from('B', payload, offset)[0]
            offset += 1

            if code == 0:
                continue

            if code == 255:
                break

            length = struct.unpack_from('B', payload, offset)[0]
            offset += 1
            value = struct.unpack_from('{0}s'.format(length), payload, offset)[0]
            offset += length
            optid = PacketOption(code)
            self.options[optid] = Option(optid, packed=value)

    def pack(self):
        result = bytearray(bytes(240))
        struct.pack_into('BBBB', result, 0, int(self.op), self.htype, self.hlen, self.hops)
        struct.pack_into('!I', result, 4, self.xid)
        struct.pack_into('HH', result, 8, self.secs, self.flags)
        struct.pack_into('!II', result, 12, int(self.ciaddr), int(self.yiaddr))
        struct.pack_into('!II', result, 20, int(self.siaddr), int(self.giaddr))
        struct.pack_into('12s', result, 28, self.chaddr)
        struct.pack_into('64s', result, 40, self.sname.encode('ascii'))
        struct.pack_into('4s', result, 236, MAGIC_COOKIE)

        for id, i in self.options.items():
            packed = i.pack()
            result += struct.pack('BB{0}s'.format(len(packed)), int(id), len(packed), packed)

        return result

    def dump(self, f):
        print("Op: {0}".format(self.op.name))
        print("Client address: {0}".format(self.ciaddr), file=f)
        print("Your address: {0}".format(self.yiaddr), file=f)
        print("Server address: {0}".format(self.siaddr), file=f)
        print("Gateway address: {0}".format(self.giaddr), file=f)
        print("Client hardware address: {0}".format(':'.join('%02x' % b for b in self.chaddr[:6])))
        print("XID: {0}".format(self.xid))
        print("Sname: {0}".format(self.sname))
        print("Magic cookie: {0}".format(self.cookie))
        print("Options:", file=f)
        for i in self.options.values():
            print("\t{0} = {1}".format(i.id.name, i.value), file=f)


class Option(object):
    def __init__(self, id, value=None, packed=None):
        self.id = id

        if value:
            self.value = value
            return

        if packed:
            self.unpack(packed)

    def unpack(self, value):
        if self.id in (PacketOption.ROUTER, PacketOption.REQUESTED_IP, PacketOption.SUBNET_MASK):
            self.value = ipaddress.ip_address(value)
            return

        if self.id in (PacketOption.HOST_NAME, PacketOption.DOMAIN_NAME):
            self.value = value.decode('ascii')
            return

        if self.id in (PacketOption.DOMAIN_NAME_SERVER, PacketOption.LOG_SERVER, PacketOption.TIME_SERVER):
            self.value = []
            for i in struct.iter_unpack('I', value):
                self.value.append(ipaddress.ip_address(i[0]))

        if self.id == PacketOption.MESSAGE_TYPE:
            self.value = MessageType(value[0])
            return

        self.value = value

    def pack(self):
        if self.id in (PacketOption.ROUTER, PacketOption.REQUESTED_IP, PacketOption.SUBNET_MASK):
            return self.value.packed

        if self.id in (PacketOption.DOMAIN_NAME_SERVER, PacketOption.LOG_SERVER, PacketOption.TIME_SERVER):
            return b''.join(i.packed for i in self.value)

        if self.id in (PacketOption.HOST_NAME, PacketOption.DOMAIN_NAME):
            return self.value.encode('ascii')

        if self.id == PacketOption.MESSAGE_TYPE:
            return bytes([int(self.value)])

        if self.id == PacketOption.LEASE_TIME:
            return struct.pack('!I', self.value)