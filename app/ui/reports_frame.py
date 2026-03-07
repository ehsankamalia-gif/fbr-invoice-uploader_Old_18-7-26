import customtkinter as ctk
from tkinter import messagebox, filedialog, ttk
import csv
from datetime import datetime
from openpyxl import Workbook
from app.db.session import SessionLocal
from app.db.models import Invoice, Motorcycle, Customer, ProductModel, InvoiceItem
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from app.services.report_service import report_service, SalesFilter
from app.services.print_service import print_service
from app.ui.calendar_dialog import CalendarDialog

class ReportsFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # Header
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, padx=20, pady=10, sticky="ew")
        
        self.title = ctk.CTkLabel(self.header_frame, text="Reports & Analytics", font=ctk.CTkFont(size=24, weight="bold"))
        self.title.pack(side="left")
        
        self.refresh_btn = ctk.CTkButton(self.header_frame, text="Refresh Data", command=self.load_data)
        self.refresh_btn.pack(side="right")
        
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        
        self.tab_sales = self.tabview.add("Sales Report")
        self.tab_inventory = self.tabview.add("Inventory Report")
        self.tab_analytics = self.tabview.add("Analytics")
        
        self.setup_sales_tab()
        self.setup_inventory_tab()
        self.setup_analytics_tab()
        
        # Initial Load
        self.load_data()
        
        # Start Auto Refresh
        self.start_auto_refresh()

    def setup_sales_tab(self):
        self.tab_sales.grid_columnconfigure(0, weight=1)
        self.tab_sales.grid_rowconfigure(0, weight=0) # Controls row
        self.tab_sales.grid_rowconfigure(1, weight=1) # Table row
        
        # Controls
        self.sales_controls = ctk.CTkFrame(self.tab_sales, fg_color="transparent")
        self.sales_controls.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        # Filters
        ctk.CTkLabel(self.sales_controls, text="Search:").pack(side="left", padx=(0, 5))
        self.sales_search = ctk.CTkEntry(self.sales_controls, width=300, placeholder_text="Inv #, Buyer, Chassis or Engine")
        self.sales_search.pack(side="left", padx=5)
        
        ctk.CTkLabel(self.sales_controls, text="Status:").pack(side="left", padx=(10, 5))
        self.sales_status_var = ctk.StringVar(value="All")
        self.sales_status_combo = ctk.CTkComboBox(self.sales_controls, values=["All", "Synced", "Pending", "Failed"], variable=self.sales_status_var, width=120)
        self.sales_status_combo.pack(side="left", padx=5)

        ctk.CTkLabel(self.sales_controls, text="Payment:").pack(side="left", padx=(10, 5))
        self.sales_payment_var = ctk.StringVar(value="All")
        self.sales_payment_combo = ctk.CTkComboBox(
            self.sales_controls,
            values=["All", "Cash", "Card", "Cheque", "Pay Order", "Online", "Credit"],
            variable=self.sales_payment_var,
            width=140
        )
        self.sales_payment_combo.pack(side="left", padx=5)

        # Period Filter
        ctk.CTkLabel(self.sales_controls, text="Period:").pack(side="left", padx=(10, 5))
        self.sales_period_var = ctk.StringVar(value="All Time")
        self.sales_period_combo = ctk.CTkComboBox(self.sales_controls, values=["All Time", "Today", "This Month", "Custom"], variable=self.sales_period_var, width=120, command=self.toggle_date_inputs)
        self.sales_period_combo.pack(side="left", padx=5)
        
        self.date_frame = ctk.CTkFrame(self.sales_controls, fg_color="transparent")
        self.date_frame.pack(side="left", padx=0) # Hidden initially by toggle_date_inputs logic
        
        self.start_date_entry = ctk.CTkEntry(self.date_frame, width=100, placeholder_text="YYYY-MM-DD")
        self.start_date_entry.pack(side="left", padx=2)
        
        # Calendar Button for Start Date
        ctk.CTkButton(self.date_frame, text="📅", width=30, command=lambda: self.open_calendar(self.start_date_entry)).pack(side="left", padx=(0, 5))
        
        self.end_date_entry = ctk.CTkEntry(self.date_frame, width=100, placeholder_text="YYYY-MM-DD")
        self.end_date_entry.pack(side="left", padx=2)
        
        # Calendar Button for End Date
        ctk.CTkButton(self.date_frame, text="📅", width=30, command=lambda: self.open_calendar(self.end_date_entry)).pack(side="left", padx=(0, 5))
        
        self.filter_sales_btn = ctk.CTkButton(self.sales_controls, text="Filter", width=80, command=self.load_sales)
        self.filter_sales_btn.pack(side="left", padx=10)

        # Initial Toggle
        self.toggle_date_inputs("All Time")

        self.export_sales_excel_btn = ctk.CTkButton(self.sales_controls, text="Export Excel", command=self.export_sales_excel)
        self.export_sales_excel_btn.pack(side="right")

        self.export_sales_btn = ctk.CTkButton(self.sales_controls, text="Export CSV", command=self.export_sales)
        self.export_sales_btn.pack(side="right", padx=5)
        
        self.view_detail_btn = ctk.CTkButton(self.sales_controls, text="View Details", fg_color="#E67E22", hover_color="#D35400", command=lambda: self.show_sales_detail(None))
        self.view_detail_btn.pack(side="right", padx=10)
        
        self.print_sales_btn = ctk.CTkButton(self.sales_controls, text="Print Invoice", fg_color="green", hover_color="darkgreen", command=self.print_selected_invoice)
        self.print_sales_btn.pack(side="right", padx=10)
        
        # Table Frame
        self.sales_table_frame = ctk.CTkFrame(self.tab_sales)
        self.sales_table_frame.grid(row=1, column=0, sticky="nsew")
        
        # Treeview Scrollbars
        v_scroll = ttk.Scrollbar(self.sales_table_frame)
        v_scroll.pack(side="right", fill="y")
        
        # Treeview
        columns = ("date", "inv_num", "buyer", "chassis", "engine", "total", "status")
        self.sales_tree = ttk.Treeview(self.sales_table_frame, columns=columns, show="headings", yscrollcommand=v_scroll.set)
        
        self.sales_tree.heading("date", text="Date")
        self.sales_tree.heading("inv_num", text="Invoice #")
        self.sales_tree.heading("buyer", text="Buyer")
        self.sales_tree.heading("chassis", text="Chassis Number")
        self.sales_tree.heading("engine", text="Engine Number")
        self.sales_tree.heading("total", text="Total")
        self.sales_tree.heading("status", text="FBR Status")
        
        self.sales_tree.column("date", width=120)
        self.sales_tree.column("inv_num", width=100)
        self.sales_tree.column("buyer", width=150)
        self.sales_tree.column("chassis", width=120)
        self.sales_tree.column("engine", width=120)
        self.sales_tree.column("total", width=100)
        self.sales_tree.column("status", width=80)
        
        self.sales_tree.pack(side="left", fill="both", expand=True)
        v_scroll.config(command=self.sales_tree.yview)
        
        # Configure Tags for Status
        self.sales_tree.tag_configure("synced", foreground="white")
        self.sales_tree.tag_configure("pending", foreground="#E67E22") # Orange
        self.sales_tree.tag_configure("failed", foreground="red")
        
        # Bind double click
        self.sales_tree.bind("<Double-1>", self.show_sales_detail)

    def setup_inventory_tab(self):
        self.tab_inventory.grid_columnconfigure(0, weight=1)
        self.tab_inventory.grid_rowconfigure(0, weight=0) # Controls row
        self.tab_inventory.grid_rowconfigure(1, weight=1) # Table row
        
        # Controls
        self.inv_controls = ctk.CTkFrame(self.tab_inventory, fg_color="transparent")
        self.inv_controls.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        # Filters
        ctk.CTkLabel(self.inv_controls, text="Search:").pack(side="left", padx=(0, 5))
        self.inv_search = ctk.CTkEntry(self.inv_controls, width=200, placeholder_text="Chassis, Engine or Model")
        self.inv_search.pack(side="left", padx=5)
        
        ctk.CTkLabel(self.inv_controls, text="Status:").pack(side="left", padx=(10, 5))
        self.inv_status_var = ctk.StringVar(value="All")
        self.inv_status_combo = ctk.CTkComboBox(self.inv_controls, values=["All", "IN_STOCK", "SOLD"], variable=self.inv_status_var, width=120)
        self.inv_status_combo.pack(side="left", padx=5)

        ctk.CTkLabel(self.inv_controls, text="Color:").pack(side="left", padx=(10, 5))
        self.inv_color_var = ctk.StringVar(value="All")
        self.inv_color_combo = ctk.CTkComboBox(
            self.inv_controls,
            values=["All", "Red", "Black", "Blue", "Other"],
            variable=self.inv_color_var,
            width=120
        )
        self.inv_color_combo.pack(side="left", padx=5)
        
        self.filter_inv_btn = ctk.CTkButton(self.inv_controls, text="Filter", width=80, command=self.load_inventory)
        self.filter_inv_btn.pack(side="left", padx=5)

        self.export_inv_excel_btn = ctk.CTkButton(self.inv_controls, text="Export Excel", command=self.export_inventory_excel)
        self.export_inv_excel_btn.pack(side="right")

        self.export_inv_btn = ctk.CTkButton(self.inv_controls, text="Export CSV", command=self.export_inventory)
        self.export_inv_btn.pack(side="right", padx=5)
        
        # Table Frame
        self.inv_table_frame = ctk.CTkFrame(self.tab_inventory)
        self.inv_table_frame.grid(row=1, column=0, sticky="nsew")
        
        # Treeview Scrollbars
        v_scroll = ttk.Scrollbar(self.inv_table_frame)
        v_scroll.pack(side="right", fill="y")
        
        # Treeview
        columns = ("chassis", "engine", "model", "color", "status")
        self.inv_tree = ttk.Treeview(self.inv_table_frame, columns=columns, show="headings", yscrollcommand=v_scroll.set)
        
        self.inv_tree.heading("chassis", text="Chassis Number")
        self.inv_tree.heading("engine", text="Engine Number")
        self.inv_tree.heading("model", text="Model")
        self.inv_tree.heading("color", text="Color")
        self.inv_tree.heading("status", text="Status")
        
        self.inv_tree.column("chassis", width=150)
        self.inv_tree.column("engine", width=150)
        self.inv_tree.column("model", width=100)
        self.inv_tree.column("color", width=100)
        self.inv_tree.column("status", width=100)
        
        self.inv_tree.pack(side="left", fill="both", expand=True)
        v_scroll.config(command=self.inv_tree.yview)

    def setup_analytics_tab(self):
        self.tab_analytics.grid_columnconfigure(0, weight=1)
        self.tab_analytics.grid_rowconfigure(0, weight=0)
        self.tab_analytics.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self.tab_analytics, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        title = ctk.CTkLabel(header, text="Analytics Overview", font=ctk.CTkFont(size=18, weight="bold"))
        title.pack(side="left")

        info = ctk.CTkLabel(header, text="Uses current Sales filters for calculations", text_color="gray")
        info.pack(side="left", padx=10)

        refresh_btn = ctk.CTkButton(header, text="Refresh Analytics", command=self.load_analytics)
        refresh_btn.pack(side="right")

        metrics_frame = ctk.CTkFrame(self.tab_analytics)
        metrics_frame.grid(row=1, column=0, sticky="nsew")
        metrics_frame.grid_columnconfigure(0, weight=1)
        metrics_frame.grid_columnconfigure(1, weight=1)

        kpi_frame_left = ctk.CTkFrame(metrics_frame, fg_color="transparent")
        kpi_frame_left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        kpi_frame_right = ctk.CTkFrame(metrics_frame, fg_color="transparent")
        kpi_frame_right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        self.analytics_total_sales = ctk.CTkLabel(kpi_frame_left, text="Total Sales: 0.00", font=ctk.CTkFont(size=14, weight="bold"))
        self.analytics_total_sales.pack(anchor="w", pady=5)

        self.analytics_total_invoices = ctk.CTkLabel(kpi_frame_left, text="Invoices: 0", font=ctk.CTkFont(size=14))
        self.analytics_total_invoices.pack(anchor="w", pady=5)

        self.analytics_total_qty = ctk.CTkLabel(kpi_frame_left, text="Total Quantity: 0", font=ctk.CTkFont(size=14))
        self.analytics_total_qty.pack(anchor="w", pady=5)

        self.analytics_avg_invoice = ctk.CTkLabel(kpi_frame_left, text="Avg Invoice: 0.00", font=ctk.CTkFont(size=14))
        self.analytics_avg_invoice.pack(anchor="w", pady=5)

        status_title = ctk.CTkLabel(kpi_frame_right, text="FBR Status Distribution", font=ctk.CTkFont(size=14, weight="bold"))
        status_title.pack(anchor="w", pady=(0, 10))

        status_synced_frame = ctk.CTkFrame(kpi_frame_right, fg_color="transparent")
        status_synced_frame.pack(fill="x", pady=2)
        label_synced = ctk.CTkLabel(status_synced_frame, text="Synced", width=80, anchor="w")
        label_synced.pack(side="left")
        self.analytics_bar_synced = ctk.CTkProgressBar(status_synced_frame)
        self.analytics_bar_synced.pack(side="left", fill="x", expand=True, padx=5)
        self.analytics_label_synced = ctk.CTkLabel(status_synced_frame, text="0%")
        self.analytics_label_synced.pack(side="right")

        status_pending_frame = ctk.CTkFrame(kpi_frame_right, fg_color="transparent")
        status_pending_frame.pack(fill="x", pady=2)
        label_pending = ctk.CTkLabel(status_pending_frame, text="Pending", width=80, anchor="w")
        label_pending.pack(side="left")
        self.analytics_bar_pending = ctk.CTkProgressBar(status_pending_frame)
        self.analytics_bar_pending.pack(side="left", fill="x", expand=True, padx=5)
        self.analytics_label_pending = ctk.CTkLabel(status_pending_frame, text="0%")
        self.analytics_label_pending.pack(side="right")

        status_failed_frame = ctk.CTkFrame(kpi_frame_right, fg_color="transparent")
        status_failed_frame.pack(fill="x", pady=2)
        label_failed = ctk.CTkLabel(status_failed_frame, text="Failed", width=80, anchor="w")
        label_failed.pack(side="left")
        self.analytics_bar_failed = ctk.CTkProgressBar(status_failed_frame)
        self.analytics_bar_failed.pack(side="left", fill="x", expand=True, padx=5)
        self.analytics_label_failed = ctk.CTkLabel(status_failed_frame, text="0%")
        self.analytics_label_failed.pack(side="right")

    def toggle_date_inputs(self, choice):
        if choice == "Custom":
            self.date_frame.pack(side="left", padx=5, before=self.filter_sales_btn)
        else:
            self.date_frame.pack_forget()

    def open_calendar(self, entry_widget):
        current_text = entry_widget.get().strip()
        current_date = None
        if current_text:
             try:
                 current_date = datetime.strptime(current_text, "%Y-%m-%d")
             except ValueError:
                 pass

        def on_date_select(date_str):
            entry_widget.delete(0, "end")
            entry_widget.insert(0, date_str)
            
        CalendarDialog(self, on_date_select, current_date=current_date)

    def load_data(self):
        self.load_sales()
        self.load_inventory()
        self.load_analytics()

    def _build_sales_filter(self):
        search_text = self.sales_search.get().strip()
        status_filter = self.sales_status_var.get()
        period = self.sales_period_var.get()
        payment_filter = self.sales_payment_var.get()

        start_date = None
        end_date = None

        if period == "Custom":
            s_str = self.start_date_entry.get().strip()
            e_str = self.end_date_entry.get().strip()
            if s_str:
                try:
                    start_date = datetime.strptime(s_str, "%Y-%m-%d")
                except ValueError:
                    start_date = None
            if e_str:
                try:
                    end_date = datetime.strptime(e_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                except ValueError:
                    end_date = None

        return SalesFilter(
            search_text=search_text,
            status=status_filter,
            payment_mode=payment_filter,
            period=period,
            start_date=start_date,
            end_date=end_date,
        )

    def load_sales(self):
        for item in self.sales_tree.get_children():
            self.sales_tree.delete(item)

        db = SessionLocal()
        try:
            flt = self._build_sales_filter()
            invoices = report_service.get_sales(db, flt)

            for inv in invoices:
                date_str = inv.datetime.strftime("%Y-%m-%d %H:%M")

                if inv.is_fiscalized:
                    status = "Synced"
                    tag = "synced"
                elif inv.sync_status == "FAILED":
                    status = "Failed"
                    tag = "failed"
                else:
                    status = "Pending"
                    tag = "pending"

                buyer_name = inv.customer.name if inv.customer else "N/A"

                chassis_list = []
                engine_list = []
                for item in inv.items:
                    if item.motorcycle:
                        chassis_list.append(item.motorcycle.chassis_number or "")
                        engine_list.append(item.motorcycle.engine_number or "")

                chassis_str = ", ".join(filter(None, chassis_list))
                engine_str = ", ".join(filter(None, engine_list))

                self.sales_tree.insert("", "end", values=(
                    date_str,
                    inv.invoice_number,
                    buyer_name,
                    chassis_str,
                    engine_str,
                    f"{inv.total_amount:,.2f}",
                    status
                ), tags=(tag,))

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load sales: {e}")
        finally:
            db.close()

    def start_auto_refresh(self):
        self._auto_refresh_loop()

    def _auto_refresh_loop(self):
        try:
            # Only update if frame is visible to prevent background flickering/load
            if self.winfo_exists() and self.winfo_viewable():
                if self.tabview.get() == "Sales Report":
                    self.update_sales_status()
        except Exception:
            pass # Ignore GUI errors if tabview destroyed
            
        if self.winfo_exists():
            self.after(5000, self._auto_refresh_loop)

    def update_sales_status(self):
        items = self.sales_tree.get_children()
        if not items:
            return
            
        inv_map = {} 
        for item_id in items:
            vals = self.sales_tree.item(item_id)['values']
            if vals and len(vals) > 1:
                inv_map[str(vals[1])] = item_id
                
        if not inv_map:
            return
            
        db = SessionLocal()
        try:
            invoices = db.query(Invoice.invoice_number, Invoice.is_fiscalized, Invoice.sync_status).filter(
                Invoice.invoice_number.in_(inv_map.keys())
            ).all()
            
            for inv_num, is_fiscalized, sync_status in invoices:
                item_id = inv_map.get(inv_num)
                if not item_id: continue
                
                if is_fiscalized:
                    status = "Synced"
                    tag = "synced"
                elif sync_status == "FAILED":
                    status = "Failed"
                    tag = "failed"
                else:
                    status = "Pending"
                    tag = "pending"
                
                current_vals = list(self.sales_tree.item(item_id)['values'])
                if len(current_vals) > 6:
                    current_status = current_vals[6]
                    
                    if current_status != status:
                        current_vals[6] = status
                        self.sales_tree.item(item_id, values=current_vals, tags=(tag,))
                    
        except Exception as e:
            print(f"Auto refresh error: {e}")
        finally:
            db.close()

    def load_inventory(self):
        # Clear existing items
        for item in self.inv_tree.get_children():
            self.inv_tree.delete(item)
            
        db = SessionLocal()
        try:
            query = db.query(Motorcycle).options(joinedload(Motorcycle.product_model))
            
            # Apply Filters
            search_text = self.inv_search.get().strip()
            status_filter = self.inv_status_var.get()
            color_filter = self.inv_color_var.get()
            
            if search_text:
                search = f"%{search_text}%"
                query = query.join(ProductModel).filter(
                    or_(
                        Motorcycle.chassis_number.ilike(search),
                        Motorcycle.engine_number.ilike(search),
                        ProductModel.model_name.ilike(search)
                    )
                )
                
            if status_filter and status_filter != "All":
                query = query.filter(Motorcycle.status == status_filter)

            if color_filter and color_filter != "All":
                query = query.filter(Motorcycle.color == color_filter)
            
            bikes = query.all()
            
            for bike in bikes:
                self.inv_tree.insert("", "end", values=(
                    bike.chassis_number,
                    bike.engine_number,
                    bike.product_model.model_name if bike.product_model else "Unknown",
                    bike.color,
                    bike.status
                ))
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load inventory: {e}")
        finally:
            db.close()

    def export_sales(self):
        filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if not filename:
            return
            
        db = SessionLocal()
        try:
            query = self._build_sales_query(db)
            invoices = query.options(
                joinedload(Invoice.customer),
                joinedload(Invoice.items).joinedload(InvoiceItem.motorcycle)
            ).all()
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["Invoice No", "Date", "Buyer", "CNIC", "Chassis Number", "Engine Number", "Total Amount", "Tax", "Further Tax", "FBR Status"])
                for inv in invoices:
                    # Get chassis and engine numbers
                    chassis_list = []
                    engine_list = []
                    for item in inv.items:
                        if item.motorcycle:
                            chassis_list.append(item.motorcycle.chassis_number or "")
                            engine_list.append(item.motorcycle.engine_number or "")
                    
                    chassis_str = ", ".join(filter(None, chassis_list))
                    engine_str = ", ".join(filter(None, engine_list))

                    writer.writerow([
                        inv.invoice_number,
                        inv.datetime,
                        inv.customer.name if inv.customer else "",
                        inv.customer.cnic if inv.customer else "",
                        chassis_str,
                        engine_str,
                        inv.total_amount,
                        inv.total_tax_charged,
                        inv.total_further_tax,
                        "Fiscalized" if inv.is_fiscalized else "Pending"
                    ])
            messagebox.showinfo("Success", "Sales report exported successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {e}")
        finally:
            db.close()

    def export_sales_excel(self):
        filename = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel Files", "*.xlsx *.xlsm")])
        if not filename:
            return

        db = SessionLocal()
        try:
            query = self._build_sales_query(db)
            invoices = query.all()

            wb = Workbook()
            ws = wb.active
            ws.title = "Sales"

            headers = [
                "Invoice No",
                "Date",
                "Buyer",
                "CNIC",
                "Payment Mode",
                "Chassis Number",
                "Engine Number",
                "Total Amount",
                "Tax",
                "Further Tax",
                "FBR Status"
            ]
            ws.append(headers)

            for inv in invoices:
                chassis_list = []
                engine_list = []
                for item in inv.items:
                    if item.motorcycle:
                        chassis_list.append(item.motorcycle.chassis_number or "")
                        engine_list.append(item.motorcycle.engine_number or "")

                chassis_str = ", ".join(filter(None, chassis_list))
                engine_str = ", ".join(filter(None, engine_list))

                if inv.is_fiscalized:
                    status = "Fiscalized"
                elif inv.sync_status == "FAILED":
                    status = "Failed"
                else:
                    status = "Pending"

                ws.append([
                    inv.invoice_number,
                    inv.datetime,
                    inv.customer.name if inv.customer else "",
                    inv.customer.cnic if inv.customer else "",
                    inv.payment_mode or "",
                    chassis_str,
                    engine_str,
                    inv.total_amount,
                    inv.total_tax_charged,
                    inv.total_further_tax,
                    status
                ])

            wb.save(filename)
            messagebox.showinfo("Success", "Sales report (Excel) exported successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {e}")
        finally:
            db.close()

    def load_analytics(self):
        db = SessionLocal()
        try:
            query = self._build_sales_query(db)
            invoices = query.all()

            total_sales = sum(inv.total_amount for inv in invoices)
            total_invoices = len(invoices)
            total_qty = sum(inv.total_quantity for inv in invoices)
            avg_invoice = total_sales / total_invoices if total_invoices else 0

            self.analytics_total_sales.configure(text=f"Total Sales: {total_sales:,.2f}")
            self.analytics_total_invoices.configure(text=f"Invoices: {total_invoices}")
            self.analytics_total_qty.configure(text=f"Total Quantity: {total_qty:,.2f}")
            self.analytics_avg_invoice.configure(text=f"Avg Invoice: {avg_invoice:,.2f}")

            synced = sum(1 for inv in invoices if inv.is_fiscalized)
            failed = sum(1 for inv in invoices if inv.sync_status == "FAILED")
            pending = total_invoices - synced - failed

            def safe_ratio(count):
                return (count / total_invoices) if total_invoices else 0

            synced_ratio = safe_ratio(synced)
            failed_ratio = safe_ratio(failed)
            pending_ratio = safe_ratio(pending)

            self.analytics_bar_synced.set(synced_ratio)
            self.analytics_bar_failed.set(failed_ratio)
            self.analytics_bar_pending.set(pending_ratio)

            self.analytics_label_synced.configure(text=f"{synced_ratio*100:.0f}%")
            self.analytics_label_failed.configure(text=f"{failed_ratio*100:.0f}%")
            self.analytics_label_pending.configure(text=f"{pending_ratio*100:.0f}%")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load analytics: {e}")
        finally:
            db.close()

    def show_sales_detail(self, event):
        selection = self.sales_tree.selection()
        if not selection:
            return
            
        item = self.sales_tree.item(selection[0])
        # Values are (Date, Invoice #, Buyer, Total, Status)
        inv_num = item['values'][1]
        
        self.configure(cursor="wait")
        self.update_idletasks()
        
        db = SessionLocal()
        try:
            inv = db.query(Invoice).options(
                joinedload(Invoice.customer), 
                joinedload(Invoice.items).joinedload(InvoiceItem.motorcycle).joinedload(Motorcycle.product_model)
            ).filter(Invoice.invoice_number == inv_num).first()
            
            if inv:
                self.open_sales_detail_dialog(inv)
            else:
                messagebox.showerror("Error", "Invoice not found in database.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch invoice details: {e}")
        finally:
            db.close()
            self.configure(cursor="")

    def _format_error_message(self, msg):
        """Helper to make error messages user-friendly."""
        if not msg:
            return "Unknown Error"
            
        # Common FBR/Network Errors
        if "ConnectionError" in msg:
            return "Internet Connection Failed. Please check your network."
        if "Timeout" in msg:
            return "FBR Server Timeout. The server might be busy or down."
        if "RetryError" in msg:
            # Try to extract the underlying cause if visible
            if "ConnectionError" in msg:
                 return "Internet Connection Failed (Retried multiple times)."
            return "Upload failed after multiple attempts. FBR Server may be down."
            
        return msg

    def open_sales_detail_dialog(self, inv):
        dialog = ctk.CTkToplevel(self)
        
        status_str = "SYNCED"
        if inv.sync_status == "FAILED": status_str = "FAILED"
        elif not inv.is_fiscalized: status_str = "PENDING"
            
        dialog.title(f"Invoice Detail: {inv.invoice_number} [{status_str}]")
        dialog.geometry("900x700")
        dialog.grab_set() # Modal behavior
        
        # Main Scrollable Frame
        scroll_frame = ctk.CTkScrollableFrame(dialog)
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # --- Status Banner (if not synced) ---
        if inv.sync_status == "FAILED":
             banner = ctk.CTkFrame(scroll_frame, fg_color="#FFCDD2") # Light Red
             banner.pack(fill="x", pady=5)
             
             clean_msg = self._format_error_message(inv.fbr_response_message)
             ctk.CTkLabel(banner, text=f"⚠️ Upload Failed: {clean_msg}", text_color="#C62828", font=ctk.CTkFont(weight="bold")).pack(pady=10)
        elif not inv.is_fiscalized:
             banner = ctk.CTkFrame(scroll_frame, fg_color="#FFE0B2") # Light Orange
             banner.pack(fill="x", pady=5)
             ctk.CTkLabel(banner, text=f"⏳ Pending Upload: {inv.fbr_response_message or 'Waiting for connection...'}", text_color="#EF6C00", font=ctk.CTkFont(weight="bold")).pack(pady=10)

        # --- Customer Info ---
        cust_frame = ctk.CTkFrame(scroll_frame)
        cust_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(cust_frame, text="Customer Information", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=5)
        
        if inv.customer:
            grid_frame = ctk.CTkFrame(cust_frame, fg_color="transparent")
            grid_frame.pack(fill="x", padx=10, pady=5)
            
            fields = [
                ("Name:", inv.customer.name),
                ("Father Name:", inv.customer.father_name),
                ("CNIC:", inv.customer.cnic),
                ("Phone:", inv.customer.phone),
                ("NTN:", inv.customer.ntn),
                ("Type:", inv.customer.type),
                ("Address:", inv.customer.address)
            ]
            
            for i, (label, value) in enumerate(fields):
                row = i // 2
                col = (i % 2) * 2
                ctk.CTkLabel(grid_frame, text=label, font=ctk.CTkFont(weight="bold")).grid(row=row, column=col, sticky="w", padx=5, pady=2)
                ctk.CTkLabel(grid_frame, text=str(value or "N/A")).grid(row=row, column=col+1, sticky="w", padx=5, pady=2)
        else:
            ctk.CTkLabel(cust_frame, text="No Customer Linked").pack()

        # --- Invoice Info ---
        inv_frame = ctk.CTkFrame(scroll_frame)
        inv_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(inv_frame, text="Invoice Information", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=5)
        
        grid_frame = ctk.CTkFrame(inv_frame, fg_color="transparent")
        grid_frame.pack(fill="x", padx=10, pady=5)
        
        fields = [
            ("Invoice #:", inv.invoice_number),
            ("Date:", inv.datetime.strftime("%Y-%m-%d %H:%M:%S")),
            ("POS ID:", inv.pos_id),
            ("USIN:", inv.usin),
            ("Payment Mode:", inv.payment_mode),
            ("Sync Status:", inv.sync_status),
            ("Status Updated:", inv.status_updated_at.strftime("%Y-%m-%d %H:%M:%S") if inv.status_updated_at else "N/A")
        ]
        
        for i, (label, value) in enumerate(fields):
            row = i // 2
            col = (i % 2) * 2
            ctk.CTkLabel(grid_frame, text=label, font=ctk.CTkFont(weight="bold")).grid(row=row, column=col, sticky="w", padx=5, pady=2)
            
            # Color code Sync Status
            text_color = "text_color" # Default
            if label == "Sync Status:":
                if value == "SYNCED":
                    text_color = "green"
                elif value == "FAILED":
                    text_color = "red"
                elif value == "PENDING":
                    text_color = "#E67E22"
            
            lbl = ctk.CTkLabel(grid_frame, text=str(value or "N/A"))
            if text_color != "text_color":
                lbl.configure(text_color=text_color, font=ctk.CTkFont(weight="bold"))
            lbl.grid(row=row, column=col+1, sticky="w", padx=5, pady=2)

        # --- Items ---
        items_frame = ctk.CTkFrame(scroll_frame)
        items_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(items_frame, text="Invoice Items", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=5)
        
        # Items Table Header
        header_frame = ctk.CTkFrame(items_frame)
        header_frame.pack(fill="x", padx=5)
        headers = ["Item", "Qty", "Rate", "Value", "Tax", "Total"]
        for col, h in enumerate(headers):
            ctk.CTkLabel(header_frame, text=h, font=ctk.CTkFont(weight="bold"), width=100).grid(row=0, column=col, padx=2)
            
        # Items List
        for item in inv.items:
            row_frame = ctk.CTkFrame(items_frame, fg_color="transparent")
            row_frame.pack(fill="x", padx=5, pady=2)
            
            vals = [
                item.item_name,
                f"{item.quantity}",
                f"{item.sale_value/item.quantity if item.quantity else 0:,.2f}", # Approx rate
                f"{item.sale_value:,.2f}",
                f"{item.tax_charged:,.2f}",
                f"{item.total_amount:,.2f}"
            ]
            for col, v in enumerate(vals):
                ctk.CTkLabel(row_frame, text=v, width=100).grid(row=0, column=col, padx=2)
                
        # --- Motorcycle Information ---
        has_motorcycles = any(item.motorcycle for item in inv.items)
        if has_motorcycles:
            moto_frame = ctk.CTkFrame(scroll_frame)
            moto_frame.pack(fill="x", pady=5)
            
            ctk.CTkLabel(moto_frame, text="Motorcycle Information", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=5)
            
            for item in inv.items:
                if item.motorcycle:
                    # Item Header
                    ctk.CTkLabel(moto_frame, text=f"• {item.item_name}", font=ctk.CTkFont(weight="bold"), anchor="w").pack(fill="x", padx=20, pady=(5,0))
                    
                    # Details Grid
                    details_frame = ctk.CTkFrame(moto_frame, fg_color="transparent")
                    details_frame.pack(fill="x", padx=30, pady=2)
                    
                    m_fields = [
                        ("Chassis Number:", item.motorcycle.chassis_number),
                        ("Engine Number:", item.motorcycle.engine_number),
                        ("Color:", item.motorcycle.color),
                        ("Model Year:", item.motorcycle.year)
                    ]
                    
                    for k, (lbl, val) in enumerate(m_fields):
                        r = k // 2
                        c = (k % 2) * 2
                        ctk.CTkLabel(details_frame, text=lbl, font=ctk.CTkFont(weight="bold")).grid(row=r, column=c, sticky="w", padx=5)
                        ctk.CTkLabel(details_frame, text=str(val or "N/A")).grid(row=r, column=c+1, sticky="w", padx=5)
            
            # Add some spacing
            ctk.CTkLabel(moto_frame, text="").pack(pady=2)

        # --- Financial Summary ---
        sum_frame = ctk.CTkFrame(scroll_frame)
        sum_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(sum_frame, text="Financial Summary", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=5)
        
        grid_frame = ctk.CTkFrame(sum_frame, fg_color="transparent")
        grid_frame.pack(fill="x", padx=10, pady=5)
        
        fields = [
            ("Total Sale Value:", f"{inv.total_sale_value:,.2f}"),
            ("Total Tax:", f"{inv.total_tax_charged:,.2f}"),
            ("Further Tax:", f"{inv.total_further_tax:,.2f}"),
            ("Discount:", f"{inv.discount:,.2f}"),
            ("Grand Total:", f"{inv.total_amount:,.2f}")
        ]
        
        for i, (label, value) in enumerate(fields):
            ctk.CTkLabel(grid_frame, text=label, font=ctk.CTkFont(weight="bold")).grid(row=i, column=0, sticky="w", padx=20, pady=2)
            ctk.CTkLabel(grid_frame, text=value).grid(row=i, column=1, sticky="e", padx=20, pady=2)

        # --- FBR Response ---
        if inv.fbr_response_message or inv.fbr_invoice_number:
            fbr_frame = ctk.CTkFrame(scroll_frame)
            fbr_frame.pack(fill="x", pady=5)
            
            ctk.CTkLabel(fbr_frame, text="FBR Response Details", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=5)
            
            grid_frame = ctk.CTkFrame(fbr_frame, fg_color="transparent")
            grid_frame.pack(fill="x", padx=10, pady=5)
            
            fields = [
                ("FBR Invoice #:", inv.fbr_invoice_number),
                ("Response Code:", inv.fbr_response_code),
                ("Message:", inv.fbr_response_message)
            ]
            
            for i, (label, value) in enumerate(fields):
                ctk.CTkLabel(grid_frame, text=label, font=ctk.CTkFont(weight="bold")).grid(row=i, column=0, sticky="w", padx=5, pady=2)
                ctk.CTkLabel(grid_frame, text=str(value or "N/A"), wraplength=600).grid(row=i, column=1, sticky="w", padx=5, pady=2)

        # --- Print Action ---
        btn_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=20)
        
        def _do_print():
            try:
                success, msg = print_service.print_invoice(inv)
                if not success:
                    messagebox.showerror("Print Error", msg)
            except Exception as e:
                messagebox.showerror("Error", f"An error occurred while printing: {e}")

        ctk.CTkButton(btn_frame, text="🖨 Print Invoice", command=_do_print, 
                      height=40, font=ctk.CTkFont(size=14, weight="bold"),
                      fg_color="#00897B", hover_color="#00695C").pack()

    def show_inventory_detail(self, event):
        selection = self.inv_tree.selection()
        if not selection:
            return
            
        item = self.inv_tree.item(selection[0])
        # Values are (chassis, engine, model, color, status)
        chassis = item['values'][0]
        
        db = SessionLocal()
        try:
            bike = db.query(Motorcycle).options(
                joinedload(Motorcycle.product_model),
                joinedload(Motorcycle.supplier)
            ).filter(Motorcycle.chassis_number == chassis).first()
            
            if bike:
                self.open_inventory_detail_dialog(bike)
        finally:
            db.close()

    def ensure_visible_sales(self, event):
        try:
            focus_item = self.sales_tree.focus()
            if focus_item:
                self.sales_tree.see(focus_item)
        except Exception:
            pass

    def ensure_visible_inv(self, event):
        try:
            focus_item = self.inv_tree.focus()
            if focus_item:
                self.inv_tree.see(focus_item)
        except Exception:
            pass

    def open_inventory_detail_dialog(self, bike):
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Motorcycle Detail: {bike.chassis_number}")
        dialog.geometry("600x500")
        
        # Main Frame
        main_frame = ctk.CTkFrame(dialog)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(main_frame, text="Motorcycle Details", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=10)
        
        grid_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        grid_frame.pack(fill="x", padx=10, pady=5)
        
        model_name = bike.product_model.model_name if bike.product_model else "Unknown"
        make = bike.product_model.make if bike.product_model else "Honda"
        supplier_name = bike.supplier.name if bike.supplier else "N/A"
        
        fields = [
            ("Make:", make),
            ("Model:", model_name),
            ("Year:", bike.year),
            ("Color:", bike.color),
            ("Chassis Number:", bike.chassis_number),
            ("Engine Number:", bike.engine_number),
            ("VIN:", bike.vin),
            ("Status:", bike.status),
            ("Cost Price:", f"{bike.cost_price:,.2f}"),
            ("Sale Price:", f"{bike.sale_price:,.2f}"),
            ("Supplier:", supplier_name),
            ("Purchase Date:", bike.purchase_date.strftime("%Y-%m-%d") if bike.purchase_date else "N/A")
        ]
        
        for i, (label, value) in enumerate(fields):
            ctk.CTkLabel(grid_frame, text=label, font=ctk.CTkFont(weight="bold")).grid(row=i, column=0, sticky="w", padx=10, pady=5)
            ctk.CTkLabel(grid_frame, text=str(value or "N/A")).grid(row=i, column=1, sticky="w", padx=10, pady=5)


    def print_selected_invoice(self):
        selection = self.sales_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select an invoice to print.")
            return
            
        item = self.sales_tree.item(selection[0])
        # Values are (Date, Invoice #, Buyer, Total, Status)
        invoice_number = str(item['values'][1]) 
        
        db = SessionLocal()
        try:
            invoice = db.query(Invoice).filter(Invoice.invoice_number == invoice_number).options(
                joinedload(Invoice.customer),
                joinedload(Invoice.items).joinedload(InvoiceItem.motorcycle).joinedload(Motorcycle.product_model)
            ).first()
            
            if not invoice:
                messagebox.showerror("Error", "Invoice not found in database.")
                return
                
            success, message = print_service.print_invoice(invoice)
            if not success:
                messagebox.showerror("Error", f"Failed to print invoice: {message}")
                
        except Exception as e:
            messagebox.showerror("Error", f"Print error: {e}")
        finally:
            db.close()


    def export_inventory(self):
        filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if not filename:
            return
            
        db = SessionLocal()
        try:
            bikes = db.query(Motorcycle).options(joinedload(Motorcycle.product_model)).all()
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["Chassis", "Engine", "Make", "Model", "Year", "Color", "Cost", "Price", "Status"])
                for bike in bikes:
                    model_name = bike.product_model.model_name if bike.product_model else "Unknown"
                    make = bike.product_model.make if bike.product_model else "Honda"
                    writer.writerow([
                        bike.chassis_number,
                        bike.engine_number,
                        make,
                        model_name,
                        bike.year,
                        bike.color,
                        bike.cost_price,
                        bike.sale_price,
                        bike.status
                    ])
            messagebox.showinfo("Success", "Inventory report exported successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {e}")
        finally:
            db.close()

    def export_inventory_excel(self):
        filename = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel Files", "*.xlsx *.xlsm")])
        if not filename:
            return

        db = SessionLocal()
        try:
            query = db.query(Motorcycle).options(joinedload(Motorcycle.product_model))

            search_text = self.inv_search.get().strip()
            status_filter = self.inv_status_var.get()
            color_filter = self.inv_color_var.get()

            if search_text:
                search = f"%{search_text}%"
                query = query.join(ProductModel).filter(
                    or_(
                        Motorcycle.chassis_number.ilike(search),
                        Motorcycle.engine_number.ilike(search),
                        ProductModel.model_name.ilike(search)
                    )
                )

            if status_filter and status_filter != "All":
                query = query.filter(Motorcycle.status == status_filter)

            if color_filter and color_filter != "All":
                query = query.filter(Motorcycle.color == color_filter)

            bikes = query.all()

            wb = Workbook()
            ws = wb.active
            ws.title = "Inventory"

            headers = ["Chassis", "Engine", "Make", "Model", "Year", "Color", "Cost", "Price", "Status"]
            ws.append(headers)

            for bike in bikes:
                model_name = bike.product_model.model_name if bike.product_model else "Unknown"
                make = bike.product_model.make if bike.product_model else "Honda"
                ws.append([
                    bike.chassis_number,
                    bike.engine_number,
                    make,
                    model_name,
                    bike.year,
                    bike.color,
                    bike.cost_price,
                    bike.sale_price,
                    bike.status
                ])

            wb.save(filename)
            messagebox.showinfo("Success", "Inventory report (Excel) exported successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {e}")
        finally:
            db.close()
