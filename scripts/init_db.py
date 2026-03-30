#!/usr/bin/env python3
"""Initialize the TGMA database with schema and seed data.

Usage:
    python scripts/init_db.py                # Create tables + seed users only
    python scripts/init_db.py --synthetic    # Also generate ~50 synthetic participants
"""

import sys
import os
import random
from datetime import date, datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import db
from app.models import (User, Participant, HealthScreening, Anthropometrics, MenstrualData,
                         LifestyleData, EnvironmentSES, Sample, HormoneResult, IdAllocation)
from app.utils.helpers import generate_tracking_id, generate_sample_id


def create_seed_users():
    """Create the 4 default user accounts."""
    users = [
        {'username': 'pi_sb', 'full_name': 'Prof. Surajit Bhattacharjee', 'role': 'pi', 'password': 'changeme_pi_2026'},
        {'username': 'copi_ssd', 'full_name': 'Dr. Shib Sekhar Datta', 'role': 'co_pi', 'password': 'changeme_copi_2026'},
        {'username': 'bioinfo_as', 'full_name': 'Argajit Sarkar', 'role': 'bioinformatician', 'password': 'changeme_bioinfo_2026'},
        {'username': 'field_sup', 'full_name': 'Field Supervisor', 'role': 'field_supervisor', 'password': 'changeme_field_2026'},
    ]

    for u in users:
        existing = User.query.filter_by(username=u['username']).first()
        if existing:
            print(f"  User '{u['username']}' already exists, skipping.")
            continue
        user = User(username=u['username'], full_name=u['full_name'], role=u['role'])
        user.set_password(u['password'])
        db.session.add(user)
        print(f"  Created user: {u['username']} ({u['role']})")

    db.session.commit()


