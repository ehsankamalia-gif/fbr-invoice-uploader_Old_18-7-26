import re
from typing import Tuple


def digits_only(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def normalize_phone(value: str) -> str:
    return digits_only(value)[:11]


def is_valid_phone(value: str) -> bool:
    v = normalize_phone(value)
    return bool(re.fullmatch(r"03\d{9}", v))


def normalize_cnic_digits(value: str) -> str:
    return digits_only(value)[:13]


def format_cnic(value: str) -> str:
    d = normalize_cnic_digits(value)
    if len(d) != 13:
        return d
    return f"{d[:5]}-{d[5:12]}-{d[12:]}"


def is_valid_cnic(value: str) -> bool:
    d = normalize_cnic_digits(value)
    return len(d) == 13


def normalize_name(value: str) -> str:
    return (value or "").strip()


def is_valid_name(value: str) -> bool:
    v = normalize_name(value)
    return (not v) or len(v) >= 2


def validate_lookup_inputs(phone: str, cnic: str, name: str) -> Tuple[str, str, str]:
    phone_norm = normalize_phone(phone or "")
    cnic_digits = normalize_cnic_digits(cnic or "")
    name_norm = normalize_name(name or "")

    if phone_norm and not is_valid_phone(phone_norm):
        raise ValueError("Invalid phone number. Use 03XXXXXXXXX (11 digits).")
    if cnic_digits and len(cnic_digits) != 13:
        raise ValueError("Invalid CNIC format. Use 12345-1234567-1.")
    if name_norm and len(name_norm) < 2:
        raise ValueError("Name must be at least 2 characters.")

    return phone_norm, cnic_digits, name_norm
