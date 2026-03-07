import customtkinter as ctk
from tkinter import messagebox
import re

from app.services.settings_service import settings_service
from app.core.config import reload_settings, settings

class FBRSettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("FBR Settings")
        self.geometry("1050x800")
        self.resizable(True, True)
        
        # Ensure dialog is large enough and centered
        self.update_idletasks()
        
        self.transient(parent)
        self.grab_set()

        # Main Layout Configuration
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Main Scrollable Frame - Increased padding to prevent cut-off
        self.main_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(1, weight=1)

        # --- Section 1: API Configuration (Left Column) ---
        self.api_frame = ctk.CTkFrame(self.main_frame)
        self.api_frame.grid(row=0, column=0, padx=15, pady=10, sticky="nsew")
        self.api_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(self.api_frame, text="API Connection", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=2, pady=15)

        # Environment
        self._add_label(self.api_frame, "Environment:", 1, "Select FBR Environment (Sandbox for testing)")
        self.env_combo = ctk.CTkOptionMenu(self.api_frame, values=["SANDBOX", "PRODUCTION"], command=self.on_env_change)
        self.env_combo.grid(row=1, column=1, padx=10, pady=8, sticky="ew")

        # Base URL
        self._add_label(self.api_frame, "Base URL *:", 2, "FBR API Endpoint URL")
        self.base_url_entry = ctk.CTkEntry(self.api_frame)
        self.base_url_entry.grid(row=2, column=1, padx=10, pady=8, sticky="ew")

        # POS ID
        self._add_label(self.api_frame, "POS ID *:", 3, "Point of Sale ID assigned by FBR")
        self.pos_entry = ctk.CTkEntry(self.api_frame)
        self.pos_entry.grid(row=3, column=1, padx=10, pady=8, sticky="ew")

        # USIN
        self._add_label(self.api_frame, "USIN *:", 4, "Unique System Identification Number")
        self.usin_entry = ctk.CTkEntry(self.api_frame)
        self.usin_entry.grid(row=4, column=1, padx=10, pady=8, sticky="ew")

        # Token
        self._add_label(self.api_frame, "Auth Token *:", 5, "Bearer Token for API Authentication")
        self.token_entry = ctk.CTkEntry(self.api_frame, show="*")
        self.token_entry.grid(row=5, column=1, padx=10, pady=8, sticky="ew")

        # --- Section 2: Invoice Defaults (Right Column) ---
        self.defaults_frame = ctk.CTkFrame(self.main_frame)
        self.defaults_frame.grid(row=0, column=1, padx=15, pady=10, sticky="nsew")
        self.defaults_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.defaults_frame, text="Invoice & Item Defaults", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=2, pady=15)

        # Invoice Type
        self._add_label(self.defaults_frame, "Invoice Type:", 1, "Default type for new invoices")
        self.invoice_type_combo = ctk.CTkOptionMenu(self.defaults_frame, values=["Standard", "Simplified", "Proforma"])
        self.invoice_type_combo.grid(row=1, column=1, padx=10, pady=8, sticky="ew")

        # Tax Rate
        self._add_label(self.defaults_frame, "Tax Rate (%):", 2, "Standard Sales Tax Rate (e.g., 18.0)")
        self.tax_rate_entry = ctk.CTkEntry(self.defaults_frame)
        self.tax_rate_entry.grid(row=2, column=1, padx=10, pady=8, sticky="ew")

        # Discount
        self._add_label(self.defaults_frame, "Discount (%):", 3, "Default discount percentage (0-100)")
        self.discount_entry = ctk.CTkEntry(self.defaults_frame)
        self.discount_entry.grid(row=3, column=1, padx=10, pady=8, sticky="ew")

        # Item Defaults
        ctk.CTkLabel(self.defaults_frame, text="Default Item Details", font=ctk.CTkFont(size=14, weight="bold")).grid(row=4, column=0, columnspan=2, pady=(20, 10))

        self._add_label(self.defaults_frame, "PCT Code:", 5, "HS Code / PCT Code")
        self.pct_code_entry = ctk.CTkEntry(self.defaults_frame)
        self.pct_code_entry.grid(row=5, column=1, padx=10, pady=8, sticky="ew")

        self._add_label(self.defaults_frame, "Item Code:", 6, "Alphanumeric SKU/Code")
        self.item_code_entry = ctk.CTkEntry(self.defaults_frame)
        self.item_code_entry.grid(row=6, column=1, padx=10, pady=8, sticky="ew")

        self._add_label(self.defaults_frame, "Item Name:", 7, "Default product name")
        self.item_name_entry = ctk.CTkEntry(self.defaults_frame)
        self.item_name_entry.grid(row=7, column=1, padx=10, pady=8, sticky="ew")

        # --- Section 3: App Features (Full Width) ---
        self.features_frame = ctk.CTkFrame(self.main_frame)
        self.features_frame.grid(row=1, column=0, columnspan=2, padx=15, pady=20, sticky="nsew")
        self.features_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.features_frame, text="Application Features", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=2, pady=15)

        self.auto_push_var = ctk.BooleanVar(value=False)
        self.auto_push_cb = ctk.CTkCheckBox(self.features_frame, text="Auto-Sync Code to Bitbucket (Uploads changes automatically on save)", variable=self.auto_push_var)
        self.auto_push_cb.grid(row=1, column=0, columnspan=2, padx=20, pady=10, sticky="w")

        # --- Buttons ---
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=1, column=0, pady=20)

        ctk.CTkButton(btn_frame, text="Save Settings", command=self.save, width=150, height=40).pack(side="left", padx=15)
        ctk.CTkButton(btn_frame, text="Close", command=self.destroy, fg_color="gray", width=120, height=40).pack(side="left", padx=15)

        # --- Preview Section ---
        self.preview_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.preview_frame.grid(row=1, column=0, columnspan=2, padx=15, pady=30, sticky="ew")
        self.preview_frame.grid_columnconfigure((0, 1), weight=1)
        
        # Ensure preview frame has enough height by setting minsize if needed, or rely on content
        # We'll rely on content but add padding to cards


        # Initialize
        active_env = settings_service.get_active_environment()
        self.env_combo.set(active_env)
        
        # Load App Config
        app_config = settings_service.get_app_config()
        self.auto_push_var.set(app_config.get("auto_push_enabled", False))

        self.on_env_change(active_env)
        self.refresh_preview()

    def _add_label(self, parent, text, row, tooltip_text):
        label = ctk.CTkLabel(parent, text=text)
        label.grid(row=row, column=0, padx=10, pady=5, sticky="e")
        # Simple tooltip simulation using a smaller label below could be added if needed,
        # but for now we'll rely on the label itself. 
        # Ideally, we'd use a ToolTip class, but to keep it simple and robust without external deps:
        # We could add a status bar or help text.
        pass

    def on_env_change(self, env):
        data = settings_service.get_environment(env)
        
        self._set_entry(self.base_url_entry, data.get("base_url", "https://esp.fbr.gov.pk:8243/PT/v1"))
        self._set_entry(self.pos_entry, data.get("pos_id", ""))
        self._set_entry(self.usin_entry, data.get("usin", ""))
        self._set_entry(self.token_entry, data.get("token", ""))
        self._set_entry(self.tax_rate_entry, data.get("tax_rate", "18.0"))
        self._set_entry(self.pct_code_entry, data.get("pct_code", "8711.2010"))
        
        # New Fields
        self.invoice_type_combo.set(data.get("invoice_type", "Standard"))
        self._set_entry(self.discount_entry, data.get("discount", "0.0"))
        self._set_entry(self.item_code_entry, data.get("item_code", ""))
        self._set_entry(self.item_name_entry, data.get("item_name", ""))
        
        self.refresh_preview()

    def _set_entry(self, entry, value):
        entry.delete(0, "end")
        entry.insert(0, str(value) if value is not None else "")

    def refresh_preview(self):
        for widget in self.preview_frame.winfo_children():
            widget.destroy()

        all_settings = settings_service.get_all_settings()
        active_env = all_settings['active']

        # Header
        header = ctk.CTkLabel(self.preview_frame, text="Current Configuration Status", font=ctk.CTkFont(size=14, weight="bold"))
        header.grid(row=0, column=0, columnspan=2, pady=(0, 10))

        status_color = "#2ECC71" if active_env == "PRODUCTION" else "#3498DB"
        ctk.CTkLabel(self.preview_frame, text=f"Active: {active_env}", text_color="white", fg_color=status_color, corner_radius=6).grid(row=0, column=1, sticky="e", padx=20)

        # Scrollable Container for Cards
        cards_container = ctk.CTkScrollableFrame(self.preview_frame, height=200, fg_color="transparent")
        cards_container.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=5)
        cards_container.grid_columnconfigure(0, weight=1)
        cards_container.grid_columnconfigure(1, weight=1)

        def create_card(col, title, data, is_active):
            card = ctk.CTkFrame(cards_container, border_width=2 if is_active else 0, border_color=status_color)
            card.grid(row=0, column=col, sticky="nsew", padx=10, pady=5)
            
            # Better column distribution
            card.grid_columnconfigure(0, weight=1)
            card.grid_columnconfigure(1, weight=2)
            
            ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, columnspan=2, pady=(10, 15), sticky="ew")
            
            rows = [
                ("POS ID", data.get('pos_id')),
                ("USIN", data.get('usin')),
                ("Tax Rate", f"{data.get('tax_rate')}%"),
                ("Inv Type", data.get('invoice_type')),
            ]
            
            for i, (lbl, val) in enumerate(rows):
                ctk.CTkLabel(card, text=f"{lbl}", text_color=("gray50", "gray70"), font=ctk.CTkFont(size=12, weight="bold")).grid(row=i+1, column=0, padx=(15, 5), pady=4, sticky="e")
                ctk.CTkLabel(card, text=str(val or "-"), font=ctk.CTkFont(size=12)).grid(row=i+1, column=1, padx=(5, 15), pady=4, sticky="w")
            
            # Bottom padding
            ctk.CTkLabel(card, text="", height=5).grid(row=len(rows)+1, column=0, columnspan=2)

        create_card(0, "Sandbox", all_settings['sandbox'], active_env == "SANDBOX")
        create_card(1, "Production", all_settings['production'], active_env == "PRODUCTION")

    def save(self):
        try:
            # 1. Gather Data
            env = self.env_combo.get()
            base_url = self.base_url_entry.get().strip()
            pos_id = self.pos_entry.get().strip()
            usin = self.usin_entry.get().strip()
            token = self.token_entry.get().strip()
            
            tax_rate = self.tax_rate_entry.get().strip()
            pct_code = self.pct_code_entry.get().strip()
            
            invoice_type = self.invoice_type_combo.get()
            discount = self.discount_entry.get().strip()
            item_code = self.item_code_entry.get().strip()
            item_name = self.item_name_entry.get().strip()

            # 2. Validation
            errors = []
            if not base_url: errors.append("Base URL is required.")
            if not pos_id: errors.append("POS ID is required.")
            if not usin: errors.append("USIN is required.")
            if not token: errors.append("Auth Token is required.")
            
            # Numeric Validation
            try:
                float(tax_rate)
            except ValueError:
                errors.append("Tax Rate must be a number.")
                
            try:
                d = float(discount)
                if not (0 <= d <= 100): errors.append("Discount must be between 0 and 100.")
            except ValueError:
                errors.append("Discount must be a number.")

            # Text Validation
            if not item_code.isalnum() and item_code != "":
                errors.append("Item Code must be alphanumeric.")
            
            if len(item_name) > 100:
                errors.append("Item Name is too long (max 100 chars).")

            if errors:
                messagebox.showerror("Validation Error", "\n".join(errors))
                return

            # 3. Save
            settings_service.save_environment(
                env=env,
                base_url=base_url,
                pos_id=pos_id,
                usin=usin,
                token=token,
                tax_rate=tax_rate,
                pct_code=pct_code,
                invoice_type=invoice_type,
                discount=discount,
                item_code=item_code,
                item_name=item_name
            )
            
            # Save App Configuration (Auto-Push)
            settings_service.set_app_config(
                auto_push_enabled=self.auto_push_var.get()
            )
            
            # Trigger application to update auto-sync status if master has the method
            if hasattr(self.master, 'update_auto_sync_status'):
                self.master.update_auto_sync_status()

            settings_service.set_active_environment(env)
            reload_settings()
            
            if hasattr(self.master, 'update_env_badge'):
                self.master.update_env_badge()
                
            messagebox.showinfo("Success", f"FBR {env} settings saved and activated.")
            self.refresh_preview()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")
