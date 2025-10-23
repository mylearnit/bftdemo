import json, hashlib, hmac
from django.conf import settings
from datetime import datetime

def canonical(d):
    return json.dumps(d, sort_keys=True, separators=(',', ':'))

def sign(message_dict, secret=None):
    secret = secret or settings.NODE_SECRET
    payload = canonical(message_dict)
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

def verify(message_dict, signature, secret):
    expected = hmac.new(secret.encode(), canonical(message_dict).encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

def hash_block_payload(payload_dict):
    """
    payload_dict should contain the canonical fields used to compute block hash
    (index, value, prev_hash, timestamp, proposer)
    """
    s = canonical(payload_dict).encode()
    return hashlib.sha256(s).hexdigest()
