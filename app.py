from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
import mysql.connector
import os
import bcrypt
import csv
import io
import secrets
import requests
from collections import defaultdict
from functools import wraps
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "finguard_secret_2024")

BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
MAIL_USER     = os.environ.get("MAIL_USER", "")
print(f"Brevo API key loaded: {'YES' if BREVO_API_KEY else 'NO - KEY MISSING'}")

def get_db():
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", "Eshwar02@sql"),
        database=os.environ.get("DB_NAME", "expense_tracker"),
        port=int(os.environ.get("DB_PORT", 3306))
    )

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please login to continue.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

CATEGORY_THRESHOLDS = {
    "Food": 1500, "Travel": 8000, "Bills": 5000,
    "Shopping": 6000, "Entertainment": 3000, "Others": 3000,
}

def detect_fraud(amount, category, all_transactions):
    amount = float(amount)
    flags = []
    category_amounts = defaultdict(list)
    for t in all_transactions:
        category_amounts[t[3]].append(float(t[2]))

    if category in CATEGORY_THRESHOLDS:
        limit = CATEGORY_THRESHOLDS[category]
        if amount > limit:
            flags.append(f"{category} expense Rs.{amount:.0f} exceeds safe limit of Rs.{limit}")

    if category in category_amounts and len(category_amounts[category]) >= 3:
        avg = sum(category_amounts[category]) / len(category_amounts[category])
        if avg > 0 and amount > 3 * avg:
            flags.append(f"Rs.{amount:.0f} is {round(amount/avg,1)}x above your usual {category} average of Rs.{avg:.0f}")

    if amount > 15000:
        flags.append(f"Very large single transaction of Rs.{amount:.0f}")
    elif amount > 10000:
        flags.append(f"High-value transaction of Rs.{amount:.0f} - please verify")

    recent_same_cat = [float(t[2]) for t in all_transactions[-10:] if t[3] == category]
    if len(recent_same_cat) >= 3:
        recent_total = sum(recent_same_cat) + amount
        if recent_total > CATEGORY_THRESHOLDS.get(category, 5000) * 3:
            flags.append(f"Rapid repeated {category} spending - Rs.{recent_total:.0f} in last few transactions")

    if amount >= 1000 and amount % 1000 == 0 and amount > 5000:
        flags.append(f"Round-number transaction Rs.{amount:.0f} - verify this is genuine")

    return len(flags) > 0, "; ".join(flags)