def generate_synthetic_data(count=50):
    """Generate synthetic participants with related data for dashboard testing."""
    first_names_m = ['Abhijit', 'Biplab', 'Chinmoy', 'Debajit', 'Gaurav', 'Hriday',
                     'Jayanta', 'Kamal', 'Manas', 'Nikhil', 'Pranab', 'Rajib',
                     'Sanjay', 'Tapan', 'Ujjal']
    first_names_f = ['Ananya', 'Barnali', 'Chumki', 'Deepa', 'Gargi', 'Haimanti',
                     'Jayashri', 'Kaberi', 'Madhuri', 'Nibedita', 'Priya', 'Ranjita',
                     'Sarmila', 'Tanushri', 'Uma']
    last_names = ['Das', 'Deb', 'Sarkar', 'Paul', 'Roy', 'Saha', 'Chakraborty',
                  'Nath', 'Debnath', 'Bhowmik', 'Majumder', 'Sen', 'Barman', 'Reang', 'Debbarma']

    villages = {
        'WT': ['Agartala', 'Jirania', 'Mohanpur', 'Bishalgarh', 'Melaghar'],
        'ST': ['Belonia', 'Sabroom', 'Santirbazar', 'Rajnagar', 'Hrishyamukh'],
        'DL': ['Ambassa', 'Kamalpur', 'Gandacherra', 'Longtharai', 'Manu'],
    }

    districts = ['WT', 'ST', 'DL']
    district_weights = [0.45, 0.25, 0.3]  # roughly proportional to targets
    genders = ['M', 'F']
    lifestyles = ['AT', 'AP', 'SDT', 'SP']

    seq_counters = {f'{d}-{g}': 0 for d in districts for g in genders}

    participants_created = 0
    used_positions = set()  # Track freezer positions to avoid duplicates
    for i in range(count):
        district = random.choices(districts, weights=district_weights)[0]
        gender = random.choice(genders)
        key = f'{district}-{gender}'
        seq_counters[key] += 1
        seq = seq_counters[key]

        tracking_id = generate_tracking_id(district, gender, seq)
        age = random.randint(12, 18)
        dob = date.today() - timedelta(days=age * 365 + random.randint(0, 364))

        if gender == 'M':
            name = f"{random.choice(first_names_m)} {random.choice(last_names)}"
        else:
            name = f"{random.choice(first_names_f)} {random.choice(last_names)}"

        # GPS coordinates within Tripura
        lat = round(random.uniform(23.0, 24.3), 7)
        lon = round(random.uniform(91.2, 92.2), 7)

        p = Participant(
            tracking_id=tracking_id,
            full_name=name,
            dob=dob,
            age=age,
            gender=gender,
            district=district,
            village_town=random.choice(villages[district]),
            guardian_phone=f'9{random.randint(100000000, 999999999)}',
            school_class=f'Class {random.randint(7, 12)}',
            religion=random.choice(['Hindu', 'Christian', 'Muslim', 'Buddhist']),
            community_tribe=random.choice(['Bengali', 'Tripuri', 'Reang', 'Jamatia', 'Chakma']),
            mother_tongue=random.choice(['Bengali', 'Kokborok', 'Hindi']),
            lifestyle_group_assigned=random.choice(lifestyles),
            enrollment_date=date.today() - timedelta(days=random.randint(1, 90)),
            enrollment_status='enrolled',
            field_worker_name=f'FW-{random.randint(1, 5)}',
            gps_latitude=lat,
            gps_longitude=lon,
            consent_parent=True,
            assent_participant=True,
        )
        db.session.add(p)

        # Health screening
        hs = HealthScreening(
            tracking_id=tracking_id,
            chronic_illness=False,
            antibiotics_3mo=random.choice([True, False, False, False]),
            hospital_3mo=False,
            delivery_mode=random.choice(['vaginal', 'cesarean']),
            breastfed=random.choice([True, True, True, False]),
            bf_duration=random.choice(['6 months', '1 year', '2 years']),
        )
        db.session.add(hs)

        # Anthropometrics
        if gender == 'M':
            height = round(random.gauss(158, 10), 1)
            weight = round(random.gauss(48, 8), 1)
        else:
            height = round(random.gauss(153, 8), 1)
            weight = round(random.gauss(44, 7), 1)

        waist = round(random.gauss(68, 6), 1)
        hip = round(random.gauss(80, 5), 1)

        anthro = Anthropometrics(
            tracking_id=tracking_id,
            height_cm=max(height, 120),
            weight_kg=max(weight, 25),
            waist_cm=max(waist, 45),
            hip_cm=max(hip, 55),
            bp_systolic=random.randint(95, 130),
            bp_diastolic=random.randint(55, 85),
            heart_rate=random.randint(60, 100),
            tanner_stage=random.randint(2, 5),
            measurement_date=p.enrollment_date,
            measured_by='Dr. Field Team',
        )
        db.session.add(anthro)

        # Menstrual data (girls only)
        if gender == 'F' and age >= 13:
            md = MenstrualData(
                tracking_id=tracking_id,
                menstruation_started=True,
                menarche_age=random.randint(11, 14),
                cycle_regularity=random.choice(['regular', 'irregular']),
            )
            db.session.add(md)

        # Lifestyle data
        ld = LifestyleData(
            tracking_id=tracking_id,
            vigorous_activity=random.choice(['daily', '3-4x/week', '1-2x/week', 'rarely', 'never']),
            moderate_activity=random.choice(['daily', '3-4x/week', '1-2x/week', 'rarely']),
            sedentary_weekday=round(random.uniform(2, 8), 1),
            sedentary_weekend=round(random.uniform(3, 10), 1),
            meals_per_day=random.choice([2, 3, 3, 3, 4]),
            sleep_quality=random.choice(['good', 'fair', 'poor']),
            daily_screen=round(random.uniform(1, 6), 1),
            pss_control=random.randint(0, 4),
            pss_confident=random.randint(0, 4),
            pss_going_well=random.randint(0, 4),
            pss_overwhelmed=random.randint(0, 4),
            passive_smoke=random.choice([True, False, False]),
        )
        db.session.add(ld)

        # Environment/SES
        es = EnvironmentSES(
            tracking_id=tracking_id,
            water_source=random.choice(['tap', 'tubewell', 'well', 'river']),
            cooking_fuel=random.choice(['LPG', 'firewood', 'electric', 'kerosene']),
            toilet_type=random.choice(['flush', 'pit', 'open']),
            household_income=random.choice(['<5000', '5000-10000', '10000-20000', '20000-50000', '>50000']),
            household_size=random.randint(3, 8),
            father_edu=random.choice(['illiterate', 'primary', 'secondary', 'higher_secondary', 'graduate']),
            mother_edu=random.choice(['illiterate', 'primary', 'secondary', 'higher_secondary', 'graduate']),
        )
        db.session.add(es)

        # Samples (varying completeness)
        sample_types = ['stool', 'blood', 'saliva_1', 'saliva_2', 'saliva_3', 'saliva_4']
        # 70% have complete sets, 30% have partial
        if random.random() < 0.7:
            types_to_create = sample_types
        else:
            types_to_create = random.sample(sample_types, random.randint(2, 5))

        for st in types_to_create:
            sid = generate_sample_id(tracking_id, st)
            storage_status = 'stored'
            dispatched_to = None
            dispatch_dt = None

            # Some stool samples dispatched
            if st == 'stool' and random.random() < 0.3:
                storage_status = 'dispatched'
                dispatched_to = 'Nucleome Informatics'
                dispatch_dt = date.today() - timedelta(days=random.randint(5, 30))

            # Generate unique freezer position for non-blood samples
            freezer_pos = {}
            if st != 'blood':
                while True:
                    pos = (
                        'F1',
                        str(random.randint(1, 4)),
                        str(random.randint(1, 3)),
                        str(random.randint(1, 10)),
                        chr(65 + random.randint(0, 8)),
                        str(random.randint(1, 9)),
                    )
                    if pos not in used_positions:
                        used_positions.add(pos)
                        freezer_pos = dict(
                            freezer_id=pos[0], rack=pos[1], shelf=pos[2],
                            box_number=pos[3], box_row=pos[4], box_column=pos[5],
                        )
                        break

            sample = Sample(
                sample_id=sid,
                tracking_id=tracking_id,
                sample_type=st,
                collection_status='collected',
                storage_status=storage_status,
                storage_date=p.enrollment_date,
                storage_temp='-80' if st in ('stool', 'serum') else ('-80' if 'saliva' in st else None),
                dispatched_to=dispatched_to,
                dispatch_date=dispatch_dt,
                **freezer_pos,
            )
            db.session.add(sample)

        # Hormone results (~40% of participants)
        if random.random() < 0.4:
            glucose = round(random.gauss(90, 12), 1)
            insulin = round(random.gauss(10, 4), 1)
            hr = HormoneResult(
                tracking_id=tracking_id,
                lab_name='NABL Diagnostics Agartala',
                collection_date=p.enrollment_date,
                report_date=p.enrollment_date + timedelta(days=7),
                fasting_glucose_mg_dl=max(glucose, 50),
                insulin_uiu_ml=max(insulin, 2),
                cortisol_serum_ug_dl=round(random.uniform(5, 20), 1),
                igf1_ng_ml=round(random.gauss(300, 80), 1),
                total_cholesterol_mg_dl=round(random.gauss(170, 25), 1),
                hdl_mg_dl=round(random.gauss(50, 10), 1),
                ldl_mg_dl=round(random.gauss(100, 20), 1),
                triglycerides_mg_dl=round(random.gauss(100, 30), 1),
                import_batch_id='SEED-DATA',
                import_date=datetime.now(),
            )
            db.session.add(hr)

        participants_created += 1

    db.session.commit()
    print(f"  Created {participants_created} synthetic participants with related data.")


def main():
    synthetic = '--synthetic' in sys.argv

    app = create_app()
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("  Tables created.")

        print("Creating seed users...")
        create_seed_users()

        if synthetic:
            print("Generating synthetic data...")
            generate_synthetic_data(50)

        print("\nDone! Default login credentials:")
        print("  PI:              pi_sb / changeme_pi_2026")
        print("  Co-PI:           copi_ssd / changeme_copi_2026")
        print("  Bioinformatician: bioinfo_as / changeme_bioinfo_2026")
        print("  Field Supervisor: field_sup / changeme_field_2026")
        print("\n  *** CHANGE THESE PASSWORDS IMMEDIATELY IN PRODUCTION ***")


if __name__ == '__main__':
    main()
