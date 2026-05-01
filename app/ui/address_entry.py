import customtkinter as ctk
import logging
from app.services.settings_service import settings_service

logger = logging.getLogger(__name__)

class AddressEntry(ctk.CTkEntry):
    """
    A specialized CTkEntry for address fields that supports auto-expansion of shortcodes.
    Example: Typing 'KT' and pressing Space expands to 'Tehsil Kamalia District Toba Tek Singh'.
    """
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.bind("<KeyRelease>", self._on_key_release)
        # We don't cache shortcodes here to ensure we always use the latest ones from settings_service
        
    def _on_key_release(self, event):
        # Trigger expansion on space, comma, or return
        if event.keysym in ["space", "Return", "comma"]:
            self._check_expansion(event.keysym)
        # Also force uppercase if it's not already (common pattern in this app)
        val = self.get()
        if val != val.upper():
            pos = self.index("insert")
            self.delete(0, "end")
            self.insert(0, val.upper())
            self.icursor(pos)

    def _check_expansion(self, keysym):
        content = self.get()
        if not content:
            return
            
        # Get latest shortcodes
        try:
            shortcodes = settings_service.get_address_shortcodes()
        except Exception as e:
            logger.error(f"Failed to fetch shortcodes: {e}")
            return
            
        if not shortcodes:
            return
            
        # We want to check the word just typed before the delimiter
        # text_to_check is the content before the last key press was processed
        text_to_check = content.strip()
        if not text_to_check:
            return
            
        words = text_to_check.split()
        if not words:
            return
            
        # Strip trailing comma if present on the last word for matching
        last_word_raw = words[-1].upper()
        last_word = last_word_raw.rstrip(',')
        
        if last_word in shortcodes:
            expansion = shortcodes[last_word].upper()
            
            # Reconstruct the text
            prefix = " ".join(words[:-1])
            
            # If the last word had a comma, preserve it if the keysym wasn't comma
            # Actually, let's just replace the word part
            if prefix:
                new_content = prefix + " " + expansion
            else:
                new_content = expansion
                
            # Add back comma if it was stripped from last_word_raw
            if last_word_raw.endswith(','):
                new_content += ","
                
            # Add back the delimiter if it wasn't Return
            if keysym == "space":
                new_content += " "
            elif keysym == "comma":
                # If we just pressed comma, the entry content might already have it 
                # but we've reconstructed it from words
                if not new_content.endswith(','):
                    new_content += ","
                new_content += " "
                
            self.delete(0, "end")
            self.insert(0, new_content)
            self.icursor("end")
            logger.info(f"Expanded shortcode '{last_word}' to '{expansion}'")
