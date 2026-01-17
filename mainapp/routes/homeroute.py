from flask import render_template, Blueprint

homeapp = Blueprint("homeroutes",
                    __name__)

@homeapp.route("/")
def home():
    return render_template("home.html")