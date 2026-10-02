# drive_backup.py - SMART SYNC VERSION (Rolling DBs & Delta ID Sync)
import os
import threading
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import sys

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(__file__)

SCOPES = ['https://www.googleapis.com/auth/drive.file']
TOKEN_FILE = os.path.join(BASE_DIR, 'token.json')
CREDENTIALS_FILE = os.path.join(BASE_DIR, 'credentials.json')
DB_FILE = os.path.join(BASE_DIR, 'rentals.db')
ID_FOLDER = os.path.join(BASE_DIR, 'ID_Proofs')
CLOUD_ID_FOLDER = 'Rental_ID_Proofs' # Name of folder in Google Drive

def show_message(msg_type, title, message):
    """Safely triggers Tkinter messageboxes from a background thread."""
    try:
        root = tk._default_root
        if root:
            if msg_type == 'info':
                root.after(0, lambda: messagebox.showinfo(title, message))
            elif msg_type == 'error':
                root.after(0, lambda: messagebox.showerror(title, message))
        else:
            print(f"[{msg_type.upper()}] {title}: {message}")
    except:
        pass

def _upload_to_drive(silent):
    """The actual Smart Sync logic that runs in the background"""
    try:
        creds = None
        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(CREDENTIALS_FILE):
                    if not silent:
                        show_message('error', "Cloud Backup Error", f"Missing '{CREDENTIALS_FILE}'.")
                    return
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
        
        service = build('drive', 'v3', credentials=creds)

        # ========================================================
        # 1. ROLLING BACKUP FOR rentals.db (Keep Last 10)
        # ========================================================
        if os.path.exists(DB_FILE):
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            cloud_db_name = f"rentals_backup_{timestamp}.db"
            
            # Upload new DB
            media = MediaFileUpload(DB_FILE, mimetype='application/octet-stream', resumable=True)
            file_metadata = {'name': cloud_db_name}
            service.files().create(body=file_metadata, media_body=media, fields='id').execute()

            # Find all DB backups on Drive
            results = service.files().list(
                q="name contains 'rentals_backup_' and name contains '.db' and trashed=false",
                fields="files(id, name, createdTime)",
                orderBy="createdTime"
            ).execute()
            
            db_files = results.get('files', [])
            
            # If we have more than 10, delete the oldest ones
            if len(db_files) > 10:
                files_to_delete = len(db_files) - 10
                for i in range(files_to_delete):
                    service.files().delete(fileId=db_files[i]['id']).execute()

        # ========================================================
        # 2. DELTA SYNC FOR ID_Proofs (Upload only missing files)
        # ========================================================
        if os.path.exists(ID_FOLDER):
            # A. Check if 'Rental_ID_Proofs' folder exists on Drive, if not, create it
            folder_query = f"name='{CLOUD_ID_FOLDER}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = service.files().list(q=folder_query, fields="files(id)").execute()
            folders = results.get('files', [])
            
            if not folders:
                folder_metadata = {'name': CLOUD_ID_FOLDER, 'mimeType': 'application/vnd.google-apps.folder'}
                folder = service.files().create(body=folder_metadata, fields='id').execute()
                folder_id = folder.get('id')
            else:
                folder_id = folders[0]['id']

            # B. Get list of all files currently inside that cloud folder
            cloud_files_query = f"'{folder_id}' in parents and trashed=false"
            page_token = None
            cloud_file_names = set()
            
            while True:
                results = service.files().list(q=cloud_files_query, fields="nextPageToken, files(id, name)", pageToken=page_token).execute()
                for f in results.get('files', []):
                    cloud_file_names.add(f.get('name'))
                page_token = results.get('nextPageToken')
                if not page_token:
                    break

            # C. Compare local folder to cloud folder and upload ONLY new files
            uploaded_count = 0
            for local_file in os.listdir(ID_FOLDER):
                if local_file not in cloud_file_names:
                    local_path = os.path.join(ID_FOLDER, local_file)
                    if os.path.isfile(local_path):
                        media = MediaFileUpload(local_path, resumable=True)
                        file_metadata = {'name': local_file, 'parents': [folder_id]}
                        service.files().create(body=file_metadata, media_body=media, fields='id').execute()
                        uploaded_count += 1

        if not silent:
            msg = "☁️ Database successfully backed up to Google Drive!"
            if uploaded_count > 0:
                msg += f"\n📁 {uploaded_count} new ID Proofs were also synced."
            else:
                msg += "\n📁 ID Proofs are already up to date."
            show_message('info', "Cloud Sync Complete", msg)
                
    except Exception as e:
        if not silent:
            show_message('error', "Cloud Sync Failed", f"Could not connect to Google Drive:\n\n{e}")
        else:
            print(f"[ERROR] Silent Cloud Sync Failed: {e}")

def backup_files(silent=False):
    """Spawns a background thread so the app doesn't freeze"""
    if not silent:
        show_message('info', "Sync Started", "Cloud sync started in the background.\nYou can keep working!")
        
    thread = threading.Thread(target=_upload_to_drive, args=(silent,))
    # By setting daemon=False, the script waits for upload to finish 
    # EVEN IF the Tkinter window is closed!
    thread.daemon = False 
    thread.start()