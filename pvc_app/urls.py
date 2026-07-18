from flask import Blueprint
from .views import bp as main_bp


def register_urls(app):
    app.register_blueprint(main_bp)

