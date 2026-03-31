from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
import mysql.connector
import os
import bcrypt
import csv
import io
import secrets
from collections import defaultdict
from functools import wraps
from flask_mail import Mail, Message
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "finguard_secret_2024")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "Eshwar02@sql")

app.config['MAIL_SERVER']         = 'smtp.gmail.com'
app.config['MAIL_PORT']           = 587
app.config['MAIL_USE_TLS']        = True
app.config['MAIL_USERNAME']       = os.environ.get("MAIL_USER", "")
app.config['MAIL_PASSWORD']       = os.environ.get("MAIL_PASS", "")
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get("MAIL_USER", "")
mail = Mail(app)

def get_db():
    return mysql.connector.connect(
        host="localhost", user="root",
        password=DB_PASSWORD, database="expense_tracker"
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

def send_fraud_email(user_email, username, amount, category, description, fraud_reason):
    try:
        msg = Message(subject="Fraud Alert - Suspicious Transaction on FinGuard", recipients=[user_email])
        msg.html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #e0e0e0;border-radius:10px;overflow:hidden;">
            <div style="background:#1a1a2e;color:white;padding:24px;text-align:center;">
                <h1 style="margin:0;">FinGuard</h1>
                <p style="color:#a0aec0;margin:4px 0 0;">Fraud Detection Alert</p>
            </div>
            <div style="padding:28px;">
                <p>Hi <strong>{username}</strong>,</p>
                <p style="color:#555;">A suspicious transaction was detected:</p>
                <div style="background:#fff5f5;border-left:4px solid #e53e3e;border-radius:6px;padding:16px;margin:20px 0;">
                    <table style="width:100%;color:#333;">
                        <tr><td style="color:#718096;padding:4px 0;">Amount</td><td><strong>Rs.{amount:.2f}</strong></td></tr>
                        <tr><td style="color:#718096;padding:4px 0;">Category</td><td>{category}</td></tr>
                        <tr><td style="color:#718096;padding:4px 0;">Description</td><td>{description or '-'}</td></tr>
                        <tr><td style="color:#718096;padding:4px 0;vertical-align:top;">Reason</td><td style="color:#c53030;">{fraud_reason}</td></tr>
                    </table>
                </div>
                <p>If you made this transaction, ignore this alert. Otherwise review your account immediately.</p>
                <p>- FinGuard Team</p>
            </div>
        </div>"""
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Email failed: {e}")
        return False

# ── Signup ───────────────────────────────────────────────────
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'user_id' in session: return redirect(url_for('home'))
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
    if 'user_id' in session: return redirect(url_for('home'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        db = get_db(); cursor = db.cursor()
        cursor.execute("SELECT id, username, password_hash FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close(); db.close()
        if user and bcrypt.checkpw(password.encode('utf-8'), user[2].encode('utf-8')):
            session['user_id']  = user[0]
            session['username'] = user[1]
            flash(f"Welcome back, {user[1]}!", "success")
            return redirect(url_for('home'))
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

    cursor.execute("SELECT * FROM transactions WHERE user_id = %s ORDER BY date DESC", (uid,))
    data = cursor.fetchall()

    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id = %s", (uid,))
    total = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id = %s AND is_fraud = TRUE", (uid,))
    fraud_total = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM transactions WHERE user_id = %s AND is_fraud = TRUE", (uid,))
    fraud_count = cursor.fetchone()[0] or 0

    cursor.execute("SELECT category, SUM(amount) FROM transactions WHERE user_id = %s GROUP BY category", (uid,))
    category_data = cursor.fetchall()

    cursor.execute(
        "SELECT SUM(amount) FROM transactions WHERE user_id=%s AND MONTH(date)=%s AND YEAR(date)=%s",
        (uid, now.month, now.year)
    )
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
        budget_percent=budget_percent, budget_status=budget_status
    )

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
        if amount <= 0: return redirect(url_for('home'))
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
            flash("Fraud alert! Suspicious transaction flagged. (Email not configured)", "warning")

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

# ── Export CSV (Excel-compatible) ────────────────────────────
@app.route('/export')
@login_required
def export_csv():
    db = get_db(); cursor = db.cursor()
    cursor.execute("SELECT * FROM transactions WHERE user_id=%s ORDER BY date DESC", (session['user_id'],))
    transactions = cursor.fetchall()
    cursor.close(); db.close()

    output = io.StringIO()
    # ✅ Excel-compatible: use excel dialect, QUOTE_ALL to prevent cell merge issues
    writer = csv.writer(output, dialect='excel', quoting=csv.QUOTE_ALL)
    writer.writerow(['ID', 'Amount (Rs.)', 'Category', 'Description', 'Date', 'Fraud Flag', 'Fraud Reason'])
    for t in transactions:
        writer.writerow([
            t[0],
            f"{float(t[2]):.2f}",
            t[3],
            t[4] if t[4] else '',
            str(t[5]),
            'Yes' if t[6] else 'No',
            t[7] if t[7] else ''
        ])
    output.seek(0)
    # ✅ Add BOM for Excel to correctly detect UTF-8 (fixes Rs. symbol)
    bom = '\ufeff'
    return Response(
        bom + output.getvalue(),
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
    return render_template('fraud.html', flagged=flagged,
        fraud_total=round(fraud_total,2), username=session['username'])

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
                if budget <= 0: raise ValueError
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

    return render_template('profile.html',
        user=user, username=session['username'],
        total_transactions=total_transactions,
        total_spent=round(total_spent,2),
        total_fraud=total_fraud)

# ── Forgot Password ──────────────────────────────────────────
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip()
        db = get_db(); cursor = db.cursor()
        cursor.execute("SELECT id, username FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if user:
            # Generate a secure token valid for 1 hour
            token = secrets.token_urlsafe(32)
            expiry = datetime.now() + timedelta(hours=1)
            cursor.execute(
                "UPDATE users SET reset_token=%s, reset_expiry=%s WHERE id=%s",
                (token, expiry, user[0])
            )
            db.commit()

            # Send reset email
            reset_url = url_for('reset_password', token=token, _external=True)
            try:
                msg = Message(
                    subject="FinGuard — Password Reset Request",
                    recipients=[email]
                )
                msg.html = f"""
                <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #e0e0e0;border-radius:10px;overflow:hidden;">
                    <div style="background:#1a1a2e;color:white;padding:24px;text-align:center;">
                        <h1 style="margin:0;">FinGuard</h1>
                        <p style="color:#a0aec0;margin:4px 0 0;">Password Reset</p>
                    </div>
                    <div style="padding:28px;">
                        <p>Hi <strong>{user[1]}</strong>,</p>
                        <p style="color:#555;">You requested a password reset. Click the button below to set a new password:</p>
                        <div style="text-align:center;margin:28px 0;">
                            <a href="{reset_url}" style="background:#0f3460;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600;">Reset Password</a>
                        </div>
                        <p style="color:#a0aec0;font-size:0.85rem;">This link expires in 1 hour. If you didn't request this, ignore this email.</p>
                        <p>— FinGuard Team</p>
                    </div>
                </div>"""
                mail.send(msg)
            except Exception as e:
                print(f"Reset email failed: {e}")

        cursor.close(); db.close()
        # Always show success (don't reveal if email exists)
        flash("If that email is registered, a reset link has been sent.", "success")
        return redirect(url_for('login'))

    return render_template('forgot.html')

# ── Reset Password ────────────────────────────────────────────
@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    db = get_db(); cursor = db.cursor()
    cursor.execute(
        "SELECT id FROM users WHERE reset_token=%s AND reset_expiry > %s",
        (token, datetime.now())
    )
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
        cursor.execute(
            "UPDATE users SET password_hash=%s, reset_token=NULL, reset_expiry=NULL WHERE id=%s",
            (new_hash, user[0])
        )
        db.commit()
        cursor.close(); db.close()
        flash("Password reset successful! Please login.", "success")
        return redirect(url_for('login'))

    cursor.close(); db.close()
    return render_template('reset.html', token=token)

if __name__ == '__main__':
    app.run(debug=True)