
# Phone Number Login System - Complete Guide

## ✅ **System Updated!**

The customer portal now uses **Customer table directly** for authentication, with **phone number as username**.

---

## 🎯 **Key Changes Made:**

1. **Customer table is now the auth table** - no more Django auth.User
2. **Phone number is the login username**
3. **Login form updated** to accept phone number
4. **Templates updated** for phone number login
5. **New management command** to activate customers

---

## 🚀 **How to Activate a Customer for Portal Access**

### **Method 1: Using Admin Panel**

1. Go to: `http://127.0.0.1:8000/admin`
2. Login with admin / admin123
3. Click **Customers**
4. Select any customer
5. Set:
   - **Phone**: (must have a valid phone number)
   - **Password Hash**: (we'll set this via command)
   - **Is Portal Active**: ✅ Checked
6. Save

Then run this command to set password:
```cmd
python manage.py activate_customer &lt;customer_id&gt; &lt;password&gt;
```

Example:
```cmd
python manage.py activate_customer 5 customer123
```

---

### **Method 2: Using Command Line (Easiest!)**

```cmd
cd c:\laragon\www\fbr-invoice-uploader\customer_portal
python manage.py activate_customer &lt;customer_id&gt; &lt;password&gt;
```

**Example:**
```cmd
python manage.py activate_customer 5 mypassword123
```

This will:
- Set password for customer ID 5
- Mark them as portal active
- Show you their phone number for login

---

## 🔑 **Customer Login Credentials**

Customers login with:
- **Phone Number**: Their phone number from the customers table
- **Password**: The password you set via the command

---

## 📋 **Files Modified/Added:**

| File | Change |
|------|---------|
| `portal/forms.py` | Updated LoginForm to use phone_number field |
| `templates/portal/login.html` | Updated login template for phone number |
| `portal/management/commands/activate_customer.py` | NEW - Command to activate customers |
| `PHONE_NUMBER_LOGIN_GUIDE.md` | NEW - This guide |

---

## 🏃 **Quick Test:**

1. Activate a test customer:
   ```cmd
   python manage.py activate_customer 1 test123
   ```

2. Go to `http://127.0.0.1:8000`

3. Login with:
   - Phone number: (customer's phone)
   - Password: test123

---

## 💡 **Important Notes:**

- Customers **must have a phone number** in the `phone` field
- Use the `activate_customer` command to set passwords (never set manually!)
- The system uses the **Customer table directly** - no separate auth tables!

---

**That's it! Your customers can now login with their phone numbers!** 🎉
