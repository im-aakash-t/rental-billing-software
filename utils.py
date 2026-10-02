# utils.py - REFINED VERSION
import re
import logging
from math import ceil
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def calculate_rental_days_unified(start_date_str, start_time_str, return_date_str=None, return_time_str=None):
    try:
        start_dt = datetime.strptime(f"{start_date_str} {start_time_str}", "%d-%m-%y %I:%M %p")
        
        if return_date_str and return_time_str:
            try: end_dt = datetime.strptime(f"{return_date_str} {return_time_str}", "%d-%m-%y %I:%M %p")
            except ValueError: end_dt = datetime.now()
        else:
            end_dt = datetime.now()
            
        if end_dt < start_dt: return 1
            
        delta = end_dt - start_dt
        hours = delta.total_seconds() / 3600
        
        if hours <= 24: return 1
        else: return ceil(hours / 24)
            
    except Exception as e:
        logger.warning(f"Date calculation error: {e}")
        return 1

def parse_date_key(date_str):
    if not date_str:
        return datetime.min
    date_str = str(date_str).strip()
    for fmt in ("%d-%m-%Y", "%d-%m-%y", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            pass
    return datetime.min


def safe_float(val, default=0.0):
    if val is None: return default
    if isinstance(val, str):
        val = val.strip()
        if not val: return default
        val = re.sub(r'[^\d.-]', '', val)
    try:
        result = float(val)
        if result != result: return default
        return result
    except (ValueError, TypeError): return default

def safe_int(val, default=0):
    if val is None: return default
    if isinstance(val, str):
        val = val.strip()
        if not val: return default
        val = re.sub(r'[^\d]', '', val)
        if not val: return default
    try: return int(float(val))
    except (ValueError, TypeError): return default

def sync_lists(*lists, pad_value=0):
    if not lists: return []
    lists = [lst if lst is not None else [] for lst in lists]
    lists = [lst if isinstance(lst, list) else [lst] for lst in lists]
    max_len = max((len(l) for l in lists), default=0)
    synced = []
    for lst in lists:
        if isinstance(lst, list):
            padded = list(lst) + [pad_value] * (max_len - len(lst))
            synced.append(padded)
        else:
            synced.append([pad_value] * max_len)
    return synced

def validate_phone(phone):
    if not phone or not phone.strip(): return False, "Phone number is required"
    phone_clean = re.sub(r'[\s\-+]', '', phone.strip())
    if len(phone_clean) < 10: return False, "Phone number must be at least 10 digits"
    if not re.match(r'^[6-9]\d{9}$', phone_clean): return False, "Invalid Indian phone number format"
    return True, "Valid"

def validate_date(date_str, date_format='%d-%m-%y'):
    if not date_str or not date_str.strip(): return False, "Date is required"
    try:
        date_obj = datetime.strptime(date_str.strip(), date_format)
        if date_obj > datetime.now(): return False, "Date cannot be in the future"
        return True, "Valid"
    except ValueError: return False, f"Invalid date format. Use DD-MM-YY"

def validate_time(time_str, time_format='%I:%M %p'):
    if not time_str or not time_str.strip(): return False, "Time is required"
    try:
        datetime.strptime(time_str.strip().upper(), time_format)
        return True, "Valid"
    except ValueError: return False, "Invalid time format"

def format_currency(amount):
    try: return f"₹{safe_float(amount):,.2f}"
    except: return "₹0.00"

def sanitize_sql_input(text):
    if text is None: return ""
    text = str(text)
    for pattern in [';', '--', '/*', '*/', 'xp_', 'sp_', 'exec', 'union', 'select', 'insert', 'update', 'delete', 'drop']:
        text = text.replace(pattern, '')
    return text.strip()

def calculate_rental_total(rents, quantities, rental_days=1):
    try:
        total = 0.0
        rents_list, quantities_list = sync_lists(rents if isinstance(rents, list) else [rents], 
                                                 quantities if isinstance(quantities, list) else [quantities], pad_value=0)
        for rent, qty in zip(rents_list, quantities_list):
            total += safe_float(rent) * safe_int(qty, 1) * safe_int(rental_days, 1)
        return round(total, 2)
    except: return 0.0

def calculate_balance(due_amount, advance, deduction=0, damage=0, amount_paid=0):
    try:
        balance = safe_float(due_amount) - safe_float(advance) - safe_float(deduction) + safe_float(damage) - safe_float(amount_paid)
        return round(balance, 2)
    except: return 0.0

def validate_machine_data(machines, quantities, rents):
    if not machines or not any(machines): return False, "At least one machine is required"
    return True, "Valid"

def log_error(context, error, level='ERROR'):
    logger.error(f"{context}: {error}")