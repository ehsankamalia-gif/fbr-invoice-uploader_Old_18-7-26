import customtkinter as ctk
from typing import List, Callable, Any, Optional

class AutocompleteEntry(ctk.CTkEntry):
    def __init__(self, master, fetch_suggestions: Callable[[str], List[Any]], on_select: Callable[[Any], None], 
                 display_attr: str = 'business_name', 
                 suggestion_format: Optional[Callable[[Any], str]] = None,
                 typing_delay: int = 300,
                 **kwargs):
        super().__init__(master, **kwargs)
        
        self.fetch_suggestions = fetch_suggestions
        self.on_select = on_select
        self.display_attr = display_attr
        self.suggestion_format = suggestion_format
        
        self.dropdown_window: Optional[ctk.CTkToplevel] = None
        self.suggestions = []
        self.suggestion_buttons = []
        self._debounce_job = None
        self._typing_delay = typing_delay  # ms
        self.selected_index = -1
        
        self.bind("<KeyRelease>", self._on_key_release)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Down>", self._move_selection_down)
        self.bind("<Up>", self._move_selection_up)
        self.bind("<Return>", self._confirm_selection)
        self.bind("<Escape>", self._close_dropdown)
        
        # Store colors for highlighting
        self.default_fg = "transparent"
        self.highlight_fg = ("gray75", "gray25")

    def _on_key_release(self, event):
        # Ignore navigation keys and modifier keys
        if event.keysym in ["Up", "Down", "Return", "Escape", "Tab", "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Control_V", "Control_C", "Control_X"]:
            return
            
        if self._debounce_job:
            self.after_cancel(self._debounce_job)
            
        self._debounce_job = self.after(self._typing_delay, self._fetch_and_show)

    def _fetch_and_show(self):
        query = self.get().strip()
        # Debug print for developers to see in console
        # print(f"Autocomplete fetch query: '{query}'")
        
        if not query or len(query) < 1:
            self._close_dropdown()
            return
            
        # Fetch suggestions
        try:
            results = self.fetch_suggestions(query)
            self.suggestions = results
            
            if results:
                self._show_dropdown(results)
            else:
                self._close_dropdown()
        except Exception as e:
            print(f"Autocomplete fetch error: {e}")
            self._close_dropdown()

    def _show_dropdown(self, items):
        if not self.dropdown_window or not self.dropdown_window.winfo_exists():
            # Use the root window as the master to ensure the Toplevel is not nested
            root = self.winfo_toplevel()
            self.dropdown_window = ctk.CTkToplevel(root)
            self.dropdown_window.overrideredirect(True)
            self.dropdown_window.attributes("-topmost", True)
            try:
                # Windows specific attribute to ensure it stays on top of everything
                self.dropdown_window.wm_attributes("-topmost", True)
            except:
                pass
            
            # Use a regular frame inside to hold buttons, packed in a scrollable frame if needed
            self.dropdown_frame = ctk.CTkFrame(self.dropdown_window, corner_radius=0, fg_color=("gray95", "gray10"))
            self.dropdown_frame.pack(fill="both", expand=True)

        # Position the window
        try:
            x = self.winfo_rootx()
            y = self.winfo_rooty() + self.winfo_height()
            width = self.winfo_width()
            
            # Calculate height based on items
            item_height = 30
            total_height = len(items) * item_height + 4 # +4 for padding
            
            # Check screen boundaries to prevent overflow
            screen_height = self.winfo_screenheight()
            if y + total_height > screen_height:
                # Place above the entry if it overflows bottom
                y = self.winfo_rooty() - total_height

            self.dropdown_window.geometry(f"{width}x{total_height}+{x}+{y}")
            self.dropdown_window.deiconify()
            self.dropdown_window.lift()
        except Exception as e:
            print(f"Error positioning dropdown: {e}")
            return

        # Clear previous
        for widget in self.dropdown_frame.winfo_children():
            widget.destroy()
            
        self.suggestion_buttons = []
        self.selected_index = -1
        
        for index, item in enumerate(items):
            # Extract text for display
            if self.suggestion_format:
                display_text = self.suggestion_format(item)
            else:
                display_text = getattr(item, self.display_attr, str(item))
            
            btn = ctk.CTkButton(
                self.dropdown_frame,
                text=display_text,
                anchor="w",
                fg_color=self.default_fg,
                text_color=("black", "white"),
                hover_color=self.highlight_fg,
                height=30,
                corner_radius=0,
                command=lambda i=item: self._select_item(i)
            )
            btn.pack(fill="x", padx=1, pady=0)
            self.suggestion_buttons.append(btn)

    def _close_dropdown(self, event=None):
        if self.dropdown_window:
            if self.dropdown_window.winfo_exists():
                self.dropdown_window.destroy()
            self.dropdown_window = None
            self.suggestion_buttons = []
            self.selected_index = -1

    def _on_focus_out(self, event):
        # Check if focus moved to the dropdown window (not possible with overrideredirect usually, but good practice)
        # We delay closing to allow button click to register
        self.after(150, self._check_focus_and_close)

    def _check_focus_and_close(self):
        # If the widget itself has focus, don't close (e.g. came back)
        if self.focus_get() == self:
            return
        self._close_dropdown()

    def _move_selection_down(self, event):
        if not self.dropdown_window or not self.suggestion_buttons:
            return
        
        new_index = self.selected_index + 1
        if new_index < len(self.suggestion_buttons):
            self._highlight_item(new_index)

    def _move_selection_up(self, event):
        if not self.dropdown_window or not self.suggestion_buttons:
            return
            
        new_index = self.selected_index - 1
        if new_index >= 0:
            self._highlight_item(new_index)

    def _highlight_item(self, index):
        # Reset previous
        if 0 <= self.selected_index < len(self.suggestion_buttons):
            self.suggestion_buttons[self.selected_index].configure(fg_color=self.default_fg)
            
        self.selected_index = index
        
        # Highlight new
        if 0 <= index < len(self.suggestion_buttons):
            self.suggestion_buttons[index].configure(fg_color=self.highlight_fg)

    def _confirm_selection(self, event):
        if self.dropdown_window and 0 <= self.selected_index < len(self.suggestions):
            item = self.suggestions[self.selected_index]
            self._select_item(item)
            return "break" # Prevent default Return behavior

    def _select_item(self, item):
        # Update entry text based on display_attr
        text = getattr(item, self.display_attr, str(item))
        self.delete(0, "end")
        self.insert(0, text)
        
        # Trigger callback
        self.on_select(item)
        self._close_dropdown()
