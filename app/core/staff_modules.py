"""Fixed list of module codenames a Company Admin can grant to a Staff
account, one per sidebar page key in app/qt_ui/main_window.py. Mirrors the
Django portal's STAFF_MODULES concept (customer_portal/portal/models.py) in
spirit only - this list, and the desktop_staff_permissions table it backs,
are entirely independent of the Django app's permission system.

Admin accounts bypass this list entirely (always full access). Company
Management and Staff Management themselves are deliberately NOT in this
list - they're implicit Admin-only capabilities, never grantable to Staff.
"""

STAFF_MODULES = [
    ("dashboard", "Dashboard"),
    ("reports", "Reports"),
    ("invoice", "Invoice (create & upload to FBR)"),
    ("print_document", "Print Document"),
    ("inventory", "Inventory"),
    ("captured_data", "Captured Data"),
    ("prices", "Prices"),
    ("customers", "Customers"),
    ("dealers", "Dealers"),
    ("advance_booking", "Advance Booking"),
    ("quotation", "Quotation"),
    ("credit_ledger", "Credit Ledger System"),
    ("spare_ledger", "Spare Ledger"),
    ("sms", "SMS Module"),
    ("whatsapp", "WhatsApp Module"),
    ("portal_accounts", "Customer Portal Accounts"),
    ("settings", "Settings"),
]

STAFF_MODULE_CODES = {code for code, _label in STAFF_MODULES}
