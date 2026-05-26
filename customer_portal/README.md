
# Customer &amp; Dealer Portal - Quick Start Guide (MySQL ONLY)

## 🔧 **MySQL Configuration ONLY!**
- ✅ Now using **MySQL exclusively** (matches your main FBR app!)
- ✅ Make sure your MySQL server is running on localhost:3306 first!
- ✅ Database: `fbr_invoice_uploader` (same as your main app)

---

## 🚀 **4-Step Setup**

### **IMPORTANT PRE-REQUISITE:**
Make sure your **MySQL server is running** on `localhost:3306` and the database `fbr_invoice_uploader` exists!

---

### Step 1: Install Dependencies (including MySQL)
**Double-click → `install_and_start.bat`**

*(Or run manually:)*
```cmd
cd c:\laragon\www\fbr-invoice-uploader\customer_portal
pip install django==4.2 python-dotenv cryptography pymysql mysqlclient
```

---

### Step 2: Initialize Django (One-time only!)
**Double-click → `initialize_django.bat`**

This sets up Django's own tables (admin, authentication, sessions, etc.)

---

### Step 3: Create Admin Account
```cmd
python manage.py createsuperuser
```
- Username: `admin`
- Password: `admin123`
- Skip email by pressing Enter

---

### Step 4: Start the Server!
**Double-click → `start_server.bat`**

*(Or run manually:)*
```cmd
python manage.py runserver
```

---

## 🌐 **Access the Portal**

| What | URL |
|------|-----|
| **Customer Login** | http://127.0.0.1:8000 |
| **Admin Panel** | http://127.0.0.1:8000/admin |

---

## 🔑 **Activate Customer Accounts**

### Method 1: Using Admin Panel (Easiest)
1. Go to **http://127.0.0.1:8000/admin**
2. Log in with your admin account
3. Click **Customers**
4. Select any customer
5. Set:
   - **Username**: (e.g., `john123`)
   - **Is Portal Active**: ✅ Checked
6. Save
7. Then use the Python shell below to set a password

### Method 2: Set Password via Command Line
```cmd
python manage.py shell
```

Then paste this (replace with actual customer ID):
```python
from django.contrib.auth.hashers import make_password
from portal.models import Customer

c = Customer.objects.get(id=1)  # Change 1 to actual customer ID
c.password_hash = make_password("customerpassword123")
c.save()
print("Password set successfully!")
exit()
```

---

## 📋 **Files in This Folder**

| File | What it does |
|------|---------------|
| `install_and_start.bat` | Installs all dependencies (including MySQL) |
| `initialize_django.bat` | One-time Django initialization |
| `start_server.bat` | Starts the Django server |
| `diagnose.py` | Runs diagnostics if you have issues |
| `manage.py` | Django management script |
| `requirements.txt` | List of all Python packages needed |
| `QUICKSTART.txt` | Super simple 4-step guide (MySQL only) |
| `.env` | MySQL database configuration |

---

## 📱 **What Customers/Dealers Can Do**

✅ Login with username or CNIC  
✅ Dashboard showing all active loans  
✅ Complete bike details (chassis, engine, model)  
✅ Outstanding balance display  
✅ Complete payment history  
✅ Installment schedule with due dates  
✅ Transaction ledger  
✅ Profile page with all information  

---

## 🛡️ **Important Notes**

- **No changes to main FBR application** - completely separate!
- **Uses the same MySQL database** - reads from your existing data
- **MySQL only** - no SQLite, just like your main app!
- **Read-only access recommended** to prevent accidental changes

---

## ❓ **Troubleshooting**

### "Can't connect to MySQL server" error
- Make sure your MySQL server is running on localhost:3306
- Verify the database `fbr_invoice_uploader` exists
- Check that your username/password are correct in `.env`

### "No such file or directory" error
Make sure you're in the correct folder first:
```cmd
cd c:\laragon\www\fbr-invoice-uploader\customer_portal
```

### "Django not found" error
Reinstall dependencies:
```cmd
pip install django==4.2 python-dotenv cryptography pymysql
```

### Migration warnings
Don't worry about these - we've disabled them because our models use existing tables!

---

## 🎉 **That's It!**

Your Customer &amp; Dealer Portal is ready to use! Just follow the 4 easy steps above!
