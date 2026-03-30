from app.extensions import db


class Sample(db.Model):
    __tablename__ = 'samples'

    # Primary key — e.g. TGMA-WT-F-0037-STL
    sample_id = db.Column(db.String(30), primary_key=True)
    tracking_id = db.Column(db.String(20), db.ForeignKey('participants.tracking_id',
                            onupdate='CASCADE', ondelete='RESTRICT'), nullable=False, index=True)

    sample_type = db.Column(db.String(20), nullable=False)
    # stool, blood, saliva_1, saliva_2, saliva_3, saliva_4, dna_extract, serum

    # Collection
    collection_datetime = db.Column(db.DateTime, nullable=True)
    collection_status = db.Column(db.String(20), default='collected', nullable=False)
    # collected, not_collected, failed
    barcode_scanned = db.Column(db.Boolean, default=False)

    # Stool-specific
    bristol_scale = db.Column(db.Integer, nullable=True)

    # Blood-specific
    fasting_confirmed = db.Column(db.Boolean, nullable=True)
    last_meal_time = db.Column(db.DateTime, nullable=True)

    # Storage
    storage_status = db.Column(db.String(20), default='stored', nullable=False)
    # in_transit, stored, dispatched, used, depleted
    freezer_id = db.Column(db.String(20), nullable=True)
    rack = db.Column(db.String(10), nullable=True)
    shelf = db.Column(db.String(10), nullable=True)
    box_number = db.Column(db.String(10), nullable=True)
    box_row = db.Column(db.String(5), nullable=True)
    box_column = db.Column(db.String(5), nullable=True)
    storage_date = db.Column(db.Date, nullable=True)
    storage_temp = db.Column(db.String(10), nullable=True)  # -80, -20, 4, RT

    # Dispatch (for sequencing vendor)
    dispatched_to = db.Column(db.String(200), nullable=True)
    dispatch_date = db.Column(db.Date, nullable=True)
    dispatch_tracking_number = db.Column(db.String(100), nullable=True)
    dispatch_manifest_id = db.Column(db.String(50), nullable=True)
    received_by_vendor_date = db.Column(db.Date, nullable=True)

    # QC (post-extraction)
    dna_concentration_ng_ul = db.Column(db.Numeric(8, 2), nullable=True)
    a260_a280_ratio = db.Column(db.Numeric(4, 2), nullable=True)
    quantity_ug = db.Column(db.Numeric(8, 2), nullable=True)
    qc_pass = db.Column(db.Boolean, nullable=True)

    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    __table_args__ = (
        db.CheckConstraint(
            "sample_type IN ('stool', 'blood', 'saliva_1', 'saliva_2', 'saliva_3', 'saliva_4', 'dna_extract', 'serum')",
            name='ck_samples_type'
        ),
        db.CheckConstraint(
            "collection_status IN ('collected', 'not_collected', 'failed')",
            name='ck_samples_collection_status'
        ),
        db.CheckConstraint(
            "storage_status IN ('in_transit', 'stored', 'dispatched', 'used', 'depleted')",
            name='ck_samples_storage_status'
        ),
        db.CheckConstraint(
            'bristol_scale IS NULL OR (bristol_scale >= 1 AND bristol_scale <= 7)',
            name='ck_samples_bristol'
        ),
        # Prevent double-booking a freezer position (only when all storage fields are set)
        db.UniqueConstraint('freezer_id', 'rack', 'shelf', 'box_number', 'box_row', 'box_column',
                            name='uq_samples_freezer_position'),
        db.Index('ix_samples_status', 'storage_status'),
        db.Index('ix_samples_dispatch', 'dispatch_manifest_id'),
    )

    def __repr__(self):
        return f'<Sample {self.sample_id}>'

    @property
    def is_dispatched(self):
        return self.storage_status == 'dispatched'

    @property
    def freezer_location(self):
        """Human-readable freezer location."""
        parts = [self.freezer_id, self.rack, self.shelf, self.box_number]
        if all(parts):
            pos = f"{self.box_row}{self.box_column}" if self.box_row and self.box_column else ""
            return f"Freezer {self.freezer_id} / Rack {self.rack} / Shelf {self.shelf} / Box {self.box_number} / {pos}"
        return "Not assigned"
