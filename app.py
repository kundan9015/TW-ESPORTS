import os
import uuid
from datetime import datetime, date

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import text

from config import Config
from models import db, User, Stats, Announcement, Attendance, ActivityLog, Notification
app = Flask(__name__)
app.config.from_object(Config)

# ensure upload folder exists
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR

# database initialization
db.init_app(app)

# Login Manager
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def log_activity(username, user_id, action):
    """Log login, logout, or attendance_mark for activity log."""
    try:
        db.session.add(ActivityLog(username=username, user_id=user_id, action=action))
        db.session.commit()
    except Exception:
        db.session.rollback()


# Create tables and default admin if no users exist
with app.app_context():
    db.create_all()
    # lightweight migrations for Stats / Announcement tables
    try:
        db.session.execute(text("ALTER TABLE stats ADD COLUMN match_type VARCHAR(20)"))
        db.session.commit()
    except Exception:
        db.session.rollback()
    try:
        db.session.execute(text("ALTER TABLE stats ADD COLUMN position INTEGER"))
        db.session.commit()
    except Exception:
        db.session.rollback()
    try:
        db.session.execute(text("ALTER TABLE announcement ADD COLUMN active BOOLEAN DEFAULT 1"))
        db.session.commit()
    except Exception:
        db.session.rollback()
    if User.query.count() == 0:
        admin_user = os.environ.get("ADMIN_USERNAME", "TW_AIMED")
        admin_pass = os.environ.get("ADMIN_PASSWORD", "admin123")
        db.session.add(User(
            username=admin_user,
            password=generate_password_hash(admin_pass),
            role="admin"
        ))
        db.session.commit()

# ---------------- HOME ----------------
@app.route("/")
def home():
    return redirect(url_for("public_team"))

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET","POST"])
def login():

    # already logged in -> go straight to dashboard
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if not username or not password:
            flash("Invalid username or password")
            return render_template("login.html")
        user = User.query.filter_by(username=username).first()

        # CORRECT PASSWORD CHECK
        if user and user.active and check_password_hash(user.password, password):
            login_user(user, remember=True)
            log_activity(user.username, user.id, "login")
            return redirect(url_for("dashboard"))
        else:
            flash("Account deactivated or invalid credentials")

    return render_template("login.html")

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
@login_required
def dashboard():

    latest = Announcement.query.filter_by(active=True).order_by(Announcement.id.desc()).first()
    notifications = Notification.query.order_by(Notification.created_at.desc()).limit(10).all()
    # quick stats for the logged-in player
    user_stats = None
    if current_user.role == 'player':
        recs = Stats.query.filter_by(player_id=current_user.id).all()
        total_kills = sum(r.kills for r in recs)
        total_matches = len(recs)
        user_stats = {'kills': total_kills, 'matches': total_matches}

    return render_template("dashboard.html", user=current_user, note=latest, notifications=notifications, user_stats=user_stats)

# ----------- ADD PLAYER (ADMIN ONLY) -----------
@app.route("/add_player", methods=["GET","POST"])
@login_required
def add_player():

    if current_user.role != "admin":
        return "Access Denied"

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        ff_uid = (request.form.get("ff_uid") or "").strip()
        player_role = (request.form.get("player_role") or "").strip()
        if not username or not password:
            flash("Username and password are required.")
            return redirect(url_for("add_player"))
        # CHECK USER EXISTS
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash("Username already exists! Try another.")
            return redirect(url_for("add_player"))

        hashed_pw = generate_password_hash(password)

        new_player = User(
            username=username,
            password=hashed_pw,
            role="player",
            ff_uid=ff_uid,
            player_role=player_role
        )

        db.session.add(new_player)
        db.session.commit()

        flash("Player Created Successfully!")
        return redirect(url_for("add_player"))

    return render_template("add_player.html")

# ----------- MANAGE PLAYERS (ADMIN) -----------
@app.route("/manage_players")
@login_required
def manage_players():
    if current_user.role != "admin":
        return "Access Denied"
    players = User.query.filter_by(role="player").all()  # include inactive accounts
    return render_template("manage_players.html", players=players)


