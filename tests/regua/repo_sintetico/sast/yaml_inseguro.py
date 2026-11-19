import flask
import yaml

app = flask.Flask(__name__)


@app.route("/config", methods=["POST"])
def config():
    return yaml.load(flask.request.data, Loader=yaml.Loader)
