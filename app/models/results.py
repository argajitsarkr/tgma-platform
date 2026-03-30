from app.extensions import db


class HormoneResult(db.Model):
    __tablename__ = 'hormone_results'

    id = db.Column(db.Integer, primary_key=True)
    tracking_id = db.Column(db.String(20), db.ForeignKey('participants.tracking_id',
                            onupdate='CASCADE', ondelete='RESTRICT'), nullable=False, index=True)

    # Lab info
    lab_name = db.Column(db.String(200), nullable=True)
    lab_report_id = db.Column(db.String(100), nullable=True)
    collection_date = db.Column(db.Date, nullable=True)
    report_date = db.Column(db.Date, nullable=True)

    # Glucose & Insulin
    fasting_glucose_mg_dl = db.Column(db.Numeric(6, 2), nullable=True)
    insulin_uiu_ml = db.Column(db.Numeric(8, 2), nullable=True)

    # Cortisol
    cortisol_serum_ug_dl = db.Column(db.Numeric(6, 2), nullable=True)
    cortisol_saliva_awakening = db.Column(db.Numeric(6, 3), nullable=True)
    cortisol_saliva_30min = db.Column(db.Numeric(6, 3), nullable=True)
    cortisol_saliva_4pm = db.Column(db.Numeric(6, 3), nullable=True)
    cortisol_saliva_bedtime = db.Column(db.Numeric(6, 3), nullable=True)

    # Growth factor
    igf1_ng_ml = db.Column(db.Numeric(8, 2), nullable=True)

    # Lipid panel
    total_cholesterol_mg_dl = db.Column(db.Numeric(6, 2), nullable=True)
    hdl_mg_dl = db.Column(db.Numeric(6, 2), nullable=True)
    ldl_mg_dl = db.Column(db.Numeric(6, 2), nullable=True)
    triglycerides_mg_dl = db.Column(db.Numeric(7, 2), nullable=True)

    # Import tracking
    import_batch_id = db.Column(db.String(50), nullable=True)
    import_date = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    @property
    def homa_ir(self):
        """HOMA-IR = (fasting_glucose * insulin) / 405"""
        if self.fasting_glucose_mg_dl and self.insulin_uiu_ml:
            return round(float(self.fasting_glucose_mg_dl) * float(self.insulin_uiu_ml) / 405, 2)
        return None

    @property
    def tg_hdl_ratio(self):
        """Triglyceride / HDL ratio"""
        if self.triglycerides_mg_dl and self.hdl_mg_dl and float(self.hdl_mg_dl) > 0:
            return round(float(self.triglycerides_mg_dl) / float(self.hdl_mg_dl), 2)
        return None


class SequencingResult(db.Model):
    __tablename__ = 'sequencing_results'

    id = db.Column(db.Integer, primary_key=True)
    tracking_id = db.Column(db.String(20), db.ForeignKey('participants.tracking_id',
                            onupdate='CASCADE', ondelete='RESTRICT'), nullable=False, index=True)

    # Vendor info
    vendor = db.Column(db.String(200), default='Nucleome Informatics')
    sequencing_batch_id = db.Column(db.String(50), nullable=True)

    # Read stats
    total_reads = db.Column(db.BigInteger, nullable=True)
    reads_post_qc = db.Column(db.BigInteger, nullable=True)
    host_removal_pct = db.Column(db.Numeric(5, 2), nullable=True)

    # Assembly
    assembly_contigs = db.Column(db.Integer, nullable=True)
    assembly_n50 = db.Column(db.Integer, nullable=True)

    # Profile paths (filesystem)
    taxonomy_profile_path = db.Column(db.String(500), nullable=True)  # Vendor LCA-based
    metaphlan4_profile_path = db.Column(db.String(500), nullable=True)  # In-house MetaPhlAn4
    functional_profile_path = db.Column(db.String(500), nullable=True)

    # MAGs
    mag_count = db.Column(db.Integer, nullable=True)
    hq_mag_count = db.Column(db.Integer, nullable=True)  # >90% completeness, <5% contamination
    mq_mag_count = db.Column(db.Integer, nullable=True)  # >50% completeness, <10% contamination

    # Status
    data_received_date = db.Column(db.Date, nullable=True)
    qc_status = db.Column(db.String(20), default='pending')  # pending, passed, failed, resequencing

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    __table_args__ = (
        db.CheckConstraint(
            "qc_status IN ('pending', 'passed', 'failed', 'resequencing')",
            name='ck_sequencing_qc_status'
        ),
    )


class MetabolicRisk(db.Model):
    __tablename__ = 'metabolic_risk'

    id = db.Column(db.Integer, primary_key=True)
    tracking_id = db.Column(db.String(20), db.ForeignKey('participants.tracking_id',
                            onupdate='CASCADE', ondelete='RESTRICT'), nullable=False, unique=True)

    risk_score_continuous = db.Column(db.Numeric(5, 4), nullable=True)  # 0–1 probability
    risk_category = db.Column(db.String(20), nullable=True)  # low, moderate, high
    model_version = db.Column(db.String(50), nullable=True)
    prediction_date = db.Column(db.Date, nullable=True)

    # JSON: which criteria met (HOMA-IR >= 2.5, TG/HDL >= 3.0, waist >90th, HDL <10th)
    at_risk_criteria_met = db.Column(db.JSON, nullable=True)
    selected_for_adipocyte_validation = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    __table_args__ = (
        db.CheckConstraint(
            "risk_category IS NULL OR risk_category IN ('low', 'moderate', 'high')",
            name='ck_metabolic_risk_category'
        ),
    )