@app.route("/admin/edit_player/<int:player_id>", methods=["GET", "POST"])
@login_required
def admin_edit_player(player_id):
    if current_user.role != "admin":
        return "Access Denied", 403

    player = db.session.get(User, player_id)
    if not player or player.role not in ("player", "viewer"):
        flash("Player not found.")
        return redirect(url_for("manage_players"))

    allowed_roles = ["Rusher", "Sniper", "Support", "IGL", "Nadder"]

    if request.method == "POST":
        ff_uid = (request.form.get("ff_uid") or "").strip()
        player_role = (request.form.get("player_role") or "").strip()

        # allow blank role, but validate if present
        if player_role and player_role not in allowed_roles:
            flash("Invalid player role selected.")
            return render_template("admin_edit_player.html", player=player, allowed_roles=allowed_roles)

        player.ff_uid = ff_uid
        player.player_role = player_role
        db.session.commit()
        flash(f"Updated {player.username}.")
        return redirect(url_for("manage_players"))

    return render_template("admin_edit_player.html", player=player, allowed_roles=allowed_roles)


@app.route("/delete_player_hard/<int:player_id>", methods=["POST"])
@login_required
def delete_player_hard(player_id):
    """Permanently delete a player and all related data."""
    if current_user.role != "admin":
        return "Access Denied", 403

    player = db.session.get(User, player_id)
    if not player or player.role not in ("player", "viewer"):
        flash("Player not found.")
        return redirect(url_for("manage_players"))

    # delete all stats + screenshots for this player
    stats = Stats.query.filter_by(player_id=player.id).all()
    for stat in stats:
        if stat.screenshot:
            fpath = os.path.join(app.config["UPLOAD_FOLDER"], stat.screenshot)
            if os.path.isfile(fpath):
                try:
                    os.remove(fpath)
                except OSError:
                    pass
        db.session.delete(stat)

    # remove attendance records and activity logs
    Attendance.query.filter_by(player_id=player.id).delete()
    ActivityLog.query.filter_by(user_id=player.id).delete()

    # finally remove the player account itself
    username = player.username
    db.session.delete(player)
    db.session.commit()

    flash(f"Player {username} permanently deleted with all records.")
    return redirect(url_for("manage_players"))

@app.route("/delete_player/<int:player_id>")
@login_required
def delete_player(player_id):
    if current_user.role != "admin":
        return "Access Denied"
    player = db.session.get(User, player_id)
    if player and player.role == "player" and player.active:
        # soft-delete: mark inactive, leave stats
        player.active = False
        db.session.commit()
        flash(f"Player {player.username} deactivated.")
    else:
        flash("Player not found or already inactive.")
    return redirect(url_for("manage_players"))

@app.route("/restore_player/<int:player_id>")
@login_required
def restore_player(player_id):
    if current_user.role != "admin":
        return "Access Denied"
    player = db.session.get(User, player_id)
    if player and player.role == "player" and not player.active:
        player.active = True
        db.session.commit()
        flash(f"Player {player.username} restored.")
    else:
        flash("Player not found or already active.")
    return redirect(url_for("manage_players"))

@app.route("/toggle_role/<int:player_id>")
@login_required
def toggle_role(player_id):
    if current_user.role != "admin":
        return "Access Denied"
    player = db.session.get(User, player_id)
    if player and player.role in ["player", "viewer"]:
        player.role = "viewer" if player.role == "player" else "player"
        db.session.commit()
        flash(f"Player {player.username} role changed to {player.role}.")
    else:
        flash("Player not found or cannot change role.")
    return redirect(url_for("manage_players"))

# ---------------- LOGOUT ----------------
@app.route("/logout")
@login_required
def logout():
    log_activity(current_user.username, current_user.id, "logout")
    logout_user()
    return redirect(url_for("login"))


