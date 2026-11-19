import hashlib


def senha(p):
    return hashlib.md5(p.encode()).hexdigest()
