from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, DeclarativeBase

class Base(DeclarativeBase): # SQLAlchemy declarative base
    pass

def init_db(app): # call this once during app startup
    db_path = Path(app.root_path) / "app.db" # store SQLite DB inside mainapp by default
    app.config["DB_PATH"] = str(db_path) # path for debugging

    engine = create_engine(
        f"sqlite:///{db_path}", # SQLite file path
        echo = False, # False for no SQL logs
        connect_args = {"check_same_thread": False} # allow use across Flask threads
    )

    Session = scoped_session(sessionmaker(bind = engine, autoflush = False, autocommit = False)) # per-thread sessions
    app.extensions["db_engine"] = engine # store engine on app
    app.extensions["db_session"] = Session # store session factory on app

    @app.teardown_appcontext
    def _cleanup_db(exception = None):
        Session.remove() # prevent session leaks between requests

    return engine, Session

def get_session(app): # grab current scoped session
    return app.extensions["db_session"]