# helper for allowed screenshot types
ALLOWED_EXT = {"png","jpg","jpeg","gif"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


# position → tournament points mapping
POSITION_POINTS = {
    1: 12,
    2: 9,
    3: 8,
    4: 7,
    5: 6,
    6: 5,
    7: 4,
    8: 3,
    9: 2,
    10: 1,
    11: 0,
    12: 0,
}


def position_to_points(pos):
    try:
        pos_int = int(pos) if pos is not None else 0
    except (TypeError, ValueError):
        pos_int = 0
    # fallback for legacy rows that only have booyah: treat any win as top placement
    return POSITION_POINTS.get(pos_int, 0)

# ----------- ADD STATS -----------
@app.route("/add_stats", methods=["GET","POST"])
@login_required
def add_stats():

    if current_user.role == "viewer":
        return "Access Denied"

    if request.method == "POST":
        date_str = request.form.get("date")
        if not date_str:
            flash("Please select a date.")
            return redirect(url_for("add_stats"))
        try:
            match_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid date format.")
            return redirect(url_for("add_stats"))
        kills = int(request.form.get("kills", 0))
        # placement position 1–12 instead of direct booyah input
        position = int(request.form.get("position", 0))
        if position < 1 or position > 12:
            flash("Position must be between 1 and 12.")
            return redirect(url_for("add_stats"))
        # derive booyah (win) flag from position for legacy analytics
        booyah = 1 if position == 1 else 0
        damage = int(request.form.get("damage", 0))
        survival = int(request.form.get("survival", 0))
        match_type = (request.form.get("match_type") or "").strip()
        allowed_types = {"BR", "CS", "Scrims", "Custom"}
        if match_type and match_type not in allowed_types:
            match_type = None

        # screenshot upload
        file = request.files.get("screenshot")
        if not file or file.filename == "":
            flash("Please select a screenshot file.")
            return redirect(url_for("add_stats"))
        if not allowed_file(file.filename):
            flash("Invalid file type. Allowed: png, jpg, jpeg, gif.")
            return redirect(url_for("add_stats"))
        filename = str(uuid.uuid4()) + "_" + secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        new_record = Stats(
            player_id=current_user.id,
            date=match_date,
            kills=kills,
            booyah=booyah,
            position=position,
            damage=damage,
            survival=survival,
            screenshot=filename,
            match_type=match_type
        )

        db.session.add(new_record)

        # BEST RECORD AUTO UPDATE
        if kills > current_user.best_kills:
            current_user.best_kills = kills
        if damage > current_user.best_damage:
            current_user.best_damage = damage

        db.session.commit()

        flash("Match record uploaded!")

        return redirect(url_for("dashboard"))

    return render_template("add_stats.html")


# ----------- BULK STATS UPLOAD (ADMIN ONLY) -----------
@app.route("/admin/bulk_stats", methods=["GET", "POST"])
@login_required
def bulk_stats():

    if current_user.role != "admin":
        return "Access Denied", 403

    if request.method == "POST":
        date_str = request.form.get("date")
        if not date_str:
            flash("Please select a date.")
            return redirect(url_for("bulk_stats"))
        try:
            match_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid date format.")
            return redirect(url_for("bulk_stats"))

        match_type = (request.form.get("match_type") or "").strip()
        allowed_types = {"BR", "CS", "Scrims", "Custom"}
        if match_type and match_type not in allowed_types:
            match_type = None

        # one screenshot used for all rows
        file = request.files.get("screenshot")
        if not file or file.filename == "":
            flash("Please select a screenshot file.")
            return redirect(url_for("bulk_stats"))
        if not allowed_file(file.filename):
            flash("Invalid file type. Allowed: png, jpg, jpeg, gif.")
            return redirect(url_for("bulk_stats"))
        filename = str(uuid.uuid4()) + "_" + secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        player_ids = request.form.getlist("player_id")
        kills_list = request.form.getlist("kills")
        positions = request.form.getlist("position")
        damages = request.form.getlist("damage")
        survivals = request.form.getlist("survival")

        created_any = False

        for idx, pid in enumerate(player_ids):
            pid = (pid or "").strip()
            if not pid:
                continue
            try:
                player_id = int(pid)
            except ValueError:
                continue

            try:
                kills_val = int(kills_list[idx]) if idx < len(kills_list) else 0
            except (ValueError, TypeError):
                kills_val = 0
            try:
                pos_val = int(positions[idx]) if idx < len(positions) else 0
            except (ValueError, TypeError):
                pos_val = 0
            if pos_val < 1 or pos_val > 12:
                pos_val = 0
            try:
                damage_val = int(damages[idx]) if idx < len(damages) else 0
            except (ValueError, TypeError):
                damage_val = 0
            try:
                survival_val = int(survivals[idx]) if idx < len(survivals) else 0
            except (ValueError, TypeError):
                survival_val = 0

            booyah_val = 1 if pos_val == 1 else 0

            new_record = Stats(
                player_id=player_id,
                date=match_date,
                kills=kills_val,
                booyah=booyah_val,
                position=pos_val or None,
                damage=damage_val,
                survival=survival_val,
                screenshot=filename,
                match_type=match_type,
            )

            db.session.add(new_record)

            # BEST RECORD AUTO UPDATE per player
            player = db.session.get(User, player_id)
            if player:
                if kills_val > (player.best_kills or 0):
                    player.best_kills = kills_val
                if damage_val > (player.best_damage or 0):
                    player.best_damage = damage_val

            created_any = True

        if not created_any:
            # no valid rows, remove saved screenshot to avoid orphan file
            if os.path.isfile(filepath):
                try:
                    os.remove(filepath)
                except OSError:
                    pass
            flash("No valid player rows submitted.")
            return redirect(url_for("bulk_stats"))

        db.session.commit()
        flash("Bulk match records uploaded!")
        return redirect(url_for("bulk_stats"))

    # GET: load players list for dropdowns
    players = User.query.filter_by(role="player", active=True).all()
    players_data = [{"id": p.id, "username": p.username} for p in players]
    return render_template("bulk_stats.html", players=players_data)


# ----------- LEADERBOARD -----------
@app.route("/leaderboard")
@login_required
def leaderboard():

    raw_type = (request.args.get("type") or "").strip().lower()
    type_map = {
        "br": "BR",
        "cs": "CS",
        "scrims": "Scrims",
        "custom": "Custom",
        "all": "overall",
        "overall": "overall",
        "": "overall",
    }
    match_type = type_map.get(raw_type, "overall")

    players = User.query.filter_by(role="player", active=True).all()

    board = []

    for p in players:
        q = Stats.query.filter_by(player_id=p.id)
        if match_type != "overall":
            q = q.filter(Stats.match_type == match_type)
        records = q.all()

        total_kills = sum(r.kills for r in records)
        # legacy rows may not have position; treat booyah>0 as a win
        total_wins = sum(
            1
            for r in records
            if (r.position == 1) or (r.position is None and (r.booyah or 0) > 0)
        )
        total_position_points = sum(
            position_to_points(r.position) if r.position is not None else (12 * (r.booyah or 0))
            for r in records
        )
        total_damage = sum(r.damage for r in records)
        total_survival = sum(r.survival for r in records)

        score = total_kills + total_position_points + (total_damage / 100) + (total_survival * 0.5)

        board.append({
            "name": p.username,
            "kills": total_kills,
            "booyah": total_wins,
            "position_points": total_position_points,
            "damage": total_damage,
            "survival": total_survival,
            "score": round(score, 2)
        })

    # sort by score descending
    board = sorted(board, key=lambda x: x["score"], reverse=True)

    return render_template("leaderboard.html", board=board, match_type=match_type)


# ----------- PUBLIC TEAM ROSTER (NO LOGIN REQUIRED) -----------
@app.route("/team")
def public_team():
    raw_type = (request.args.get("type") or "").strip().lower()
    type_map = {
        "br": "BR",
        "cs": "CS",
        "scrims": "Scrims",
        "custom": "Custom",
        "all": "overall",
        "overall": "overall",
        "": "overall",
    }
    match_type = type_map.get(raw_type, "overall")

    players = User.query.filter_by(role="player", active=True).all()

    board = []
    for p in players:
        q = Stats.query.filter_by(player_id=p.id)
        if match_type != "overall":
            q = q.filter(Stats.match_type == match_type)
        records = q.all()

        total_kills = sum(r.kills for r in records)
        total_wins = sum(
            1
            for r in records
            if (r.position == 1) or (r.position is None and (r.booyah or 0) > 0)
        )
        total_position_points = sum(
            position_to_points(r.position) if r.position is not None else (12 * (r.booyah or 0))
            for r in records
        )
        total_damage = sum(r.damage for r in records)
        total_survival = sum(r.survival for r in records)

        score = total_kills + total_position_points + (total_damage / 100) + (total_survival * 0.5)

        board.append({
            "name": p.username,
            "ff_uid": p.ff_uid,
            "player_role": p.player_role,
            "kills": total_kills,
            "booyah": total_wins,
            "position_points": total_position_points,
            "damage": total_damage,
            "survival": total_survival,
            "score": round(score, 2)
        })

    board = sorted(board, key=lambda x: x["score"], reverse=True)

    return render_template("public_team.html", board=board, match_type=match_type)


# ----------- ANALYTICS REPORT API -----------
@app.route("/api/report")
@login_required
def report_data():
    # optional date range filtering via query params (YYYY-MM-DD)
    start = request.args.get('start')
    end = request.args.get('end')
    match_type = request.args.get('type')

    start_date = None
    end_date = None
    try:
        start_date = datetime.strptime(start, "%Y-%m-%d").date() if start else None
    except ValueError:
        start_date = None
    try:
        end_date = datetime.strptime(end, "%Y-%m-%d").date() if end else None
    except ValueError:
        end_date = None

    players = User.query.filter_by(role="player", active=True).all()
    report = []

    for p in players:
        q = Stats.query.filter_by(player_id=p.id)
        if match_type and match_type.lower() != "all":
            q = q.filter(Stats.match_type == match_type)
        if start_date:
            q = q.filter(Stats.date >= start_date)
        if end_date:
            q = q.filter(Stats.date <= end_date)
        records = q.all()

        matches = len(records)
        total_kills = sum(r.kills for r in records)
        total_damage = sum(r.damage for r in records)
        total_wins = sum(
            1
            for r in records
            if (r.position == 1) or (r.position is None and (r.booyah or 0) > 0)
        )

        if matches > 0:
            avg_kills = total_kills / matches
            winrate = (total_wins / matches) * 100
        else:
            avg_kills = 0
            winrate = 0

        report.append({
            "name": p.username,
            "matches": matches,
            "kills": total_kills,
            "damage": total_damage,
            "avg_kills": round(avg_kills, 2),
            "winrate": round(winrate, 2)
        })

    return jsonify(report)

# CSV export for report
@app.route("/api/report/csv")
@login_required
def report_csv():
    # reuse report_data logic
    players = User.query.filter_by(role="player", active=True).all()
    start = request.args.get('start')
    end = request.args.get('end')
    match_type = request.args.get('type')
    start_date = None
    end_date = None
    try:
        start_date = datetime.strptime(start, "%Y-%m-%d").date() if start else None
    except ValueError:
        start_date = None
    try:
        end_date = datetime.strptime(end, "%Y-%m-%d").date() if end else None
    except ValueError:
        end_date = None
    import csv
    from io import StringIO
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["name","matches","kills","damage","avg_kills","winrate"])
    for p in players:
        q = Stats.query.filter_by(player_id=p.id)
        if match_type and match_type.lower() != "all":
            q = q.filter(Stats.match_type == match_type)
        if start_date:
            q = q.filter(Stats.date >= start_date)
        if end_date:
            q = q.filter(Stats.date <= end_date)
        records = q.all()
        matches = len(records)
        total_kills = sum(r.kills for r in records)
        total_damage = sum(r.damage for r in records)
        total_wins = sum(
            1
            for r in records
            if (r.position == 1) or (r.position is None and (r.booyah or 0) > 0)
        )
        avg_kills = total_kills / matches if matches > 0 else 0
        winrate = (total_wins / matches) * 100 if matches > 0 else 0
        writer.writerow([p.username, matches, total_kills, total_damage, round(avg_kills, 2), round(winrate, 2)])
    output.seek(0)
    return app.response_class(output.getvalue(), mimetype='text/csv', headers={
        'Content-Disposition':'attachment;filename=report.csv'
    })

