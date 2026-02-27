import os
import uuid
from datetime import datetime, date

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from config import Config
from models import db, User, Stats, Announcement, Attendance
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

# Create tables and default admin if no users exist
with app.app_context():
    db.create_all()
    if User.query.count() == 0:
        admin_user = os.environ.get("ADMIN_USERNAME", "admin")
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
    return redirect(url_for("login"))

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if not username or not password:
            flash("Invalid username or password")
            return render_template("login.html")
        user = User.query.filter_by(username=username).first()

        # CORRECT PASSWORD CHECK
        if user and check_password_hash(user.password, password):
            login_user(user, remember=True)
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password")

    return render_template("login.html")

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
@login_required
def dashboard():

    latest = Announcement.query.order_by(Announcement.id.desc()).first()
    # quick stats for the logged-in player
    user_stats = None
    if current_user.role == 'player':
        recs = Stats.query.filter_by(player_id=current_user.id).all()
        total_kills = sum(r.kills for r in recs)
        total_matches = len(recs)
        user_stats = {'kills': total_kills, 'matches': total_matches}

    return render_template("dashboard.html", user=current_user, note=latest, user_stats=user_stats)

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
    logout_user()
    return redirect(url_for("login"))


# helper for allowed screenshot types
ALLOWED_EXT = {"png","jpg","jpeg","gif"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

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
        booyah = int(request.form.get("booyah", 0))
        damage = int(request.form.get("damage", 0))
        survival = int(request.form.get("survival", 0))

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
            damage=damage,
            survival=survival,
            screenshot=filename
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


# ----------- LEADERBOARD -----------
@app.route("/leaderboard")
@login_required
def leaderboard():

    players = User.query.filter_by(role="player", active=True).all()

    board = []

    for p in players:
        records = Stats.query.filter_by(player_id=p.id).all()

        total_kills = sum(r.kills for r in records)
        total_booyah = sum(r.booyah for r in records)
        total_damage = sum(r.damage for r in records)
        total_survival = sum(r.survival for r in records)

        score = (total_kills*2) + (total_booyah*10) + (total_damage/100) + (total_survival*0.5)

        board.append({
            "name": p.username,
            "kills": total_kills,
            "booyah": total_booyah,
            "damage": total_damage,
            "survival": total_survival,
            "score": round(score,2)
        })

    # sort by score descending
    board = sorted(board, key=lambda x: x["score"], reverse=True)

    return render_template("leaderboard.html", board=board)


# ----------- ANALYTICS REPORT API -----------
@app.route("/api/report")
@login_required
def report_data():
    # optional date range filtering via query params (YYYY-MM-DD)
    start = request.args.get('start')
    end = request.args.get('end')

    players = User.query.filter_by(role="player", active=True).all()
    report = []

    for p in players:
        records = Stats.query.filter_by(player_id=p.id).all()
        if start:
            records = [r for r in records if r.date >= start]
        if end:
            records = [r for r in records if r.date <= end]

        matches = len(records)
        total_kills = sum(r.kills for r in records)
        total_damage = sum(r.damage for r in records)
        total_booyah = sum(r.booyah for r in records)

        if matches > 0:
            avg_kills = total_kills / matches
            winrate = (total_booyah / matches) * 100
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
    import csv
    from io import StringIO
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["name","matches","kills","damage","avg_kills","winrate"])
    for p in players:
        records = Stats.query.filter_by(player_id=p.id).all()
        matches = len(records)
        total_kills = sum(r.kills for r in records)
        total_damage = sum(r.damage for r in records)
        total_booyah = sum(r.booyah for r in records)
        avg_kills = total_kills / matches if matches>0 else 0
        winrate = (total_booyah / matches) * 100 if matches>0 else 0
        writer.writerow([p.username, matches, total_kills, total_damage, round(avg_kills,2), round(winrate,2)])
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
        data.append({
            "date": r.date,
            "kills": r.kills,
            "booyah": r.booyah,
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
    total_booyah = sum(r.booyah for r in records)
    total_damage = sum(r.damage for r in records)

    winrate = (total_booyah/matches)*100 if matches>0 else 0

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
            "player": player.username if player else "Unknown",
            "date": r.date,
            "kills": r.kills,
            "screenshot": r.screenshot
        })

    return render_template("proofs.html", proofs=proof_list)


# ----------- ANNOUNCEMENT ADD -----------
@app.route("/announcement", methods=["GET","POST"])
@login_required
def announcement():

    if current_user.role != "admin":
        return "Access Denied"

    if request.method == "POST":
        message = request.form.get("message")
        ann_date = request.form.get("date")
        ann_time = request.form.get("time")

        new_note = Announcement(
            message=message,
            date=ann_date,
            time=ann_time
        )

        db.session.add(new_note)
        db.session.commit()

        flash("Announcement Posted!")
        return redirect(url_for("announcement"))

    return render_template("announcement.html")




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


# ----------- CHANGE PASSWORD -----------
@app.route("/change_password", methods=["GET","POST"])
@login_required
def change_password():

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