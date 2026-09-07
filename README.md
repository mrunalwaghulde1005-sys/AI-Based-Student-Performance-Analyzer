# AI-Based Student Performance Analyzer

A beginner-friendly web application built with Python Flask, MySQL, and modern web technologies (HTML, CSS, JS) to analyze and predict student performance using a rule-based AI algorithm.

## Folder Structure
- `app.py`: The main Flask backend containing routing, database connection, and AI logic.
- `database.sql`: The SQL script to initialize the MySQL database and tables.
- `requirements.txt`: List of Python dependencies required to run the project.
- `templates/`: Contains HTML files for the UI (`login.html`, `dashboard.html`, `add_student.html`).
- `static/css/style.css`: Contains all custom CSS, dark mode styling, and animations.
- `static/js/script.js`: Contains JavaScript for dynamic elements and Chart.js integration.

## Step-by-Step Setup Guide

### 1. Database Setup
1. Make sure you have MySQL installed (e.g., via XAMPP, WAMP, or standalone MySQL Server).
2. Open your MySQL client (like phpMyAdmin or MySQL Workbench).
3. Copy the contents of `database.sql` and execute them to create the database (`student_performance_db`) and required tables.
4. Note: The database connection in `app.py` uses the default username `root` with no password. If your MySQL setup has a password, update it in `app.py` (look for `mysql.connector.connect`).

### 2. Python Environment Setup
1. Open your terminal or command prompt in this project folder.
2. (Optional but recommended) Create a virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```
3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### 3. Running the Project
1. Start the Flask server by running:
   ```bash
   python app.py
   ```
2. Open your web browser and navigate to `http://127.0.0.1:5000/`.
3. You can log in using the default admin account:
   - **Username:** admin
   - **Password:** admin123

## AI Logic Explained
The "AI" in this mini-project uses a **Weighted Rule-Based System**. It calculates an overall performance score based on:
- Marks (50% weight)
- Assignments (30% weight)
- Attendance (20% weight)

Based on the calculated score, it predicts the performance category:
- **Excellent**: Score >= 85
- **Good**: Score >= 70
- **Average**: Score >= 50
- **Needs Improvement**: Score < 50