# ----------- GRAPH PAGE -----------
@app.route("/graphs")
@login_required
def graphs():
    return render_template("graphs.html")


# ----------- PLAYER MATCH HISTORY API -----------
@app.route("/api/my_stats")
@login_required
def my_stats():

    records = Stats.query.filter_by(player_id=current_user.id).order_by(Stats.id.desc()).all()

    data = []
    for r in records:
        # derive booyah from position when available for consistency
        booyah_val = r.booyah
        if r.position is not None:
            booyah_val = 1 if r.position == 1 else 0
        data.append({
            "date": r.date.isoformat() if r.date else None,
            "kills": r.kills,
            "booyah": booyah_val,
            "position": r.position,
            "damage": r.damage,
            "survival": r.survival
        })

    return jsonify(data)


# ----------- PLAYER PROFILE -----------
@app.route("/player/<username>")
@login_required
def player_profile(username):

    player = User.query.filter_by(username=username, role="player").first()

    if not player:
        return "Player not found"

    records = Stats.query.filter_by(player_id=player.id).all()

    matches = len(records)
    total_kills = sum(r.kills for r in records)
    total_damage = sum(r.damage for r in records)
    total_wins = sum(
        1
        for r in records
        if (r.position == 1) or (r.position is None and (r.booyah or 0) > 0)
    )

    winrate = (total_wins / matches) * 100 if matches > 0 else 0

    return render_template(
        "player_profile.html",
        player=player,
        matches=matches,
        kills=total_kills,
        damage=total_damage,
        winrate=round(winrate,2)
    )


