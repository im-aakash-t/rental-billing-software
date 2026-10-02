# scanner_helper.py - HARDWARE SCANNER INTEGRATION
import os
import win32com.client
from tkinter import messagebox

def scan_and_save_id(bill_no, name, id_type):
    """
    Connects to the Windows Scanner, scans the document, 
    and saves it to the ID_Proofs folder.
    """
    # 1. Create the Master Folder if it doesn't exist
    import sys
    if getattr(sys, 'frozen', False):
        save_dir = os.path.join(os.path.dirname(sys.executable), "ID_Proofs")
    else:
        save_dir = "ID_Proofs"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    # 2. Clean the inputs (Filenames crash if they have characters like / \ : * ? " < > |)
    safe_bill = "".join([c for c in str(bill_no) if c.isalnum() or c in "-_ "]).strip()
    safe_name = "".join([c for c in str(name) if c.isalnum() or c in "-_ "]).strip()
    safe_type = "".join([c for c in str(id_type) if c.isalnum() or c in "-_ "]).strip()
    
    if not safe_bill: safe_bill = "PendingBill"
    if not safe_name: safe_name = "UnknownCustomer"
    if not safe_type: safe_type = "ID"

    # 3. Create the exact filename your Uncle wanted!
    filename = f"{safe_bill}_{safe_name}_{safe_type}.jpg"
    save_path = os.path.abspath(os.path.join(save_dir, filename))

    # 4. WIA throws an error if a file with the same name already exists, so we delete the old one
    if os.path.exists(save_path):
        os.remove(save_path)

    try:
        # 5. Summon the Windows Scanner Interface
        wia = win32com.client.Dispatch("WIA.CommonDialog")
        
        # This opens the scanner popup. It pauses the app until the user hits "Scan"
        image = wia.ShowAcquireImage()
        
        if image is not None:
            # Save the file
            image.SaveFile(save_path)
            messagebox.showinfo("Scan Successful! 🎉", f"ID Proof saved securely as:\n{filename}")
            return save_path
        else:
            return None
            
    except Exception as e:
        error_msg = str(e)
        # 80210015 is the Windows error code for "User clicked Cancel" or "Scanner unplugged"
        if "80210015" in error_msg or "cancelled" in error_msg.lower():
            print("Scan cancelled by user.")
        else:
            messagebox.showerror("Scanner Error ⚠️", 
                                 f"Could not connect to the scanner.\n\n"
                                 f"1. Check if the scanner is plugged in and turned on.\n"
                                 f"2. Check if Windows recognizes the scanner.\n\n"
                                 f"Technical Error: {e}")
        return None