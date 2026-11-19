import flask
import requests

app = flask.Flask(__name__)


@app.route("/proxy")
def proxy():
    return requests.get(flask.request.args.get("url"), timeout=5).text
