from app.extensions import db


class LifestyleData(db.Model):
    __tablename__ = 'lifestyle_data'

    id = db.Column(db.Integer, primary_key=True)
    tracking_id = db.Column(db.String(20), db.ForeignKey('participants.tracking_id',
                            onupdate='CASCADE', ondelete='RESTRICT'), nullable=False, unique=True)

    # Physical activity (frequency codes: daily, 3-4x/week, 1-2x/week, rarely, never)
    vigorous_activity = db.Column(db.String(20), nullable=True)
    moderate_activity = db.Column(db.String(20), nullable=True)
    sedentary_weekday = db.Column(db.Numeric(4, 1), nullable=True)  # hours
    sedentary_weekend = db.Column(db.Numeric(4, 1), nullable=True)  # hours
    active_transport = db.Column(db.String(20), nullable=True)

    # FFQ Traditional (12 items) — frequency codes: daily, weekly, monthly, rarely, never
    ffq_rice = db.Column(db.String(20), nullable=True)
    ffq_dal = db.Column(db.String(20), nullable=True)
    ffq_leafy_veg = db.Column(db.String(20), nullable=True)
    ffq_other_veg = db.Column(db.String(20), nullable=True)
    ffq_fruits = db.Column(db.String(20), nullable=True)
    ffq_fish = db.Column(db.String(20), nullable=True)
    ffq_meat = db.Column(db.String(20), nullable=True)
    ffq_milk = db.Column(db.String(20), nullable=True)
    ffq_fermented = db.Column(db.String(20), nullable=True)
    ffq_tubers = db.Column(db.String(20), nullable=True)
    ffq_tea = db.Column(db.String(20), nullable=True)
    ffq_eggs = db.Column(db.String(20), nullable=True)

    # FFQ Processed (10 items)
    ffq_sugary_drinks = db.Column(db.String(20), nullable=True)
    ffq_chips = db.Column(db.String(20), nullable=True)
    ffq_biscuits = db.Column(db.String(20), nullable=True)
    ffq_sweets = db.Column(db.String(20), nullable=True)
    ffq_fried_snacks = db.Column(db.String(20), nullable=True)
    ffq_instant_noodles = db.Column(db.String(20), nullable=True)
    ffq_bakery = db.Column(db.String(20), nullable=True)
    ffq_ice_cream = db.Column(db.String(20), nullable=True)
    ffq_chocolate = db.Column(db.String(20), nullable=True)
    ffq_readymeal = db.Column(db.String(20), nullable=True)

    # Meal patterns
    meals_per_day = db.Column(db.Integer, nullable=True)
    skip_breakfast = db.Column(db.String(20), nullable=True)  # always, sometimes, rarely, never
    meal_location = db.Column(db.String(50), nullable=True)  # home, school, outside
    diet_changed = db.Column(db.Boolean, nullable=True)
    late_night_snack = db.Column(db.String(20), nullable=True)

    # Sleep
    bedtime_school = db.Column(db.String(10), nullable=True)  # e.g. "22:30"
    waketime_school = db.Column(db.String(10), nullable=True)
    sleep_weekend = db.Column(db.Numeric(4, 1), nullable=True)  # hours
    sleep_quality = db.Column(db.String(20), nullable=True)  # good, fair, poor
    screen_bed = db.Column(db.Boolean, nullable=True)
    daily_screen = db.Column(db.Numeric(4, 1), nullable=True)  # hours

    # PSS-4 (Perceived Stress Scale, each 0-4)
    pss_control = db.Column(db.Integer, nullable=True)
    pss_confident = db.Column(db.Integer, nullable=True)
    pss_going_well = db.Column(db.Integer, nullable=True)
    pss_overwhelmed = db.Column(db.Integer, nullable=True)

    # Substance exposure
    passive_smoke = db.Column(db.Boolean, nullable=True)
    personal_substance = db.Column(db.Boolean, nullable=True)
    substance_frequency = db.Column(db.String(20), nullable=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    @property
    def pss4_score(self):
        """Calculate PSS-4 total score (0-16). Items 1,4 are reverse-scored."""
        vals = [self.pss_control, self.pss_confident, self.pss_going_well, self.pss_overwhelmed]
        if any(v is None for v in vals):
            return None
        # Reverse-score items 1 (control) and 2 (confident)
        return (4 - self.pss_control) + (4 - self.pss_confident) + self.pss_going_well + self.pss_overwhelmed


class EnvironmentSES(db.Model):
    __tablename__ = 'environment_ses'

    id = db.Column(db.Integer, primary_key=True)
    tracking_id = db.Column(db.String(20), db.ForeignKey('participants.tracking_id',
                            onupdate='CASCADE', ondelete='RESTRICT'), nullable=False, unique=True)

    # Environment
    water_source = db.Column(db.String(50), nullable=True)
    water_treatment = db.Column(db.String(50), nullable=True)
    cooking_fuel = db.Column(db.String(50), nullable=True)
    toilet_type = db.Column(db.String(50), nullable=True)
    domestic_animals = db.Column(db.Boolean, nullable=True)
    residence_type = db.Column(db.String(50), nullable=True)

    # Parents education & occupation
    father_edu = db.Column(db.String(50), nullable=True)
    mother_edu = db.Column(db.String(50), nullable=True)
    father_occ = db.Column(db.String(100), nullable=True)
    mother_occ = db.Column(db.String(100), nullable=True)

    # Household
    household_income = db.Column(db.String(50), nullable=True)  # bracket
    household_size = db.Column(db.Integer, nullable=True)
    num_siblings = db.Column(db.Integer, nullable=True)
    birth_order = db.Column(db.Integer, nullable=True)

    # Oral health
    brushing_freq = db.Column(db.String(20), nullable=True)
    dentist_visit = db.Column(db.String(50), nullable=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