# ----------- MATCH PROOF GALLERY (ADMIN ONLY) -----------
@app.route("/proofs")
@login_required
def proofs():
    if current_user.role != "admin":
        return "Access Denied"

    records = Stats.query.order_by(Stats.id.desc()).all()

    proof_list = []
    for r in records:
        player = db.session.get(User, r.player_id)
        proof_list.append({
            "id": r.id,
            "player": player.username if player else "Unknown",
            "date": r.date,
            "kills": r.kills,
            "position": r.position,
            "damage": r.damage,
            "survival": r.survival,
            "screenshot": r.screenshot
        })

    return render_template("proofs.html", proofs=proof_list)


# ----------- DELETE PROOF (ADMIN) - removes stats entry and file -----------
@app.route("/delete_proof/<int:stat_id>", methods=["POST"])
@login_required
def delete_proof(stat_id):
    if current_user.role != "admin":
        return "Access Denied", 403
    stat = db.session.get(Stats, stat_id)
    if not stat:
        flash("Proof not found.")
        return redirect(url_for("proofs"))
    player_id = stat.player_id
    # remove file from disk if no other records share it
    if stat.screenshot:
        other_refs = Stats.query.filter(
            Stats.screenshot == stat.screenshot,
            Stats.id != stat.id
        ).count()
        if other_refs == 0:
            fpath = os.path.join(app.config["UPLOAD_FOLDER"], stat.screenshot)
            if os.path.isfile(fpath):
                try:
                    os.remove(fpath)
                except OSError:
                    pass
    db.session.delete(stat)
    # update user best_kills / best_damage from remaining stats (exclude this stat)
    user = db.session.get(User, player_id)
    if user:
        remaining = Stats.query.filter(Stats.player_id == player_id, Stats.id != stat_id).all()
        user.best_kills = max((r.kills for r in remaining), default=0)
        user.best_damage = max((r.damage for r in remaining), default=0)
    db.session.commit()
    flash("Proof and match record deleted.")
    return redirect(url_for("proofs"))


