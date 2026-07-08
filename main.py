
import flask

from shared.models import (
    Countries,
    Sources,
    Articles,
    get_headlines_by_country
)

app = flask.Flask(__name__)

@app.route("/")
def home():
    data = get_headlines_by_country()
    print(data)
    return flask.render_template("index.html", data=data)


if __name__ == '__main__':
    app.run(debug=True)