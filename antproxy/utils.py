from binascii import b2a_hex
import hashlib
from hmac import compare_digest
import os
import socket
from threading import Thread
import uuid
import warnings
import re


# Token utilities

def new_token(*args, **kwargs):
  """generator for new random tokens

  For now, just UUIDs.
  """
  return uuid.uuid4().hex


def hash_token(token, salt=8, rounds=16384, algorithm='sha512'):
  """hash a token, and return it as `algorithm:salt:hash`

  If `salt` is an integer, a random salt of that many bytes will be used.
  """
  h = hashlib.new(algorithm)
  if isinstance(salt, int):
    salt = b2a_hex(os.urandom(salt))
  if isinstance(salt, bytes):
    bsalt = salt
    salt = salt.decode('utf8')
  else:
    bsalt = salt.encode('utf8')
  btoken = token.encode('utf8', 'replace')
  h.update(bsalt)
  for i in range(rounds):
    h.update(btoken)
  digest = h.hexdigest()

  return "{algorithm}:{rounds}:{salt}:{digest}".format(**locals())


def compare_token(compare, token):
  """compare a token with a hashed token

  uses the same algorithm and salt of the hashed token for comparison
  """
  algorithm, srounds, salt, _ = compare.split(':')
  hashed = hash_token(token, salt=salt, rounds=int(srounds), algorithm=algorithm).encode('utf8')
  compare = compare.encode('utf8')
  if compare_digest(compare, hashed):
    return True
  return False
