import re
import unicodedata
from dataclasses import dataclass

def normalize_business_name(name: str) -> str:
    """
    Normalizes a business name for uniqueness checking.
    1. Converts to lowercase.
    2. Normalizes Unicode characters (NFKD).
    3. Removes all non-alphanumeric characters (spaces, punctuation, symbols).
    
    Example: "Honda Center!" -> "hondacenter"
    """
    if not name:
        return ""
    
    # 1. Lowercase
    name = name.lower()
    
    # 2. Unicode normalization (e.g. é -> e)
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    
    # 3. Remove non-alphanumeric (keep only a-z, 0-9)
    # This removes spaces, punctuation, dashes, etc.
    name = re.sub(r'[^a-z0-9]', '', name)
    
    return name

def to_uppercase_preserving(text: str) -> str:
    if not text:
        return ""
    return "".join(ch.upper() if ch.isalpha() else ch for ch in text)

@dataclass(frozen=True)
class InvoiceFormState:
    preserve_info: bool = False
    buyer_cnic: str = ""
    buyer_ntn: str = ""
    buyer_name: str = ""
    buyer_father: str = ""
    buyer_phone: str = ""
    buyer_address: str = ""
    model: str = ""
    color: str = ""
    chassis: str = ""
    engine: str = ""
    payment_mode: str = ""
    qty: int = 1
    amount_excl: float = 0.0
    tax: float = 0.0
    further_tax: float = 0.0
    total: float = 0.0

    def after_submit(self) -> "InvoiceFormState":
        if self.preserve_info:
            return InvoiceFormState(
                preserve_info=True,
                buyer_cnic=self.buyer_cnic,
                buyer_ntn=self.buyer_ntn,
                buyer_name=self.buyer_name,
                buyer_father=self.buyer_father,
                buyer_phone=self.buyer_phone,
                buyer_address=self.buyer_address,
            )
        return InvoiceFormState()

    def after_reset(self) -> "InvoiceFormState":
        return InvoiceFormState()
