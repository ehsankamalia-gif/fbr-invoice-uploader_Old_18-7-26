import customtkinter as ctk
from tkinter import messagebox, ttk
import re
import logging
from app.services.customer_service import customer_service
from app.db.models import CustomerType
from app.ui.address_entry import AddressEntry

logger = logging.getLogger(__name__)

class CustomerFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.selected_customer_id = None
        self.prev_selection = set()

        # Header
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, padx=20, pady=20, sticky="ew")
        
        self.header = ctk.CTkLabel(self.header_frame, text="Customer Management", font=ctk.CTkFont(size=24, weight="bold"))
        self.header.pack(side="left")

        # Toggle Form Button
        self.form_visible = True
        self.toggle_btn = ctk.CTkButton(self.header_frame, text="Hide Form", width=100, command=self.toggle_form)
        self.toggle_btn.pack(side="left", padx=20)

        # Search Bar
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", self.on_search)
        self.search_entry = ctk.CTkEntry(self.header_frame, textvariable=self.search_var, placeholder_text="Search Name, CNIC, Phone...", width=250)
        self.search_entry.pack(side="right", padx=10)

        # Delete Selected Button
        self.delete_selected_btn = ctk.CTkButton(
            self.header_frame, 
            text="Delete Selected", 
            fg_color="#d32f2f", 
            hover_color="#b71c1c",
            width=120,
            command=self.delete_selected_customers
        )
        self.delete_selected_btn.pack(side="right", padx=5)

        # Select All Checkbox
        self.select_all_var = ctk.BooleanVar(value=False)
        self.select_all_chk = ctk.CTkCheckBox(
            self.header_frame,
            text="Select All",
            variable=self.select_all_var,
            command=self.toggle_select_all,
            width=80
        )
        self.select_all_chk.pack(side="right", padx=10)

        # Main Content Area (Split into Form and List)
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=1, column=0, padx=20, pady=0, sticky="nsew")
        self.content_frame.grid_columnconfigure(0, weight=1) # Form
        self.content_frame.grid_columnconfigure(1, weight=3) # List
        self.content_frame.grid_rowconfigure(0, weight=1)

        # --- Form Section ---
        self.create_form_section()

        # --- List Section ---
        self.create_list_section()
        
        # Initial Load
        self.load_customers()
        
        # Setup Navigation
        self.setup_keyboard_navigation()

    def toggle_form(self):
        """Toggles the visibility of the form section."""
        if self.form_visible:
            self.form_frame.grid_remove()
            self.content_frame.grid_columnconfigure(0, weight=0) # Collapse column 0
            self.toggle_btn.configure(text="Show Form")
            self.form_visible = False
        else:
            self.form_frame.grid()
            self.content_frame.grid_columnconfigure(0, weight=1) # Restore column 0 weight
            self.toggle_btn.configure(text="Hide Form")
            self.form_visible = True

    def setup_keyboard_navigation(self):
        """Sets up Enter key navigation through form fields."""
        self.nav_sequence = [
            self.cnic_entry,
            self.name_entry,
            self.father_name_entry,
            self.phone_entry,
            self.address_entry,
            self.ntn_entry,
            self.business_name_entry
        ]

        for i, widget in enumerate(self.nav_sequence):
            if i == len(self.nav_sequence) - 1:
                # Last field triggers save
                widget.bind("<Return>", lambda e: self.save_customer())
            else:
                next_widget = self.nav_sequence[i + 1]
                def focus_next(event, target=next_widget):
                    target.focus_set()
                    return "break"
                widget.bind("<Return>", focus_next)

    def validate_alpha(self, var):
        val = var.get()
        new_val = "".join([c for c in val if c.isalpha() or c.isspace()])
        new_val = new_val.upper()
        if val != new_val:
            var.set(new_val)

    def _force_uppercase(self, var):
        val = var.get()
        up = (val or "").upper()
        if val != up:
            var.set(up)

    def validate_cnic(self, *args):
        value = self.cnic_var.get()
        # Auto-format: XXXXX-XXXXXXX-X
        clean_digits = ''.join(filter(str.isdigit, value))[:13]

        if len(clean_digits) <= 5:
            formatted = clean_digits
        elif len(clean_digits) <= 12:
            formatted = clean_digits[:5] + '-' + clean_digits[5:]
        else:
            formatted = clean_digits[:5] + '-' + clean_digits[5:12] + '-' + clean_digits[12:]
            
        if value != formatted:
            self.cnic_var.set(formatted)
            # Fix cursor position - move to end to prevent it getting stuck before hyphen
            self.cnic_entry.after(1, lambda: self.cnic_entry.icursor("end"))

    def validate_phone(self, *args):
        val = self.phone_var.get()
        # Keep only numbers
        clean = "".join([c for c in val if c.isdigit()])
        if len(clean) > 11:
            clean = clean[:11]
        
        if val != clean:
            self.phone_var.set(clean)

    def toggle_business_name(self, choice):
        if choice == "DEALER":
            self.lbl_business.grid(row=8, column=0, padx=10, pady=5, sticky="e")
            self.business_name_entry.grid(row=8, column=1, padx=10, pady=5, sticky="ew")
        else:
            self.lbl_business.grid_remove()
            self.business_name_entry.grid_remove()

    def create_form_section(self):
        self.form_frame = ctk.CTkFrame(self.content_frame)
        self.form_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=10)
        self.form_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.form_frame, text="Customer Details", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=2, pady=15)

        # 1. Type
        ctk.CTkLabel(self.form_frame, text="Type *").grid(row=1, column=0, padx=10, pady=5, sticky="e")
        self.type_var = ctk.StringVar(value=CustomerType.INDIVIDUAL.value)
        self.type_combo = ctk.CTkOptionMenu(self.form_frame, variable=self.type_var, values=[e.value for e in CustomerType], command=self.toggle_business_name)
        self.type_combo.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

        # 2. CNIC
        ctk.CTkLabel(self.form_frame, text="CNIC *").grid(row=2, column=0, padx=10, pady=5, sticky="e")
        self.cnic_var = ctk.StringVar()
        self.cnic_var.trace_add("write", self.validate_cnic)
        self.cnic_entry = ctk.CTkEntry(self.form_frame, textvariable=self.cnic_var, placeholder_text="33302-1234567-1")
        self.cnic_entry.grid(row=2, column=1, padx=10, pady=5, sticky="ew")

        # 3. Name
        ctk.CTkLabel(self.form_frame, text="Name *").grid(row=3, column=0, padx=10, pady=5, sticky="e")
        self.name_var = ctk.StringVar()
        self.name_var.trace_add("write", lambda *args: self.validate_alpha(self.name_var))
        self.name_entry = ctk.CTkEntry(self.form_frame, textvariable=self.name_var)
        self.name_entry.grid(row=3, column=1, padx=10, pady=5, sticky="ew")

        # 4. Father Name
        ctk.CTkLabel(self.form_frame, text="Father Name").grid(row=4, column=0, padx=10, pady=5, sticky="e")
        self.father_name_var = ctk.StringVar()
        self.father_name_var.trace_add("write", lambda *args: self.validate_alpha(self.father_name_var))
        self.father_name_entry = ctk.CTkEntry(self.form_frame, textvariable=self.father_name_var)
        self.father_name_entry.grid(row=4, column=1, padx=10, pady=5, sticky="ew")

        # 5. Phone
        ctk.CTkLabel(self.form_frame, text="Phone *").grid(row=5, column=0, padx=10, pady=5, sticky="e")
        self.phone_var = ctk.StringVar()
        self.phone_var.trace_add("write", self.validate_phone)
        self.phone_entry = ctk.CTkEntry(self.form_frame, textvariable=self.phone_var, placeholder_text="03001234567")
        self.phone_entry.grid(row=5, column=1, padx=10, pady=5, sticky="ew")

        # 6. Address
        ctk.CTkLabel(self.form_frame, text="Address").grid(row=6, column=0, padx=10, pady=5, sticky="e")
        self.address_var = ctk.StringVar()
        # Removed redundant uppercase trace as AddressEntry handles it
        self.address_entry = AddressEntry(self.form_frame, textvariable=self.address_var)
        self.address_entry.grid(row=6, column=1, padx=10, pady=5, sticky="ew")

        # 7. NTN
        ctk.CTkLabel(self.form_frame, text="NTN").grid(row=7, column=0, padx=10, pady=5, sticky="e")
        self.ntn_var = ctk.StringVar()
        self.ntn_entry = ctk.CTkEntry(self.form_frame, textvariable=self.ntn_var)
        self.ntn_entry.grid(row=7, column=1, padx=10, pady=5, sticky="ew")

        # 8. Business Name (Optional, for dealers/companies)
        self.lbl_business = ctk.CTkLabel(self.form_frame, text="Business Name")
        self.lbl_business.grid(row=8, column=0, padx=10, pady=5, sticky="e")
        self.business_name_var = ctk.StringVar()
        self.business_name_var.trace_add("write", lambda *args: self._force_uppercase(self.business_name_var))
        self.business_name_entry = ctk.CTkEntry(self.form_frame, textvariable=self.business_name_var)
        self.business_name_entry.grid(row=8, column=1, padx=10, pady=5, sticky="ew")
        
        # Initialize state
        self.toggle_business_name(self.type_var.get())

        # Buttons
        self.btn_frame = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        self.btn_frame.grid(row=9, column=0, columnspan=2, pady=20)
        
        self.save_btn = ctk.CTkButton(self.btn_frame, text="Save", command=self.save_customer, width=80)
        self.save_btn.pack(side="left", padx=5)
        
        self.clear_btn = ctk.CTkButton(self.btn_frame, text="Clear", fg_color="gray", command=self.clear_form, width=80)
        self.clear_btn.pack(side="left", padx=5)

        self.delete_btn = ctk.CTkButton(self.btn_frame, text="Delete", fg_color="#D32F2F", hover_color="#B71C1C", command=self.delete_customer, width=80)
        self.delete_btn.pack(side="left", padx=5)
        self.delete_btn.configure(state="disabled") # Disabled initially

    def create_list_section(self):
        self.list_frame = ctk.CTkFrame(self.content_frame)
        self.list_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=10)
        self.list_frame.grid_columnconfigure(0, weight=1)
        self.list_frame.grid_rowconfigure(1, weight=1)

        # Treeview
        columns = ("check", "id", "name", "cnic", "phone", "type", "address")
        self.tree = ttk.Treeview(self.list_frame, columns=columns, show="headings")
        
        self.tree.heading("check", text="✔")
        self.tree.column("check", width=30, anchor="center")
        
        self.tree.heading("id", text="ID")
        self.tree.heading("name", text="Name")
        self.tree.heading("cnic", text="CNIC")
        self.tree.heading("phone", text="Phone")
        self.tree.heading("type", text="Type")
        self.tree.heading("address", text="Address")

        self.tree.column("id", width=50, stretch=False)
        self.tree.column("name", width=150)
        self.tree.column("cnic", width=120)
        self.tree.column("phone", width=100)
        self.tree.column("type", width=100)
        self.tree.column("address", width=200)

        self.tree.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self.list_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        # Bind events
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

    def load_customers(self):
        # Clear existing
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        # Reset Select All
        self.select_all_var.set(False)
            
        # Fetch
        query = self.search_var.get().strip()
        if query:
            customers = customer_service.search_customers(query)
        else:
            customers = customer_service.get_all_customers()
            
        for c in customers:
            self.tree.insert("", "end", values=("☐", c.id, c.name, c.cnic, c.phone, c.type.value if hasattr(c.type, 'value') else c.type, c.address))

    def on_search(self, *args):
        self.load_customers()

    def on_tree_click(self, event):
        """Handle click on checkbox column."""
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            if column == "#1":  # Checkbox column
                item = self.tree.identify_row(event.y)
                if item:
                    # Toggle selection state
                    if item in self.tree.selection():
                        self.tree.selection_remove(item)
                    else:
                        self.tree.selection_add(item)
                    return "break"  # Prevent default selection behavior

    def toggle_select_all(self):
        """Select or deselect all items."""
        if self.select_all_var.get():
            # Select all
            children = self.tree.get_children()
            self.tree.selection_set(children)
        else:
            # Deselect all
            self.tree.selection_remove(self.tree.selection())

    def delete_selected_customers(self):
        """Delete all selected customers."""
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "No customers selected.")
            return

        count = len(selected_items)
        if not messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete {count} selected customer(s)?\nThis cannot be undone."):
            return

        ids_to_delete = []
        for item_id in selected_items:
            values = self.tree.item(item_id, "values")
            if values and len(values) > 1:
                ids_to_delete.append(int(values[1])) # ID is at index 1

        success, message = customer_service.delete_customers(ids_to_delete)
        
        if success:
            messagebox.showinfo("Success", message)
            self.load_customers()
            self.clear_form()
        else:
            messagebox.showerror("Error", message)

    def on_select(self, event):
        selected_items = self.tree.selection()
        
        # Update checkbox symbols
        for item_id in self.tree.get_children():
            values = list(self.tree.item(item_id, "values"))
            if item_id in selected_items:
                values[0] = "☑"
            else:
                values[0] = "☐"
            self.tree.item(item_id, values=values)

        # Update Select All checkbox state
        all_items = self.tree.get_children()
        if len(all_items) > 0 and len(selected_items) == len(all_items):
            self.select_all_var.set(True)
        else:
            self.select_all_var.set(False)

        if not selected_items:
            return
            
        item = self.tree.item(selected_items[0])
        values = item["values"]
        
        if not values:
            return
            
        # Load into form
        self.selected_customer_id = values[1] # ID is now at index 1
        customer = customer_service.get_customer_by_id(self.selected_customer_id)
        
        if customer:
            self.name_var.set(customer.name or "")
            self.cnic_var.set(customer.cnic or "")
            self.father_name_var.set(customer.father_name or "")
            self.phone_var.set(customer.phone or "")
            self.address_var.set(customer.address or "")
            self.ntn_var.set(customer.ntn or "")
            self.business_name_var.set(customer.business_name or "")
            self.type_var.set(customer.type.value if hasattr(customer.type, 'value') else customer.type)
            
            # Update business name visibility based on type
            self.toggle_business_name(self.type_var.get())
            
            self.save_btn.configure(text="Update")
            self.delete_btn.configure(state="normal")

    def clear_form(self):
        self.selected_customer_id = None
        self.name_var.set("")
        self.cnic_var.set("")
        self.father_name_var.set("")
        self.phone_var.set("")
        self.address_var.set("")
        self.ntn_var.set("")
        self.business_name_var.set("")
        self.type_var.set(CustomerType.INDIVIDUAL.value)
        
        self.save_btn.configure(text="Save")
        self.delete_btn.configure(state="disabled")
        self.tree.selection_remove(self.tree.selection())

    def save_customer(self):
        name = self.name_var.get().strip()
        cnic = self.cnic_var.get().strip()
        phone = self.phone_var.get().strip()
        
        if not name or not cnic or not phone:
            messagebox.showwarning("Validation Error", "Name, CNIC, and Phone are required!")
            return

        # Basic Validation
        if not re.match(r"^\d{5}-\d{7}-\d{1}$", cnic):
            messagebox.showwarning("Validation Error", "Invalid CNIC Format! (e.g. 33302-1234567-1)")
            return
            
        if not re.match(r"^03\d{9}$", phone):
             messagebox.showwarning("Validation Error", "Invalid Phone Format! (e.g. 03001234567)")
             return

        try:
            if self.selected_customer_id:
                # Update
                customer_service.update_customer(
                    self.selected_customer_id,
                    cnic=cnic,
                    name=name,
                    father_name=self.father_name_var.get().strip(),
                    phone=phone,
                    address=self.address_var.get().strip(),
                    ntn=self.ntn_var.get().strip(),
                    business_name=self.business_name_var.get().strip(),
                    customer_type=self.type_var.get()
                )
                messagebox.showinfo("Success", "Customer updated successfully!")
            else:
                # Create
                # Check duplicate CNIC
                if customer_service.get_customer_by_cnic(cnic):
                    messagebox.showerror("Error", "Customer with this CNIC already exists!")
                    return
                    
                customer_service.create_customer(
                    cnic=cnic,
                    name=name,
                    father_name=self.father_name_var.get().strip(),
                    phone=phone,
                    address=self.address_var.get().strip(),
                    ntn=self.ntn_var.get().strip(),
                    business_name=self.business_name_var.get().strip(),
                    customer_type=self.type_var.get()
                )
                messagebox.showinfo("Success", "Customer created successfully!")
            
            self.clear_form()
            self.load_customers()
            
        except Exception as e:
            messagebox.showerror("Error", f"Operation failed: {e}")

    def delete_customer(self):
        if not self.selected_customer_id:
            return
            
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this customer?\nThis might affect historical invoices."):
            if customer_service.delete_customer(self.selected_customer_id):
                messagebox.showinfo("Success", "Customer deleted.")
                self.clear_form()
                self.load_customers()
            else:
                messagebox.showerror("Error", "Failed to delete customer.")
