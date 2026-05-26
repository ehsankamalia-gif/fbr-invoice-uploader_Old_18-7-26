
# Credit Portal Auto-Activation Integration

## ✅ **Completely Separate - NO Changes to Existing Application!**

This module provides auto-activation for the customer portal **without modifying ANY existing application code!**

---

## 🎯 **What It Does**

### **1. Auto-Activation Service**
- 🕵️ Monitors for **new credit sales** every 10 seconds
- 🎯 Automatically activates portal access when a new credit sale is created
- 🔐 Generates secure random passwords
- 📱 Uses the customer's **phone number as login username**
- 📄 Saves credentials to text files for staff reference
- ⚠️ Skips activation if customer already has portal access

### **2. Credential Manager UI**
- 📊 Qt UI page to view all generated credentials
- 🔄 Auto-refreshes every 10 seconds
- 📂 One-click to open credentials folder
- 🎨 Beautiful UI matching your main app style

---

## 🚀 **Quick Start**

---

### **Option 1: Run the Auto-Activation Service**

Just double-click:
```
start_auto_activation.bat
```

Or run manually:
```cmd
cd c:\laragon\www\fbr-invoice-uploader\credit_portal_integration
python auto_activation_service.py
```

---

### **Option 2: Add to Main Application (Optional)**

To add the Credential Manager page to your main app's sidebar (NO existing code changes):

1. Find your main app's sidebar/menu code
2. Add a new menu item that opens `CreditPortalCredentialViewer` widget

Example code (add to your main window):
```python
from credit_portal_integration.qt_credential_viewer import CreditPortalCredentialViewer

# Add to your sidebar/menu
credential_page = CreditPortalCredentialViewer()
# Add to your stacked widget or tab system
```

---

## 📋 **How It Works**

### **Activation Flow**
1. Staff creates a new credit sale in main app
2. Auto-activation service detects the new sale
3. Service checks if customer already has portal access
   - If YES: Skips activation
   - If NO: Proceeds
4. Service checks if customer has a phone number
   - If NO: Skips (warns in console)
   - If YES: Proceeds
5. Service generates random password
6. Service creates portal auth record
7. Service saves credentials to text file
8. Staff can view/give credentials to customer!

---

## 📁 **Files in This Module**

| File | Purpose |
|------|---------|
| `auto_activation_service.py` | Main auto-activation background service |
| `start_auto_activation.bat` | One-click to start the service |
| `qt_credential_viewer.py` | Qt UI for viewing credentials |
| `generated_credentials/` | Directory where credential files are saved |
| `__init__.py` | Makes it a Python module |
| `README.md` | This guide |

---

## 💡 **Key Features**

✅ **NO CHANGES TO EXISTING CODE** - 100% non-intrusive  
✅ **Auto-detects new credit sales** - no manual activation needed  
✅ **One activation per customer** - avoids duplicates  
✅ **Phone number as login** - simple for customers  
✅ **Secure password generation**  
✅ **Credential files for staff** - easy to share  
✅ **Beautiful Qt UI** - integrates perfectly  
✅ **Auto-refreshing UI** - always up-to-date  

---

## 🛠️ **Troubleshooting**

### **Service not detecting sales?**
- Make sure Django customer portal is set up
- Make sure `customer_portal_auth` table exists
- Check the service console for errors

### **Customer not activated?**
- Check if customer has a phone number in database
- Check if customer already has portal access
- Look in service console for warnings/errors

---

**That's it! Your customer portal activation is now completely automatic!** 🎉
