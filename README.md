# 🛡️ FinGuard — Smart Expense Tracker with Fraud Detection

[![Live Demo](https://img.shields.io/badge/Live%20Demo-finguards.up.railway.app-blue?style=for-the-badge)](https://finguards.up.railway.app)
[![Python](https://img.shields.io/badge/Python-3.13-blue?style=for-the-badge&logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-black?style=for-the-badge&logo=flask)](https://flask.palletsprojects.com)
[![MySQL](https://img.shields.io/badge/MySQL-8.0-orange?style=for-the-badge&logo=mysql)](https://mysql.com)

> A full-stack web application for tracking personal expenses with real-time fraud detection and instant email alerts.

---

## 🌐 Live Demo

**[https://finguards.up.railway.app](https://finguards.up.railway.app)**

---

## ✨ Features

### 💰 Expense Management
- Add, edit, and delete transactions
- 6 spending categories: Food, Travel, Bills, Shopping, Entertainment, Others
- Full transaction history with search, filter by category, date range, and status
- Export transactions to Excel-compatible CSV

### 🚨 Fraud Detection (Rule-Based System)
Automatically flags suspicious transactions based on 5 rules:
| Rule | Description |
|------|-------------|
| Category threshold | Each category has a safe spending limit (e.g. Food > ₹1,500) |
| Personal average | Flags if amount is 3x above your own average for that category |
| High-value transaction | Warns for transactions above ₹10,000, alerts above ₹15,000 |
| Rapid spending | Detects repeated spending in the same category within a short time |
| Round number anomaly | Flags suspiciously round large amounts as potential fake entries |

### 📧 Email Notifications (via SendGrid)
- **Welcome email** on account creation
- **Instant fraud alert** when a suspicious transaction is detected
- **Password reset** via secure token link (expires in 1 hour)

### 📊 Analytics Dashboard
- Monthly spending trend (line chart — last 6 months)
- Category-wise bar chart
- Fraud vs Safe transaction ratio (doughnut chart)
- Top 5 highest transactions
- Month-over-month spending comparison

### 👤 User Management
- Secure signup/login with **bcrypt password hashing**
- Session-based authentication with `@login_required` decorator
- Profile management (update username, email, change password)
- Monthly budget with progress bar (green → orange → red)
- Forgot password / reset password flow

### 🎨 UI/UX
- Light/Dark mode toggle (persists via localStorage)
- Glassmorphism login/signup pages with animated background
- Fully mobile responsive
- Doughnut chart for spending by category

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | HTML, CSS, Jinja2, Chart.js |
| Backend | Python, Flask |
| Database | MySQL |
| Authentication | bcrypt, Flask sessions |
| Email | SendGrid API |
| Deployment | Railway |
| Version Control | GitHub |

---

## 📁 Project Structure

```
EXPENSE_TRACKER/
├── app.py                  # All backend routes and logic
├── requirements.txt        # Python dependencies
├── Procfile               # Railway deployment config
├── static/
│   └── style.css          # All styling + dark mode
└── templates/
    ├── index.html         # Dashboard
    ├── analytics.html     # Analytics page
    ├── login.html         # Login
    ├── signup.html        # Signup
    ├── edit.html          # Edit transaction
    ├── fraud.html         # Fraud history
    ├── profile.html       # User profile
    ├── forgot.html        # Forgot password
    └── reset.html         # Reset password
```

---

## 🚀 Local Setup

### Prerequisites
- Python 3.10+
- MySQL 8.0
- Git

### Steps

1. **Clone the repository**
```bash
git clone https://github.com/Eshwarmp/finguard.git
cd finguard
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set up MySQL database**
```sql
CREATE DATABASE expense_tracker;
USE expense_tracker;
-- Run setup.sql
```

4. **Create `.env` file**
```env
SECRET_KEY=your_secret_key
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=expense_tracker
DB_PORT=3306
MAIL_USER=your_gmail@gmail.com
SENDGRID_API_KEY=your_sendgrid_key
```

5. **Run the app**
```bash
# Windows
run.bat

# Mac/Linux
python app.py
```

6. **Open in browser**
```
http://localhost:5000
```

---

## 🔐 Security Features
- Passwords hashed with **bcrypt** (never stored in plain text)
- Environment variables for all secrets (never hardcoded)
- `@login_required` decorator protects all authenticated routes
- Delete/edit operations verify `user_id` to prevent unauthorized access
- Password reset tokens expire after 1 hour

---

## 📸 Screenshots

> *(Add screenshots here after taking them)*

---

## 👨‍💻 Author

**Eshwar M P**
- GitHub: [@Eshwarmp](https://github.com/Eshwarmp)
- Project: [FinGuard](https://finguards.up.railway.app)

---

## 📄 License

This project is open source and available under the [MIT License](LICENSE).