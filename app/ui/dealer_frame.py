import customtkinter as ctk
from tkinter import messagebox, ttk, Menu
import re
from app.services.dealer_service import dealer_service
from app.ui.address_entry import AddressEntry

class DealerFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._cnic_cursor_job = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        self.header = ctk.CTkLabel(self, text="Dealer Management", font=ctk.CTkFont(size=24, weight="bold"))
        self.header.grid(row=0, column=0, padx=20, pady=20, sticky="w")

        # Main Content Area (Split into Form and List)
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=1, column=0, padx=20, pady=0, sticky="nsew")
        self.content_frame.grid_columnconfigure(0, weight=1) # Form
        self.content_frame.grid_columnconfigure(1, weight=2) # List
        self.content_frame.grid_rowconfigure(0, weight=1)

        # --- Form Section ---
        self.form_frame = ctk.CTkFrame(self.content_frame)
        self.form_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=10)
        self.form_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.form_frame, text="Add New Dealer", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=2, pady=15)

        # 1. ID Card (CNIC)
        ctk.CTkLabel(self.form_frame, text="CNIC *").grid(row=1, column=0, padx=10, pady=5, sticky="e")
        self.cnic_var = ctk.StringVar()
        self.cnic_var.trace_add("write", self.validate_cnic)
        
        # Real-time CNIC validation
        self.cnic_var.trace_add("write", self.on_cnic_change)
        self._cnic_check_job = None
        
        self.cnic_entry = ctk.CTkEntry(self.form_frame, textvariable=self.cnic_var, placeholder_text="33302-1234567-1")
        self.cnic_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

        # 2. Name
        ctk.CTkLabel(self.form_frame, text="Name *").grid(row=2, column=0, padx=10, pady=5, sticky="e")
        self.name_var = ctk.StringVar()
        self.name_var.trace_add("write", lambda *args: self.validate_alpha_upper(self.name_var))
        self.name_entry = ctk.CTkEntry(self.form_frame, textvariable=self.name_var)
        self.name_entry.grid(row=2, column=1, padx=10, pady=5, sticky="ew")

        # 3. Father Name
        ctk.CTkLabel(self.form_frame, text="Father Name *").grid(row=3, column=0, padx=10, pady=5, sticky="e")
        self.father_name_var = ctk.StringVar()
        self.father_name_var.trace_add("write", lambda *args: self.validate_alpha_upper(self.father_name_var))
        self.father_name_entry = ctk.CTkEntry(self.form_frame, textvariable=self.father_name_var)
        self.father_name_entry.grid(row=3, column=1, padx=10, pady=5, sticky="ew")

        # 4. Business Name
        ctk.CTkLabel(self.form_frame, text="Business Name *").grid(row=4, column=0, padx=10, pady=5, sticky="e")
        self.business_name_var = ctk.StringVar()
        self.business_name_var.trace_add("write", lambda *args: self.validate_alpha_upper(self.business_name_var))
        self.business_name_entry = ctk.CTkEntry(self.form_frame, textvariable=self.business_name_var)
        self.business_name_entry.grid(row=4, column=1, padx=10, pady=5, sticky="ew")

        # 5. Phone Number
        ctk.CTkLabel(self.form_frame, text="Phone *").grid(row=5, column=0, padx=10, pady=5, sticky="e")
        self.phone_var = ctk.StringVar()
        self.phone_var.trace_add("write", self.validate_phone)
        
        # Real-time business name validation (debounced)
        self.business_name_var.trace_add("write", self.on_business_name_change)
        self._biz_check_job = None
        self.phone_entry = ctk.CTkEntry(self.form_frame, textvariable=self.phone_var, placeholder_text="03007288190")
        self.phone_entry.grid(row=5, column=1, padx=10, pady=5, sticky="ew")

        # 6. Address
        ctk.CTkLabel(self.form_frame, text="Address *").grid(row=6, column=0, padx=10, pady=5, sticky="e")
        self.address_var = ctk.StringVar()
        # AddressEntry handles uppercase expansion
        self.address_entry = AddressEntry(self.form_frame, textvariable=self.address_var)
        self.address_entry.grid(row=6, column=1, padx=10, pady=5, sticky="ew")

        # Buttons
        self.btn_frame = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        self.btn_frame.grid(row=7, column=0, columnspan=2, pady=20)
        
        self.save_btn = ctk.CTkButton(self.btn_frame, text="Save Dealer", command=self.save_dealer)
        self.save_btn.pack(side="left", padx=5)
        
        self.clear_btn = ctk.CTkButton(self.btn_frame, text="Clear", fg_color="gray", command=self.clear_form)
        self.clear_btn.pack(side="left", padx=5)

        self.delete_btn = ctk.CTkButton(self.btn_frame, text="Delete", fg_color="#D32F2F", hover_color="#B71C1C", command=self.delete_dealer)
        self.delete_btn.pack(side="left", padx=5)
        self.delete_btn.pack_forget() # Hide initially

        # --- List Section ---
        self.list_frame = ctk.CTkFrame(self.content_frame)
        self.list_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=10)
        self.list_frame.grid_columnconfigure(0, weight=1)
        self.list_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self.list_frame, text="Registered Dealers", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, pady=15)

        # Treeview
        columns = ("id", "business_name", "cnic", "phone")
        self.tree = ttk.Treeview(self.list_frame, columns=columns, show="headings")
        self.tree.heading("id", text="ID")
        self.tree.heading("business_name", text="Business Name")
        self.tree.heading("cnic", text="CNIC")
        self.tree.heading("phone", text="Phone")
        
        self.tree.column("id", width=30)
        self.tree.column("business_name", width=150)
        self.tree.column("cnic", width=120)
        self.tree.column("phone", width=100)

        self.tree.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        
        # Context Menu
        self.context_menu = Menu(self, tearoff=0)
        self.context_menu.add_command(label="Delete", command=self.delete_dealer)
        self.tree.bind("<Button-3>", self.show_context_menu)

        # Scrollbar
        scrollbar = ttk.Scrollbar(self.list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=1, column=1, sticky="ns", pady=(0, 10))

        self.load_dealers()
        
        self.selected_dealer_id = None
        
        # Initialize Keyboard Navigation
        self.setup_keyboard_navigation()

    def setup_keyboard_navigation(self):
        """Sets up Enter key navigation through form fields."""
        self.nav_sequence = [
            self.cnic_entry,
            self.name_entry,
            self.father_name_entry,
            self.business_name_entry,
            self.phone_entry,
            self.address_entry
        ]

        for i, widget in enumerate(self.nav_sequence):
            if i == len(self.nav_sequence) - 1:
                # Last field triggers save
                widget.bind("<Return>", lambda e: self.save_dealer())
            else:
                next_widget = self.nav_sequence[i + 1]
                def focus_next(event, target=next_widget):
                    target.focus_set()
                    return "break"
                widget.bind("<Return>", focus_next)

    def validate_alpha_upper(self, var):
        val = var.get()
        # Allow alpha and spaces, convert to upper
        new_val = "".join([c for c in val if c.isalpha() or c.isspace()]).upper()
        if val != new_val:
            var.set(new_val)
    
    def validate_upper(self, var):
        val = var.get()
        if val != val.upper():
            var.set(val.upper())

    def on_business_name_change(self, *args):
        if self._biz_check_job:
            self.after_cancel(self._biz_check_job)
        self._biz_check_job = self.after(500, self.check_business_name_uniqueness)

    def check_business_name_uniqueness(self):
        name = self.business_name_var.get().strip()
        if not name:
            self.business_name_entry.configure(border_color=["#979DA2", "#565B5E"]) # Default
            return
            
        # Check duplicate via service
        try:
            # check_duplicate_dealer returns error message if duplicate, None otherwise
            error_msg = dealer_service.check_duplicate_dealer(name, "", exclude_id=self.selected_dealer_id)
            if error_msg and "Business Name" in error_msg:
                self.business_name_entry.configure(border_color="red")
            else:
                self.business_name_entry.configure(border_color="green")
        except Exception:
            pass

    def on_cnic_change(self, *args):
        if self._cnic_check_job:
            self.after_cancel(self._cnic_check_job)
        self._cnic_check_job = self.after(500, self.check_cnic_uniqueness)

    def check_cnic_uniqueness(self):
        cnic = self.cnic_var.get().strip()
        # Only check if full CNIC is entered (15 chars with dashes)
        if len(cnic) < 15:
             self.cnic_entry.configure(border_color=["#979DA2", "#565B5E"])
             return

        try:
             # Check duplicate via service
             error_msg = dealer_service.check_duplicate_dealer("", cnic, exclude_id=self.selected_dealer_id)
             if error_msg and "CNIC" in error_msg:
                 self.cnic_entry.configure(border_color="red")
             else:
                 self.cnic_entry.configure(border_color="green")
        except Exception:
             pass

    def validate_cnic(self, *args):
        value = self.cnic_var.get()
        
        # Get current cursor position (safe fallback)
        try:
            cursor_pos = self.cnic_entry.index("insert")
        except:
            cursor_pos = len(value)

        # Auto-format: XXXXX-XXXXXXX-X
        clean_digits = ''.join(filter(str.isdigit, value))
        
        formatted = clean_digits
        if len(clean_digits) > 5:
             formatted = clean_digits[:5] + '-' + clean_digits[5:]
        if len(clean_digits) > 12:
             formatted = formatted[:13] + '-' + formatted[13:]
             
        if len(formatted) > 15:
            formatted = formatted[:15]
            
        if value != formatted:
            # Adjust cursor position
            # Calculate clean cursor position (relative to digits only)
            non_digits_before = sum(1 for c in value[:cursor_pos] if not c.isdigit())
            clean_pos = cursor_pos - non_digits_before
            
            # Map to formatted position based on fixed dashes
            new_cursor = clean_pos
            if clean_pos > 5:
                new_cursor += 1
            if clean_pos > 12:
                new_cursor += 1
                
            self.cnic_var.set(formatted)
            
            # Restore cursor with slight delay to ensure UI update is complete
            # and cancel any pending cursor updates to prevent race conditions
            if hasattr(self, '_cnic_cursor_job') and self._cnic_cursor_job:
                try:
                    self.after_cancel(self._cnic_cursor_job)
                except:
                    pass
            
            def set_cursor():
                try:
                    self.cnic_entry.icursor(new_cursor)
                except:
                    pass
                self._cnic_cursor_job = None

            # Use after(1) to ensure this runs after Tkinter's internal variable update events
            self._cnic_cursor_job = self.after(1, set_cursor)

    def validate_phone(self, *args):
        val = self.phone_var.get()
        # Keep only numbers
        clean = "".join([c for c in val if c.isdigit()])
        if len(clean) > 11:
            clean = clean[:11]
        
        if val != clean:
            self.phone_var.set(clean)

    def save_dealer(self):
        cnic = self.cnic_var.get().strip()
        name = self.name_var.get().strip()
        father = self.father_name_var.get().strip()
        business = self.business_name_var.get().strip()
        phone = self.phone_var.get().strip()
        address = self.address_var.get().strip()

        if not all([cnic, name, father, business, phone, address]):
            messagebox.showerror("Error", "All fields are required!")
            return

        # Validate CNIC format strictness if needed (e.g. regex)
        # 33302-1234567-1
        if not re.match(r"^\d{5}-\d{7}-\d{1}$", cnic):
            messagebox.showerror("Error", "Invalid CNIC Format! Use XXXXX-XXXXXXX-X")
            return
            
        if not re.match(r"^\d{11}$", phone):
             messagebox.showerror("Error", "Invalid Phone Format! Use 03XXXXXXXXX (11 digits)")
             return

        try:
            if self.selected_dealer_id:
                dealer_service.update_dealer(self.selected_dealer_id, cnic, name, father, business, phone, address)
                messagebox.showinfo("Success", "Dealer updated successfully!")
            else:
                dealer_service.create_dealer(cnic, name, father, business, phone, address)
                messagebox.showinfo("Success", "Dealer saved successfully!")
            
            self.clear_form()
            self.load_dealers()
        except ValueError as ve:
             messagebox.showwarning("Validation Error", str(ve))
        except Exception as e:
            messagebox.showerror("Error", f"Could not save dealer: {str(e)}")

    def delete_dealer(self):
        if not self.selected_dealer_id:
            return
            
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this dealer?"):
            try:
                dealer_service.delete_dealer(self.selected_dealer_id)
                messagebox.showinfo("Success", "Dealer deleted successfully!")
                self.clear_form()
                self.load_dealers()
            except Exception as e:
                messagebox.showerror("Error", f"Could not delete dealer: {str(e)}")

    def clear_form(self):
        self.cnic_var.set("")
        self.name_var.set("")
        self.father_name_var.set("")
        self.business_name_var.set("")
        self.phone_var.set("")
        self.address_var.set("")
        
        self.selected_dealer_id = None
        self.save_btn.configure(text="Save Dealer")
        self.delete_btn.pack_forget()
        
        # Deselect tree
        if len(self.tree.selection()) > 0:
            self.tree.selection_remove(self.tree.selection()[0])

    def on_tree_select(self, event):
        # Ensure the focused item is visible (for keyboard navigation)
        try:
            focus_item = self.tree.focus()
            if focus_item:
                self.tree.see(focus_item)
        except Exception:
            pass

        selected_items = self.tree.selection()
        if not selected_items:
            return

        item_id = selected_items[0]
        values = self.tree.item(item_id, "values")
        
        if values:
            dealer_id = values[0]
            dealer = dealer_service.get_dealer_by_id(dealer_id)
            
            if dealer:
                self.selected_dealer_id = dealer.id
                
                # Populate form
                self.cnic_var.set(dealer.cnic)
                self.name_var.set(dealer.name)
                self.father_name_var.set(dealer.father_name)
                self.business_name_var.set(dealer.business_name)
                self.phone_var.set(dealer.phone)
                self.address_var.set(dealer.address)
                
                # Update UI state
                self.save_btn.configure(text="Update Dealer")
                self.delete_btn.pack(side="left", padx=5)
            
    def load_dealers(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        dealers = dealer_service.get_all_dealers()
        for d in dealers:
            self.tree.insert("", "end", values=(d.id, d.business_name, d.cnic, d.phone))

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.on_tree_select(None) # Ensure selection logic runs
            self.context_menu.post(event.x_root, event.y_root)