# ----------- DELETE ONLY SCREENSHOT (ADMIN) -----------
@app.route("/delete_proof_image/<int:stat_id>", methods=["POST"])
@login_required
def delete_proof_image(stat_id):
    if current_user.role != "admin":
        return "Access Denied", 403
    stat = db.session.get(Stats, stat_id)
    if not stat:
        flash("Proof not found.")
        return redirect(url_for("proofs"))
    if stat.screenshot:
        other_refs = Stats.query.filter(
            Stats.screenshot == stat.screenshot,
            Stats.id != stat.id
        ).count()
        if other_refs == 0:
            fpath = os.path.join(app.config["UPLOAD_FOLDER"], stat.screenshot)
            if os.path.isfile(fpath):
                try:
                    os.remove(fpath)
                except OSError:
                    pass
        stat.screenshot = None
        db.session.commit()
        flash("Screenshot deleted, match record kept.")
    return redirect(url_for("proofs"))


# ----------- EDIT PROOF / MATCH RECORD (ADMIN) -----------
@app.route("/edit_proof/<int:stat_id>", methods=["GET", "POST"])
@login_required
def edit_proof(stat_id):
    if current_user.role != "admin":
        return "Access Denied", 403
    stat = db.session.get(Stats, stat_id)
    if not stat:
        flash("Proof not found.")
        return redirect(url_for("proofs"))

    player = db.session.get(User, stat.player_id) if stat.player_id else None

    if request.method == "POST":
        date_str = request.form.get("date") or ""
        try:
            stat.date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid date format.")
            return redirect(url_for("edit_proof", stat_id=stat_id))

        try:
            stat.kills = int(request.form.get("kills", stat.kills or 0))
        except (TypeError, ValueError):
            stat.kills = stat.kills or 0

        try:
            pos_val = int(request.form.get("position") or (stat.position or 0))
        except (TypeError, ValueError):
            pos_val = stat.position or 0
        if pos_val < 1 or pos_val > 12:
            pos_val = 0
        stat.position = pos_val or None
        # keep booyah in sync
        stat.booyah = 1 if pos_val == 1 else 0

        try:
            stat.damage = int(request.form.get("damage", stat.damage or 0))
        except (TypeError, ValueError):
            stat.damage = stat.damage or 0
        try:
            stat.survival = int(request.form.get("survival", stat.survival or 0))
        except (TypeError, ValueError):
            stat.survival = stat.survival or 0

        match_type = (request.form.get("match_type") or "").strip()
        allowed_types = {"BR", "CS", "Scrims", "Custom"}
        if match_type and match_type not in allowed_types:
            match_type = None
        stat.match_type = match_type

        # optional new screenshot
        file = request.files.get("screenshot")
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Invalid file type. Allowed: png, jpg, jpeg, gif.")
                return redirect(url_for("edit_proof", stat_id=stat_id))
            # remove old file if present and not shared
            if stat.screenshot:
                other_refs = Stats.query.filter(
                    Stats.screenshot == stat.screenshot,
                    Stats.id != stat.id
                ).count()
                if other_refs == 0:
                    old_path = os.path.join(app.config["UPLOAD_FOLDER"], stat.screenshot)
                    if os.path.isfile(old_path):
                        try:
                            os.remove(old_path)
                        except OSError:
                            pass
            new_name = str(uuid.uuid4()) + "_" + secure_filename(file.filename)
            new_path = os.path.join(app.config["UPLOAD_FOLDER"], new_name)
            file.save(new_path)
            stat.screenshot = new_name

        # update best stats for player
        if player:
            remaining = Stats.query.filter(Stats.player_id == player.id).all()
            player.best_kills = max((r.kills for r in remaining), default=0)
            player.best_damage = max((r.damage for r in remaining), default=0)

        db.session.commit()
        flash("Match record updated.")
        return redirect(url_for("proofs"))

    return render_template("edit_proof.html", stat=stat, player=player)


