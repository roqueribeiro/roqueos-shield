import os

import flask

app = flask.Flask(__name__)


@app.route("/arquivo")
def arquivo():
    nome = flask.request.args.get("f")
    with open(os.path.join("/srv/dados", nome)) as fh:
        return fh.read()
