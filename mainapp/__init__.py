from flask import Flask
from .db import init_db
from .models import Base
from .api.api import apiapp

def create_app():
    app=Flask(__name__,
              template_folder="templates",
              static_folder="static",)
    
    engine, Session = init_db(app) # init engine + session
    Base.metadata.create_all(engine) # create tables if missings

    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024 # limit max upload size

    from .routes.homeroute import homeapp as home_blueprint
    from .api.api import apiapp as api_blueprint

    app.register_blueprint(home_blueprint, url_prefix="/")
    app.register_blueprint(api_blueprint, url_prefix="/api")

    return app