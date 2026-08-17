from flask import Flask, render_template
from flask_cors import CORS

app = Flask(__name__, template_folder="templates")
CORS(app)


@app.get("/")
def dashboard():
    return render_template("dashboard.html")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5002, debug=True)
