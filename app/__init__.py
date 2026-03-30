import os
from flask import Flask
from dotenv import load_dotenv

from .extensions import db, migrate, login_manager, csrf

load_dotenv()


def create_app(config_name=None):
    app = Flask(__name__)

    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    from config import config as config_map
    app.config.from_object(config_map.get(config_name, config_map['default']))

    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Register blueprints
    from .auth import auth_bp
    app.register_blueprint(auth_bp)

    from .routes.dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp)

    from .routes.participants import participants_bp
    app.register_blueprint(participants_bp)

    from .routes.samples import samples_bp
    app.register_blueprint(samples_bp)

    from .routes.diagnostics import diagnostics_bp
    app.register_blueprint(diagnostics_bp)

    from .routes.ids import ids_bp
    app.register_blueprint(ids_bp)

    from .routes.quality import quality_bp
    app.register_blueprint(quality_bp)

    from .routes.ml import ml_bp
    app.register_blueprint(ml_bp)

    from .routes.reports import reports_bp
    app.register_blueprint(reports_bp)

    # Context processor for templates
    @app.context_processor
    def inject_config():
        return {
            'target_enrollment': app.config['TARGET_ENROLLMENT'],
            'district_targets': app.config['DISTRICT_TARGETS'],
        }

    return app
