import io
import mock
import pytest

from ..trezor import client
from .. import formats
from .. import util


ADDR = [2147483661, 2810943954, 3938368396, 3454558782, 3848009040]
CURVE = 'nist256p1'

PUBKEY = (b'\x03\xd8(\xb5\xa6`\xbet0\x95\xac:[;]\xdc,\xbd\xdc?\xd7\xc0\xec'
          b'\xdd\xbc+\xfar~\x9dAis')
PUBKEY_TEXT = ('ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzd'
               'HAyNTYAAABBBNgotaZgvnQwlaw6Wztd3Cy93D/XwOzdvCv6cn6dQWlzNMEQeW'
               'VUfhvrGljR2Z/CMRONY6ejB+9PnpUOPuzYqi8= ssh://localhost:22\n')


class ConnectionMock(object):

    def __init__(self, version):
        self.features = mock.Mock(spec=[])
        self.features.device_id = '123456789'
        self.features.label = 'mywallet'
        self.features.vendor = 'mock'
        self.features.major_version = version[0]
        self.features.minor_version = version[1]
        self.features.patch_version = version[2]
        self.features.revision = b'456'
        self.closed = False

    def close(self):
        self.closed = True

    def clear_session(self):
        self.closed = True

    def get_public_node(self, n, ecdsa_curve_name=b'secp256k1'):
        assert not self.closed
        assert n == ADDR
        assert ecdsa_curve_name in {b'secp256k1', b'nist256p1'}
        result = mock.Mock(spec=[])
        result.node = mock.Mock(spec=[])
        result.node.public_key = PUBKEY
        return result

    def ping(self, msg):
        assert not self.closed
        return msg


class FactoryMock(object):

    @staticmethod
    def client():
        return ConnectionMock(version=(1, 3, 4))

    @staticmethod
    def identity_type(**kwargs):
        result = mock.Mock(spec=[])
        result.index = 0
        result.proto = result.user = result.host = result.port = None
        result.path = None
        for k, v in kwargs.items():
            setattr(result, k, v)
        return result


BLOB = (b'\x00\x00\x00 \xce\xe0\xc9\xd5\xceu/\xe8\xc5\xf2\xbfR+x\xa1\xcf\xb0'
        b'\x8e;R\xd3)m\x96\x1b\xb4\xd8s\xf1\x99\x16\xaa2\x00\x00\x00\x05roman'
        b'\x00\x00\x00\x0essh-connection\x00\x00\x00\tpublickey'
        b'\x01\x00\x00\x00\x13ecdsa-sha2-nistp256\x00\x00\x00h\x00\x00\x00'
        b'\x13ecdsa-sha2-nistp256\x00\x00\x00\x08nistp256\x00\x00\x00A'
        b'\x04\xd8(\xb5\xa6`\xbet0\x95\xac:[;]\xdc,\xbd\xdc?\xd7\xc0\xec'
        b'\xdd\xbc+\xfar~\x9dAis4\xc1\x10yeT~\x1b\xeb\x1aX\xd1\xd9\x9f\xc21'
        b'\x13\x8dc\xa7\xa3\x07\xefO\x9e\x95\x0e>\xec\xd8\xaa/')

SIG = (b'\x00R\x19T\xf2\x84$\xef#\x0e\xee\x04X\xc6\xc3\x99T`\xd1\xd8\xf7!'
       b'\x862@cx\xb8\xb9i@1\x1b3#\x938\x86]\x97*Y\xb2\x02Xa\xdf@\xecK'
       b'\xdc\xf0H\xab\xa8\xac\xa7? \x8f=C\x88N\xe2')


def test_ssh_agent():
    label = 'localhost:22'
    c = client.Client(factory=FactoryMock)
    ident = c.get_identity(label=label)
    assert ident.host == 'localhost'
    assert ident.proto == 'ssh'
    assert ident.port == '22'
    assert ident.user is None
    assert ident.path is None

    with c:
        assert c.get_public_key(label) == PUBKEY_TEXT

        def ssh_sign_identity(identity, challenge_hidden,
                              challenge_visual, ecdsa_curve_name):
            assert challenge_hidden == BLOB
            assert challenge_visual == identity.path
            assert ecdsa_curve_name == b'nist256p1'

            result = mock.Mock(spec=[])
            result.public_key = PUBKEY
            result.signature = SIG
            return result

        c.client.sign_identity = ssh_sign_identity
        signature = c.sign_ssh_challenge(label=label, blob=BLOB)

        key = formats.import_public_key(PUBKEY_TEXT)
        serialized_sig = key['verifier'](sig=signature, msg=BLOB)

        stream = io.BytesIO(serialized_sig)
        r = util.read_frame(stream)
        s = util.read_frame(stream)
        assert not stream.read()
        assert r[:1] == b'\x00'
        assert s[:1] == b'\x00'
        assert r[1:] + s[1:] == SIG[1:]


def test_utils():
    identity = mock.Mock(spec=[])
    identity.proto = 'https'
    identity.user = 'user'
    identity.host = 'host'
    identity.port = '443'
    identity.path = '/path'

    url = 'https://user@host:443/path'
    assert client.identity_to_string(identity) == url


def test_old_version():

    class OldFactoryMock(FactoryMock):

        @staticmethod
        def client():
            return ConnectionMock(version=(1, 2, 3))

    with pytest.raises(ValueError):
        client.Client(factory=OldFactoryMock)
