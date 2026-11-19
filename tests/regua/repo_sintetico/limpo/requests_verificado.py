import requests


def saude():
    return requests.get("https://api.exemplo.test/status", timeout=5).status_code
