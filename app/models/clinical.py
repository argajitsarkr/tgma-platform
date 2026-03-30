from app.extensions import db


class HealthScreening(db.Model):
    __tablename__ = 'health_screening'

    id = db.Column(db.Integer, primary_key=True)
    tracking_id = db.Column(db.String(20), db.ForeignKey('participants.tracking_id',
                            onupdate='CASCADE', ondelete='RESTRICT'), nullable=False, unique=True)

    # Eligibility criteria
    chronic_illness = db.Column(db.Boolean, default=False)
    antibiotics_3mo = db.Column(db.Boolean, default=False)
    hospital_3mo = db.Column(db.Boolean, default=False)
    genetic_disorder = db.Column(db.Boolean, default=False)
    pregnant = db.Column(db.Boolean, default=False)

    # Medications
    regular_medication = db.Column(db.Boolean, default=False)
    medication_details = db.Column(db.Text, nullable=True)

    # Family history (stores affected members, e.g. "father,mother")
    fam_diabetes = db.Column(db.String(200), nullable=True)
    fam_obesity = db.Column(db.String(200), nullable=True)
    fam_hypertension = db.Column(db.String(200), nullable=True)
    fam_heart = db.Column(db.String(200), nullable=True)
    fam_thyroid = db.Column(db.String(200), nullable=True)
    fam_cholesterol = db.Column(db.String(200), nullable=True)
    fam_pcos = db.Column(db.String(200), nullable=True)

    # Birth / early life
    delivery_mode = db.Column(db.String(20), nullable=True)  # vaginal, cesarean
    preterm = db.Column(db.Boolean, nullable=True)
    breastfed = db.Column(db.Boolean, nullable=True)
    bf_duration = db.Column(db.String(50), nullable=True)  # e.g. "6 months", "2 years"

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())


class Anthropometrics(db.Model):
    __tablename__ = 'anthropometrics'

    id = db.Column(db.Integer, primary_key=True)
    tracking_id = db.Column(db.String(20), db.ForeignKey('participants.tracking_id',
                            onupdate='CASCADE', ondelete='RESTRICT'), nullable=False, unique=True)

    # Measurements
    height_cm = db.Column(db.Numeric(5, 1), nullable=True)
    weight_kg = db.Column(db.Numeric(5, 1), nullable=True)
    waist_cm = db.Column(db.Numeric(5, 1), nullable=True)
    hip_cm = db.Column(db.Numeric(5, 1), nullable=True)
    muac_cm = db.Column(db.Numeric(5, 1), nullable=True)
    body_fat_pct = db.Column(db.Numeric(5, 1), nullable=True)

    # Vitals
    bp_systolic = db.Column(db.Integer, nullable=True)
    bp_diastolic = db.Column(db.Integer, nullable=True)
    heart_rate = db.Column(db.Integer, nullable=True)

    # Clinical
    tanner_stage = db.Column(db.Integer, nullable=True)
    skin_type = db.Column(db.String(50), nullable=True)

    # Metadata
    measurement_date = db.Column(db.Date, nullable=True)
    measured_by = db.Column(db.String(200), nullable=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    __table_args__ = (
        db.CheckConstraint('tanner_stage IS NULL OR (tanner_stage >= 1 AND tanner_stage <= 5)',
                           name='ck_anthropometrics_tanner'),
    )

    @property
    def bmi(self):
        if self.height_cm and self.weight_kg and float(self.height_cm) > 0:
            h_m = float(self.height_cm) / 100
            return round(float(self.weight_kg) / (h_m * h_m), 1)
        return None

    @property
    def waist_hip_ratio(self):
        if self.waist_cm and self.hip_cm and float(self.hip_cm) > 0:
            return round(float(self.waist_cm) / float(self.hip_cm), 3)
        return None


class MenstrualData(db.Model):
    __tablename__ = 'menstrual_data'

    id = db.Column(db.Integer, primary_key=True)
    tracking_id = db.Column(db.String(20), db.ForeignKey('participants.tracking_id',
                            onupdate='CASCADE', ondelete='RESTRICT'), nullable=False, unique=True)

    menstruation_started = db.Column(db.Boolean, nullable=True)
    menarche_age = db.Column(db.Integer, nullable=True)
    cycle_regularity = db.Column(db.String(20), nullable=True)  # regular, irregular, unknown
    lmp_date = db.Column(db.Date, nullable=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
