import flask

app = flask.Flask(__name__)


@app.route("/user")
def user(db):
    uid = flask.request.args.get("id")
    return db.execute("SELECT * FROM users WHERE id = '" + uid + "'")
