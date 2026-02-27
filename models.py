from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

# ---------------- USERS TABLE ----------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)   # admin / player / viewer

    # Player Details
    ff_uid = db.Column(db.String(20))
    player_role = db.Column(db.String(20))   # Rusher / Sniper / Support
    best_kills = db.Column(db.Integer, default=0)
    best_damage = db.Column(db.Integer, default=0)
    # account active? soft-delete support
    active = db.Column(db.Boolean, default=True)

# ---------------- MATCH STATS ----------------
class Stats(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    player_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    date = db.Column(db.String(20))
    kills = db.Column(db.Integer)
    booyah = db.Column(db.Integer)
    damage = db.Column(db.Integer)
    survival = db.Column(db.Integer)
    screenshot = db.Column(db.String(200))

# ---------------- ATTENDANCE ----------------
class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    player_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    date = db.Column(db.String(20))
    status = db.Column(db.String(10))  # Present / Absent

# ---------------- ANNOUNCEMENTS ----------------
class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    message = db.Column(db.String(200))
    time = db.Column(db.String(20))
    date = db.Column(db.String(20))