import subprocess

import flask

app = flask.Flask(__name__)


@app.route("/ping")
def ping():
    host = flask.request.args.get("host")
    return subprocess.check_output("ping -c1 " + host, shell=True)
