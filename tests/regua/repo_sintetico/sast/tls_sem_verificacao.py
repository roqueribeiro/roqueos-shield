import requests


def status(url):
    return requests.get(url, verify=False, timeout=5).status_code
