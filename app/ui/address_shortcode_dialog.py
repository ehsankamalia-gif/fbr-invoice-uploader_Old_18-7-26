import customtkinter as ctk
from tkinter import messagebox, ttk
import logging
from app.services.settings_service import settings_service

logger = logging.getLogger(__name__)

class AddressShortcodeDialog(ctk.CTkToplevel):
    """
    Dialog to manage address shortcodes (e.g., KT -> Tehsil Kamalia District Toba Tek Singh).
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Address Shortcodes Management")
        self.geometry("600x500")
        self.transient(parent)
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Header ---
        self.header_label = ctk.CTkLabel(
            self, 
            text="Manage Address Shortcodes", 
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.header_label.grid(row=0, column=0, pady=20)

        # --- Main Content ---
        self.content_frame = ctk.CTkFrame(self)
        self.content_frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(1, weight=1)

        # Form to add/edit
        self.form_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.form_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.form_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.form_frame, text="Short Code:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.code_var = ctk.StringVar()
        self.code_entry = ctk.CTkEntry(self.form_frame, textvariable=self.code_var, placeholder_text="e.g. KT")
        self.code_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(self.form_frame, text="Full Address:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.address_var = ctk.StringVar()
        self.address_entry = ctk.CTkEntry(self.form_frame, textvariable=self.address_var, placeholder_text="e.g. Tehsil Kamalia District Toba Tek Singh")
        self.address_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        self.save_btn = ctk.CTkButton(self.form_frame, text="Add / Update", command=self.save_shortcode)
        self.save_btn.grid(row=2, column=0, columnspan=2, pady=10)

        # List of shortcodes
        self.list_frame = ctk.CTkFrame(self.content_frame)
        self.list_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)
        self.list_frame.grid_rowconfigure(0, weight=1)

        columns = ("code", "address")
        self.tree = ttk.Treeview(self.list_frame, columns=columns, show="headings")
        self.tree.heading("code", text="Short Code")
        self.tree.heading("address", text="Full Address")
        self.tree.column("code", width=100)
        self.tree.column("address", width=350)
        self.tree.grid(row=0, column=0, sticky="nsew")

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self.list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        # Delete button
        self.delete_btn = ctk.CTkButton(
            self.content_frame, 
            text="Delete Selected", 
            fg_color="#d32f2f", 
            hover_color="#b71c1c",
            command=self.delete_shortcode
        )
        self.delete_btn.grid(row=2, column=0, pady=10)

        # --- Footer ---
        self.close_btn = ctk.CTkButton(self, text="Close", command=self.destroy, fg_color="gray")
        self.close_btn.grid(row=2, column=0, pady=20)

        self.load_shortcodes()

    def load_shortcodes(self):
        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        try:
            shortcodes = settings_service.get_address_shortcodes()
            for code, address in sorted(shortcodes.items()):
                self.tree.insert("", "end", values=(code, address))
        except Exception as e:
            logger.error(f"Failed to load shortcodes: {e}")

    def on_select(self, event):
        selected = self.tree.selection()
        if not selected:
            return
            
        item = self.tree.item(selected[0])
        values = item["values"]
        self.code_var.set(values[0])
        self.address_var.set(values[1])

    def save_shortcode(self):
        code = self.code_var.get().strip().upper()
        address = self.address_var.get().strip().upper()
        
        if not code or not address:
            messagebox.showwarning("Validation Error", "Both code and address are required!")
            return
            
        try:
            shortcodes = settings_service.get_address_shortcodes()
            shortcodes[code] = address
            settings_service.set_address_shortcodes(shortcodes)
            
            self.load_shortcodes()
            self.code_var.set("")
            self.address_var.set("")
            messagebox.showinfo("Success", f"Shortcode '{code}' saved.")
        except Exception as e:
            logger.error(f"Failed to save shortcode: {e}")
            messagebox.showerror("Error", f"Failed to save shortcode: {e}")

    def delete_shortcode(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Selection Error", "Please select a shortcode to delete.")
            return
            
        item = self.tree.item(selected[0])
        code = item["values"][0]
        
        if not messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete shortcode '{code}'?"):
            return
            
        try:
            shortcodes = settings_service.get_address_shortcodes()
            if code in shortcodes:
                del shortcodes[code]
                settings_service.set_address_shortcodes(shortcodes)
                self.load_shortcodes()
                self.code_var.set("")
                self.address_var.set("")
                messagebox.showinfo("Success", f"Shortcode '{code}' deleted.")
        except Exception as e:
            logger.error(f"Failed to delete shortcode: {e}")
            messagebox.showerror("Error", f"Failed to delete shortcode: {e}")
