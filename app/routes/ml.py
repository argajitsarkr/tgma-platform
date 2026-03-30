from flask import Blueprint, render_template
from flask_login import login_required

ml_bp = Blueprint('ml', __name__, url_prefix='/ml')


@ml_bp.route('/')
@login_required
def status():
    return render_template('ml/status.html')
