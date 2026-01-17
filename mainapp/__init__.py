from flask import Flask

def create_app():
    app=Flask(__name__,
              template_folder="templates",
              static_folder="static",)
    
    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024 # limit max upload size

    from .routes.homeroute import homeapp as home_blueprint
    from .api.api import apiapp as api_blueprint

    app.register_blueprint(home_blueprint, url_prefix="/")
    app.register_blueprint(api_blueprint, url_prefix="/api")

    return app