from flask import Flask
from .db import init_mysql, init_mongo
from dotenv import load_dotenv

load_dotenv()

def create_app(template_folder=None):
    app = Flask(__name__, template_folder=template_folder or "templates")

    init_mysql(app)
    init_mongo(app)

    return app