# ----------- ANNOUNCEMENT ADD -----------
@app.route("/announcement", methods=["GET","POST"])
@login_required
def announcement():

    if current_user.role != "admin":
        return "Access Denied"

    if request.method == "POST":
        message = (request.form.get("message") or "").strip()
        ann_date = request.form.get("date")
        ann_time = request.form.get("time")

        if not message:
            flash("Message is required.")
            return redirect(url_for("announcement"))

        new_note = Announcement(
            message=message,
            date=ann_date,
            time=ann_time,
            active=True,
        )

        db.session.add(new_note)
        db.session.commit()

        flash("Announcement posted.")
        return redirect(url_for("announcement"))

    all_ann = Announcement.query.order_by(Announcement.id.desc()).all()
    return render_template("announcement.html", announcements=all_ann)


@app.route("/announcement/toggle/<int:ann_id>", methods=["POST"])
@login_required
def announcement_toggle(ann_id):
    if current_user.role != "admin":
        return "Access Denied", 403
    ann = db.session.get(Announcement, ann_id)
    if not ann:
        flash("Announcement not found.")
        return redirect(url_for("announcement"))
    ann.active = not bool(ann.active)
    db.session.commit()
    flash("Announcement visibility updated.")
    return redirect(url_for("announcement"))


@app.route("/announcement/delete/<int:ann_id>", methods=["POST"])
@login_required
def announcement_delete(ann_id):
    if current_user.role != "admin":
        return "Access Denied", 403
    ann = db.session.get(Announcement, ann_id)
    if not ann:
        flash("Announcement not found.")
        return redirect(url_for("announcement"))
    db.session.delete(ann)
    db.session.commit()
    flash("Announcement deleted.")
    return redirect(url_for("announcement"))




# ----------- PLAYER GRAPH API -----------
@app.route("/api/player_graph/<username>")
@login_required
def player_graph(username):

    player = User.query.filter_by(username=username, role="player").first()

    if not player:
        return jsonify({})

    records = Stats.query.filter_by(player_id=player.id).order_by(Stats.id).all()

    dates = [r.date for r in records]
    kills = [r.kills for r in records]

    return jsonify({
        "dates": dates,
        "kills": kills
    })



