# bill_number.py - ENHANCED VERSION (4-Digit Format)
import re
import logging

logger = logging.getLogger(__name__)

def increment_prefix(prefix: str) -> str:
    """
    Increments an alphabetic bill prefix: 'A' → 'B', ..., 'Z' → 'AA', ..., 'ZZ' → 'AAA'.
    Handles case-insensitivity and empty input robustly.
    """
    if not prefix:
        return "A"
    
    prefix = prefix.upper()
    chars = list(prefix)
    i = len(chars) - 1
    
    while i >= 0:
        if chars[i] != "Z":
            chars[i] = chr(ord(chars[i]) + 1)
            # Reset all characters to the right to 'A'
            chars[i+1:] = ['A'] * (len(chars) - i - 1)
            return ''.join(chars)
        i -= 1
    
    # All characters were 'Z', add new 'A' at beginning
    return "A" * (len(prefix) + 1)

# Bills created on the phone/web app use their own series per branch
# (e.g. VDV-M0001) so they can never clash with numbers a branch PC picks
# while it is offline. PC numbering therefore never uses the "M" letter.
MOBILE_SERIES = "M"


def get_branch_code(cur) -> str:
    """This PC's branch code (VDV/BMP/KVP) once cloud sync is set up, else ''."""
    try:
        cur.execute("SELECT value FROM sync_meta WHERE key = 'branch_code'")
        row = cur.fetchone()
        return str(row[0]).strip().upper() if row and row[0] else ""
    except Exception:
        return ""  # sync not set up: single-shop numbering exactly as before


def get_bill_series(cur) -> str:
    """'M' on the phone/web app (its own series), '' on branch PCs."""
    try:
        cur.execute("SELECT value FROM sync_meta WHERE key = 'bill_series'")
        row = cur.fetchone()
        return str(row[0]).strip().upper() if row and row[0] else ""
    except Exception:
        return ""


def _next_mobile_bill_no(cur, branch: str) -> str:
    """Next phone/web bill for a branch: VDV-M0001, VDV-M0002, ..."""
    cur.execute("SELECT bill_no FROM rentals WHERE bill_no LIKE ?", (f"{branch}-{MOBILE_SERIES}%",))
    best = 0
    for (raw,) in cur.fetchall():
        match = re.match(rf"^{branch}-{MOBILE_SERIES}(\d{{4,}})$", str(raw).strip().upper())
        if match:
            best = max(best, int(match.group(1)))
    return f"{branch}-{MOBILE_SERIES}{best + 1:04d}"


def _next_branch_bill_no(cur, branch: str) -> str:
    """Next PC bill number for a branch, e.g. 'VDV-A3003'.

    Looks back from the newest bill for this PC's own series: legacy numbers
    without a branch (A3002, the main branch's old bills) or '<branch>-A....'.
    Phone-series bills (VDV-M....) and other branches' bills are skipped.
    """
    # The HIGHEST number in the series (not the newest row): after a restore from the
    # cloud, rows arrive in update order, so an old bill edited later may be the newest row.
    cur.execute("SELECT bill_no FROM rentals WHERE bill_no IS NOT NULL AND bill_no != ''")
    best = None
    for (raw,) in cur.fetchall():
        bill = str(raw).strip().upper()
        if bill.startswith(branch + "-"):
            bill = bill[len(branch) + 1:]
        elif "-" in bill:
            continue
        match = re.match(r"^([A-Z]+)(\d{4})$", bill)
        if not match or match.group(1) == MOBILE_SERIES:
            continue
        key = (len(match.group(1)), match.group(1), int(match.group(2)))
        if best is None or key > best:
            best = key
    if best is None:
        return f"{branch}-A0001"
    prefix, number = best[1], best[2] + 1
    if number > 9999:
        prefix = increment_prefix(prefix)
        if prefix == MOBILE_SERIES:
            prefix = increment_prefix(prefix)
        number = 1
    return f"{branch}-{prefix}{number:04d}"


def generate_next_bill_no(db) -> str:
    """
    Scheme: PREFIX + 4-digit number (e.g., 'A0001'). Rolls over after 9999 → next prefix.
    Returns 'A0001' if no bill exists, or if an invalid last bill found.
    """
    try:
        conn = db.get_connection()
        cur = conn.cursor()

        # Multi-branch mode (cloud sync set up on this PC): "VDV-A3003" style numbers
        branch = get_branch_code(cur)
        if branch:
            if get_bill_series(cur) == MOBILE_SERIES:
                return _next_mobile_bill_no(cur, branch)
            return _next_branch_bill_no(cur, branch)

        # Get the latest bill number with proper error handling
        cur.execute("""
            SELECT bill_no FROM rentals 
            WHERE bill_no IS NOT NULL AND bill_no != '' 
            ORDER BY id DESC LIMIT 1
        """)
        row = cur.fetchone()
        last = str(row[0]).strip().upper() if row and row[0] else ""
        
        # If no existing bills, start with A0001
        if not last:
            logger.info("No existing bills found, starting with A0001")
            return "A0001"

        # Validate and parse the last bill number (Changed to 4 digits)
        match = re.match(r"^([A-Z]+)(\d{4})$", last)
        if not match:
            logger.warning(f"Invalid bill number format: '{last}', resetting to A0001")
            return "A0001"

        prefix, number_str = match.groups()
        
        try:
            number = int(number_str) + 1
        except ValueError:
            logger.warning(f"Invalid number in bill '{last}', resetting to A0001")
            return "A0001"
        
        # Changed rollover limit to 9999
        if number > 9999:
            prefix = increment_prefix(prefix)
            number = 1
            logger.info(f"Bill number rolled over to new prefix: {prefix}")
        
        # Format with 4 digits instead of 5
        next_bill = f"{prefix}{number:04d}"
        logger.debug(f"Generated next bill number: {next_bill}")
        return next_bill
        
    except Exception as e:
        logger.error(f"Bill number generation failed: {e}")
        # Fallback to ensure we always return a valid bill number
        return "A0001"

def validate_bill_no(bill_no: str) -> bool:
    """
    Validate bill number format.
    """
    if not bill_no or not isinstance(bill_no, str):
        return False
    
    # Changed regex to expect exactly 4 digits
    return bool(re.match(r"^[A-Z]+\d{4}$", bill_no.strip().upper()))

def extract_bill_components(bill_no: str):
    """
    Extract prefix and number from bill number.
    Returns (prefix, number) or (None, None) if invalid.
    """
    if not validate_bill_no(bill_no):
        return None, None
    
    # Changed regex to expect exactly 4 digits
    match = re.match(r"^([A-Z]+)(\d{4})$", bill_no.strip().upper())
    if match:
        return match.groups()
    return None, None