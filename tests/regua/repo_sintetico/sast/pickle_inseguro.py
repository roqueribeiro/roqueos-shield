import pickle

import flask

app = flask.Flask(__name__)


@app.route("/load", methods=["POST"])
def load():
    return pickle.loads(flask.request.data)
