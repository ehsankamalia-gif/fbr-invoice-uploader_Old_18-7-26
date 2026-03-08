import customtkinter as ctk
from tkinter import messagebox, filedialog
import re
from datetime import datetime
import requests
import qrcode
from PIL import Image
from tenacity import RetryError
from app.db.session import SessionLocal, init_db
from app.services.invoice_service import invoice_service
from app.services.price_service import price_service
from app.services.settings_service import settings_service
from app.services.ocr_service import ocr_service
from app.api.schemas import InvoiceCreate, InvoiceItemCreate
from app.ui.inventory_frame import InventoryFrame
from app.ui.reports_frame import ReportsFrame
from app.ui.dealer_frame import DealerFrame
from app.ui.customer_frame import CustomerFrame
from app.ui.print_invoice_frame import PrintInvoiceFrame
from app.ui.price_list_dialog import PriceListDialog
from app.ui.fbr_settings_dialog import FBRSettingsDialog
from app.ui.db_settings_dialog import DatabaseSettingsDialog
from app.ui.backup_frame import BackupFrame
from app.ui.spare_ledger_frame import SpareLedgerFrame
from app.services.dealer_service import dealer_service
from app.services.customer_service import customer_service
from app.services.backup_service import backup_service
from app.services.form_capture_service import form_capture_service
from app.services.update_service import UpdateService
from app.services.sync_service import sync_service
from app.ui.captured_data_frame import CapturedDataFrame
from app.ui.welcome_frame import WelcomeFrame
from app.ui.autocomplete_entry import AutocompleteEntry
from app.ui.stock_summary_frame import StockSummaryFrame

from app.utils.auto_git import auto_git_manager
from app.utils.price_data import price_manager
import app.core.config as config
import threading
import webbrowser

from reporting.server import start_reporting_server

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

from app.db.models import Motorcycle, Invoice, Customer, CustomerType, CapturedData


import logging