# ----------- MARK ATTENDANCE -----------
@app.route("/join_practice")
@login_required
def join_practice():
    if current_user.role == "viewer":
        return "Access Denied"

    today = date.today()

    # check already marked or not
    existing = Attendance.query.filter_by(player_id=current_user.id, date=today).first()

    if existing:
        flash("You already joined today!")
    else:
        new_att = Attendance(
            player_id=current_user.id,
            date=today,
            status="Present"
        )
        db.session.add(new_att)
        db.session.commit()
        log_activity(current_user.username, current_user.id, "attendance_mark")
        flash("Attendance Marked Successfully!")

    return redirect(url_for("dashboard"))

# ----------- VIEW ATTENDANCE (ADMIN) -----------
@app.route("/attendance")
@login_required
def view_attendance():

    if current_user.role != "admin":
        return "Access Denied"

    records = Attendance.query.all()

    data = []
    for r in records:
        player = db.session.get(User, r.player_id)
        data.append({
            "name": player.username if player else "Unknown",
            "date": r.date,
            "status": r.status
        })

    return render_template("attendance.html", records=data)


# ----------- ACTIVITY LOG (ADMIN ONLY) -----------
@app.route("/activity_log")
@login_required
def activity_log():
    if current_user.role != "admin":
        flash("Access denied.")
        return redirect(url_for("dashboard"))
    logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(200).all()
    return render_template("activity_log.html", logs=logs)


# ----------- RESET PLAYER PASSWORD (ADMIN) -----------
@app.route("/reset_password/<int:player_id>", methods=["GET", "POST"])
@login_required
def reset_password(player_id):
    if current_user.role != "admin":
        return "Access Denied", 403
    player = db.session.get(User, player_id)
    if not player or player.role not in ("player", "viewer"):
        flash("Player not found.")
        return redirect(url_for("manage_players"))
    if request.method == "POST":
        use_random = request.form.get("use_random") == "1"
        if use_random:
            import secrets
            new_pass = secrets.token_urlsafe(8)
        else:
            new_pass = (request.form.get("new_password") or "").strip()
        if not new_pass:
            flash("Enter a password or use Generate random.")
            return render_template("reset_password.html", player=player)
        player.password = generate_password_hash(new_pass)
        db.session.commit()
        flash(f"Password reset for {player.username}. New password: {new_pass}" if use_random else f"Password reset for {player.username}.")
        return redirect(url_for("manage_players"))
    return render_template("reset_password.html", player=player)


# ----------- NOTIFICATIONS (ADMIN add/delete, show on dashboard) -----------
@app.route("/notification/add", methods=["POST"])
@login_required
def notification_add():
    if current_user.role != "admin":
        return "Access Denied", 403
    msg = (request.form.get("message") or "").strip()
    if not msg:
        flash("Notification message is required.")
        return redirect(url_for("dashboard"))
    db.session.add(Notification(message=msg))
    db.session.commit()
    flash("Notification added.")
    return redirect(url_for("dashboard"))


@app.route("/notification/delete/<int:nid>", methods=["POST"])
@login_required
def notification_delete(nid):
    if current_user.role != "admin":
        return "Access Denied", 403
    n = db.session.get(Notification, nid)
    if n:
        db.session.delete(n)
        db.session.commit()
        flash("Notification deleted.")
    return redirect(url_for("dashboard"))


# ----------- EDIT PROFILE -----------
@app.route("/edit_profile", methods=["GET","POST"])
@login_required
def edit_profile():
    if request.method == "POST":
        ff_uid = request.form.get("ff_uid")
        player_role = request.form.get("player_role")
        current_user.ff_uid = ff_uid
        current_user.player_role = player_role
        db.session.commit()
        flash("Profile updated")
        return redirect(url_for("dashboard"))
    return render_template("edit_profile.html", user=current_user)


# ----------- CHANGE PASSWORD (ADMIN ONLY) -----------
@app.route("/change_password", methods=["GET","POST"])
@login_required
def change_password():
    if current_user.role != "admin":
        flash("Only admin can change password.")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        old_pass = request.form.get("old_password") or ""
        new_pass = request.form.get("new_password") or ""
        if not old_pass or not new_pass:
            flash("Please fill all password fields.")
            return render_template("change_password.html")
        # verify old password
        if check_password_hash(current_user.password, old_pass):

            current_user.password = generate_password_hash(new_pass)
            db.session.commit()
            flash("Password changed successfully!")

            return redirect(url_for("dashboard"))
        else:
            flash("Old password incorrect!")

    return render_template("change_password.html")


if __name__ == "__main__":
    app.run(debug=False)