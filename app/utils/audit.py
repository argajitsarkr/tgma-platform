"""Application-level audit logging for all model changes."""

from flask import has_request_context
from flask_login import current_user
from sqlalchemy import event, inspect

from app.extensions import db
from app.models.admin import AuditLog

# Tables to audit (exclude audit_log itself and users)
AUDITED_TABLES = {
    'participants', 'health_screening', 'anthropometrics', 'menstrual_data',
    'lifestyle_data', 'environment_ses', 'samples', 'hormone_results',
    'sequencing_results', 'metabolic_risk', 'id_allocation',
}


def _get_current_username():
    if has_request_context() and current_user and current_user.is_authenticated:
        return current_user.username
    return 'system'


def _get_record_id(instance):
    """Get the primary key value as string for audit logging."""
    mapper = inspect(type(instance))
    pk_cols = mapper.primary_key
    pk_values = [getattr(instance, col.name) for col in pk_cols]
    return str(pk_values[0]) if len(pk_values) == 1 else str(pk_values)


def _log_insert(mapper, connection, target):
    table_name = target.__tablename__
    if table_name not in AUDITED_TABLES:
        return
    record_id = _get_record_id(target)
    username = _get_current_username()
    db.session.add(AuditLog(
        table_name=table_name,
        record_id=record_id,
        field_name=None,
        old_value=None,
        new_value='[created]',
        changed_by=username,
        change_type='INSERT',
    ))


def _log_update(mapper, connection, target):
    table_name = target.__tablename__
    if table_name not in AUDITED_TABLES:
        return
    state = inspect(target)
    record_id = _get_record_id(target)
    username = _get_current_username()
    for attr in state.attrs:
        hist = attr.history
        if hist.has_changes() and attr.key not in ('created_at', 'updated_at'):
            old_val = str(hist.deleted[0]) if hist.deleted else None
            new_val = str(hist.added[0]) if hist.added else None
            db.session.add(AuditLog(
                table_name=table_name,
                record_id=record_id,
                field_name=attr.key,
                old_value=old_val,
                new_value=new_val,
                changed_by=username,
                change_type='UPDATE',
            ))


def _log_delete(mapper, connection, target):
    table_name = target.__tablename__
    if table_name not in AUDITED_TABLES:
        return
    record_id = _get_record_id(target)
    username = _get_current_username()
    db.session.add(AuditLog(
        table_name=table_name,
        record_id=record_id,
        field_name=None,
        old_value='[deleted]',
        new_value=None,
        changed_by=username,
        change_type='DELETE',
    ))


def init_audit_listeners():
    """Register SQLAlchemy event listeners for audit logging.
    Call this after all models are imported."""
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if hasattr(cls, '__tablename__') and cls.__tablename__ in AUDITED_TABLES:
            event.listen(cls, 'after_insert', _log_insert)
            event.listen(cls, 'after_update', _log_update)
            event.listen(cls, 'after_delete', _log_delete)