# Configure logging
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ToolTip(object):
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.id = None
        self.x = self.y = 0
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(500, self.showtip)

    def unschedule(self):
        id = self.id
        self.id = None
        if id:
            self.widget.after_cancel(id)

    def showtip(self, event=None):
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20
        self.tip_window = ctk.CTkToplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry("+%d+%d" % (x, y))
        
        label = ctk.CTkLabel(self.tip_window, text=self.text, text_color="white", fg_color="#333333", corner_radius=5, width=150)
        label.pack()

    def hidetip(self):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Honda FBR Invoice Uploader")
        self.geometry("800x600")

        # Initialize DB
        init_db()
        
        # Migrate prices if needed
        self.migrate_prices()

        # Start reporting portal in background (non-blocking)
        start_reporting_server()

        # Grid Configuration for Top-Bar Layout
        self.grid_columnconfigure(0, weight=1) # Full width content
        self.grid_rowconfigure(0, weight=0)    # Header (Top Bar)
        self.grid_rowconfigure(1, weight=1)    # Main Content Area

        # Define Menu Structure
        self.setup_navigation_structure()
        self.is_dealer_selected = False

        # Create Navigation Bars
        self.create_menu_bar()
        
        self.create_home_frame()
        self.create_inventory_frame()
        self.create_invoice_frame()
        self.create_reports_frame()
        self.create_dealer_frame()
        self.create_customer_frame()
        self.create_print_frame()
        self.create_backup_frame()
        self.create_spare_ledger_frame()
        self.create_captured_data_frame()

        self.select_frame_by_name("home")
        
        # Show Welcome Screen
        self.create_welcome_frame()
        
        # Start Backup Scheduler if enabled
        backup_service.start_scheduler()
        # Start ledger auto-close daily check
        self.after(60000, self.ledger_auto_close_tick)
        
        # Start Sync Service
        sync_service.set_status_callback(self.on_sync_status_change)
        sync_service.start()
        
        # Register Data Capture Callback
        form_capture_service.on_data_captured = self.on_browser_data_captured
        
        # Handle Window Close
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Keyboard Shortcuts
        self.bind("<Escape>", self.on_escape)

        # Initialize Auto-Git Sync if enabled
        self.update_auto_sync_status()

    def update_auto_sync_status(self):
        """Starts or stops the auto-sync manager based on current settings."""
        config = settings_service.get_app_config()
        if config.get("auto_push_enabled", False):
            # Pass a callback to show sync status if desired
            auto_git_manager.start()
            logger.info("Auto-Git Sync feature is ENABLED")
        else:
            auto_git_manager.stop()
            logger.info("Auto-Git Sync feature is DISABLED")

    def on_escape(self, event=None):
        pass # Sidebar toggle removed

    def on_closing(self):
        """Clean up resources before closing"""
        try:
            auto_git_manager.stop()
        except Exception:
            pass
        try:
            form_capture_service.stop_capture_session()
        except Exception as e:
            print(f"Error stopping capture: {e}")
        try:
            sync_service.stop()
        except Exception as e:
            print(f"Error stopping sync service: {e}")
        self.destroy()

    def on_browser_data_captured(self, chassis):
        """Called when data is captured in the background browser."""
        # Use after() to ensure UI updates on main thread
        if self.winfo_exists():
             self.after(0, lambda: self._handle_bg_capture(chassis))

    def _handle_bg_capture(self, chassis):
        # If we are on the invoice frame, try to auto-fill
        # and maybe show a notification
        if hasattr(self, "invoice_frame") and self.invoice_frame.winfo_viewable():
            if chassis:
                # Set chassis and trigger auto-fill
                self.chassis_var.set(chassis)
                self.auto_fill_chassis()
                messagebox.showinfo("Data Captured", f"Successfully imported details for chassis: {chassis}")
            else:
                messagebox.showinfo("Data Captured", "New data was captured from the browser.\nYou can now use 'Fetch Last' or enter a chassis number.")

    def fetch_last_captured_record(self):
        """Fetches the most recent record from CapturedData and fills the form."""
        db = SessionLocal()
        try:
            last = db.query(CapturedData).order_by(CapturedData.created_at.desc()).first()
            if last:
                self.chassis_var.set(last.chassis_number)
                self.auto_fill_chassis()
                messagebox.showinfo("Success", f"Loaded last captured data for {last.chassis_number}")
            else:
                messagebox.showwarning("No Data", "No captured data found in database.")
        except Exception as e:
             messagebox.showerror("Error", f"Failed to fetch captured data: {e}")
        finally:
             db.close()

    def on_sync_status_change(self, is_online, pending_count):
        """Called by background thread, so must use after to update UI safely"""
        if self.winfo_exists():
             self.after(0, lambda: self._update_sync_ui(is_online, pending_count))

    def _update_sync_ui(self, is_online, pending_count):
        if not self.winfo_exists(): return
        
        try:
            if is_online:
                self.sync_status_dot.configure(text_color="#2ECC71") # Green
                self.sync_status_label.configure(text="Online")
            else:
                self.sync_status_dot.configure(text_color="#E74C3C") # Red
                self.sync_status_label.configure(text="Offline")
                
            if pending_count > 0:
                self.pending_label.configure(text=f"{pending_count} Pending Uploads")
            else:
                self.pending_label.configure(text="")
        except Exception:
            pass

    def ledger_auto_close_tick(self):
        try:
            from app.services.spare_ledger_service import spare_ledger_service
            spare_ledger_service.auto_close_daily_check()
        except Exception:
            pass
        finally:
            # Run again in 60 seconds
            if self.winfo_exists():
                self.after(60000, self.ledger_auto_close_tick)

    def migrate_prices(self):
        # Import data from legacy JSON if DB is empty
        try:
            legacy_data = price_manager.get_all()
            price_service.bulk_import_from_json(legacy_data)
        except Exception as e:
            print(f"Migration warning: {e}")

    def setup_navigation_structure(self):
        """Defines the hierarchical menu structure."""
        self.menu_structure = {
            "dashboard": {
                "label": "Dashboard", 
                "command": lambda: self.select_frame_by_name("home"),
                "subitems": [] 
            },
            "invoice": {
                "label": "Invoices",
                "command": None,
                "subitems": [
                    ("New Invoice", "invoice", self.invoice_button_event),
                    ("Print Invoice", "print_invoice", self.print_invoice_button_event),
                    ("Reports", "reports", self.reports_button_event),
                    ("Web Reporting Portal", None, self.open_reporting_portal),
                ]
            },
            "inventory": {
                "label": "Inventory",
                "command": None,
                "subitems": [
                    ("Inventory Stock", "inventory", self.inventory_button_event),
                    ("Captured Customer Data", "captured_data", self.captured_data_button_event),
                    ("Launch Capture Browser", "capture_live", self.form_capture_button_event),
                    ("Customers", "customer", self.customer_button_event),
                    ("Dealers", "dealer", self.dealer_button_event),
                    ("Price List", "pricelist", self.open_price_list)
                ]
            },
            "system": {
                "label": "System",
                "command": None,
                "subitems": [
                    ("Backup & Restore", "backup", self.backup_button_event),
                    ("FBR Settings", "settings", self.open_fbr_settings),
                    ("DB Settings", "db_settings", self.open_db_settings),
                    ("Spare Ledger", "spare_ledger", self.spare_ledger_button_event),
                    ("Check Updates", "update", self.check_updates)
                ]
            }
        }
        
        self.top_nav_buttons = {}
        self.active_menu_frame = None
        self.active_menu_key = None

    def create_menu_bar(self):
        """Creates the main horizontal menu bar."""
        # Main Header Frame
        self.header_frame = ctk.CTkFrame(self, height=40, corner_radius=0, fg_color=("gray95", "gray10"))
        self.header_frame.grid(row=0, column=0, sticky="ew")
        self.header_frame.grid_columnconfigure(2, weight=1) # Spacer 
        
        # 1. Logo / Brand (Left)
        brand_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        brand_frame.grid(row=0, column=0, padx=(10, 20), sticky="w")
        
        ctk.CTkLabel(brand_frame, text="HONDA", 
                     font=ctk.CTkFont(family="Arial", size=16, weight="bold"),
                     text_color=("#C0392B", "#E74C3C")).pack(side="left")
        
        ctk.CTkLabel(brand_frame, text="| FBR", 
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="gray").pack(side="left", padx=5)

        # 2. Menu Items (Next to logo)
        self.nav_bar_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.nav_bar_frame.grid(row=0, column=1, sticky="w")
        
        for key, data in self.menu_structure.items():
            cmd = data['command']
            if not cmd:
                # Use default arguments to capture loop variable
                cmd = lambda k=key: self.toggle_menu(k)
                
            btn = ctk.CTkButton(self.nav_bar_frame, 
                                text=data['label'],
                                command=cmd,
                                width=30, height=30,
                                corner_radius=4,
                                font=ctk.CTkFont(size=13),
                                fg_color="transparent",
                                text_color=("gray10", "gray90"),
                                hover_color=("gray80", "gray25"))
            btn.pack(side="left", padx=2)
            
            # Bind hover event for auto-opening
            btn.bind("<Enter>", lambda e, k=key: self.on_menu_hover(k))
            
            self.top_nav_buttons[key] = btn

        # 3. Right Side Utilities
        right_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        right_frame.grid(row=0, column=3, padx=10, sticky="e")

        # Environment Badge
        self.env_badge = ctk.CTkLabel(right_frame, text="ENV", 
                                      font=ctk.CTkFont(size=10, weight="bold"),
                                      text_color="white", corner_radius=4)
        self.env_badge.pack(side="left", padx=10)
        self.update_env_badge()

        # Sync Status
        self.sync_status_dot = ctk.CTkLabel(right_frame, text="●", font=("Arial", 14), text_color="gray")
        self.sync_status_dot.pack(side="left")
        self.sync_status_label = ctk.CTkLabel(right_frame, text="Checking...", font=("Arial", 11))
        self.sync_status_label.pack(side="left", padx=5)
        
        # Sync Button
        ctk.CTkButton(right_frame, text="↻", width=25, height=25,
                      command=lambda: sync_service.trigger_sync_now()).pack(side="left", padx=5)
        
        # Exit Button
        ctk.CTkButton(right_frame, text="Exit", width=50, height=25,
                      fg_color="#C0392B", hover_color="#E74C3C",
                      command=self.on_closing).pack(side="left", padx=10)

    def on_menu_hover(self, key):
        """Opens the menu on hover if it's not already open."""
        if self.active_menu_key != key:
            self.toggle_menu(key)

    def toggle_menu(self, key):
        """Toggles the dropdown menu for the given key."""
        if self.active_menu_frame:
            # If clicking same button, close and return
            if self.active_menu_key == key:
                self.close_menu()
                return
            self.close_menu()

        self.active_menu_key = key
        btn = self.top_nav_buttons[key]
        btn.configure(fg_color=("gray80", "gray25"))
        
        # Create Dropdown Frame
        self.active_menu_frame = ctk.CTkFrame(self, corner_radius=4, border_width=1, border_color="gray50", fg_color=("white", "gray20"))
        
        # Calculate position: x = button x absolute position
        x = btn.winfo_x() + self.nav_bar_frame.winfo_x() + self.header_frame.winfo_x() + 10 
        y = 40 # Header height
        
        # Populate
        data = self.menu_structure[key]
        for text, name, command in data['subitems']:
            sub_btn = ctk.CTkButton(self.active_menu_frame, text=text, anchor="w",
                                  command=lambda c=command: self._menu_item_click(c),
                                  width=160, height=28,
                                  fg_color="transparent",
                                  text_color=("black", "white"),
                                  hover_color=("gray90", "gray30"))
            sub_btn.pack(fill="x", padx=1, pady=1)
            
        self.active_menu_frame.place(x=x, y=y)
        self.active_menu_frame.lift()
        
        # Bind global click to close menu
        self.after(100, lambda: self.bind_all("<Button-1>", self.check_menu_close, add="+"))
        
    def _menu_item_click(self, command):
        self.close_menu()
        command()

    def check_menu_close(self, event):
        if not self.active_menu_frame:
            self.unbind_all("<Button-1>")
            return

        # Check if clicked widget is inside menu
        widget = event.widget
        try:
            # Check if widget is menu or child of menu
            if widget == self.active_menu_frame or str(widget).startswith(str(self.active_menu_frame)): 
                return
            
            # Check if clicked on a top nav button (let toggle_menu handle it)
            for btn in self.top_nav_buttons.values():
                if widget == btn or str(widget).startswith(str(btn)): 
                    return
        except Exception:
            pass
            
        self.close_menu()

    def close_menu(self, event=None):
        if self.active_menu_frame:
            self.active_menu_frame.destroy()
            self.active_menu_frame = None
        
        # Reset highlights
        for k, btn in self.top_nav_buttons.items():
            btn.configure(fg_color="transparent")
        
        self.active_menu_key = None
        self.unbind_all("<Button-1>")

    def update_sub_navigation(self, category_key):
        pass # Deprecated



    def update_env_badge(self):
        # Use settings_service to get the true active environment directly from file
        # This avoids issues with load_dotenv caching or stale config objects
        active_env = settings_service.get_active_environment()
        is_prod = active_env == "PRODUCTION"
        
        env_color = "#27AE60" if is_prod else "#E67E22" 
        env_text = "  PRODUCTION  " if is_prod else "  SANDBOX ENV  "
        
        self.env_badge.configure(text=env_text, fg_color=env_color)


    def check_updates(self):
        """Checks for software updates from git."""
        try:
            updater = UpdateService()
            available, msg = updater.check_for_updates()
            
            if available:
                if messagebox.askyesno("Update Available", f"{msg}\n\nDo you want to update now?"):
                    success, update_msg = updater.perform_update()
                    if success:
                        messagebox.showinfo("Update Successful", "Application updated successfully.\nPlease restart the application.")
                        self.on_closing() # Close app
                    else:
                        messagebox.showerror("Update Failed", update_msg)
            else:
                messagebox.showinfo("Software Update", msg)
                
        except Exception as e:
            messagebox.showerror("Update Error", f"Failed to check for updates:\n{str(e)}")

    def create_spare_ledger_frame(self):
        self.spare_ledger_frame = SpareLedgerFrame(self)
        self.spare_ledger_frame.grid(row=0, column=1, sticky="nsew")
        self.spare_ledger_frame.grid_forget()

    def spare_ledger_button_event(self):
        self.select_frame_by_name("spare_ledger")

    def create_home_frame(self):
        self.home_frame = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        self.home_frame.grid_columnconfigure(0, weight=1)

        # Header Section
        header_frame = ctk.CTkFrame(self.home_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=(60, 20), pady=(20, 10), sticky="ew")
        
        self.label_home = ctk.CTkLabel(header_frame, text="Dashboard Overview", 
                                     font=ctk.CTkFont(family="Arial", size=28, weight="bold"),
                                     text_color=("gray10", "gray90"))
        self.label_home.pack(side="left")

        # Refresh Button (Modern pill shape)
        self.refresh_btn = ctk.CTkButton(header_frame, text="Refresh Data", 
                                       command=self.refresh_stats,
                                       width=120, height=32,
                                       corner_radius=20,
                                       fg_color=("#3498DB", "#2980B9"),
                                       font=ctk.CTkFont(size=12, weight="bold"))
        self.refresh_btn.pack(side="right")
        
        # Stats Grid Container
        self.stats_grid = ctk.CTkFrame(self.home_frame, fg_color="transparent")
        self.stats_grid.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.stats_grid.grid_columnconfigure((0, 1, 2), weight=1, uniform="stat_card")

        # Create Cards
        # Row 1
        self.card_stock = self.create_stat_card(self.stats_grid, "In Stock", "0", 
                                              icon="📦", row=0, col=0, color="#27AE60",
                                              command=self.show_stock_details) # Green
        self.card_sold = self.create_stat_card(self.stats_grid, "Total Sold", "0", 
                                             icon="🤝", row=0, col=1, color="#F39C12",
                                             command=self.show_sold_details) # Orange
        self.card_sales = self.create_stat_card(self.stats_grid, "Total Revenue", "PKR 0", 
                                              icon="💰", row=0, col=2, color="#8E44AD",
                                              command=self.show_revenue_details) # Purple
        
        # Row 2
        self.card_fbr_success = self.create_stat_card(self.stats_grid, "FBR Success", "0", 
                                            icon="✅", row=1, col=0, color="#27AE60",
                                            command=self.show_fbr_success_details) # Green
        self.card_fbr_failed = self.create_stat_card(self.stats_grid, "FBR Failed", "0", 
                                            icon="❌", row=1, col=1, color="#C0392B",
                                            command=self.show_fbr_failed_details) # Red
        self.card_customers = self.create_stat_card(self.stats_grid, "Customers", "0", 
                                                  icon="👥", row=1, col=2, color="#2980B9",
                                                  command=self.show_customers_details) # Blue
        
        # Row 3
        self.card_dealers = self.create_stat_card(self.stats_grid, "Dealers", "0", 
                                                icon="🏢", row=2, col=0, color="#16A085",
                                                command=self.show_dealers_details) # Teal
        self.card_pending = self.create_stat_card(self.stats_grid, "Pending Uploads", "0",
                                                icon="⏳", row=2, col=1, color="#E67E22",
                                                command=self.show_pending_details) # Orange

        # Stock Summary Dashboard Component
        self.stock_summary = StockSummaryFrame(self.home_frame)
        self.stock_summary.grid(row=2, column=0, padx=10, pady=10, sticky="nsew")

        self.auto_refresh_stats()

    def auto_refresh_stats(self):
        """Refreshes stats and schedules the next refresh."""
        try:
            if self.winfo_exists():
                # Only refresh if on dashboard and window is visible
                if getattr(self, "current_frame_name", "home") == "home" and self.winfo_viewable():
                    self.refresh_stats()
                
                # Schedule next refresh in 5000ms (5 seconds) to reduce load/flickering
                self.after(5000, self.auto_refresh_stats)
        except Exception as e:
            print(f"Auto refresh error: {e}")

    # Dashboard Interactive Handlers
    def show_stock_details(self):
        self.select_frame_by_name("inventory")
        if hasattr(self, 'inventory_frame'):
            self.inventory_frame.status_var.set("IN_STOCK")
            self.inventory_frame.apply_filters()

    def show_sold_details(self):
        self.select_frame_by_name("inventory")
        if hasattr(self, 'inventory_frame'):
            self.inventory_frame.status_var.set("SOLD")
            self.inventory_frame.apply_filters()

    def show_revenue_details(self):
        self.select_frame_by_name("reports")
        if hasattr(self, 'reports_frame'):
            self.reports_frame.tabview.set("Sales Report")
            self.reports_frame.sales_status_var.set("All")
            self.reports_frame.load_sales()

    def show_fbr_success_details(self):
        self.select_frame_by_name("reports")
        if hasattr(self, 'reports_frame'):
            self.reports_frame.tabview.set("Sales Report")
            self.reports_frame.sales_status_var.set("Synced")
            self.reports_frame.load_sales()

    def show_fbr_failed_details(self):
        self.select_frame_by_name("reports")
        if hasattr(self, 'reports_frame'):
            self.reports_frame.tabview.set("Sales Report")
            self.reports_frame.sales_status_var.set("Failed")
            self.reports_frame.load_sales()

    def show_customers_details(self):
        self.select_frame_by_name("customer")

    def show_dealers_details(self):
        self.select_frame_by_name("dealer")

    def show_pending_details(self):
        self.select_frame_by_name("reports")
        if hasattr(self, 'reports_frame'):
            self.reports_frame.tabview.set("Sales Report")
            self.reports_frame.sales_status_var.set("Pending")
            self.reports_frame.load_sales()

    def create_stat_card(self, parent, title, value, icon, row, col, color, command=None):
        """Creates a stylish stat card."""
        card = ctk.CTkFrame(parent, corner_radius=15, fg_color=("white", "gray20"))
        card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
        
        if command:
            card.configure(cursor="hand2")
            card.bind("<Button-1>", lambda e: command())
        
        # Left accent bar
        accent = ctk.CTkFrame(card, width=6, corner_radius=10, fg_color=color)
        accent.pack(side="left", fill="y", pady=5, padx=(5, 10))
        if command:
            accent.bind("<Button-1>", lambda e: command())
            accent.configure(cursor="hand2")
        
        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True, padx=5, pady=10)
        if command:
            content.bind("<Button-1>", lambda e: command())
            content.configure(cursor="hand2")
        
        # Title
        title_label = ctk.CTkLabel(content, text=title.upper(), 
                   font=ctk.CTkFont(size=11, weight="bold"),
                   text_color=("gray50", "gray40"),
                   anchor="w")
        title_label.pack(fill="x")
        if command:
            title_label.bind("<Button-1>", lambda e: command())
            title_label.configure(cursor="hand2")
        
        # Value
        val_label = ctk.CTkLabel(content, text=value, 
                               font=ctk.CTkFont(size=22, weight="bold"),
                               text_color=("gray10", "gray90"),
                               anchor="w")
        val_label.pack(fill="x", pady=(2, 0))
        if command:
            val_label.bind("<Button-1>", lambda e: command())
            val_label.configure(cursor="hand2")
        
        # Icon (Right side)
        icon_label = ctk.CTkLabel(card, text=icon, 
                                font=ctk.CTkFont(size=30),
                                text_color=color)
        icon_label.pack(side="right", padx=15)
        if command:
            icon_label.bind("<Button-1>", lambda e: command())
            icon_label.configure(cursor="hand2")
        
        return val_label  # Return the value label to update it later

    def refresh_stats(self):
        """Starts background thread to fetch stats."""
        threading.Thread(target=self._refresh_stats_thread, daemon=True).start()

    def _refresh_stats_thread(self):
        db = SessionLocal()
        try:
            data = {}
            # Count Motorcycles (In Stock)
            data['stock'] = db.query(Motorcycle).filter(Motorcycle.status == "IN_STOCK").count()
            
            # Count Sold Motorcycles
            data['sold'] = db.query(Motorcycle).filter(Motorcycle.status == "SOLD").count()
            
            # Sum Invoices
            invoices = db.query(Invoice).all()
            data['sales'] = sum(inv.total_amount for inv in invoices)
            
            # FBR Success
            data['fbr_success'] = db.query(Invoice).filter(Invoice.fbr_invoice_number != None).count()

            # FBR Failed
            data['fbr_failed'] = db.query(Invoice).filter(Invoice.sync_status == "FAILED").count()

            # Customers (Excluding Dealers)
            data['customers'] = db.query(Customer).filter(Customer.type != CustomerType.DEALER).count()

            # Dealers
            data['dealers'] = db.query(Customer).filter(Customer.type == CustomerType.DEALER).count()
            
            # Pending Uploads
            data['pending'] = db.query(Invoice).filter(Invoice.sync_status == "PENDING").count()
            
            if self.winfo_exists():
                self.after(0, lambda: self._update_stats_ui(data))
            
        except Exception as e:
            print(f"Error refreshing stats: {e}")
        finally:
            db.close()

    def _update_stats_ui(self, data):
        """Updates UI with fetched data on main thread."""
        try:
            # Helper to update label only if changed to prevent flickering
            def update_label(label, new_text):
                try:
                    if label.cget("text") != str(new_text):
                        label.configure(text=str(new_text))
                except Exception:
                    pass

            update_label(self.card_stock, data['stock'])
            update_label(self.card_sold, data['sold'])
            update_label(self.card_sales, f"PKR {data['sales']:,.0f}")
            update_label(self.card_fbr_success, data['fbr_success'])
            update_label(self.card_fbr_failed, data['fbr_failed'])
            
            if hasattr(self, 'fbr_stat_value'):
                update_label(self.fbr_stat_value, data['fbr_success'])

            update_label(self.card_customers, data['customers'])
            update_label(self.card_dealers, data['dealers'])
            update_label(self.card_pending, data['pending'])
            
            # Refresh Stock Summary
            if hasattr(self, 'stock_summary'):
                self.stock_summary.load_data()
                
        except Exception as e:
            print(f"Error updating stats UI: {e}")

    def show_field_error(self, widget, message):
        """Highlights a field with error and shows a tooltip."""
        try:
            widget.configure(border_color="red")
        except ValueError:
            # Fallback for widgets that don't support border_color (like OptionMenu sometimes)
            try:
                 widget.configure(fg_color="#C0392B") # Dark Red
            except:
                pass
        
        # Remove existing tooltip if any
        if hasattr(widget, "_error_tooltip"):
            widget._error_tooltip.hidetip()
            del widget._error_tooltip
            
        # Add new tooltip
        tooltip = ToolTip(widget, message)
        widget._error_tooltip = tooltip
        
        # Optional: Flash the widget or play sound? Keep it professional.
        logger.warning(f"Validation Error on {widget}: {message}")

    def clear_field_error(self, widget):
        """Clears error highlight and tooltip."""
        # Reset to default border color (approximate for System theme)
        try:
            widget.configure(border_color=["#979DA2", "#565B5E"])
        except ValueError:
             try:
                 # Restore OptionMenu default color (approximate)
                 if isinstance(widget, ctk.CTkOptionMenu):
                     widget.configure(fg_color=["#3B8ED0", "#1F6AA5"]) # Standard Blue theme
             except:
                 pass
        
        if hasattr(widget, "_error_tooltip"):
            widget._error_tooltip.hidetip()
            del widget._error_tooltip

    def create_invoice_frame(self):
        self.invoice_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.invoice_frame.grid_columnconfigure(0, weight=1) # Main area expands
        self.invoice_frame.grid_columnconfigure(1, weight=0, minsize=180) # Sidebar has fixed min width
        self.invoice_frame.grid_rowconfigure(1, weight=1)
        
        self.current_price_obj = None

        # Header Frame for Title and Stats
        self.invoice_header = ctk.CTkFrame(self.invoice_frame, fg_color="transparent")
        self.invoice_header.grid(row=0, column=0, columnspan=2, fill="x", padx=20, pady=10)
        self.invoice_header.grid_columnconfigure(0, weight=1)

        self.label_invoice = ctk.CTkLabel(self.invoice_header, text="New Invoice", font=ctk.CTkFont(size=24, weight="bold"))
        self.label_invoice.grid(row=0, column=0, padx=40, pady=10, sticky="w")
        
        # FBR Submitted Statistic Box (Now in Header, Right Aligned)
        self.fbr_stat_frame = ctk.CTkFrame(self.invoice_header, fg_color=("#C0392B", "#922B21"), corner_radius=10)
        self.fbr_stat_frame.grid(row=0, column=1, padx=20, pady=5, sticky="e")
        
        ctk.CTkLabel(self.fbr_stat_frame, text="FBR Submitted", font=ctk.CTkFont(size=11, weight="bold"), text_color="white").pack(padx=10, pady=(5,0))
        self.fbr_stat_value = ctk.CTkLabel(self.fbr_stat_frame, text="0", font=ctk.CTkFont(size=20, weight="bold"), text_color="white")
        self.fbr_stat_value.pack(padx=10, pady=(0,5))

        self.form_frame = ctk.CTkScrollableFrame(
            self.invoice_frame, 
            label_text="Invoice Details",
            label_font=ctk.CTkFont(size=18, weight="bold")
        )
        self.form_frame.grid(row=1, column=0, padx=(20, 10), pady=10, sticky="nsew")
        self.form_frame.grid_columnconfigure(1, weight=1)

        # Right Sidebar for QR (Fixed, not scrolling)
        self.right_sidebar = ctk.CTkFrame(self.invoice_frame, fg_color="transparent", width=180)
        self.right_sidebar.grid(row=1, column=1, padx=(10, 20), pady=10, sticky="nsew")

        # QR Code Display Area (Fixed in Sidebar)
        self.qr_code_label = ctk.CTkLabel(self.right_sidebar, text="", width=150, height=150)
        self.qr_code_label.pack(pady=10)
        
        # FBR Invoice Number Label (Fixed in Sidebar)
        self.fbr_inv_label = ctk.CTkLabel(self.right_sidebar, text="", font=("Arial", 12, "bold"), text_color="blue", wraplength=160)
        self.fbr_inv_label.pack(pady=10)

        # Configure columns with minsize to prevent squashing
        self.form_frame.grid_columnconfigure(1, weight=1, minsize=200)

        # --- Fields ---
        
        # 1. Invoice Number
        ctk.CTkLabel(self.form_frame, text="Invoice Number").grid(row=0, column=0, padx=10, pady=5, sticky="e")
        self.inv_num_var = ctk.StringVar()
        self.inv_num_var.trace_add("write", lambda *args: self.check_form_validity())
        self.inv_num_entry = ctk.CTkEntry(self.form_frame, textvariable=self.inv_num_var, state="readonly")
        self.inv_num_entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        
        # Auto-generate button (optional, but good for manual refresh if needed)
        self.refresh_inv_btn = ctk.CTkButton(self.form_frame, text="↺", width=30, command=self.generate_invoice_number)
        self.refresh_inv_btn.grid(row=0, column=2, padx=5, sticky="w")

        # Create empty image for clearing QR code safely
        # Use a 1x1 transparent image to avoid layout shifts or None-state bugs
        self.empty_qr_image = ctk.CTkImage(
            light_image=Image.new("RGBA", (1, 1), (0, 0, 0, 0)),
            dark_image=Image.new("RGBA", (1, 1), (0, 0, 0, 0)),
            size=(1, 1)
        )

        # 1.5 ID Card (CNIC)
        ctk.CTkLabel(self.form_frame, text="ID Card (CNIC)").grid(row=1, column=0, padx=10, pady=5, sticky="e")
        self.buyer_cnic_var = ctk.StringVar()
        self.buyer_cnic_var.trace_add("write", self.validate_cnic_input)
        self.buyer_cnic_entry = ctk.CTkEntry(
            self.form_frame,
            textvariable=self.buyer_cnic_var,
            placeholder_text="33302-1234567-0"
        )
        self.buyer_cnic_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        self.buyer_cnic_entry.bind("<KeyRelease>", self.on_cnic_key_release)
        self.buyer_cnic_entry.bind("<Down>", self.on_cnic_suggestion_nav)
        self.buyer_cnic_entry.bind("<Up>", self.on_cnic_suggestion_nav)
        self.buyer_cnic_entry.bind("<Return>", self.on_cnic_suggestion_select)
        self.buyer_cnic_entry.bind("<FocusOut>", lambda e: self.after(150, self.on_cnic_focus_out))
        
        # Scan ID Card Button
        self.scan_btn = ctk.CTkButton(self.form_frame, text="📷 Scan ID", width=80, command=self.scan_cnic_action, fg_color="#E67E22", hover_color="#D35400")
        self.scan_btn.grid(row=1, column=2, padx=5, sticky="w")
        
        # Disable if OCR not available
        if not ocr_service.is_available():
            self.scan_btn.grid_forget() # Hide if no OCR

        # 1.6 NTN (National Tax Number)
        ctk.CTkLabel(self.form_frame, text="NTN").grid(row=2, column=0, padx=10, pady=5, sticky="e")
        self.buyer_ntn_var = ctk.StringVar()
        self.buyer_ntn_var.trace_add("write", self.validate_ntn_input)
        self.buyer_ntn_entry = ctk.CTkEntry(self.form_frame, textvariable=self.buyer_ntn_var, placeholder_text="1234567-8")
        self.buyer_ntn_entry.grid(row=2, column=1, padx=10, pady=5, sticky="ew")
        self.buyer_ntn_entry.bind("<FocusOut>", self.validate_ntn_strict)

        # 2. Buyer Name
        ctk.CTkLabel(self.form_frame, text="Buyer Name").grid(row=3, column=0, padx=10, pady=5, sticky="e")
        self.buyer_name_var = ctk.StringVar()
        self.buyer_name_var.trace_add("write", self.validate_buyer_name)
        self.buyer_name_entry = AutocompleteEntry(
            self.form_frame, 
            textvariable=self.buyer_name_var,
            fetch_suggestions=self._fetch_dealer_suggestions,
            on_select=self._on_dealer_selected,
            typing_delay=150
        )
        self.buyer_name_entry.grid(row=3, column=1, padx=10, pady=5, sticky="ew")

        # Checkbox to preserve buyer details
        self.preserve_buyer_details_var = ctk.BooleanVar(value=False)
        self.preserve_buyer_details_chk = ctk.CTkCheckBox(
            self.form_frame, 
            text="Preserve",
            variable=self.preserve_buyer_details_var,
            font=ctk.CTkFont(size=12),
            checkbox_width=20,
            checkbox_height=20,
            width=80
        )
        self.preserve_buyer_details_chk.grid(row=3, column=2, padx=5, sticky="w")

        # 3. Father
        ctk.CTkLabel(self.form_frame, text="Father Name").grid(row=4, column=0, padx=10, pady=5, sticky="e")
        self.father_name_var = ctk.StringVar()
        self.father_name_var.trace_add("write", self.validate_father_name)
        self.buyer_father_entry = ctk.CTkEntry(self.form_frame, textvariable=self.father_name_var)
        self.buyer_father_entry.grid(row=4, column=1, padx=10, pady=5, sticky="ew")

        # 4. Cell
        ctk.CTkLabel(self.form_frame, text="Cell (Phone)").grid(row=5, column=0, padx=10, pady=5, sticky="e")
        self.buyer_cell_var = ctk.StringVar()
        self.buyer_cell_var.trace_add("write", self.validate_cell_input)
        self.buyer_cell_entry = ctk.CTkEntry(self.form_frame, textvariable=self.buyer_cell_var, placeholder_text="03XXXXXXXXX")
        self.buyer_cell_entry.grid(row=5, column=1, padx=10, pady=5, sticky="ew")
        self.buyer_cell_entry.bind("<FocusOut>", self.validate_cell_strict)

        # 5. Address
        ctk.CTkLabel(self.form_frame, text="Address").grid(row=6, column=0, padx=10, pady=5, sticky="e")
        self.buyer_address_var = ctk.StringVar()
        self.buyer_address_var.trace_add("write", self.validate_address)
        self.buyer_address_entry = ctk.CTkEntry(self.form_frame, textvariable=self.buyer_address_var)
        self.buyer_address_entry.grid(row=6, column=1, padx=10, pady=5, sticky="ew")

        # 5.5 Model & Color
        ctk.CTkLabel(self.form_frame, text="Model").grid(row=7, column=0, padx=10, pady=5, sticky="e")
        
        self.model_color_frame = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        self.model_color_frame.grid(row=7, column=1, padx=10, pady=5, sticky="ew")
        
        # Get active models from DB
        active_prices = price_service.get_all_active_prices()
        model_names = [p.product_model.model_name for p in active_prices if p.product_model] if active_prices else ["CD70", "CG125"]
        
        self.model_combo = ctk.CTkOptionMenu(self.model_color_frame, values=model_names, command=self.on_model_change)
        self.model_combo.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.model_combo.set("") # Start empty
        
        ctk.CTkLabel(self.model_color_frame, text="Color").pack(side="left", padx=5)
        
        self.color_combo = ctk.CTkOptionMenu(self.model_color_frame, values=["Red", "Blue"], command=self.on_color_change)
        self.color_combo.pack(side="left", fill="x", expand=True)
        self.color_combo.set("") # Start empty

        # 6. Payment Mode (New)
        ctk.CTkLabel(self.form_frame, text="Payment Mode").grid(row=8, column=0, padx=10, pady=5, sticky="e")
        self.payment_mode_combo = ctk.CTkOptionMenu(self.form_frame, values=["Cash", "Credit", "Cheque", "Online"])
        self.payment_mode_combo.grid(row=8, column=1, padx=10, pady=5, sticky="ew")

        # 7. Chassis Number
        ctk.CTkLabel(self.form_frame, text="Chassis Number").grid(row=9, column=0, padx=10, pady=5, sticky="e")
        self.chassis_var = ctk.StringVar()
        self.chassis_var.trace_add("write", self.validate_chassis)
        self.chassis_entry = ctk.CTkEntry(self.form_frame, textvariable=self.chassis_var)
        self.chassis_entry.grid(row=9, column=1, padx=10, pady=5, sticky="ew")
        self.chassis_entry.bind("<KeyRelease>", self.on_chassis_key_release)
        self.chassis_entry.bind("<Down>", self.on_suggestion_nav)
        self.chassis_entry.bind("<Up>", self.on_suggestion_nav)
        self.chassis_entry.bind("<Return>", self.on_suggestion_select)
        self.chassis_entry.bind("<FocusOut>", self.on_chassis_focus_out)
        
        # Suggestion Windows (Toplevels for floating effect)
        self.suggestion_window = None
        self.suggestion_buttons = []
        self.selected_suggestion_index = -1
        
        self.cnic_suggestion_window = None
        self.cnic_suggestion_buttons = []
        self.cnic_selected_suggestion_index = -1
        self.cnic_suggestions_data = [] # Store actual customer objects
        
        # Container for Chassis Tools (Checkbox + Feedback) in Column 2
        self.chassis_tools_frame = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        self.chassis_tools_frame.grid(row=9, column=2, padx=5, pady=5, sticky="w")

        # Verify Chassis Checkbox (New)
        self.verify_chassis_var = ctk.BooleanVar(value=False)
        self.verify_chassis_chk = ctk.CTkCheckBox(self.chassis_tools_frame, text="Manual", width=70,
                                                variable=self.verify_chassis_var,
                                                command=self.on_verify_chassis_change)
        self.verify_chassis_chk.pack(side="left", padx=(0, 5))
        ToolTip(self.verify_chassis_chk, "Bypass chassis verification (Allow submission if not in stock)")

        # Chassis Feedback Label
        self.chassis_feedback_label = ctk.CTkLabel(self.chassis_tools_frame, text="", width=20)
        self.chassis_feedback_label.pack(side="left")

        # Check Stock Button - Moved to Column 2
        self.check_stock_btn = ctk.CTkButton(self.form_frame, text="Check Stock", width=100, command=self.check_stock)
        self.check_stock_btn.grid(row=9, column=2, padx=5, pady=5, sticky="w")

        # 8. Engine Number
        ctk.CTkLabel(self.form_frame, text="Engine Number").grid(row=10, column=0, padx=10, pady=5, sticky="e")
        self.engine_var = ctk.StringVar()
        self.engine_var.trace_add("write", self.validate_engine)
        self.engine_entry = ctk.CTkEntry(self.form_frame, textvariable=self.engine_var)
        self.engine_entry.grid(row=10, column=1, padx=10, pady=5, sticky="ew")

        # 9. Quantity
        ctk.CTkLabel(self.form_frame, text="Quantity").grid(row=11, column=0, padx=10, pady=5, sticky="e")
        
        self.qty_var = ctk.StringVar(value="1")
        self.qty_var.trace_add("write", lambda *args: self.check_form_validity())
        
        # Entry in Column 1 (Main area)
        self.qty_entry = ctk.CTkEntry(self.form_frame, textvariable=self.qty_var, state="disabled")
        self.qty_entry.grid(row=11, column=1, padx=10, pady=5, sticky="ew")
        
        # Checkbox in Column 2 (Right side - Red Dot Position)
        self.manual_qty_var = ctk.BooleanVar(value=False)
        self.manual_qty_chk = ctk.CTkCheckBox(self.form_frame, text="Edit", variable=self.manual_qty_var, width=60, command=self.toggle_quantity_mode)
        self.manual_qty_chk.grid(row=11, column=2, padx=5, pady=5, sticky="w")



        # 10. Amount Excluding Sale Tax
        ctk.CTkLabel(self.form_frame, text="Amount (Excl. Tax)").grid(row=12, column=0, padx=10, pady=5, sticky="e")
        self.amount_var = ctk.StringVar()
        self.amount_var.trace_add("write", lambda *args: self.check_form_validity())
        self.amount_excl_entry = ctk.CTkEntry(self.form_frame, textvariable=self.amount_var, state="disabled")
        self.amount_excl_entry.grid(row=12, column=1, padx=10, pady=5, sticky="ew")
        self.amount_excl_entry.bind("<KeyRelease>", self.calculate_totals)
        
        self.manual_amount_var = ctk.BooleanVar(value=False)
        self.manual_amount_chk = ctk.CTkCheckBox(self.form_frame, text="", variable=self.manual_amount_var, width=20, 
                                                 command=lambda: self.toggle_field_edit(self.amount_excl_entry, self.manual_amount_var))
        self.manual_amount_chk.grid(row=12, column=2, padx=5, pady=5, sticky="w")

        # 11. Sale Tax (Read Only or Editable)
        ctk.CTkLabel(self.form_frame, text="Sale Tax").grid(row=13, column=0, padx=10, pady=5, sticky="e")
        self.tax_entry = ctk.CTkEntry(self.form_frame, state="disabled")
        self.tax_entry.grid(row=13, column=1, padx=10, pady=5, sticky="ew")
        self.tax_entry.bind("<KeyRelease>", self.calculate_totals)

        self.manual_tax_var = ctk.BooleanVar(value=False)
        self.manual_tax_chk = ctk.CTkCheckBox(self.form_frame, text="", variable=self.manual_tax_var, width=20,
                                              command=lambda: self.toggle_field_edit(self.tax_entry, self.manual_tax_var))
        self.manual_tax_chk.grid(row=13, column=2, padx=5, pady=5, sticky="w")

        # 12. Further Tax
        ctk.CTkLabel(self.form_frame, text="Further Tax").grid(row=14, column=0, padx=10, pady=5, sticky="e")
        self.further_tax_entry = ctk.CTkEntry(self.form_frame, state="disabled")
        self.further_tax_entry.grid(row=14, column=1, padx=10, pady=5, sticky="ew")
        self.further_tax_entry.bind("<KeyRelease>", self.calculate_totals)

        self.manual_ft_var = ctk.BooleanVar(value=False)
        self.manual_ft_chk = ctk.CTkCheckBox(self.form_frame, text="", variable=self.manual_ft_var, width=20,
                                             command=lambda: self.toggle_field_edit(self.further_tax_entry, self.manual_ft_var))
        self.manual_ft_chk.grid(row=14, column=2, padx=5, pady=5, sticky="w")

        # 13. Price (Total)
        ctk.CTkLabel(self.form_frame, text="Total Price (Incl. Tax)").grid(row=15, column=0, padx=10, pady=5, sticky="e")
        self.total_price_entry = ctk.CTkEntry(self.form_frame, state="disabled")
        self.total_price_entry.grid(row=15, column=1, padx=10, pady=5, sticky="ew")

        self.manual_total_var = ctk.BooleanVar(value=False)
        self.manual_total_chk = ctk.CTkCheckBox(self.form_frame, text="", variable=self.manual_total_var, width=20,
                                                command=lambda: self.toggle_field_edit(self.total_price_entry, self.manual_total_var))
        self.manual_total_chk.grid(row=15, column=2, padx=5, pady=5, sticky="w")

        # Button Frame for Submit and Reset
        self.btn_frame = ctk.CTkFrame(self.invoice_frame, fg_color="transparent")
        self.btn_frame.grid(row=2, column=0, padx=20, pady=20)

        self.submit_btn = ctk.CTkButton(self.btn_frame, text="Submit Invoice", command=self.submit_invoice, state="disabled")
        self.submit_btn.grid(row=0, column=0, padx=10)

        self.reset_btn = ctk.CTkButton(self.btn_frame, text="Reset Form", command=self.confirm_and_reset, fg_color="gray")
        self.reset_btn.grid(row=0, column=1, padx=10)

        # Initialize Keyboard Navigation
        self.setup_keyboard_navigation()

    def toggle_field_edit(self, entry_widget, check_var):
        """Toggles the editable state of an entry widget based on checkbox variable."""
        if check_var.get():
            entry_widget.configure(state="normal")
        else:
            entry_widget.configure(state="disabled")

    def update_entry_value(self, entry_widget, value):
        """Updates the value of an entry widget, handling disabled state."""
        current_state = entry_widget.cget("state")
        
        if current_state == "disabled":
            entry_widget.configure(state="normal")
            
        entry_widget.delete(0, "end")
        entry_widget.insert(0, str(value))
        
        if current_state == "disabled":
            entry_widget.configure(state="disabled")

    def setup_keyboard_navigation(self):
        """Sets up Enter key navigation through form fields in a specific sequence."""
        # Define the sequence of widgets
        # Sequence: ID -> NTN -> Name -> Father -> Cell -> Address -> Model -> Color -> Payment -> Chassis -> Engine
        self.nav_sequence = [
            self.buyer_cnic_entry,
            self.buyer_ntn_entry,
            self.buyer_name_entry,
            self.buyer_father_entry,
            self.buyer_cell_entry,
            self.buyer_address_entry,
            self.model_combo,
            self.color_combo,
            self.payment_mode_combo,
            self.chassis_entry,
            self.engine_entry
        ]

        # Bind <Return> key for each widget to focus the next one
        for i, widget in enumerate(self.nav_sequence):
            # For the last widget (Engine), bind to Submit
            if i == len(self.nav_sequence) - 1:
                if isinstance(widget, ctk.CTkEntry):
                    widget.bind("<Return>", self.on_last_field_enter)
                else:
                    # Fallback for non-entry widgets if any end up last
                    try:
                        widget.bind("<Return>", self.on_last_field_enter)
                    except:
                        pass
            else:
                next_widget = self.nav_sequence[i + 1]
                
                # Define a closure to capture next_widget
                def focus_next(event, target=next_widget, current_widget=widget):
                    # Special check for CNIC field to trigger lookup on Enter
                    if current_widget == self.buyer_cnic_entry:
                        self.perform_cnic_lookup()
                    
                    target.focus_set()
                    return "break" # Prevent default behavior
                
                if isinstance(widget, ctk.CTkEntry):
                    widget.bind("<Return>", focus_next)
                elif isinstance(widget, ctk.CTkOptionMenu):
                    # CTkOptionMenu is a frame, usually doesn't capture key events easily unless focused.
                    # We try binding to the widget itself.
                    # Note: CTkOptionMenu might need explicit focus_set() to receive keys.
                    widget.bind("<Return>", focus_next) 
        
        # Explicitly bind FocusOut to CNIC for lookup and hide suggestions
        self.buyer_cnic_entry.bind("<FocusOut>", lambda e: self.after(150, self.on_cnic_focus_out))

        # Bind Up/Down keys for OptionMenus
        self._bind_option_menu_arrows(self.model_combo, self.on_model_change)
        self._bind_option_menu_arrows(self.color_combo, self.on_color_change)
        self._bind_option_menu_arrows(self.payment_mode_combo, None)

    def _bind_option_menu_arrows(self, widget, callback=None):
        """Binds Up/Down keys to cycle options in a CTkOptionMenu."""
        widget.bind("<Up>", lambda e: self._handle_option_arrow(e, widget, -1, callback))
        widget.bind("<Down>", lambda e: self._handle_option_arrow(e, widget, 1, callback))

    def _handle_option_arrow(self, event, widget, delta, callback=None):
        """Handles arrow key press for OptionMenu."""
        values = widget._values
        if not values:
            return "break"
            
        current_val = widget.get()
        try:
            index = values.index(current_val)
        except ValueError:
            # If current value not in list (e.g. empty), start at -1 so next is 0
            index = -1
            
        new_index = index + delta
        
        # Clamp index
        if new_index < 0:
            new_index = 0
        elif new_index >= len(values):
            new_index = len(values) - 1
            
        if new_index != index:
            new_val = values[new_index]
            widget.set(new_val)
            if callback:
                callback(new_val)
        
        return "break"

    def on_last_field_enter(self, event):
        """Handles Enter key on the last field (Engine Number)."""
        # Directly trigger submit logic which handles its own validation
        self.submit_invoice()
             
    def validate_all_fields(self):
        """Checks if all fields in the navigation sequence have values."""
        for widget in self.nav_sequence:
            # Skip disabled widgets
            try:
                if widget.cget("state") == "disabled":
                    continue
            except:
                pass

            value = ""
            if isinstance(widget, ctk.CTkEntry):
                value = widget.get()
            elif isinstance(widget, ctk.CTkOptionMenu):
                value = widget.get()
            
            if not value or value.strip() == "":
                # Focus the first empty widget
                try:
                    widget.focus_set()
                except:
                    pass
                return False
        return True

    def toggle_quantity_mode(self):
        if self.manual_qty_var.get():
            self.qty_entry.configure(state="normal")
        else:
            self.qty_var.set("1")
            self.qty_entry.configure(state="disabled")
        self.calculate_totals()

    def calculate_totals(self, *args):
        try:
            qty = float(self.qty_entry.get() or 0)
            amount_excl = float(self.amount_excl_entry.get() or 0)
            
            # Identify which widget has focus to prevent overwriting user input while typing
            focused_widget = self.focus_get()

            # Default values if no price object
            tax_charged = 0.0
            total_further_tax = 0.0
            
            if self.current_price_obj:
                # Use exact values from Price Table as per requirement
                # These are per-unit values from the database
                tax_per_unit = self.current_price_obj.tax_amount
                # If dealer is selected, further tax is typically 0
                further_tax_per_unit = 0.0 if self.is_dealer_selected else self.current_price_obj.levy_amount
                
                # Calculate totals based on quantity
                tax_charged = tax_per_unit * qty
                total_further_tax = further_tax_per_unit * qty
                
                # We trust the user/price table for the base amount. 
                # If the user edited the Amount(Excl), we still use the fixed tax from table.
                
            else:
                # Fallback to Rate-based calculation (Legacy/Manual mode)
                from app.services.settings_service import settings_service
                settings = settings_service.get_active_settings()
                tax_rate = float(settings.get("tax_rate", 18.0))
                
                sale_value = amount_excl * qty
                tax_charged = (sale_value * tax_rate) / 100
                
                # Preserver existing Further Tax in manual mode (don't force to 0 if not dealer)
                try:
                    if self.is_dealer_selected:
                        total_further_tax = 0.0
                    else:
                        total_further_tax = float(self.further_tax_entry.get() or 0)
                except ValueError:
                    total_further_tax = 0.0
            
            # Allow manual override if user is currently typing in these fields
            if focused_widget == self.tax_entry:
                try:
                    tax_charged = float(self.tax_entry.get() or 0)
                except ValueError:
                    pass
            
            if focused_widget == self.further_tax_entry:
                try:
                    total_further_tax = float(self.further_tax_entry.get() or 0)
                except ValueError:
                    pass

            # Final Calculation
            sale_value_total = amount_excl * qty
            total_amount = sale_value_total + tax_charged + total_further_tax
            
            # Update UI Fields (Only if not focused, to avoid fighting with user input)
            if focused_widget != self.tax_entry:
                self.update_entry_value(self.tax_entry, f"{tax_charged:.2f}")
            
            if focused_widget != self.further_tax_entry:
                self.update_entry_value(self.further_tax_entry, f"{total_further_tax:.2f}")
            
            if focused_widget != self.total_price_entry:
                self.update_entry_value(self.total_price_entry, f"{total_amount:.2f}")
            
            self.check_form_validity()
            
        except ValueError:
            pass

    def on_model_change(self, choice):
        """Auto-fill price and colors when model is selected."""


        # 1. Get all active prices for this model to find all available colors
        prices = price_service.get_active_prices_for_model(choice)
        
        if not prices:
            self.current_price_obj = None
            return

        # 2. Collect unique colors from ALL price entries for this model
        all_colors = []
        for p in prices:
            if p.optional_features and isinstance(p.optional_features, dict):
                c_str = p.optional_features.get("colors", "")
                if c_str:
                    parts = [c.strip() for c in c_str.split(",")]
                    for part in parts:
                        if part and part not in all_colors:
                            all_colors.append(part)
        
        # 3. Update Color Dropdown
        if all_colors:
            self.color_combo.configure(values=all_colors)
            # Select first color by default
            default_color = all_colors[0]
            self.color_combo.set(default_color)
            
            # 4. Set Price based on Model + Default Color
            self.on_color_change(default_color)
        else:
            # Fallback if no colors defined
            self.color_combo.configure(values=[])
            self.color_combo.set("")
            
            # Use first available price
            price = prices[0]
            self.current_price_obj = price
            self.update_entry_value(self.amount_excl_entry, str(price.base_price))
            self.calculate_totals()

    def on_color_change(self, color_choice):
        """Update price based on selected model and color."""


        model = self.model_combo.get()
        price = price_service.get_price_by_model_and_color(model, color_choice)
        
        self.current_price_obj = price
        if price:
            self.update_entry_value(self.amount_excl_entry, str(price.base_price))
            self.calculate_totals()

    def _fetch_dealer_suggestions(self, query):
        """Fetch dealer suggestions for autocomplete."""
        return dealer_service.search_dealers_by_business_name(query, limit=5)

    def _fetch_cnic_suggestions(self, query):
        """Fetch customer/dealer suggestions by CNIC for autocomplete."""
        # Clean query for search
        clean_query = query.strip()
        if not clean_query:
            return []
        
        # Search customers by CNIC prefix
        return customer_service.db.query(Customer).filter(
            Customer.is_deleted == False,
            Customer.cnic.ilike(f"{clean_query}%")
        ).limit(5).all()

    def _on_cnic_select(self, customer):
        """Handle CNIC selection from suggestions."""
        if not customer:
            return
            
        # Fill form with customer data
        self.buyer_cnic_var.set(customer.cnic)
        self.buyer_name_var.set(customer.name or "")
        self.father_name_var.set(customer.father_name or "")
        self.buyer_cell_var.set(customer.phone or "")
        self.buyer_address_var.set(customer.address or "")
        
        if hasattr(self, 'buyer_ntn_var') and customer.ntn:
            self.buyer_ntn_var.set(customer.ntn)
            
        # Clear any errors
        self.clear_field_error(self.buyer_cnic_entry)
        self.clear_field_error(self.buyer_name_entry)
        self.clear_field_error(self.buyer_father_entry)
        self.clear_field_error(self.buyer_cell_entry)
        self.clear_field_error(self.buyer_address_entry)

    def _on_dealer_selected(self, dealer):
        """Handle dealer selection from autocomplete."""
        if not dealer:
            return
            
        self.is_dealer_selected = True
        # Populate fields
        self.buyer_cnic_var.set(dealer.cnic)
        self.father_name_var.set(dealer.father_name)
        self.buyer_cell_var.set(dealer.phone)
        self.buyer_address_var.set(dealer.address)
        if hasattr(self, 'buyer_ntn_var') and dealer.ntn:
            self.buyer_ntn_var.set(dealer.ntn)
            
        # Dealers are registered, reset Further Tax to 0
        self.update_entry_value(self.further_tax_entry, "0.00")
        self.calculate_totals()

    def validate_buyer_name(self, *args):
        self._validate_name(self.buyer_name_var)
        
        # If user manually edits name, reset dealer selection flag
        # We need to distinguish between manual edit and auto-populate
        # For now, we'll just check if the name matches any dealer
        
        name = self.buyer_name_var.get().strip()
        if name:
            # Check for dealer match
            dealer = dealer_service.get_dealer_by_business_name(name)
            if dealer:
                self.is_dealer_selected = True
                self.buyer_cnic_var.set(dealer.cnic)
                self.father_name_var.set(dealer.father_name)
                self.buyer_cell_var.set(dealer.phone)
                self.buyer_address_var.set(dealer.address)
                if hasattr(self, 'buyer_ntn_var') and dealer.ntn:
                    self.buyer_ntn_var.set(dealer.ntn)
                
                # Replace Business Name with Dealer Name
                if dealer.name and name != dealer.name.upper():
                    self.buyer_name_var.set(dealer.name.upper())
                    
                # Dealers are registered, reset Further Tax to 0
                self.update_entry_value(self.further_tax_entry, "0.00")
                self.calculate_totals()
            else:
                self.is_dealer_selected = False

    def validate_father_name(self, *args):
        self._validate_name(self.father_name_var)

    def validate_ntn_strict(self, event=None):
        value = self.buyer_ntn_var.get()
        if not value:
            self.clear_field_error(self.buyer_ntn_entry)
            return

        # Simple check: 7 digits or 7+1 digits
        # Regex: ^\d{7}(-\d)?$ 
        if not re.match(r"^\d{7}(-\d)?$", value):
             self.show_field_error(self.buyer_ntn_entry, "Invalid NTN. Format: 1234567 or 1234567-8")
        else:
             self.clear_field_error(self.buyer_ntn_entry)

    def _validate_name(self, var):
        value = var.get()
        if not value:
            self.check_form_validity()
            return

        # Check if value contains only alphabets and spaces
        if not all(x.isalpha() or x.isspace() for x in value):
            # Filter valid characters
            cleaned = ''.join(c for c in value if c.isalpha() or c.isspace())
            var.set(cleaned.upper())
            return
        
        # Ensure uppercase
        if value != value.upper():
            var.set(value.upper())
            return
            
        self.check_form_validity()

    def validate_address(self, *args):
        value = self.buyer_address_var.get()
        if not value:
            self.check_form_validity()
            return
            
        # Ensure uppercase
        if value != value.upper():
            self.buyer_address_var.set(value.upper())
            return
            
        self.check_form_validity()

    def validate_chassis(self, *args):
        value = self.chassis_var.get()
        if not value:
            self.check_form_validity()
            return
            
        # Ensure uppercase
        if value != value.upper():
            self.chassis_var.set(value.upper())
            return
            
        self.check_form_validity()

    def validate_engine(self, *args):
        value = self.engine_var.get()
        if not value:
            self.check_form_validity()
            return
            
        # Ensure uppercase
        if value != value.upper():
            self.engine_var.set(value.upper())
            return
            
        self.check_form_validity()

    def validate_cell_input(self, *args):
        value = self.buyer_cell_var.get()
        # Allow only digits and max 11 chars
        if not value.isdigit() and value != "":
            # Remove non-digits
            cleaned = ''.join(filter(str.isdigit, value))
            if value != cleaned:
                self.buyer_cell_var.set(cleaned)
                return
        
        if len(value) > 11:
            self.buyer_cell_var.set(value[:11])
            return

        self.check_form_validity()
        
        # Real-time feedback
        if len(value) == 11:
            if not value.startswith("03"):
                 self.show_field_error(self.buyer_cell_entry, "Invalid Format. Must start with 03")
            else:
                 self.clear_field_error(self.buyer_cell_entry)
        elif len(value) > 0:
             # Don't show error while typing unless it's obviously wrong (not implemented here to be less annoying)
             pass
        else:
             self.clear_field_error(self.buyer_cell_entry)

    def validate_cell_strict(self, event=None):
        """Strict validation on FocusOut."""
        value = self.buyer_cell_var.get()
        if not value:
            return # Empty is handled by required check on submit
            
        if not re.match(r"^03\d{9}$", value):
            self.show_field_error(self.buyer_cell_entry, "Invalid Format. Must be 03XXXXXXXXX (11 digits)")
        else:
            self.clear_field_error(self.buyer_cell_entry)

    def validate_ntn_input(self, *args):
        value = self.buyer_ntn_var.get()
        try:
            cursor_pos = self.buyer_ntn_entry.index(ctk.INSERT)
        except:
            cursor_pos = len(value)
        
        if value == "":
            self.check_form_validity()
            return
        
        # Allow digits and dash (hyphen) for NTN like "1234567-8"
        cleaned = ''.join(c for c in value if c.isdigit() or c == '-')
        
        if value != cleaned:
            # Preserve cursor relative to allowed chars
            # Subtract count of removed chars before cursor
            removed_before = 0
            for i, c in enumerate(value[:cursor_pos]):
                if not (c.isdigit() or c == '-'):
                    removed_before += 1
            
            new_cursor = cursor_pos - removed_before
            
            self.buyer_ntn_var.set(cleaned)
            
            # Defer cursor restore to avoid UI reset races
            if hasattr(self, '_ntn_cursor_job') and self._ntn_cursor_job:
                try:
                    self.after_cancel(self._ntn_cursor_job)
                except:
                    pass
            
            def set_cursor():
                try:
                    self.buyer_ntn_entry.icursor(new_cursor)
                except:
                    pass
                self._ntn_cursor_job = None
            
            self._ntn_cursor_job = self.after(1, set_cursor)
            return
        
        self.check_form_validity()

    def check_form_validity(self):
        # We now handle validation on submit with detailed errors.
        # So we always keep the button enabled to allow the user to click and see errors.
        if hasattr(self, 'submit_btn'):
            self.submit_btn.configure(state="normal")
        return

    def validate_cnic_input(self, *args):
        if hasattr(self, '_cnic_formatting') and self._cnic_formatting:
            return

        value = self.buyer_cnic_var.get()
        
        # Debounce/Throttle: Trigger suggestions after a short delay
        if hasattr(self, '_cnic_suggestion_job') and self._cnic_suggestion_job:
            self.after_cancel(self._cnic_suggestion_job)
        self._cnic_suggestion_job = self.after(100, self._run_cnic_suggestion)
        
        # Get current cursor position to restore it later
        try:
            cursor_pos = self.buyer_cnic_entry.index(ctk.INSERT)
        except:
            cursor_pos = len(value)

        # Remove any non-digit/non-dash characters
        clean_digits = ''.join(filter(str.isdigit, value))
        
        formatted = clean_digits
        if len(clean_digits) > 5:
             formatted = clean_digits[:5] + '-' + clean_digits[5:]
        if len(clean_digits) > 12:
             formatted = formatted[:13] + '-' + formatted[13:]
             
        # Limit to max chars (13 digits + 2 dashes = 15)
        if len(formatted) > 15:
            formatted = formatted[:15]
            
        if value != formatted:
            self._cnic_formatting = True
            try:
                # Adjust cursor position
                non_digits_before = sum(1 for c in value[:cursor_pos] if not c.isdigit())
                clean_pos = cursor_pos - non_digits_before
                
                new_cursor = clean_pos
                if clean_pos > 5:
                    new_cursor += 1
                if clean_pos > 12:
                    new_cursor += 1
                
                self.buyer_cnic_var.set(formatted)
                
                # Restore cursor with slight delay
                def set_cursor():
                    try:
                        self.buyer_cnic_entry.icursor(new_cursor)
                    except:
                        pass
                self.after(1, set_cursor)
            finally:
                self._cnic_formatting = False

            if len(clean_digits) == 13:
                 self.perform_cnic_lookup(formatted)
            return

        # Auto-fill customer details if CNIC is complete (13 digits)
        if len(clean_digits) == 13:
             self.perform_cnic_lookup(formatted)
             self.clear_field_error(self.buyer_cnic_entry)
        else:
             self.clear_field_error(self.buyer_cnic_entry)

        self.check_form_validity()

    def _run_cnic_suggestion(self):
        self._cnic_suggestion_job = None
        self.update_cnic_suggestions()

    def perform_cnic_lookup(self, cnic=None):
        """Wrapper to trigger customer lookup."""
        if not cnic:
            cnic = self.buyer_cnic_var.get()
            
        # Ensure it looks like a valid CNIC before querying (13 digits, ignoring dashes)
        clean_digits = ''.join(filter(str.isdigit, cnic))
        
        # Validation
        if not cnic:
             return

        if len(clean_digits) != 13:
             self.show_field_error(self.buyer_cnic_entry, "Invalid CNIC. Must be 13 digits.")
             return
        else:
             self.clear_field_error(self.buyer_cnic_entry)

        if len(clean_digits) == 13:
             self.auto_fill_customer_by_cnic(cnic)

    def auto_fill_customer_by_cnic(self, cnic):
        """Fetches customer details from the last invoice with this CNIC."""
        db = SessionLocal()
        try:
            invoice = invoice_service.get_last_invoice_by_cnic(db, cnic)
            if invoice:
                # Populate fields
                if invoice.buyer_name:
                    self.buyer_name_var.set(invoice.buyer_name)
                if invoice.buyer_father_name:
                    self.father_name_var.set(invoice.buyer_father_name)
                if invoice.buyer_phone:
                    self.buyer_cell_var.set(invoice.buyer_phone)
                if invoice.buyer_address:
                    self.buyer_address_var.set(invoice.buyer_address)
        except Exception as e:
            print(f"Error fetching customer by CNIC: {e}")
        finally:
            db.close()

    def display_qr_code(self, data):
        logging.info(f"Displaying QR Code for data: {data}")
        if not data:
            logging.warning("No data for QR Code")
            return
        
        try:
            # Generate QR
            qr = qrcode.QRCode(version=1, box_size=10, border=2)
            qr.add_data(data)
            qr.make(fit=True)
            qr_img_pil = qr.make_image(fill_color="black", back_color="white")
            
            # Resize (PIL Image)
            qr_img_pil = qr_img_pil.resize((150, 150))
            
            # Convert to CTkImage
            self.qr_image = ctk.CTkImage(light_image=qr_img_pil, dark_image=qr_img_pil, size=(150, 150))
            
            self.qr_code_label.configure(image=self.qr_image, text="")
            self.fbr_inv_label.configure(text=data)
            logging.info("QR Code displayed successfully")
        except Exception as e:
            logging.error(f"QR Code Error: {e}", exc_info=True)
            print(f"QR Code Error: {e}")

    def confirm_and_reset(self):
        """Asks for confirmation before resetting if form has data."""
        # Check if key fields have data
        if (self.inv_num_entry.get() or 
            self.buyer_name_entry.get() or 
            self.chassis_entry.get() or
            self.buyer_cnic_entry.get()):
            
            if not messagebox.askyesno("Confirm Reset", "Are you sure you want to reset the form?\nAll entered data will be lost."):
                return
        
        # Reset everything unconditionally when manually clicked
        self.reset_form(clear_qr=True, force_reset=True)

    def reset_form(self, clear_qr=True, qr_data=None, force_reset=False):
        self.is_dealer_selected = False
        logging.info(f"Resetting form. clear_qr={clear_qr}, qr_data={qr_data}, force_reset={force_reset}, preserve_buyer={self.preserve_buyer_details_var.get()}")
        self.generate_invoice_number() # Auto-generate next number
        
        # Clear Errors
        for entry in [self.buyer_ntn_entry, self.buyer_cnic_entry, self.buyer_name_entry, self.buyer_father_entry,
                     self.buyer_cell_entry, self.buyer_address_entry, self.chassis_entry,
                     self.engine_entry, self.amount_excl_entry,
                     self.tax_entry, self.further_tax_entry, self.total_price_entry,
                     self.qty_entry, self.inv_num_entry]:
             self.clear_field_error(entry)
        
        # Clear fields (inv_num_entry excluded as it is readonly and set via generate_invoice_number)
        # Note: qty_entry is handled separately below due to state toggle
        
        # Fields that are ALWAYS cleared
        fields_to_clear = [
            self.buyer_ntn_entry, 
            self.chassis_entry,
            self.engine_entry, 
            self.amount_excl_entry,
            self.tax_entry, 
            self.further_tax_entry, 
            self.total_price_entry
        ]

        # Fields to conditionally clear based on "Preserve" checkbox
        buyer_fields = [
            self.buyer_cnic_entry, 
            self.buyer_name_entry, 
            self.buyer_father_entry,
            self.buyer_cell_entry, 
            self.buyer_address_entry
        ]

        # If force_reset is True, clear the preserve checkbox and add buyer fields to clear list
        if force_reset:
             self.preserve_buyer_details_var.set(False)
             fields_to_clear.extend(buyer_fields)
        elif not self.preserve_buyer_details_var.get():
            fields_to_clear.extend(buyer_fields)

        for entry in fields_to_clear:
            self.update_entry_value(entry, "")

        # Reset Quantity Logic
        self.manual_qty_var.set(False)
        self.qty_entry.configure(state="normal") # Temporarily enable to clear/set
        self.qty_entry.delete(0, 'end')
        self.qty_entry.insert(0, "1")
        self.qty_entry.configure(state="disabled")

        # Reset Amount/Tax Manual Toggles
        self.manual_amount_var.set(False)
        self.amount_excl_entry.configure(state="disabled")
        
        self.manual_tax_var.set(False)
        self.tax_entry.configure(state="disabled")
        
        self.manual_ft_var.set(False)
        self.further_tax_entry.configure(state="disabled")
        
        self.manual_total_var.set(False)
        self.total_price_entry.configure(state="disabled")
        
        # Clear Dropdowns
        self.model_combo.set("")
        self.color_combo.set("")
        
        # Reset Payment Mode to default (Cash) as it should be populated
        self.payment_mode_combo.set("Cash")
        
        # Reset Chassis Verify Checkbox and Feedback
        self.verify_chassis_var.set(False)
        self.chassis_feedback_label.configure(text="")

        # Reset state
        self.current_levy = 0
        self.current_price_obj = None
        
        # QR Code Handling
        if qr_data:
             logging.info(f"Scheduling QR Code display for data: {qr_data}")
             # Use short delay to ensure UI is settled (avoid race with focus_set)
             self.after(200, lambda d=qr_data: self.display_qr_code(d))
        elif clear_qr:
             logging.info("Clearing QR Code")
             # Use empty image instead of None to avoid potential CTk bug where widget state breaks
             self.qr_code_label.configure(image=self.empty_qr_image, text="")
             self.qr_image = self.empty_qr_image # Keep reference
             self.fbr_inv_label.configure(text="")
        else:
             logging.info("Skipping QR Code clear")

        # Do not auto-select default model, so fields remain empty
        
        # Focus on ID Card field after reset
        self.after(100, lambda: self.buyer_cnic_entry.focus_set())

    def create_inventory_frame(self):
        self.inventory_frame = InventoryFrame(self, corner_radius=0, fg_color="transparent")
        self.inventory_frame.grid_columnconfigure(0, weight=1)

    def create_reports_frame(self):
        self.reports_frame = ReportsFrame(self, corner_radius=0, fg_color="transparent")
        self.reports_frame.grid_columnconfigure(0, weight=1)

    def create_dealer_frame(self):
        self.dealer_frame = DealerFrame(self, corner_radius=0, fg_color="transparent")
        self.dealer_frame.grid_columnconfigure(0, weight=1)

    def create_customer_frame(self):
        self.customer_frame = CustomerFrame(self, corner_radius=0, fg_color="transparent")
        self.customer_frame.grid_columnconfigure(0, weight=1)

    def create_print_frame(self):
        self.print_invoice_frame = PrintInvoiceFrame(self, corner_radius=0, fg_color="transparent")
        self.print_invoice_frame.grid_columnconfigure(0, weight=1)

    def create_backup_frame(self):
        self.backup_frame = BackupFrame(self, corner_radius=0, fg_color="transparent")
        self.backup_frame.grid_columnconfigure(0, weight=1)

    def create_captured_data_frame(self):
        self.captured_data_frame = CapturedDataFrame(self, corner_radius=0, fg_color="transparent")
        self.captured_data_frame.grid_columnconfigure(0, weight=1)

    def create_welcome_frame(self):
        self.welcome_frame = WelcomeFrame(self, self.dismiss_welcome)
        # Use high rowspan/columnspan to cover the entire grid (sidebar + content)
        self.welcome_frame.grid(row=0, column=0, rowspan=10, columnspan=10, sticky="nsew")
        self.welcome_frame.lift() # Ensure it's on top

    def dismiss_welcome(self):
        if hasattr(self, 'welcome_frame'):
            self.welcome_frame.destroy()
            del self.welcome_frame

    def on_cnic_key_release(self, event=None):
        """Handle key release for CNIC suggestion logic"""
        if event and event.keysym in ["Down", "Up", "Return", "Escape", "Tab"]:
            return
            
        # self.update_cnic_suggestions() # Moved to validate_cnic_input for better integration with auto-formatting
        pass

    def update_cnic_suggestions(self):
        query = self.buyer_cnic_var.get().strip()
        
        # Hide if empty or too short to be useful
        if not query or len(query) < 1:
            self.hide_cnic_suggestions()
            return
            
        db = SessionLocal()
        try:
            # BROAD SEARCH:
            # 1. Strip non-digits for raw CNIC search
            clean_query = ''.join(filter(str.isdigit, query))
            
            # 2. Build flexible search pattern
            search_pattern = f"%{query}%"
            clean_pattern = f"%{clean_query}%" if clean_query else search_pattern
            
            # 3. Query Customers table (includes Dealers)
            # Match by Formatted CNIC, Raw Digits, Name, or Business Name
            results = db.query(Customer).filter(
                Customer.is_deleted == False,
                (Customer.cnic.ilike(f"{query}%")) | 
                (Customer.cnic.ilike(clean_pattern)) |
                (Customer.name.ilike(search_pattern)) |
                (Customer.business_name.ilike(search_pattern))
            ).limit(7).all()
            
            if results:
                self.show_cnic_suggestions(results)
            else:
                self.hide_cnic_suggestions()
                
        except Exception as e:
            print(f"CNIC Suggestion error: {e}")
        finally:
            db.close()

    def show_cnic_suggestions(self, customers):
        # Update UI layout to ensure coordinate accuracy
        self.update_idletasks()
        
        # Create Toplevel if not exists
        if self.cnic_suggestion_window is None or not self.cnic_suggestion_window.winfo_exists():
            root = self.winfo_toplevel()
            self.cnic_suggestion_window = ctk.CTkToplevel(root)
            self.cnic_suggestion_window.overrideredirect(True)
            self.cnic_suggestion_window.attributes("-topmost", True)
            try:
                self.cnic_suggestion_window.wm_attributes("-topmost", True)
            except: pass
            self.cnic_suggestion_window.configure(fg_color=("gray95", "gray20"))
            
            self.cnic_suggestion_frame = ctk.CTkScrollableFrame(self.cnic_suggestion_window, corner_radius=0, fg_color="transparent")
            self.cnic_suggestion_frame.pack(fill="both", expand=True)
            
        # Clear existing buttons
        for btn in self.cnic_suggestion_buttons:
            btn.destroy()
        self.cnic_suggestion_buttons = []
        self.cnic_suggestions_data = customers
        
        # Reset selection
        self.cnic_selected_suggestion_index = -1
        
        # Populate frame
        for idx, customer in enumerate(customers):
            # Show both CNIC and Name/Business for clear identification
            name_part = customer.name or (customer.business_name or "Unknown")
            display_text = f"{customer.cnic} | {name_part}"
            
            btn = ctk.CTkButton(
                self.cnic_suggestion_frame, 
                text=display_text, 
                anchor="w",
                fg_color="transparent", 
                text_color=("black", "white"),
                hover_color=("gray75", "gray30"),
                corner_radius=0,
                command=lambda c=customer: self.select_cnic_suggestion(c)
            )
            btn.pack(fill="x", padx=0, pady=0)
            self.cnic_suggestion_buttons.append(btn)
            
        # Position the window relative to entry
        try:
            # Get entry coordinates relative to screen
            root_x = self.buyer_cnic_entry.winfo_rootx()
            root_y = self.buyer_cnic_entry.winfo_rooty()
            height = self.buyer_cnic_entry.winfo_height()
            width = self.buyer_cnic_entry.winfo_width()
            
            # Calculate height (max 200px)
            req_height = min(len(customers) * 32 + 10, 200)
            
            # SCREEN BOUNDARY AWARENESS:
            # If dropdown overflows bottom of screen, flip it above the input field
            screen_height = self.winfo_screenheight()
            if root_y + height + req_height > screen_height:
                pos_y = root_y - req_height - 2
            else:
                pos_y = root_y + height + 2
                
            geometry_str = f"{width}x{req_height}+{root_x}+{pos_y}"
            self.cnic_suggestion_window.geometry(geometry_str)
            self.cnic_suggestion_window.deiconify()
            self.cnic_suggestion_window.lift()
        except Exception as e:
            print(f"Error placing CNIC suggestion window: {e}")

    def hide_cnic_suggestions(self):
        if self.cnic_suggestion_window and self.cnic_suggestion_window.winfo_exists():
            self.cnic_suggestion_window.withdraw()
        self.cnic_selected_suggestion_index = -1

    def on_cnic_suggestion_nav(self, event):
        if not self.cnic_suggestion_window or not self.cnic_suggestion_window.winfo_exists() or not self.cnic_suggestion_window.winfo_viewable():
            return
            
        count = len(self.cnic_suggestion_buttons)
        if count == 0:
            return
            
        if event.keysym == "Down":
            self.cnic_selected_suggestion_index = (self.cnic_selected_suggestion_index + 1) % count
        elif event.keysym == "Up":
            self.cnic_selected_suggestion_index = (self.cnic_selected_suggestion_index - 1 + count) % count
            
        self.highlight_cnic_suggestion()

    def highlight_cnic_suggestion(self):
        for idx, btn in enumerate(self.cnic_suggestion_buttons):
            if idx == self.cnic_selected_suggestion_index:
                btn.configure(fg_color=("gray85", "gray40"))
                # Scroll to ensure visible if needed (CTkScrollableFrame handle)
            else:
                btn.configure(fg_color="transparent")

    def on_cnic_suggestion_select(self, event=None):
        if 0 <= self.cnic_selected_suggestion_index < len(self.cnic_suggestions_data):
            customer = self.cnic_suggestions_data[self.cnic_selected_suggestion_index]
            self.select_cnic_suggestion(customer)
            return "break"

    def select_cnic_suggestion(self, customer):
        self.hide_cnic_suggestions()
        # Use existing selection logic
        self._on_cnic_select(customer)

    def on_cnic_focus_out(self, event=None):
        """Handle focus out for CNIC entry"""
        self.hide_cnic_suggestions()
        self.perform_cnic_lookup()

    def select_frame_by_name(self, name):
        self.current_frame_name = name
        # Close any open menu first
        self.close_menu()

        # Define Frame Mapping: Name -> (Frame Instance, Refresh Callback)
        frames = {
            "home": (getattr(self, "home_frame", None), None),
            "inventory": (getattr(self, "inventory_frame", None), lambda: self.inventory_frame.refresh_inventory()),
            "invoice": (getattr(self, "invoice_frame", None), self._setup_invoice_frame),
            "reports": (getattr(self, "reports_frame", None), lambda: self.reports_frame.load_data()),
            "dealer": (getattr(self, "dealer_frame", None), lambda: self.dealer_frame.load_dealers()),
            "customer": (getattr(self, "customer_frame", None), lambda: self.customer_frame.load_customers()),
            "backup": (getattr(self, "backup_frame", None), lambda: self.backup_frame.refresh_history()),
            "print_invoice": (getattr(self, "print_invoice_frame", None), None),
            "captured_data": (getattr(self, "captured_data_frame", None), lambda: self.captured_data_frame.load_data()),
            "spare_ledger": (getattr(self, "spare_ledger_frame", None), lambda: self.spare_ledger_frame.refresh()),
        }

        # Get target frame info
        target_info = frames.get(name)
        if not target_info:
            print(f"Frame not found: {name}")
            return
            
        target_frame, refresh_action = target_info
        
        if not target_frame:
             print(f"Frame instance missing for: {name}")
             return

        # Optimization: Prevent flickering by only switching if different
        if hasattr(self, "_visible_frame") and self._visible_frame == target_frame:
            # Run refresh action even if frame is same (e.g. clicking menu item again)
            if refresh_action:
                try:
                    refresh_action()
                except Exception as e:
                    print(f"Error refreshing frame {name}: {e}")
            return

        # 1. Show New Frame (Overlay on top first to prevent white flash)
        target_frame.grid(row=1, column=0, sticky="nsew")
        target_frame.lift() # Ensure it's on top
        
        # 2. Hide Old Frame
        if hasattr(self, "_visible_frame") and self._visible_frame and self._visible_frame != target_frame:
            self._visible_frame.grid_forget()
        else:
            # Fallback: Hide all others to be safe (e.g. first run)
            for key, (frame, _) in frames.items():
                if frame and frame != target_frame:
                    frame.grid_forget()
        
        # 3. Update Tracking
        self._visible_frame = target_frame
        
        # 4. Run Refresh Action
        if refresh_action:
            try:
                self.after(10, refresh_action)
            except Exception as e:
                print(f"Error refreshing frame {name}: {e}")

    def _setup_invoice_frame(self):
        self.generate_invoice_number() # Auto-generate Invoice No
        # Focus on ID Card field when frame is shown
        if hasattr(self, 'buyer_cnic_entry'):
            self.after(100, lambda: self.buyer_cnic_entry.focus_set())

    def generate_invoice_number(self):
        """Fetches the next auto-incremented invoice number."""
        db = SessionLocal()
        try:
            next_inv_num = invoice_service.generate_next_invoice_number(db)
            self.inv_num_var.set(next_inv_num)
        except Exception as e:
            print(f"Error generating invoice number: {e}")
            self.inv_num_var.set("ERROR")
        finally:
            db.close()

    def home_button_event(self):
        self.select_frame_by_name("home")

    def inventory_button_event(self):
        self.select_frame_by_name("inventory")

    def invoice_button_event(self):
        self.select_frame_by_name("invoice")

    def reports_button_event(self):
        self.select_frame_by_name("reports")

    def dealer_button_event(self):
        self.select_frame_by_name("dealer")

    def customer_button_event(self):
        self.select_frame_by_name("customer")

    def backup_button_event(self):
        self.select_frame_by_name("backup")

    def print_invoice_button_event(self):
        self.select_frame_by_name("print_invoice")



    def captured_data_button_event(self):
        self.select_frame_by_name("captured_data")

    def open_price_list(self):
        PriceListDialog(self)

    def open_fbr_settings(self):
        FBRSettingsDialog(self)

    def open_db_settings(self):
        DatabaseSettingsDialog(self)

    def open_reporting_portal(self):
        try:
            webbrowser.open("http://localhost:9000/")
        except Exception as e:
            messagebox.showerror("Error", f"Unable to open reporting portal: {e}")

    def form_capture_button_event(self):
        """Launch the Browser for Import / Capture"""
        if form_capture_service.is_running:
             messagebox.showinfo("Browser Running", "The browser is already running.\nYou can use 'Import' or 'Capture' features now.")
             return

        # Default to Atlas Honda Portal base URL
        target_url = "https://dealers.ahlportal.com"
        
        try:
            form_capture_service.start_capture_session(target_url)
            messagebox.showinfo("Browser Launched", "Browser launched successfully.\nYou can now use 'Import' or 'Capture' features.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch browser: {e}")

    def _populate_bike_details(self, bike):
        """Helper to populate form fields from bike object"""
        # Auto-fill Engine
        self.engine_entry.delete(0, "end")
        self.engine_entry.insert(0, bike.engine_number)
        
        # Auto-fill Model & Color
        model_name = bike.product_model.model_name if bike.product_model else None
        if model_name and model_name in self.model_combo._values:
            self.model_combo.set(model_name)
            # Trigger model change logic to update colors and base price
            self.on_model_change(model_name)
        
        # Ensure the bike's color is available in the dropdown
        if bike.color:
            current_colors = self.color_combo._values
            if bike.color not in current_colors:
                 # Add missing color temporarily
                 new_values = list(current_colors) + [bike.color]
                 self.color_combo.configure(values=new_values)
            
            self.color_combo.set(bike.color)
            # Explicitly update price for the specific color
            self.on_color_change(bike.color)
        
        # Handle Price Fallback if no active price found
        if not self.current_price_obj:
            self.update_entry_value(self.amount_excl_entry, str(bike.sale_price))
            self.current_levy = 0
            self.calculate_totals() # Trigger tax calc manually since on_model_change didn't do it fully

    def on_verify_chassis_change(self):
        """Trigger re-validation when checkbox state changes."""
        self.auto_fill_chassis()

    def scan_cnic_action(self):
        """Opens file dialog for ID Card Front (and optional Back) and extracts text."""
        if not ocr_service.is_available():
            messagebox.showerror("OCR Unavailable", f"OCR features are disabled.\nReason: {ocr_service.get_error()}")
            return

        try:
            # 1. Ask for Front Image
            front_path = filedialog.askopenfilename(
                title="Select ID Card FRONT Image",
                filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp")]
            )
            
            if not front_path:
                return # User cancelled

            # 2. Ask for Back Image (Optional)
            if messagebox.askyesno("Scan Back Side?", "Do you want to scan the BACK side for Address?"):
                back_path = filedialog.askopenfilename(
                    title="Select ID Card BACK Image",
                    filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp")]
                )
            else:
                back_path = None
            
            # 3. Show loading indicator (simple)
            original_text = self.scan_btn.cget("text")
            self.scan_btn.configure(text="Scanning...", state="disabled")
            self.update_idletasks()
            
            # 4. Process via Service
            def run_scan():
                try:
                    data = ocr_service.parse_cnic_data(front_path, back_path)
                    
                    # Schedule UI update on main thread
                    def update_ui():
                        if data["cnic"]:
                            self.buyer_cnic_var.set(data["cnic"])
                        if data["name"]:
                            self.buyer_name_var.set(data["name"])
                        if data["father_name"]:
                            self.father_name_var.set(data["father_name"])
                        if data["address"]:
                            self.buyer_address_var.set(data["address"])
                        
                        self.scan_btn.configure(text=original_text, state="normal")
                        messagebox.showinfo("Success", "ID Card scanned successfully!\nPlease verify extracted data.")
                    
                    self.after(0, update_ui)
                    
                except RuntimeError as e:
                    self.after(0, lambda: messagebox.showerror("OCR Error", str(e)))
                    self.after(0, lambda: self.scan_btn.configure(text=original_text, state="normal"))
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("Error", f"Failed to scan: {str(e)}"))
                    self.after(0, lambda: self.scan_btn.configure(text=original_text, state="normal"))

            # Run in background thread to avoid freezing UI
            threading.Thread(target=run_scan, daemon=True).start()
                
        except Exception as e:
            print(f"Scan Action Error: {e}")
            self.scan_btn.configure(text="📷 Scan ID", state="normal")

    def auto_fill_cnic(self, event=None):
        cnic = self.buyer_cnic_var.get().strip()
        
        # If CNIC is incomplete (assuming 15 chars with dashes), clear fields
        if not cnic or len(cnic) < 15: 
            self.buyer_name_var.set("")
            self.father_name_var.set("")
            self.buyer_cell_var.set("")
            self.buyer_address_var.set("")
            return
            
        db = SessionLocal()
        try:
            customer = db.query(Customer).filter(Customer.cnic == cnic).first()
            if customer:
                self.buyer_name_var.set(customer.name)
                self.father_name_var.set(customer.father_name or "")
                self.buyer_cell_var.set(customer.phone or "")
                self.buyer_address_var.set(customer.address or "")
        except Exception as e:
            print(f"CNIC Auto-fill error: {e}")
        finally:
            db.close()

    def on_chassis_key_release(self, event=None):
        """Handle key release for suggestion logic"""
        # If special keys (arrows, enter), ignore here as they are handled by separate binds
        if event and event.keysym in ["Down", "Up", "Return", "Escape"]:
            return
            
        self.update_suggestions()
        
        # Check if field was cleared or modified
        self.check_chassis_cleared()
        
        # Restore auto-fill for manual typing
        self.auto_fill_chassis()

    def check_chassis_cleared(self):
        """Clear related fields if chassis is empty or doesn't match a full chassis"""
        chassis = self.chassis_var.get().strip()
        # You can define a minimum length for a valid chassis if needed, e.g. < 5
        if not chassis:
            self.clear_bike_details()
            # self.clear_customer_details() # Keep customer details as per user request

    def clear_bike_details(self):
        """Clear all bike-related fields"""
        self.engine_var.set("")
        self.model_combo.set("")
        self.color_combo.set("")
        self.amount_var.set("")
        self.update_entry_value(self.tax_entry, "")
        self.update_entry_value(self.further_tax_entry, "")
        self.update_entry_value(self.total_price_entry, "")
        self.chassis_feedback_label.configure(text="", text_color="black")

    def clear_customer_details(self):
        self.buyer_cnic_var.set("")
        self.buyer_name_var.set("")
        self.father_name_var.set("")
        self.buyer_cell_var.set("")
        self.buyer_address_var.set("")
        
    def update_suggestions(self):
        query = self.chassis_var.get().strip()
        
        # Hide if empty or too short
        if not query or len(query) < 1:
            self.hide_suggestions()
            return
            
        db = SessionLocal()
        try:
            # Fetch IN_STOCK chassis matching query (limit 10)
            results = db.query(Motorcycle.chassis_number).filter(
                Motorcycle.status == "IN_STOCK",
                Motorcycle.chassis_number.like(f"%{query}%")
            ).limit(10).all()
            
            suggestions = [r[0] for r in results]
            
            if suggestions:
                self.show_suggestions(suggestions)
            else:
                self.hide_suggestions()
                
        except Exception as e:
            print(f"Suggestion error: {e}")
        finally:
            db.close()

    def show_suggestions(self, suggestions):
        # Create Toplevel if not exists
        if self.suggestion_window is None or not self.suggestion_window.winfo_exists():
            self.suggestion_window = ctk.CTkToplevel(self)
            self.suggestion_window.overrideredirect(True)
            self.suggestion_window.attributes("-topmost", True)
            self.suggestion_window.wm_attributes("-topmost", True) # Windows specific
            self.suggestion_window.configure(fg_color=("gray95", "gray20"))
            
            # Create a scrollable frame inside the toplevel
            self.suggestion_frame = ctk.CTkScrollableFrame(self.suggestion_window, corner_radius=0, fg_color="transparent")
            self.suggestion_frame.pack(fill="both", expand=True)
            
        # Clear existing buttons
        for btn in self.suggestion_buttons:
            btn.destroy()
        self.suggestion_buttons = []
        
        # Reset selection
        self.selected_suggestion_index = -1
        
        # Populate frame
        for idx, chassis in enumerate(suggestions):
            btn = ctk.CTkButton(
                self.suggestion_frame, 
                text=chassis, 
                anchor="w",
                fg_color="transparent", 
                text_color=("black", "white"),
                hover_color=("gray75", "gray30"),
                corner_radius=0,
                command=lambda c=chassis: self.select_suggestion(c)
            )
            btn.pack(fill="x", padx=0, pady=0)
            self.suggestion_buttons.append(btn)
            
        # Position the window relative to entry (Global Coordinates)
        try:
            root_x = self.chassis_entry.winfo_rootx()
            root_y = self.chassis_entry.winfo_rooty()
            height = self.chassis_entry.winfo_height()
            width = self.chassis_entry.winfo_width()
            
            # Calculate height based on items (max 150)
            req_height = min(len(suggestions) * 30 + 10, 150)
            
            geometry_str = f"{width}x{req_height}+{root_x}+{root_y + height + 2}"
            self.suggestion_window.geometry(geometry_str)
            self.suggestion_window.deiconify() # Ensure visible
            self.suggestion_window.lift() # Ensure on top
        except Exception as e:
            print(f"Error placing suggestion window: {e}")

    def hide_suggestions(self):
        if self.suggestion_window and self.suggestion_window.winfo_exists():
            self.suggestion_window.withdraw()
        self.selected_suggestion_index = -1

    def on_suggestion_nav(self, event):
        if not self.suggestion_window or not self.suggestion_window.winfo_exists() or not self.suggestion_window.winfo_viewable():
            return
            
        count = len(self.suggestion_buttons)
        if count == 0:
            return
            
        if event.keysym == "Down":
            self.selected_suggestion_index = (self.selected_suggestion_index + 1) % count
        elif event.keysym == "Up":
            self.selected_suggestion_index = (self.selected_suggestion_index - 1 + count) % count
            
        self.highlight_suggestion()
        return "break" # Stop default behavior

    def highlight_suggestion(self):
        for i, btn in enumerate(self.suggestion_buttons):
            if i == self.selected_suggestion_index:
                btn.configure(fg_color=("gray70", "gray40"))
                # Try to scroll to item (simple approach)
                # Scrollable frame doesn't support see() easily, but this highlights it
            else:
                btn.configure(fg_color="transparent")

    def on_suggestion_select(self, event=None):
        if self.suggestion_window and self.suggestion_window.winfo_viewable() and self.selected_suggestion_index >= 0:
            text = self.suggestion_buttons[self.selected_suggestion_index].cget("text")
            self.select_suggestion(text)
            return "break"

    def select_suggestion(self, chassis):
        self.chassis_var.set(chassis)
        self.hide_suggestions()
        self.chassis_entry.icursor("end") # Move cursor to end
        # Trigger detail population
        self.auto_fill_chassis()

    def on_chassis_focus_out(self, event):
        # Delay hiding to allow click event on button or scrollbar interaction
        self.after(200, self._check_focus_and_hide)

    def _check_focus_and_hide(self):
        """Check if we should really hide the suggestion window."""
        if not self.suggestion_window or not self.suggestion_window.winfo_exists() or not self.suggestion_window.winfo_viewable():
            return

        # 1. Check if mouse is over the suggestion window
        # This prevents closing while the user is scrolling or hovering
        try:
            x, y = self.suggestion_window.winfo_pointerxy()
            win_x = self.suggestion_window.winfo_rootx()
            win_y = self.suggestion_window.winfo_rooty()
            win_w = self.suggestion_window.winfo_width()
            win_h = self.suggestion_window.winfo_height()
            
            # Add a small buffer/margin
            if (win_x <= x <= win_x + win_w) and (win_y <= y <= win_y + win_h):
                # Mouse is over window, keep checking periodically
                self.after(100, self._check_focus_and_hide)
                return
        except Exception:
            pass

        # 2. Check focus
        # If focus moved to the suggestion window (e.g. scrollbar), keep it open
        focused = self.focus_get()
        if focused:
            # Check if focused widget is part of suggestion window
            if str(focused).startswith(str(self.suggestion_window)):
                self.after(100, self._check_focus_and_hide)
                return
            
            # If focus returned to chassis entry, stop checking (FocusOut will trigger again later)
            if focused == self.chassis_entry:
                return 

        # If neither mouse is over nor focus is inside, hide it
        self.hide_suggestions()

    def auto_fill_chassis(self, event=None):
        """Auto-fill details when chassis is typed"""
        chassis = self.chassis_entry.get()
        if not chassis:
            self.chassis_feedback_label.configure(text="", text_color="black")
            return

        if len(chassis) < 5: # Optimization: don't query for very short strings
            self.chassis_feedback_label.configure(text="", text_color="black")
            return
            
        bypass_verification = self.verify_chassis_var.get()
        
        db = SessionLocal()
        try:
            bike = db.query(Motorcycle).filter(Motorcycle.chassis_number == chassis).first()
            if bike:
                if bike.status == "IN_STOCK":
                    self._populate_bike_details(bike)
                    self.chassis_feedback_label.configure(text="✔", text_color="green")
                else:
                    if bike.status == "SOLD":
                        messagebox.showinfo("Invoice Submitted", "You have allready submitted the invoice")
                        self.clear_customer_details()
                        if bypass_verification:
                            self.chassis_feedback_label.configure(text="⚠️ SOLD", text_color="orange")
                        else:
                            self.chassis_feedback_label.configure(text="Not In Stock", text_color="red")
                        return
                    
                    if bypass_verification:
                        self.chassis_feedback_label.configure(text="⚠️ " + bike.status, text_color="orange")
                    else:
                        self.chassis_feedback_label.configure(text="Not In Stock", text_color="red")
            else:
                # Check if this chassis has been previously posted (Historical Duplicate Check)
                if invoice_service.is_chassis_used_in_posted_invoice(db, chassis):
                    logger.warning(f"Duplicate chassis attempt detected in auto-fill: {chassis}")
                    messagebox.showerror("Duplicate Invoice", f"Invoice with chassis number {chassis} has already been posted")
                    self.chassis_feedback_label.configure(text="Duplicate", text_color="red")
                    self.chassis_var.set("") # Clear to prevent usage
                    return

                if bypass_verification:
                    self.chassis_feedback_label.configure(text="⚠️ Not Found", text_color="orange")
                else:
                    self.chassis_feedback_label.configure(text="Not Found", text_color="red")

            # Populate customer info from captured_data if exists
            try:
                cap = db.query(CapturedData).filter(CapturedData.chassis_number == chassis).first()
                if cap:
                    if cap.cnic:
                        self.buyer_cnic_var.set(cap.cnic)
                    if cap.name:
                        self.buyer_name_var.set(cap.name)
                    if cap.father:
                        self.father_name_var.set(cap.father)
                    if cap.cell:
                        self.buyer_cell_var.set(cap.cell)
                    if cap.address:
                        self.buyer_address_var.set(cap.address)
                    if cap.engine_number and not self.engine_var.get().strip():
                        self.engine_var.set(cap.engine_number)
                    
                    # Also populate model and color if not already set (e.g. from inventory)
                    if cap.model and not self.model_combo.get().strip():
                        # Find closest match in model_combo values
                        for val in self.model_combo._values:
                            if cap.model.upper() in val.upper() or val.upper() in cap.model.upper():
                                self.model_combo.set(val)
                                self.on_model_change(val)
                                break
                    
                    if cap.color and not self.color_combo.get().strip():
                        # Try to match color
                        for val in self.color_combo._values:
                            if cap.color.upper() in val.upper() or val.upper() in cap.color.upper():
                                self.color_combo.set(val)
                                self.on_color_change(val)
                                break
            except Exception as ce:
                print(f"Captured data lookup error: {ce}")
        except Exception as e:
            print(f"Auto-fill error: {e}")
            self.chassis_feedback_label.configure(text="Error", text_color="red")
        finally:
            db.close()

    def check_stock(self):
        chassis = self.chassis_entry.get()
        if not chassis:
            messagebox.showwarning("Input Required", "Please enter a Chassis Number")
            return
            
        db = SessionLocal()
        try:
            bike = db.query(Motorcycle).filter(Motorcycle.chassis_number == chassis).first()
            if bike:
                status = bike.status
                if status == "IN_STOCK":
                    make = bike.product_model.make if bike.product_model else "Unknown"
                    model = bike.product_model.model_name if bike.product_model else "Unknown"
                    msg = f"Available!\nMake: {make}\nModel: {model}\nColor: {bike.color}\nPrice: {bike.sale_price}"
                    messagebox.showinfo("Stock Check", msg)
                    
                    self._populate_bike_details(bike)
                    
                else:
                    messagebox.showwarning("Stock Check", f"Bike Found but Status is: {status}")
            else:
                messagebox.showerror("Stock Check", "Chassis Number NOT found in Inventory.")
        except Exception as e:
            messagebox.showerror("Error", f"Database error: {e}")
        finally:
            db.close()

    def submit_invoice(self):
        # 1. Confirmation Dialog
        if not messagebox.askyesno("Confirm Submission", "Are you sure you want to submit this invoice to FBR?"):
            return

        # Visual indication for loading state
        self.submit_btn.configure(state="disabled", text="Submitting...")
        self.update_idletasks()
        try:
            self._process_invoice_submission()
        finally:
            self.submit_btn.configure(state="normal", text="Submit Invoice")

    def _process_invoice_submission(self):
        # 1. Clear previous errors
        self.clear_field_error(self.inv_num_entry)
        self.clear_field_error(self.buyer_name_entry)
        self.clear_field_error(self.buyer_cnic_entry)
        self.clear_field_error(self.buyer_ntn_entry)
        self.clear_field_error(self.buyer_cell_entry)
        self.clear_field_error(self.chassis_entry)
        self.clear_field_error(self.qty_entry)
        self.clear_field_error(self.amount_excl_entry)
        self.clear_field_error(self.buyer_father_entry)
        self.clear_field_error(self.buyer_address_entry)
        self.clear_field_error(self.engine_entry)
        self.clear_field_error(self.model_combo)
        self.clear_field_error(self.color_combo)
        self.clear_field_error(self.payment_mode_combo)

        inv_num = self.inv_num_entry.get()
        buyer_cnic = self.buyer_cnic_entry.get()
        buyer_ntn = self.buyer_ntn_entry.get()
        buyer_name = self.buyer_name_entry.get()
        buyer_father = self.buyer_father_entry.get()
        buyer_cell = self.buyer_cell_entry.get()
        buyer_address = self.buyer_address_entry.get()
        payment_mode = self.payment_mode_combo.get()
        
        chassis = self.chassis_entry.get()
        engine = self.engine_entry.get()
        
        has_error = False

        # 2. Validate Numbers
        try:
            qty = float(self.qty_entry.get().replace(',', '') or 0)
            if qty <= 0:
                self.show_field_error(self.qty_entry, "Quantity must be > 0")
                has_error = True
            
            amount_excl = float(self.amount_excl_entry.get().replace(',', '') or 0)
            if amount_excl <= 0:
                self.show_field_error(self.amount_excl_entry, "Amount must be > 0")
                has_error = True

            tax = float(self.tax_entry.get().replace(',', '') or 0)
            further_tax = float(self.further_tax_entry.get().replace(',', '') or 0)
            total = float(self.total_price_entry.get().replace(',', '') or 0)
        except ValueError:
            logger.error("Invalid number format in invoice form")
            messagebox.showerror("Error", "Invalid Number Fields. Please check quantity and amounts.")
            return

        # 3. Validate Required Fields
        if not inv_num:
            self.show_field_error(self.inv_num_entry, "Invoice Number is required")
            has_error = True
        
        if not buyer_name:
            self.show_field_error(self.buyer_name_entry, "Buyer Name is required")
            has_error = True

        if not buyer_father:
            self.show_field_error(self.buyer_father_entry, "Father Name is required")
            has_error = True

        if not buyer_cnic:
            self.show_field_error(self.buyer_cnic_entry, "CNIC is required")
            has_error = True

        if not buyer_cell:
            self.show_field_error(self.buyer_cell_entry, "Cell Number is required")
            has_error = True

        if not buyer_address:
            self.show_field_error(self.buyer_address_entry, "Address is required")
            has_error = True

        if not chassis:
            self.show_field_error(self.chassis_entry, "Chassis Number is required")
            has_error = True

        if not engine:
            self.show_field_error(self.engine_entry, "Engine Number is required")
            has_error = True

        model_val = self.model_combo.get()
        if not model_val:
            self.show_field_error(self.model_combo, "Model is required")
            has_error = True

        color_val = self.color_combo.get()
        if not color_val:
            self.show_field_error(self.color_combo, "Color is required")
            has_error = True
            
        if not payment_mode:
             self.show_field_error(self.payment_mode_combo, "Payment Mode is required")
             has_error = True

        # 4. Validate Formats
        if buyer_cnic and not re.match(r"^\d{5}-\d{7}-\d{1}$", buyer_cnic):
            self.show_field_error(self.buyer_cnic_entry, "Invalid CNIC Format (33302-1234567-0)")
            has_error = True

        if buyer_ntn and not re.match(r"^\d{7}(-\d)?$", buyer_ntn):
            self.show_field_error(self.buyer_ntn_entry, "Invalid NTN Format (1234567-8)")
            has_error = True

        if buyer_cell and not re.match(r"^03\d{9}$", buyer_cell):
            self.show_field_error(self.buyer_cell_entry, "Invalid Cell Format (03XXXXXXXXX)")
            has_error = True

        # 5. Validate Chassis (Database Check)
        if chassis:
            bypass_verification = self.verify_chassis_var.get()
            db_check = SessionLocal()
            try:
                # Historical Duplicate Check (Critical for preventing double invoicing)
                if invoice_service.is_chassis_used_in_posted_invoice(db_check, chassis):
                    logger.warning(f"Submission blocked: Chassis {chassis} already invoiced")
                    self.show_field_error(self.chassis_entry, "Chassis already invoiced")
                    messagebox.showerror("Duplicate Invoice", f"Invoice with chassis number {chassis} has already been posted")
                    has_error = True
                
                bike = db_check.query(Motorcycle).filter(Motorcycle.chassis_number == chassis).first()
                if not bypass_verification:
                    if not bike:
                        self.show_field_error(self.chassis_entry, "Chassis not found in inventory")
                        has_error = True
                    elif bike.status != "IN_STOCK":
                        self.show_field_error(self.chassis_entry, f"Chassis is {bike.status}")
                        has_error = True
                else:
                    if not bike:
                        logger.warning(f"Bypassing verification: Chassis {chassis} not found")
                    elif bike.status != "IN_STOCK":
                        logger.warning(f"Bypassing verification: Chassis {chassis} is {bike.status}")

            except Exception as e:
                logger.error(f"Database error during chassis validation: {e}")
                messagebox.showerror("Database Error", f"Could not validate chassis: {e}")
                return
            finally:
                db_check.close()
        
        if has_error:
            logger.warning("Invoice submission blocked due to validation errors")
            messagebox.showwarning("Validation Error", "Please correct the highlighted fields before submitting.")
            return

        # 6. Proceed with Submission
        # Create dummy item for simplicity in this UI demo
        model = self.model_combo.get()
        color = self.color_combo.get()
        
        # Calculate standard sales tax rate (just for record)
        # tax (Sales Tax) and further_tax (Levy) are separate now
        # sales_tax_rate = (tax / amount_excl * 100) if amount_excl > 0 else 0
        
        # Fetch dynamic settings
        from app.services.settings_service import settings_service
        settings = settings_service.get_active_settings()
        
        sales_tax_rate = settings.get("tax_rate", 18.0)
        
        # Construct Item Name and Code based on FBR Settings
        # Format: {FBR_SETTING} {MODEL} {COLOR}
        fbr_item_name_base = settings.get("item_name", "Motorcycle") or "Motorcycle"
        fbr_item_code_base = settings.get("item_code", "MOTO") or "MOTO"
        fbr_pct_code = settings.get("pct_code", "8711.2010") or "8711.2010"

        final_item_name = f"{fbr_item_name_base} {model} {color}"
        final_item_code = f"{fbr_item_code_base}-{model}-{color}"

        item = InvoiceItemCreate(
            item_code=final_item_code,
            item_name=final_item_name,
            quantity=qty,
            tax_rate=sales_tax_rate, 
            sale_value=amount_excl, 
            tax_charged=tax,
            further_tax=further_tax,
            pct_code=fbr_pct_code,
            chassis_number=chassis,
            engine_number=engine,
            model_name=model,
            color=color
        )
        
        # Prepare NTN - Send "-" if empty or 0
        raw_ntn = self.buyer_ntn_var.get().strip()
        final_ntn = "-" if not raw_ntn or raw_ntn == "0" else raw_ntn

        inv = InvoiceCreate(
            invoice_number=inv_num,
            buyer_cnic=buyer_cnic,
            buyer_name=buyer_name,
            buyer_father_name=buyer_father,
            buyer_phone=buyer_cell,
            buyer_address=buyer_address,
            buyer_ntn=final_ntn,
            buyer_type=CustomerType.DEALER if self.is_dealer_selected else CustomerType.INDIVIDUAL,
            payment_mode=payment_mode,
            items=[item]
        )

        db = SessionLocal()
        try:
            logger.info(f"Submitting invoice {inv_num} for {buyer_name}")
            invoice = invoice_service.create_invoice(db, inv)
            fbr_id = invoice.fbr_invoice_number or "N/A"
            logger.info(f"Invoice {inv_num} created successfully. FBR ID: {fbr_id}")
            messagebox.showinfo("Success", f"Invoice Created and Queued for Sync\nFBR ID: {fbr_id}")
            
            # Pass fbr_id to reset_form directly to ensure it is displayed
            # This handles both resetting the form AND showing the QR code in one consistent step
            logging.info(f"Calling reset_form with qr_data={invoice.fbr_invoice_number}")
            self.reset_form(clear_qr=False, qr_data=invoice.fbr_invoice_number)
            
            if not invoice.fbr_invoice_number:
                logging.warning("No FBR invoice number to display QR code")
            
            # Stay on the same screen (reset done above)
        except RetryError as e:
            # Handle FBR Connection/Retry errors
            try:
                last_exception = e.last_attempt.exception()
                if isinstance(last_exception, requests.exceptions.ConnectionError):
                    msg = "Could not connect to FBR Server.\nPlease check your internet connection or FBR URL settings."
                elif isinstance(last_exception, requests.exceptions.Timeout):
                    msg = "Connection to FBR Server timed out."
                else:
                    msg = f"FBR Submission Failed: {str(last_exception)}"
            except:
                msg = f"FBR Submission Error: {str(e)}"
            
            logger.error(f"FBR RetryError: {msg}")
            messagebox.showerror("FBR Connection Error", msg)
        except Exception as e:
            logger.error(f"Unexpected error during invoice submission: {e}", exc_info=True)
            messagebox.showerror("Error", f"An unexpected error occurred:\n{str(e)}")
        finally:
            db.close()

if __name__ == "__main__":
    app = App()
    app.mainloop()
