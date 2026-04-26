from app.extensions import db
from app.utils.helpers import DISTRICT_CODES


class Participant(db.Model):
    __tablename__ = 'participants'

    # Primary key — the universal join key
    tracking_id = db.Column(db.String(20), primary_key=True)

    # Demographics
    full_name = db.Column(db.String(200), nullable=False)
    dob = db.Column(db.Date, nullable=True)
    age = db.Column(db.Integer, nullable=True)
    gender = db.Column(db.String(1), nullable=False)  # M or F
    district = db.Column(db.String(2), nullable=False)  # WT, ST, DL, NT, GT, UK
    village_town = db.Column(db.String(200), nullable=True)
    guardian_phone = db.Column(db.String(15), nullable=True)

    # Education & background
    school_class = db.Column(db.String(20), nullable=True)
    religion = db.Column(db.String(50), nullable=True)
    community_tribe = db.Column(db.String(100), nullable=True)
    mother_tongue = db.Column(db.String(50), nullable=True)

    # Lifestyle classification
    lifestyle_group_assigned = db.Column(db.String(5), nullable=True)  # AT, AP, SDT, SP
    lifestyle_group_final = db.Column(db.String(5), nullable=True)

    # Enrollment
    enrollment_date = db.Column(db.Date, nullable=True)
    enrollment_status = db.Column(db.String(20), default='enrolled', nullable=False)

    # Field worker
    field_worker_id = db.Column(db.String(50), nullable=True)
    field_worker_name = db.Column(db.String(200), nullable=True)

    # GPS
    gps_latitude = db.Column(db.Numeric(10, 7), nullable=True)
    gps_longitude = db.Column(db.Numeric(10, 7), nullable=True)

    # Photo
    photo_path = db.Column(db.String(500), nullable=True)

    # Consent
    consent_parent = db.Column(db.Boolean, default=False)
    assent_participant = db.Column(db.Boolean, default=False)
    photo_consent = db.Column(db.Boolean, default=False)

    # KoboToolbox link
    kobo_submission_id = db.Column(db.String(100), nullable=True, unique=True)

    # Notes
    notes = db.Column(db.Text, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    # Constraints
    __table_args__ = (
        db.CheckConstraint("gender IN ('M', 'F')", name='ck_participants_gender'),
        db.CheckConstraint(
            "district IN ('WT', 'ST', 'DL', 'NT', 'GT', 'UK')",
            name='ck_participants_district'
        ),
        db.CheckConstraint(
            "enrollment_status IN ('enrolled', 'completed', 'withdrawn', 'excluded')",
            name='ck_participants_status'
        ),
        db.CheckConstraint(
            "lifestyle_group_assigned IS NULL OR lifestyle_group_assigned IN ('AT', 'AP', 'SDT', 'SP')",
            name='ck_participants_lifestyle_assigned'
        ),
        db.CheckConstraint(
            "lifestyle_group_final IS NULL OR lifestyle_group_final IN ('AT', 'AP', 'SDT', 'SP')",
            name='ck_participants_lifestyle_final'
        ),
        db.Index('ix_participants_district', 'district'),
        db.Index('ix_participants_status', 'enrollment_status'),
        db.Index('ix_participants_enrollment_date', 'enrollment_date'),
    )

    # Relationships
    health_screening = db.relationship('HealthScreening', backref='participant', uselist=False,
                                       cascade='all, delete-orphan')
    anthropometrics = db.relationship('Anthropometrics', backref='participant', uselist=False,
                                      cascade='all, delete-orphan')
    menstrual_data = db.relationship('MenstrualData', backref='participant', uselist=False,
                                     cascade='all, delete-orphan')
    lifestyle_data = db.relationship('LifestyleData', backref='participant', uselist=False,
                                     cascade='all, delete-orphan')
    environment_ses = db.relationship('EnvironmentSES', backref='participant', uselist=False,
                                      cascade='all, delete-orphan')
    samples = db.relationship('Sample', backref='participant', cascade='all, delete-orphan')
    hormone_results = db.relationship('HormoneResult', backref='participant', cascade='all, delete-orphan')
    sequencing_results = db.relationship('SequencingResult', backref='participant', cascade='all, delete-orphan')
    metabolic_risk = db.relationship('MetabolicRisk', backref='participant', uselist=False,
                                     cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Participant {self.tracking_id}>'

    @property
    def sample_completeness(self):
        """Check if participant has all required sample types."""
        collected_types = {s.sample_type for s in self.samples if s.collection_status == 'collected'}
        required = {'stool', 'blood', 'saliva_1', 'saliva_2', 'saliva_3', 'saliva_4'}
        return required.issubset(collected_types)

    @property
    def display_district(self):
        return DISTRICT_CODES.get(self.district, self.district)
