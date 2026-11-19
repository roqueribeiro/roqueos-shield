import subprocess


def versao():
    return subprocess.run(["git", "--version"], check=True, capture_output=True).stdout
