import flask

app = flask.Flask(__name__)


@app.route("/calc")
def calc():
    return str(eval(flask.request.args.get("expr")))
