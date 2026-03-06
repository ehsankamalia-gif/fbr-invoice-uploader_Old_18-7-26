import customtkinter as ctk
import threading
from tkinter import messagebox, ttk, filedialog, Menu
from app.db.session import SessionLocal
from app.db.models import Motorcycle, Supplier, ProductModel
from app.services.scraper_service import HondaScraper
from app.utils.url_manager import UrlManager
from sqlalchemy import or_
from app.services.price_service import price_service

class InventoryFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)  # Changed row index for treeview

        # Header
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, padx=20, pady=10, sticky="ew")
        
        self.title_label = ctk.CTkLabel(self.header_frame, text="Inventory Management", font=ctk.CTkFont(size=24, weight="bold"))
        self.title_label.pack(side="left")
        
        self.add_btn = ctk.CTkButton(self.header_frame, text="Add Motorcycle", command=self.open_add_dialog)
        self.add_btn.pack(side="right", padx=10)

        self.import_web_btn = ctk.CTkButton(self.header_frame, text="Import Inventory", command=self.open_web_import_dialog, fg_color="#E67E22", hover_color="#D35400")
        self.import_web_btn.pack(side="right", padx=10)
        
        # New Capture Buttons
        self.capture_btn = ctk.CTkButton(self.header_frame, text="Launch Capture", command=self.launch_capture_browser, fg_color="#3498DB", hover_color="#2980B9")
        self.capture_btn.pack(side="right", padx=10)
        
        self.view_captured_btn = ctk.CTkButton(self.header_frame, text="View Captured", command=self.view_captured_data, fg_color="#1ABC9C", hover_color="#16A085")
        self.view_captured_btn.pack(side="right", padx=10)

        # Stats Badges
        self.stats_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.stats_frame.pack(side="right", padx=20)
        
        self.lbl_stock = ctk.CTkLabel(self.stats_frame, text="In Stock: 0", text_color="#2ECC71", font=("Arial", 14, "bold"))
        self.lbl_stock.pack(side="left", padx=15)
        
        self.lbl_sold = ctk.CTkLabel(self.stats_frame, text="Sold: 0", text_color="#E74C3C", font=("Arial", 14, "bold"))
        self.lbl_sold.pack(side="left", padx=15)

        # Filter Bar
        self.filter_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.filter_frame.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="ew")
        
        # Search Entry
        # Removed textvariable to ensure placeholder visibility
        self.search_entry = ctk.CTkEntry(self.filter_frame, placeholder_text="Search by Chassis, Engine or Model...", width=300)
        self.search_entry.pack(side="left", padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", lambda event: self.apply_filters())

        # Status Filter
        self.status_var = ctk.StringVar(value="All")
        self.status_filter = ctk.CTkOptionMenu(self.filter_frame, values=["All", "IN_STOCK", "SOLD"], variable=self.status_var, command=lambda x: self.apply_filters())
        self.status_filter.pack(side="left", padx=10)
        
        # Reset Button
        self.reset_filter_btn = ctk.CTkButton(self.filter_frame, text="Reset Filters", width=100, fg_color="gray", command=self.reset_filters)
        self.reset_filter_btn.pack(side="left", padx=10)

        # Separator
        ctk.CTkFrame(self.filter_frame, width=2, height=20, fg_color="gray50").pack(side="left", padx=10)

        # Bulk Selection Controls
        self.chk_sold_var = ctk.BooleanVar()
        self.chk_sold = ctk.CTkCheckBox(self.filter_frame, text="Select All Sold", variable=self.chk_sold_var, command=self.toggle_select_sold, width=120)
        self.chk_sold.pack(side="left", padx=5)

        self.chk_stock_var = ctk.BooleanVar()
        self.chk_stock = ctk.CTkCheckBox(self.filter_frame, text="Select All In-Stock", variable=self.chk_stock_var, command=self.toggle_select_stock, width=120)
        self.chk_stock.pack(side="left", padx=5)
        
        self.lbl_selection_count = ctk.CTkLabel(self.filter_frame, text="Selected: 0", font=("Arial", 12, "bold"), text_color="#3498db")
        self.lbl_selection_count.pack(side="left", padx=15)

        # Inventory List (Treeview)
        self.tree_frame = ctk.CTkFrame(self)
        self.tree_frame.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")
        
        # Style for Treeview
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", 
                        background="#2b2b2b", 
                        foreground="white", 
                        fieldbackground="#2b2b2b", 
                        rowheight=25)
        style.map('Treeview', background=[('selected', '#1f538d')])
        
        columns = ("id", "make", "model", "chassis", "engine", "color", "price", "status", "check")
        self.tree = ttk.Treeview(self.tree_frame, columns=columns, show="headings")
        
        self.tree.heading("id", text="ID", command=lambda: self.sort_column("id", False))
        self.tree.heading("make", text="Make", command=lambda: self.sort_column("make", False))
        self.tree.heading("model", text="Model", command=lambda: self.sort_column("model", False))
        self.tree.heading("chassis", text="Chassis No", command=lambda: self.sort_column("chassis", False))
        self.tree.heading("engine", text="Engine No", command=lambda: self.sort_column("engine", False))
        self.tree.heading("color", text="Color", command=lambda: self.sort_column("color", False))
        self.tree.heading("price", text="Price", command=lambda: self.sort_column("price", False))
        self.tree.heading("status", text="Status", command=lambda: self.sort_column("status", False))
        self.tree.heading("check", text="Select")
        
        self.tree.column("id", width=30)
        self.tree.column("make", width=80)
        self.tree.column("model", width=100)
        self.tree.column("chassis", width=120)
        self.tree.column("engine", width=120)
        self.tree.column("color", width=80)
        self.tree.column("price", width=80)
        self.tree.column("status", width=80)
        self.tree.column("check", width=50, anchor="center")
        
        # Scrollbar
        self.scrollbar_y = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        self.scrollbar_x = ttk.Scrollbar(self.tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.scrollbar_y.set, xscrollcommand=self.scrollbar_x.set)
        
        self.scrollbar_y.pack(side="right", fill="y")
        self.scrollbar_x.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)
        
        # Context Menu
        self.context_menu = Menu(self, tearoff=0)
        self.context_menu.add_command(label="Edit Motorcycle", command=self.edit_selected_motorcycle)
        self.context_menu.add_command(label="Delete Motorcycle", command=self.delete_selected_motorcycle)
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.tree.bind("<Double-1>", self.edit_selected_motorcycle)
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        
        self.prev_selection = set()
        self.selected_ids = set() # Global set of selected IDs (int)

        # Refresh Data
        self.refresh_inventory()

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            # If item is not in current selection, select it (clearing others)
            # If item IS in current selection, keep selection as is (for bulk actions)
            if item not in self.tree.selection():
                self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            # Column #9 corresponds to the "check" column (indices are #1 based in identify_column usually, or match display columns)
            # Our columns: id, make, model, chassis, engine, color, price, status, check
            # That is 9 columns. The last one is #9.
            if column == "#9":
                item = self.tree.identify_row(event.y)
                if item:
                    if item in self.tree.selection():
                        self.tree.selection_remove(item)
                    else:
                        self.tree.selection_add(item)
                    return "break"  # Prevent default selection behavior

    def on_tree_select(self, event):
        # Ensure the focused item is visible (for keyboard navigation)
        try:
            focus_item = self.tree.focus()
            if focus_item:
                self.tree.see(focus_item)
        except Exception:
            pass

        current_selection = set(self.tree.selection())
        
        # Determine changed items
        changed_items = current_selection.symmetric_difference(self.prev_selection)
        
        for item_id in changed_items:
            try:
                values = list(self.tree.item(item_id, "values"))
                db_id = int(values[0]) if values[0] else 0
                
                # Update checkbox symbol (last column)
                if item_id in current_selection:
                    values[-1] = "☑"
                    self.selected_ids.add(db_id)
                else:
                    values[-1] = "☐"
                    self.selected_ids.discard(db_id)
                    
                    # If user deselects an item, uncheck the corresponding bulk checkbox
                    status = values[7] # Status column index
                    if status == "SOLD":
                        self.chk_sold_var.set(False)
                    elif status == "IN_STOCK":
                        self.chk_stock_var.set(False)
                    
                self.tree.item(item_id, values=values)
            except Exception:
                pass # Item might have been deleted
                
        self.prev_selection = current_selection
        self.update_selection_label()

    def update_selection_label(self):
        count = len(self.selected_ids)
        self.lbl_selection_count.configure(text=f"Selected: {count}")

    def toggle_select_sold(self):
        self.toggle_bulk_select("SOLD", self.chk_sold_var.get())

    def toggle_select_stock(self):
        self.toggle_bulk_select("IN_STOCK", self.chk_stock_var.get())

    def toggle_bulk_select(self, status, is_selected):
        self.configure(cursor="watch")
        self.update()
        
        db = SessionLocal()
        try:
            # Get IDs for the status
            rows = db.query(Motorcycle.id).filter(Motorcycle.status == status).all()
            ids = {row[0] for row in rows}
            
            if is_selected:
                self.selected_ids.update(ids)
            else:
                self.selected_ids.difference_update(ids)
                
            self.restore_selection()
            self.update_selection_label()
        except Exception as e:
            messagebox.showerror("Error", f"Bulk selection failed: {e}")
        finally:
            db.close()
            self.configure(cursor="")

    def restore_selection(self):
        # Sync treeview selection with self.selected_ids
        items_to_select = []
        items_to_deselect = []
        
        for item_id in self.tree.get_children():
            try:
                val = self.tree.item(item_id, "values")[0]
                db_id = int(val) if val else 0
                
                if db_id in self.selected_ids:
                    items_to_select.append(item_id)
                else:
                    items_to_deselect.append(item_id)
            except:
                pass
                
        # This will trigger <<TreeviewSelect>> which updates visuals
        if items_to_select:
            self.tree.selection_add(items_to_select)
        if items_to_deselect:
            self.tree.selection_remove(items_to_deselect)

    def sort_column(self, col, reverse):
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        
        try:
            # Handle numeric sorting for Price and ID
            if col == "price":
                # Remove commas and convert to float
                l.sort(key=lambda t: float(t[0].replace(',', '') if t[0] else 0), reverse=reverse)
            elif col == "id":
                l.sort(key=lambda t: int(t[0] if t[0] else 0), reverse=reverse)
            else:
                l.sort(reverse=reverse)
        except ValueError:
             l.sort(reverse=reverse)

        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)

        # Update heading command to reverse sort next time
        self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))

    def reset_filters(self):
        self.search_entry.delete(0, "end")
        self.status_var.set("All")
        self.refresh_inventory()

    def apply_filters(self):
        search_text = self.search_entry.get()
        status = self.status_var.get()
        self.refresh_inventory(search_text, status)

    def refresh_inventory(self, search_query=None, status_filter="All"):
        # Clear current items
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.prev_selection = set()
            
        db = SessionLocal()
        try:
            query = db.query(Motorcycle).join(ProductModel)
            
            # Apply Filters
            if status_filter and status_filter != "All":
                query = query.filter(Motorcycle.status == status_filter)
                
            if search_query:
                search = f"%{search_query}%"
                query = query.filter(
                    or_(
                        Motorcycle.chassis_number.ilike(search),
                        Motorcycle.engine_number.ilike(search),
                        ProductModel.model_name.ilike(search),
                        ProductModel.make.ilike(search)
                    )
                )
            
            bikes = query.all()
            for bike in bikes:
                self.tree.insert("", "end", values=(
                    bike.id, bike.product_model.make, bike.product_model.model_name, bike.chassis_number, 
                    bike.engine_number, bike.color, f"{bike.sale_price:,.0f}", bike.status, "☐"
                ))
            
            self.update_stats()
            self.restore_selection() # Restore selection state for visible items
        finally:
            db.close()

    def update_stats(self):
        db = SessionLocal()
        try:
            in_stock = db.query(Motorcycle).filter(Motorcycle.status == "IN_STOCK").count()
            sold = db.query(Motorcycle).filter(Motorcycle.status == "SOLD").count()
            
            self.lbl_stock.configure(text=f"In Stock: {in_stock}")
            self.lbl_sold.configure(text=f"Sold: {sold}")
        except Exception:
            pass
        finally:
            db.close()

    def edit_selected_motorcycle(self, event=None):
        selected_items = self.tree.selection()
        if not selected_items:
            return
        
        # Edit the first selected item
        item_id = selected_items[0]
        item = self.tree.item(item_id)
        record_id = item['values'][0]
        
        AddMotorcycleDialog(self, mode="edit", record_id=record_id)

    def delete_selected_motorcycle(self):
        if not self.selected_ids:
            messagebox.showwarning("Warning", "Please select at least one record to delete.")
            return
            
        count = len(self.selected_ids)
        if not messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete {count} selected motorcycle(s)?"):
            return

        db = SessionLocal()
        try:
            deleted_count = 0
            for record_id in list(self.selected_ids):
                bike = db.query(Motorcycle).filter(Motorcycle.id == record_id).first()
                if bike:
                    db.delete(bike)
                    deleted_count += 1
            
            db.commit()
            messagebox.showinfo("Success", f"{deleted_count} motorcycle(s) deleted successfully")
            
            self.selected_ids.clear()
            self.update_selection_label()
            self.chk_sold_var.set(False)
            self.chk_stock_var.set(False)
            
            self.refresh_inventory()
        except Exception as e:
            db.rollback()
            messagebox.showerror("Error", f"Failed to delete: {e}")
        finally:
            db.close()

    def open_add_dialog(self):
        AddMotorcycleDialog(self)

    def launch_capture_browser(self):
        """Calls the main window's capture browser event."""
        if hasattr(self.master, "form_capture_button_event"):
            self.master.form_capture_button_event()

    def view_captured_data(self):
        """Switches view to the captured data frame."""
        if hasattr(self.master, "captured_data_button_event"):
            self.master.captured_data_button_event()

    def open_web_import_dialog(self):
        WebImportDialog(self)

class WebImportDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Import Inventory from Web")
        self.geometry("750x600") # Slightly wider for new button
        
        # Ensure window is on top and focused
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.after(100, lambda: self.attributes("-topmost", False)) # Disable topmost after 100ms to allow other windows
        
        self.scraper = HondaScraper()
        self.scraped_data = []
        self.url_manager = UrlManager()
        
        # Configure grid
        self.grid_columnconfigure(1, weight=1)
        
        # 1. URL Configuration
        ctk.CTkLabel(self, text="Portal URL:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=20, pady=10, sticky="w")
        self.url_entry = ctk.CTkEntry(self)
        
        # Load saved URL or default
        saved_url = self.url_manager.get_default_url()
        
        # Auto-correct old broken URL
        if saved_url == "https://portal.atlashonda.com.pk":
            saved_url = "https://dealers.ahlportal.com"
            
        if self.url_entry.get():
             self.url_entry.delete(0, "end")
        self.url_entry.insert(0, saved_url if saved_url else "https://dealers.ahlportal.com")
        self.url_entry.grid(row=0, column=1, padx=(20, 5), pady=10, sticky="ew")
        
        # Save URL Button
        self.save_btn = ctk.CTkButton(self, text="💾", width=40, command=self.open_save_dialog, fg_color="gray", hover_color="gray30")
        self.save_btn.grid(row=0, column=2, padx=(5, 5), pady=10)
        
        # Check if browser is already running
        btn_text = "1. Launch Browser"
        state = "normal"
        fg_color = None # Default
        
        if self.scraper.capture_service.is_running:
            btn_text = "1. Connect & Login"
            fg_color = "#2980B9" # Blue
            
        self.launch_btn = ctk.CTkButton(self, text=btn_text, command=self.launch_browser, state=state, fg_color=fg_color)
        self.launch_btn.grid(row=0, column=3, padx=20, pady=10)

        # 1.5 Credentials (New)
        cred_frame = ctk.CTkFrame(self, fg_color="transparent")
        cred_frame.grid(row=1, column=0, columnspan=4, padx=20, pady=0, sticky="ew")
        
        ctk.CTkLabel(cred_frame, text="Username:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 5))
        self.username_entry = ctk.CTkEntry(cred_frame, width=150)
        self.username_entry.pack(side="left", padx=5)
        
        ctk.CTkLabel(cred_frame, text="Password:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(10, 5))
        self.password_entry = ctk.CTkEntry(cred_frame, width=150, show="*")
        self.password_entry.pack(side="left", padx=5)

        # Show/Hide Password Checkbox
        self.show_password_var = ctk.BooleanVar(value=False)
        self.show_password_check = ctk.CTkCheckBox(
            cred_frame, 
            text="Show", 
            variable=self.show_password_var, 
            width=60,
            command=self.toggle_password_visibility
        )
        self.show_password_check.pack(side="left", padx=5)
        
        # Explicit Save Button for Credentials
        self.save_creds_btn = ctk.CTkButton(cred_frame, text="💾 Save", width=60, command=self.save_credentials, fg_color="gray", hover_color="gray30")
        self.save_creds_btn.pack(side="left", padx=5)
        
        # Load credentials from settings
        import app.core.config
        app.core.config.reload_settings()
        settings = app.core.config.settings
        
        if settings.HONDA_PORTAL_USERNAME:
            self.username_entry.insert(0, settings.HONDA_PORTAL_USERNAME)
        if settings.HONDA_PORTAL_PASSWORD:
            self.password_entry.insert(0, settings.HONDA_PORTAL_PASSWORD)
        
        # Instructions
        self.info_label = ctk.CTkLabel(self, text="Step 1: Click 'Launch Browser'.\nStep 2: Log in and navigate to the Stock/Inventory page (as shown in picture).\nStep 3: Click 'Scrape Page' below.", text_color="gray")
        self.info_label.grid(row=2, column=0, columnspan=4, padx=20, pady=5)
        
        # 2. Defaults
        ctk.CTkLabel(self, text="Default Values", font=ctk.CTkFont(weight="bold")).grid(row=3, column=0, padx=20, pady=10, sticky="w")
        
        defaults_frame = ctk.CTkFrame(self)
        defaults_frame.grid(row=4, column=0, columnspan=4, padx=20, pady=5, sticky="ew")
        
        ctk.CTkLabel(defaults_frame, text="Year:").pack(side="left", padx=5)
        self.year_entry = ctk.CTkEntry(defaults_frame, width=60)
        self.year_entry.insert(0, "2025")
        self.year_entry.pack(side="left", padx=5)
        
        ctk.CTkLabel(defaults_frame, text="Cost Price:").pack(side="left", padx=5)
        self.cost_entry = ctk.CTkEntry(defaults_frame, width=100)
        self.cost_entry.insert(0, "0")
        self.cost_entry.pack(side="left", padx=5)
        
        ctk.CTkLabel(defaults_frame, text="Sale Price:").pack(side="left", padx=5)
        self.sale_entry = ctk.CTkEntry(defaults_frame, width=100)
        self.sale_entry.insert(0, "0")
        self.sale_entry.pack(side="left", padx=5)
        
        # 3. Scrape Action
        self.pagination_var = ctk.BooleanVar(value=True)
        self.pagination_check = ctk.CTkCheckBox(self, text="Scrape All Pages (Max 50)", variable=self.pagination_var)
        self.pagination_check.grid(row=5, column=0, padx=20, pady=5)

        self.scrape_btn = ctk.CTkButton(self, text="2. Scrape Page", command=self.start_scrape, state="disabled")
        self.scrape_btn.grid(row=5, column=1, columnspan=3, padx=20, pady=20)
        
        # 4. Results Preview
        self.preview_box = ctk.CTkTextbox(self, height=200)
        self.preview_box.grid(row=6, column=0, columnspan=4, padx=20, pady=10, sticky="nsew")
        self.grid_rowconfigure(6, weight=1)
        
        # 5. Import Action
        self.import_btn = ctk.CTkButton(self, text="3. Import to Database", command=self.import_data, state="disabled", fg_color="green", hover_color="darkgreen")
        self.import_btn.grid(row=7, column=0, columnspan=4, padx=20, pady=20)
        
        # Handle close
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def toggle_password_visibility(self):
        if self.show_password_var.get():
            self.password_entry.configure(show="")
        else:
            self.password_entry.configure(show="*")

    def save_credentials(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        try:
            from app.services.settings_service import settings_service
            settings_service.save_honda_credentials(username, password)
            messagebox.showinfo("Success", "Credentials saved successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save credentials: {e}")

    def open_save_dialog(self):
        url = self.url_entry.get()
        username = self.username_entry.get()
        password = self.password_entry.get()
        
        if not url:
            messagebox.showwarning("Empty URL", "Please enter a URL to save.")
            return
            
        SaveUrlOptionsDialog(self, url, self.url_manager, self.scraper, username, password)

    def launch_browser(self):
        url = self.url_entry.get()
        username = self.username_entry.get()
        password = self.password_entry.get()
        
        if not url:
            messagebox.showerror("Error", "Please enter a URL first")
            return
            
        # Auto-save credentials for convenience
        if username or password:
            try:
                from app.services.settings_service import settings_service
                settings_service.save_honda_credentials(username, password)
            except Exception as e:
                print(f"Failed to auto-save credentials: {e}")

        self.scrape_btn.configure(text="Launching...", state="disabled")
        self.launch_btn.configure(state="disabled")
        
        def login_worker():
            try:
                self.scraper.login(url, username=username, password=password)
                self.after(0, lambda: self.scrape_btn.configure(state="normal", text="2. Scrape Page"))
                self.after(0, lambda: self.launch_btn.configure(state="normal", text="1. Connect & Login", fg_color="#2980B9"))
            except Exception as e:
                msg = str(e)
                def show_error():
                    if "ERR_NAME_NOT_RESOLVED" in msg:
                        messagebox.showerror("Connection Error", "Could not connect to the portal.\n\nPlease check:\n1. Your internet connection\n2. The URL (should be https://dealers.ahlportal.com)")
                    else:
                        messagebox.showerror("Error", f"Failed to launch browser: {e}")
                    self.scrape_btn.configure(state="normal", text="2. Scrape Page")
                    self.launch_btn.configure(state="normal", text="1. Launch Browser")
                self.after(0, show_error)

        threading.Thread(target=login_worker, daemon=True).start()

    def start_scrape(self):
        self.scrape_btn.configure(state="disabled", text="Scraping...")
        
        def update_status(msg):
            self.after(0, lambda: self.scrape_btn.configure(text=msg))

        def scrape_worker():
            try:
                if self.pagination_var.get():
                    new_data = self.scraper.scrape_all_pages(max_pages=1000, status_callback=update_status)
                else:
                    new_data = self.scraper.scrape_current_page()
                
                self.after(0, lambda: self._on_scrape_complete(new_data))
            except Exception as e:
                self.after(0, lambda: self._on_scrape_error(e))

        threading.Thread(target=scrape_worker, daemon=True).start()

    def _on_scrape_complete(self, new_data):
        try:
            # Initialize if empty
            if not self.scraped_data:
                self.scraped_data = []

            # Append new data (Avoiding Duplicates)
            existing_signatures = set((item['chassis_number'], item['engine_number']) for item in self.scraped_data)
            added_count = 0
            
            for item in new_data:
                sig = (item['chassis_number'], item['engine_number'])
                if sig not in existing_signatures:
                    self.scraped_data.append(item)
                    existing_signatures.add(sig)
                    added_count += 1
            
            # Show preview of ALL scraped data
            self.preview_box.delete("0.0", "end")
            if not self.scraped_data:
                self.preview_box.insert("0.0", "No data found. Make sure the table is visible.")
                self.scrape_btn.configure(state="normal", text="2. Scrape Page")
                return
                
            preview_text = f"Total Items: {len(self.scraped_data)} (Added New: {added_count})\n\n"
            for i, item in enumerate(self.scraped_data):
                page_info = f"[Page {item.get('page_number', '?')}] " if item.get('page_number') else ""
                preview_text += f"{i+1}. {page_info}{item['model']} - {item['color']} (Eng: {item['engine_number']}, Chas: {item['chassis_number']})\n"
            
            self.preview_box.insert("0.0", preview_text)
            self.import_btn.configure(state="normal", text=f"3. Import {len(self.scraped_data)} Items")
            self.scrape_btn.configure(state="normal", text="2. Scrape Page (Append)")
            
        except Exception as e:
            self._on_scrape_error(e)

    def _on_scrape_error(self, error):
        messagebox.showerror("Error", f"Scraping failed: {error}")
        self.scrape_btn.configure(state="normal", text="2. Scrape Page")

    def import_data(self):
        if not self.scraped_data:
            return
            
        try:
            year = int(self.year_entry.get() or 2025)
            cost = float(self.cost_entry.get() or 0)
            sale = float(self.sale_entry.get() or 0)
        except ValueError:
            messagebox.showerror("Error", "Invalid numeric values for Default Year/Price")
            return
            
        db = SessionLocal()
        imported_count = 0
        skipped_count = 0
        
        try:
            for item in self.scraped_data:
                # Check duplicate (Chassis OR Engine)
                exists = db.query(Motorcycle).filter(
                    or_(
                        Motorcycle.chassis_number == item["chassis_number"],
                        Motorcycle.engine_number == item["engine_number"]
                    )
                ).first()
                if exists:
                    skipped_count += 1
                    continue
                    
                # Find or Create Product Model
                model_name = item["model"]
                engine_capacity = "70cc" if "70" in model_name else "125cc"
                
                product_model = db.query(ProductModel).filter(ProductModel.model_name == model_name).first()
                if not product_model:
                    product_model = ProductModel(
                        model_name=model_name,
                        make="Honda",
                        engine_capacity=engine_capacity
                    )
                    db.add(product_model)
                    db.flush()
                
                new_bike = Motorcycle(
                    product_model_id=product_model.id,
                    year=year,
                    chassis_number=(item["chassis_number"] or "").upper(),
                    engine_number=(item["engine_number"] or "").upper(),
                    color=(item["color"] or "").upper(),
                    cost_price=cost,
                    sale_price=sale,
                    status="IN_STOCK"
                )
                db.add(new_bike)
                imported_count += 1
            
            db.commit()
            messagebox.showinfo("Import Complete", f"Successfully imported {imported_count} motorcycles.\nSkipped {skipped_count} duplicates.")
            self.parent.refresh_inventory()
            self.on_close()
            
        except Exception as e:
            db.rollback()
            messagebox.showerror("Import Error", f"Database error: {e}")
        finally:
            db.close()

    def on_close(self):
        try:
            self.scraper.close()
        except:
            pass
        self.destroy()

class AddMotorcycleDialog(ctk.CTkToplevel):
    def __init__(self, parent, mode="add", record_id=None):
        super().__init__(parent)
        self.parent = parent
        self.mode = mode
        self.record_id = record_id
        
        title = "Edit Motorcycle" if mode == "edit" else "Add New Motorcycle"
        self.title(title)
        # self.transient(self.parent) # Removed to allow minimize/maximize buttons
        self.geometry("900x700")
        self.resizable(True, True)
        
        # Bring to front
        self.lift()
        self.focus_force()
        
        # Maximize the window
        # self.after(0, lambda: self.state('zoomed'))
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        self.scroll_frame = ctk.CTkScrollableFrame(self)
        self.scroll_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.scroll_frame.grid_columnconfigure(1, weight=1)
        
        self.entries = {}
        
        ctk.CTkLabel(self.scroll_frame, text="Model").grid(row=0, column=0, padx=20, pady=10, sticky="e")
        self.model_var = ctk.StringVar()
        self.model_menu = ctk.CTkOptionMenu(self.scroll_frame, variable=self.model_var, values=[], command=self.on_model_change)
        self.model_menu.grid(row=0, column=1, padx=20, pady=10, sticky="ew")
        
        ctk.CTkLabel(self.scroll_frame, text="Chassis Number").grid(row=1, column=0, padx=20, pady=10, sticky="e")
        self.entries["chassis"] = ctk.CTkEntry(self.scroll_frame)
        self.entries["chassis"].grid(row=1, column=1, padx=20, pady=10, sticky="ew")
        
        ctk.CTkLabel(self.scroll_frame, text="Engine Number").grid(row=2, column=0, padx=20, pady=10, sticky="e")
        self.entries["engine"] = ctk.CTkEntry(self.scroll_frame)
        self.entries["engine"].grid(row=2, column=1, padx=20, pady=10, sticky="ew")
        
        ctk.CTkLabel(self.scroll_frame, text="Color").grid(row=3, column=0, padx=20, pady=10, sticky="e")
        self.color_var = ctk.StringVar()
        self.color_menu = ctk.CTkOptionMenu(self.scroll_frame, variable=self.color_var, values=[])
        self.color_menu.grid(row=3, column=1, padx=20, pady=10, sticky="ew")
        
        ctk.CTkLabel(self.scroll_frame, text="Cost Price").grid(row=4, column=0, padx=20, pady=10, sticky="e")
        self.entries["cost"] = ctk.CTkEntry(self.scroll_frame)
        self.entries["cost"].grid(row=4, column=1, padx=20, pady=10, sticky="ew")
        
        ctk.CTkLabel(self.scroll_frame, text="Sale Price").grid(row=5, column=0, padx=20, pady=10, sticky="e")
        self.entries["sale"] = ctk.CTkEntry(self.scroll_frame)
        self.entries["sale"].grid(row=5, column=1, padx=20, pady=10, sticky="ew")
        
        # Enter key navigation
        self.entries["chassis"].bind("<Return>", lambda e: self.check_and_save("chassis"))
        self.entries["engine"].bind("<Return>", lambda e: self.check_and_save("engine"))
        self.entries["cost"].bind("<Return>", lambda e: self.check_and_save("cost"))
        self.entries["sale"].bind("<Return>", lambda e: self.check_and_save("sale"))
        
        self.status_var = ctk.StringVar(value="IN_STOCK")
        if mode == "edit":
            ctk.CTkLabel(self.scroll_frame, text="Status").grid(row=6, column=0, padx=20, pady=10, sticky="e")
            self.status_menu = ctk.CTkOptionMenu(self.scroll_frame, variable=self.status_var, values=["IN_STOCK", "SOLD"])
            self.status_menu.grid(row=6, column=1, padx=20, pady=10, sticky="ew")
            btn_row = 7
        else:
            btn_row = 6
        
        save_btn = ctk.CTkButton(self.scroll_frame, text="Save Motorcycle", command=self.save_motorcycle)
        save_btn.grid(row=btn_row, column=0, columnspan=2, padx=20, pady=20)
        
        self.populate_models()
        
        if mode == "edit" and record_id:
            self.load_data()

    def load_data(self):
        db = SessionLocal()
        try:
            bike = db.query(Motorcycle).filter(Motorcycle.id == self.record_id).first()
            if bike:
                model_name = bike.product_model.model_name
                if model_name in self.model_menu._values:
                    self.model_menu.set(model_name)
                else:
                    self.model_menu.configure(values=list(self.model_menu._values) + [model_name])
                    self.model_menu.set(model_name)
                self.on_model_change(model_name)
                # Year and Capacity fields removed from UI
                # self.entries["year"].insert(0, str(bike.year))
                self.entries["chassis"].insert(0, bike.chassis_number)
                self.entries["engine"].insert(0, bike.engine_number)
                if bike.color:
                    colors = self.color_menu._values
                    if bike.color not in colors:
                        self.color_menu.configure(values=list(colors) + [bike.color])
                    self.color_menu.set(bike.color)
                # self.entries["capacity"].insert(0, bike.product_model.engine_capacity or "")
                self.entries["cost"].insert(0, str(bike.cost_price))
                self.entries["sale"].insert(0, str(bike.sale_price))
                self.status_var.set(bike.status)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load data: {e}")
        finally:
            db.close()

    def check_and_save(self, current_field):
        """
        Check if Model, Chassis, Engine, and Color are populated.
        If yes, save the motorcycle.
        If no, move focus to the next field.
        """
        data = {k: v.get() for k, v in self.entries.items()}
        data["model"] = self.model_menu.get()
        data["color"] = self.color_menu.get()
        
        # Conditions for auto-save
        is_populated = (
            data["model"] and 
            data["chassis"] and 
            data["engine"] and 
            data["color"]
        )
        
        if is_populated:
            self.save_motorcycle()
            return
            
        # Default navigation if not ready to save
        if current_field == "chassis":
            self.entries["engine"].focus_set()
        elif current_field == "engine":
            self.entries["cost"].focus_set()
        elif current_field == "cost":
            self.entries["sale"].focus_set()
        elif current_field == "sale":
            self.save_motorcycle() # Fallback for last field
        
    def save_motorcycle(self):
        data = {k: v.get() for k, v in self.entries.items()}
        data["model"] = self.model_menu.get()
        data["color"] = self.color_menu.get()
        
        # Basic Validation
        if not data["chassis"] or not data["engine"]:
            messagebox.showerror("Error", "Chassis and Engine numbers are required!")
            return
            
        db = SessionLocal()
        try:
            # Find or Create Product Model
            model_name = data["model"]
            product_model = db.query(ProductModel).filter(ProductModel.model_name == model_name).first()
            if not product_model:
                product_model = ProductModel(
                    model_name=model_name,
                    make="Honda",
                    engine_capacity=None # Capacity input removed
                )
                db.add(product_model)
                db.flush()

            if self.mode == "edit":
                bike = db.query(Motorcycle).filter(Motorcycle.id == self.record_id).first()
                if not bike:
                    raise Exception("Record not found")
                
                bike.product_model_id = product_model.id
                # Year input removed, keeping existing year or default
                if not bike.year:
                    bike.year = 2025
                bike.chassis_number = (data["chassis"] or "").upper()
                bike.engine_number = (data["engine"] or "").upper()
                bike.color = (data["color"] or "").upper()
                bike.cost_price = float(data["cost"] or 0)
                bike.sale_price = float(data["sale"] or 0)
                bike.status = self.status_var.get()
                
                messagebox.showinfo("Success", "Motorcycle updated successfully!")
            else:
                new_bike = Motorcycle(
                    product_model_id=product_model.id,
                    year=2025, # Default year
                    chassis_number=(data["chassis"] or "").upper(),
                    engine_number=(data["engine"] or "").upper(),
                    color=(data["color"] or "").upper(),
                    cost_price=float(data["cost"] or 0),
                    sale_price=float(data["sale"] or 0),
                    status="IN_STOCK"
                )
                db.add(new_bike)
                messagebox.showinfo("Success", "Motorcycle added successfully!")
                
            db.commit()
            self.parent.refresh_inventory()
            self.destroy()
        except Exception as e:
            db.rollback()
            messagebox.showerror("Error", f"Failed to save: {str(e)}")
        finally:
            db.close()

    def populate_models(self):
        db = SessionLocal()
        try:
            # Defined list of allowed models
            allowed_models = [
                "CG125S", "PRIDOR", "EV ICON e", "CG125S GOLD", "CG125",
                "CD70", "CD70 Dream", "CB125F", "CB150F", "CG 150", "CG150"
            ]
            
            self.model_menu.configure(values=allowed_models)
            self.model_menu.set(allowed_models[0] if allowed_models else "")
            if allowed_models:
                self.on_model_change(allowed_models[0])
        finally:
            db.close()

    def on_model_change(self, model_name):
        if model_name == "EV ICON e":
            self.color_menu.configure(values=["RED", "BLACK", "WHITE"])
            self.color_menu.set("RED")
            return

        try:
            prices = price_service.get_active_prices_for_model(model_name)
            colors = []
            for p in prices or []:
                if p.optional_features and isinstance(p.optional_features, dict):
                    c = p.optional_features.get("colors", "")
                    if c:
                        for part in [x.strip() for x in c.split(",")]:
                            if part and part not in colors:
                                colors.append(part)
            self.color_menu.configure(values=colors or [])
            self.color_menu.set(colors[0] if colors else "")
        except Exception:
            self.color_menu.configure(values=[])
            self.color_menu.set("")

class SaveUrlOptionsDialog(ctk.CTkToplevel):
    def __init__(self, parent, url, url_manager, scraper=None, username=None, password=None):
        super().__init__(parent)
        self.url = url
        self.url_manager = url_manager
        self.scraper = scraper
        self.username = username
        self.password = password
        
        self.title("Save URL & Credentials")
        self.geometry("400x420")
        self.resizable(False, False)
        
        # Grid config
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(6, weight=1)
        
        # Header
        ctk.CTkLabel(self, text="Save Configuration", font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, pady=(20, 10))
        
        # URL Display
        self.url_display = ctk.CTkEntry(self, width=350)
        self.url_display.insert(0, self.url)
        self.url_display.configure(state="readonly")
        self.url_display.grid(row=1, column=0, padx=20, pady=10)
        
        # Option 1: Save Settings (URL + Credentials)
        self.btn_default = ctk.CTkButton(self, text="Save Default Settings (Local)", command=self.save_as_default, width=250)
        self.btn_default.grid(row=2, column=0, pady=10)
        
        # Option 2: Browser Bookmarks
        self.btn_bookmark = ctk.CTkButton(self, text="Add to Browser Bookmarks (Ctrl+D)", command=self.save_to_bookmarks, width=250, fg_color="#3498db", hover_color="#2980b9")
        self.btn_bookmark.grid(row=3, column=0, pady=10)
        
        # Option 3: Save as Shortcut
        self.btn_shortcut = ctk.CTkButton(self, text="Save as Desktop Shortcut (.url)", command=self.save_as_shortcut, width=250, fg_color="green", hover_color="darkgreen")
        self.btn_shortcut.grid(row=4, column=0, pady=10)
        
        # Close Button
        self.btn_cancel = ctk.CTkButton(self, text="Cancel", command=self.destroy, fg_color="transparent", border_width=1, text_color=("gray10", "gray90"))
        self.btn_cancel.grid(row=5, column=0, pady=20, sticky="s")
        
    def save_as_default(self):
        try:
            # Save URL
            self.url_manager.save_default_url(self.url)
            
            # Save Credentials
            if self.username or self.password:
                from app.services.settings_service import settings_service
                settings_service.save_honda_credentials(self.username or "", self.password or "")
                
            messagebox.showinfo("Success", "URL and Credentials saved as default settings.")
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save setting: {e}")
            
    def save_to_bookmarks(self):
        if not self.scraper or not self.scraper.page:
            messagebox.showwarning("Browser Not Open", "Please launch the browser first to use this feature.")
            return
            
        try:
            self.scraper.trigger_bookmark_dialog()
            messagebox.showinfo("Action Sent", "Bookmark dialog triggered in the browser.\nPlease complete the save in the browser window.")
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to trigger bookmark: {e}")

    def save_as_shortcut(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".url",
            filetypes=[("Internet Shortcut", "*.url"), ("All Files", "*.*")],
            initialfile="Portal Shortcut.url",
            title="Save URL Shortcut"
        )
        
        if filename:
            try:
                self.url_manager.save_as_shortcut(self.url, filename)
                messagebox.showinfo("Success", f"Shortcut saved to:\n{filename}")
                self.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save shortcut: {e}")
