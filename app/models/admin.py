from app.extensions import db


class AuditLog(db.Model):
    __tablename__ = 'audit_log'

    id = db.Column(db.Integer, primary_key=True)
    table_name = db.Column(db.String(100), nullable=False)
    record_id = db.Column(db.String(50), nullable=False)
    field_name = db.Column(db.String(100), nullable=True)
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)
    changed_by = db.Column(db.String(80), nullable=True)
    changed_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    change_type = db.Column(db.String(10), nullable=False)  # INSERT, UPDATE, DELETE

    __table_args__ = (
        db.CheckConstraint(
            "change_type IN ('INSERT', 'UPDATE', 'DELETE')",
            name='ck_audit_change_type'
        ),
        db.Index('ix_audit_table_record', 'table_name', 'record_id'),
        db.Index('ix_audit_changed_at', 'changed_at'),
    )

    def __repr__(self):
        return f'<AuditLog {self.table_name}.{self.record_id} {self.change_type}>'


class IdAllocation(db.Model):
    __tablename__ = 'id_allocation'

    tracking_id = db.Column(db.String(20), primary_key=True)
    allocated_date = db.Column(db.Date, nullable=True)
    allocated_to = db.Column(db.String(200), nullable=True)  # field worker name
    status = db.Column(db.String(20), default='allocated', nullable=False)
    # allocated, used, returned, void
    used_date = db.Column(db.Date, nullable=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('allocated', 'used', 'returned', 'void')",
            name='ck_id_allocation_status'
        ),
    )

    def __repr__(self):
        return f'<IdAllocation {self.tracking_id} ({self.status})>'


class BloodReport(db.Model):
    __tablename__ = 'blood_reports'
    id = db.Column(db.Integer, primary_key=True)
    tracking_id = db.Column(db.String(20), db.ForeignKey('participants.tracking_id', ondelete='CASCADE'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    uploaded_by = db.Column(db.String(80), nullable=False)
    uploaded_at = db.Column(db.DateTime, server_default=db.func.now())
    notes = db.Column(db.Text, nullable=True)

    participant = db.relationship('Participant', backref=db.backref('blood_reports', lazy='dynamic'))
