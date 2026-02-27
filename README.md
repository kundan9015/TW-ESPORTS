# TW-ESPORTS Flask Application

This repository contains a simple Flask-based web application for managing "TW Esports" players, match statistics, attendance and announcements.

## Features

- User roles: **admin**, **player**, **viewer**
- Authentication with `flask-login`
- Admin panel to add/manage players, post announcements and view attendance
- Players can upload match statistics with screenshot
- Leaderboard and analytics pages with APIs (JSON/CSV) for reports
- Player profile pages and individual graphs
- Attendance tracking and viewing

## Running the project

1. Create a Python virtual environment and install dependencies:

   ```bash
   python -m venv venv
   venv\Scripts\activate    # Windows
   pip install -r requirements.txt
   ```

2. Initialize the database (automatic on first run) and create an admin user if needed.
3. Launch the server:

   ```bash
   python app.py
   ```

4. Open `http://localhost:5000` in a browser. Default admin credentials: `admin`/`admin` (created automatically by helper script).

## Notes & Fixes

- Added basic file type validation on screenshot uploads
- Prevented variable name shadowing of built-in `date` import
- Added missing `requirements.txt` dependencies
- Provided a quick start README

Feel free to extend or refactor this starter application as needed.