# ── Email helper (Brevo HTTP API) ───────────────────────────
def send_email(to_email, subject, html_content):
    try:
        if not BREVO_API_KEY:
            print("ERROR: Brevo API key not set")
            return False
        print(f"Attempting to send email to {to_email}")
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": BREVO_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "sender": {"name": "FinGuard", "email": MAIL_USER},
                "to": [{"email": to_email}],
                "subject": subject,
                "htmlContent": html_content
            }
        )
        if response.status_code == 201:
            print(f"Email sent successfully to {to_email}")
            return True
        else:
            print(f"Email failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"Email failed with error: {type(e).__name__}: {e}")
        return False

EMAIL_HEADER = (
    '<div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #e0e0e0;border-radius:10px;overflow:hidden;">'
    '<div style="background:#1a1a2e;color:white;padding:24px;text-align:center;">'
    '<div style="font-size:2rem;margin-bottom:8px;">🛡️</div>'
    '<h1 style="margin:0;font-size:1.4rem;letter-spacing:-0.5px;">FinGuard</h1>'
    '<p style="color:#a0aec0;margin:4px 0 0;font-size:0.85rem;">{subtitle}</p>'
    '</div>'
    '<div style="padding:28px;">'
)
EMAIL_FOOTER = (
    '</div>'
    '<div style="background:#f7fafc;padding:14px;text-align:center;font-size:0.75rem;color:#a0aec0;">'
    'This is an automated message from FinGuard. Do not reply to this email.'
    '</div>'
    '</div>'
)

def send_fraud_email(user_email, username, amount, category, description, fraud_reason):
    html = (
        EMAIL_HEADER.format(subtitle="Fraud Detection Alert") +
        f'<p>Hi <strong>{username}</strong>,</p>'
        '<p style="color:#555;">A suspicious transaction was detected on your account:</p>'
        '<div style="background:#fff5f5;border-left:4px solid #e53e3e;border-radius:6px;padding:16px;margin:20px 0;">'
        f'<p><strong>Amount:</strong> Rs.{amount:.2f}</p>'
        f'<p><strong>Category:</strong> {category}</p>'
        f'<p><strong>Description:</strong> {description or "-"}</p>'
        f'<p style="color:#c53030;"><strong>Reason:</strong> {fraud_reason}</p>'
        '</div>'
        '<p>If you made this transaction, you can ignore this alert. If not, please review your account immediately.</p>'
        '<p style="margin-top:20px;">- FinGuard Team</p>' +
        EMAIL_FOOTER
    )
    return send_email(user_email, "🚨 Fraud Alert - Suspicious Transaction on FinGuard", html)

def send_welcome_email(user_email, username):
    html = (
        EMAIL_HEADER.format(subtitle="Welcome aboard!") +
        f'<p>Hi <strong>{username}</strong>, welcome to FinGuard!</p>'
        '<p style="color:#555;">Your account has been created successfully. Here\'s what you can do:</p>'
        '<ul style="color:#555;line-height:2;">'
        '<li>📊 Track your daily expenses by category</li>'
        '<li>🚨 Get instant fraud alerts on suspicious transactions</li>'
        '<li>📅 Set monthly budgets and track your spending</li>'
        '<li>📥 Export your transactions as CSV anytime</li>'
        '</ul>'
        '<div style="text-align:center;margin:28px 0;">'
        '<a href="https://finguards.up.railway.app" style="background:#0f3460;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600;">Go to Dashboard →</a>'
        '</div>'
        '<p style="margin-top:20px;">- FinGuard Team</p>' +
        EMAIL_FOOTER
    )
    return send_email(user_email, "🛡️ Welcome to FinGuard!", html)

def send_reset_email(user_email, username, reset_url):
    html = (
        EMAIL_HEADER.format(subtitle="Password Reset Request") +
        f'<p>Hi <strong>{username}</strong>,</p>'
        '<p style="color:#555;">You requested a password reset. Click the button below to set a new password:</p>'
        '<div style="text-align:center;margin:28px 0;">'
        f'<a href="{reset_url}" style="background:#0f3460;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600;">Reset Password →</a>'
        '</div>'
        '<p style="color:#718096;font-size:0.85rem;">Or copy this link: ' + f'<a href="{reset_url}">{reset_url}</a></p>'
        '<p style="color:#a0aec0;font-size:0.85rem;margin-top:16px;">This link expires in 1 hour. If you did not request this, ignore this email.</p>'
        '<p style="margin-top:20px;">- FinGuard Team</p>' +
        EMAIL_FOOTER
    )
    return send_email(user_email, "🔒 FinGuard - Password Reset Request", html)

# ── Signup ───────────────────────────────────────────────────
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'user_id' in session:
        return redirect(url_for('home'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        email    = request.form['email'].strip()
        password = request.form['password']
        if not username or not email or not password:
            flash("All fields are required.", "error")
            return render_template('signup.html')
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template('signup.html')
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        db = get_db(); cursor = db.cursor()
        try:
            cursor.execute("INSERT INTO users (username, email, password_hash) VALUES (%s,%s,%s)", (username, email, hashed))
            db.commit()
            send_welcome_email(email, username)
            flash("Account created! Please login.", "success")
            return redirect(url_for('login'))
        except mysql.connector.IntegrityError:
            flash("Username or email already exists.", "error")
            return render_template('signup.html')
        finally:
            cursor.close(); db.close()
    return render_template('signup.html')

# ── Login ────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('home'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        db = get_db(); cursor = db.cursor()
        cursor.execute("SELECT id, username, password_hash, last_login FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        if user and bcrypt.checkpw(password.encode('utf-8'), user[2].encode('utf-8')):
            is_first_login = user[3] is None
            cursor.execute("UPDATE users SET last_login = %s WHERE id = %s", (datetime.now(), user[0]))
            db.commit()
            cursor.close(); db.close()
            session['user_id']  = user[0]
            session['username'] = user[1]
            if is_first_login:
                flash(f"Welcome, {user[1]}! Your account is all set.", "success")
            else:
                flash(f"Welcome back, {user[1]}!", "success")
            return redirect(url_for('home'))
        cursor.close(); db.close()
        flash("Invalid username or password.", "error")
    return render_template('login.html')

# ── Logout ───────────────────────────────────────────────────
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for('login'))

# ── Home ─────────────────────────────────────────────────────
@app.route('/')
@login_required
def home():
    db = get_db(); cursor = db.cursor()
    uid = session['user_id']
    now = datetime.now()

    # ── Search & Filter params ───────────────────────────────
    search      = request.args.get('search', '').strip()
    category_f  = request.args.get('category', '')
    date_from   = request.args.get('date_from', '')
    date_to     = request.args.get('date_to', '')
    status_f    = request.args.get('status', '')

    query  = "SELECT * FROM transactions WHERE user_id = %s"
    params = [uid]

    if search:
        query += " AND description LIKE %s"
        params.append(f"%{search}%")
    if category_f:
        query += " AND category = %s"
        params.append(category_f)
    if date_from:
        query += " AND DATE(date) >= %s"
        params.append(date_from)
    if date_to:
        query += " AND DATE(date) <= %s"
        params.append(date_to)
    if status_f == 'fraud':
        query += " AND is_fraud = TRUE"
    elif status_f == 'safe':
        query += " AND is_fraud = FALSE"

    query += " ORDER BY date DESC"
    cursor.execute(query, params)
    data = cursor.fetchall()

    # ── Dashboard stats (always full, not filtered) ──────────
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id = %s", (uid,))
    total = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id = %s AND is_fraud = TRUE", (uid,))
    fraud_total = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE user_id = %s AND is_fraud = TRUE", (uid,))
    fraud_count = cursor.fetchone()[0] or 0
    cursor.execute("SELECT category, SUM(amount) FROM transactions WHERE user_id = %s GROUP BY category", (uid,))
    category_data = cursor.fetchall()
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id=%s AND MONTH(date)=%s AND YEAR(date)=%s", (uid, now.month, now.year))
    monthly_spent = cursor.fetchone()[0] or 0
    cursor.execute("SELECT monthly_budget FROM users WHERE id = %s", (uid,))
    budget_row = cursor.fetchone()
    monthly_budget = budget_row[0] if budget_row and budget_row[0] else None

    cursor.close(); db.close()

    budget_percent = None
    budget_status  = None
    if monthly_budget and monthly_budget > 0:
        budget_percent = round((monthly_spent / monthly_budget) * 100, 1)
        budget_status  = "over" if budget_percent >= 100 else ("warning" if budget_percent >= 80 else "safe")

    return render_template('index.html',
        transactions=data, total=round(total,2),
        fraud_total=round(fraud_total,2), fraud_count=fraud_count,
        category_data=category_data, username=session['username'],
        monthly_spent=round(monthly_spent,2), monthly_budget=monthly_budget,
        budget_percent=budget_percent, budget_status=budget_status,
        search=search, category_f=category_f, date_from=date_from,
        date_to=date_to, status_f=status_f)

# ── Analytics ────────────────────────────────────────────────
@app.route('/analytics')
@login_required
def analytics():
    db = get_db(); cursor = db.cursor()
    uid = session['user_id']
    now = datetime.now()

    # Monthly spending for last 6 months
    cursor.execute("""
        SELECT DATE_FORMAT(date, '%b %Y') as month,
               MONTH(date) as m, YEAR(date) as y,
               SUM(amount) as total
        FROM transactions
        WHERE user_id = %s AND date >= DATE_SUB(NOW(), INTERVAL 6 MONTH)
        GROUP BY YEAR(date), MONTH(date), DATE_FORMAT(date, '%b %Y')
        ORDER BY YEAR(date), MONTH(date)
    """, (uid,))
    monthly_data = cursor.fetchall()

    # Category breakdown
    cursor.execute("""
        SELECT category, SUM(amount) as total, COUNT(*) as count
        FROM transactions WHERE user_id = %s
        GROUP BY category ORDER BY total DESC
    """, (uid,))
    category_breakdown = cursor.fetchall()

    # Top 5 biggest transactions
    cursor.execute("""
        SELECT * FROM transactions WHERE user_id = %s
        ORDER BY amount DESC LIMIT 5
    """, (uid,))
    top_transactions = cursor.fetchall()

    # Fraud vs Safe count
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE user_id=%s AND is_fraud=TRUE", (uid,))
    fraud_count = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE user_id=%s AND is_fraud=FALSE", (uid,))
    safe_count = cursor.fetchone()[0] or 0

    # This month vs last month
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id=%s AND MONTH(date)=%s AND YEAR(date)=%s",
        (uid, now.month, now.year))
    this_month = cursor.fetchone()[0] or 0

    last_month = now.month - 1 if now.month > 1 else 12
    last_year  = now.year if now.month > 1 else now.year - 1
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id=%s AND MONTH(date)=%s AND YEAR(date)=%s",
        (uid, last_month, last_year))
    prev_month = cursor.fetchone()[0] or 0

    cursor.close(); db.close()

    month_change = round(((this_month - prev_month) / prev_month * 100), 1) if prev_month > 0 else 0

    return render_template('analytics.html',
        username=session['username'],
        monthly_data=monthly_data,
        category_breakdown=category_breakdown,
        top_transactions=top_transactions,
        fraud_count=fraud_count, safe_count=safe_count,
        this_month=round(this_month, 2),
        prev_month=round(prev_month, 2),
        month_change=month_change)

# ── Add Expense ──────────────────────────────────────────────
@app.route('/add', methods=['POST'])
@login_required
def add():
    amount      = request.form['amount']
    category    = request.form['category']
    description = request.form['description']
    uid         = session['user_id']
    try:
        amount = float(amount)
        if amount <= 0:
            return redirect(url_for('home'))
    except ValueError:
        return redirect(url_for('home'))
    db = get_db(); cursor = db.cursor()
    cursor.execute("SELECT * FROM transactions WHERE user_id = %s", (uid,))
    existing = cursor.fetchall()
    is_fraud, fraud_reason = detect_fraud(amount, category, existing)
    cursor.execute(
        "INSERT INTO transactions (user_id, amount, category, description, is_fraud, fraud_reason) VALUES (%s,%s,%s,%s,%s,%s)",
        (uid, amount, category, description, is_fraud, fraud_reason)
    )
    db.commit()
    if is_fraud:
        cursor.execute("SELECT email FROM users WHERE id = %s", (uid,))
        user_email = cursor.fetchone()[0]
        sent = send_fraud_email(user_email, session['username'], amount, category, description, fraud_reason)
        if sent:
            flash(f"Fraud alert! Flagged transaction. Email sent to {user_email}.", "warning")
        else:
            flash("Fraud alert! Suspicious transaction flagged.", "warning")
    cursor.close(); db.close()
    return redirect(url_for('home'))

# ── Edit Transaction ─────────────────────────────────────────
@app.route('/edit/<int:tid>', methods=['GET', 'POST'])
@login_required
def edit(tid):
    db = get_db(); cursor = db.cursor()
    uid = session['user_id']
    if request.method == 'POST':
        amount      = request.form['amount']
        category    = request.form['category']
        description = request.form['description']
        try:
            amount = float(amount)
            if amount <= 0:
                flash("Amount must be positive.", "error")
                return redirect(url_for('edit', tid=tid))
        except ValueError:
            flash("Invalid amount.", "error")
            return redirect(url_for('edit', tid=tid))
        cursor.execute("SELECT * FROM transactions WHERE user_id=%s AND id!=%s", (uid, tid))
        is_fraud, fraud_reason = detect_fraud(amount, category, cursor.fetchall())
        cursor.execute(
            "UPDATE transactions SET amount=%s,category=%s,description=%s,is_fraud=%s,fraud_reason=%s WHERE id=%s AND user_id=%s",
            (amount, category, description, is_fraud, fraud_reason, tid, uid)
        )
        db.commit(); cursor.close(); db.close()
        flash("Transaction updated.", "success")
        return redirect(url_for('home'))
    cursor.execute("SELECT * FROM transactions WHERE id=%s AND user_id=%s", (tid, uid))
    t = cursor.fetchone()
    cursor.close(); db.close()
    if not t:
        flash("Transaction not found.", "error")
        return redirect(url_for('home'))
    return render_template('edit.html', t=t)

# ── Delete ───────────────────────────────────────────────────
@app.route('/delete/<int:tid>', methods=['POST'])
@login_required
def delete(tid):
    db = get_db(); cursor = db.cursor()
    cursor.execute("DELETE FROM transactions WHERE id=%s AND user_id=%s", (tid, session['user_id']))
    db.commit(); cursor.close(); db.close()
    return redirect(url_for('home'))

# ── Export CSV ───────────────────────────────────────────────
@app.route('/export')
@login_required
def export_csv():
    db = get_db(); cursor = db.cursor()
    cursor.execute("SELECT * FROM transactions WHERE user_id=%s ORDER BY date DESC", (session['user_id'],))
    transactions = cursor.fetchall()
    cursor.close(); db.close()
    output = io.StringIO()
    writer = csv.writer(output, dialect='excel', quoting=csv.QUOTE_ALL)
    writer.writerow(['ID', 'Amount (Rs.)', 'Category', 'Description', 'Date', 'Fraud Flag', 'Fraud Reason'])
    for t in transactions:
        writer.writerow([t[0], f"{float(t[2]):.2f}", t[3], t[4] or '', str(t[5]), 'Yes' if t[6] else 'No', t[7] or ''])
    output.seek(0)
    return Response(
        '\ufeff' + output.getvalue(),
        mimetype='text/csv; charset=utf-8',
        headers={"Content-Disposition": f"attachment; filename=finguard_{session['username']}.csv"}
    )

# ── Fraud History ─────────────────────────────────────────────
@app.route('/fraud')
@login_required
def fraud_history():
    db = get_db(); cursor = db.cursor()
    uid = session['user_id']
    cursor.execute("SELECT * FROM transactions WHERE user_id=%s AND is_fraud=TRUE ORDER BY date DESC", (uid,))
    flagged = cursor.fetchall()
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id=%s AND is_fraud=TRUE", (uid,))
    fraud_total = cursor.fetchone()[0] or 0
    cursor.close(); db.close()
    return render_template('fraud.html', flagged=flagged, fraud_total=round(fraud_total,2), username=session['username'])

# ── Profile ──────────────────────────────────────────────────
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    db = get_db(); cursor = db.cursor()
    uid = session['user_id']
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_info':
            username = request.form['username'].strip()
            email    = request.form['email'].strip()
            if not username or not email:
                flash("Username and email are required.", "error")
            else:
                try:
                    cursor.execute("UPDATE users SET username=%s, email=%s WHERE id=%s", (username, email, uid))
                    db.commit()
                    session['username'] = username
                    flash("Profile updated successfully.", "success")
                except mysql.connector.IntegrityError:
                    flash("Username or email already taken.", "error")
        elif action == 'change_password':
            current  = request.form['current_password']
            new_pass = request.form['new_password']
            cursor.execute("SELECT password_hash FROM users WHERE id=%s", (uid,))
            stored = cursor.fetchone()[0]
            if not bcrypt.checkpw(current.encode('utf-8'), stored.encode('utf-8')):
                flash("Current password is incorrect.", "error")
            elif len(new_pass) < 6:
                flash("New password must be at least 6 characters.", "error")
            else:
                new_hash = bcrypt.hashpw(new_pass.encode('utf-8'), bcrypt.gensalt())
                cursor.execute("UPDATE users SET password_hash=%s WHERE id=%s", (new_hash, uid))
                db.commit()
                flash("Password changed successfully.", "success")
        elif action == 'set_budget':
            budget = request.form['monthly_budget']
            try:
                budget = float(budget)
                if budget <= 0:
                    raise ValueError
                cursor.execute("UPDATE users SET monthly_budget=%s WHERE id=%s", (budget, uid))
                db.commit()
                flash(f"Monthly budget set to Rs.{budget:.2f}", "success")
            except ValueError:
                flash("Enter a valid budget amount.", "error")
        cursor.close(); db.close()
        return redirect(url_for('profile'))
    cursor.execute("SELECT username, email, monthly_budget, created_at FROM users WHERE id=%s", (uid,))
    user = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE user_id=%s", (uid,))
    total_transactions = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id=%s", (uid,))
    total_spent = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE user_id=%s AND is_fraud=TRUE", (uid,))
    total_fraud = cursor.fetchone()[0]
    cursor.close(); db.close()
    return render_template('profile.html', user=user, username=session['username'],
        total_transactions=total_transactions, total_spent=round(total_spent,2), total_fraud=total_fraud)

# ── Forgot Password ──────────────────────────────────────────
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip()
        db = get_db(); cursor = db.cursor()
        cursor.execute("SELECT id, username FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        if user:
            token  = secrets.token_urlsafe(32)
            expiry = datetime.now() + timedelta(hours=1)
            cursor.execute("UPDATE users SET reset_token=%s, reset_expiry=%s WHERE id=%s", (token, expiry, user[0]))
            db.commit()
            base_url  = os.environ.get('RENDER_EXTERNAL_URL', 'https://finguard-1tp7.onrender.com')
            reset_url = f"{base_url}/reset-password/{token}"
            print(f"Reset URL: {reset_url}")
            result = send_reset_email(email, user[1], reset_url)
            print(f"Email send result: {result}")
        cursor.close(); db.close()
        flash("If that email is registered, a reset link has been sent.", "success")
        return redirect(url_for('login'))
    return render_template('forgot.html')

# ── Reset Password ────────────────────────────────────────────
@app.route('/reset-password/<path:token>', methods=['GET', 'POST'])
def reset_password(token):
    db = get_db(); cursor = db.cursor()
    cursor.execute("SELECT id FROM users WHERE reset_token=%s AND reset_expiry > %s", (token, datetime.now()))
    user = cursor.fetchone()
    if not user:
        cursor.close(); db.close()
        flash("Reset link is invalid or has expired.", "error")
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        password         = request.form['password']
        confirm_password = request.form['confirm_password']
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template('reset.html', token=token)
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template('reset.html', token=token)
        new_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        cursor.execute("UPDATE users SET password_hash=%s, reset_token=NULL, reset_expiry=NULL WHERE id=%s", (new_hash, user[0]))
        db.commit()
        cursor.close(); db.close()
        flash("Password reset successful! Please login.", "success")
        return redirect(url_for('login'))
    cursor.close(); db.close()
    return render_template('reset.html', token=token)

if __name__ == '__main__':
    app.run(debug=True)