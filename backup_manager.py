import os
import shutil
import zipfile
import json
import sys
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox
from drive_backup import backup_files as gdrive_backup

class BackupManager:
    """Comprehensive backup and restore management"""
    
    def __init__(self, db):
        self.db = db
        if getattr(sys, 'frozen', False):
            self.backup_dir = os.path.join(os.path.dirname(sys.executable), "backups")
        else:
            self.backup_dir = "backups"
        self.auto_backup_dir = os.path.join(self.backup_dir, "auto")
        os.makedirs(self.auto_backup_dir, exist_ok=True)
    
    def create_backup(self, backup_type="manual", include_attachments=True):
        """Create a comprehensive backup"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if backup_type == "auto":
            backup_filename = f"auto_backup_{timestamp}.zip"
            backup_path = os.path.join(self.auto_backup_dir, backup_filename)
        else:
            backup_filename = f"manual_backup_{timestamp}.zip"
            backup_path = os.path.join(self.backup_dir, backup_filename)
        
        try:
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = "."

            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as backup_zip:
                # Backup essential files
                essential_files = ["rentals.db", "materials.csv"]
                for file in essential_files:
                    full_path = os.path.join(base_dir, file)
                    if os.path.exists(full_path):
                        backup_zip.write(full_path, file)
                
                # Backup directories if they exist and requested
                directories_to_backup = []
                if include_attachments:
                    directories_to_backup = ["reports", "exports"]
                
                for directory in directories_to_backup:
                    full_dir = os.path.join(base_dir, directory)
                    if os.path.exists(full_dir):
                        for root, dirs, files in os.walk(full_dir):
                            for file in files:
                                if directory == "reports" and file.endswith('.pdf'):
                                    file_path = os.path.join(root, file)
                                    arcname = os.path.relpath(file_path, base_dir)
                                    backup_zip.write(file_path, arcname)
                                elif directory == "exports" and file.endswith('.csv'):
                                    file_path = os.path.join(root, file)
                                    arcname = os.path.relpath(file_path, base_dir)
                                    backup_zip.write(file_path, arcname)
                
                # Add backup metadata
                db_path = os.path.join(base_dir, "rentals.db")
                metadata = {
                    "backup_type": backup_type,
                    "timestamp": timestamp,
                    "database_size": os.path.getsize(db_path) if os.path.exists(db_path) else 0,
                    "includes_attachments": include_attachments,
                    "version": "2.0"
                }
                
                backup_zip.writestr("backup_metadata.json", 
                                  json.dumps(metadata, indent=2))
            
            # Clean up old auto backups (keep last 10)
            if backup_type == "auto":
                self.cleanup_old_backups(self.auto_backup_dir, keep_count=10)
            
            return backup_path, True
            
        except Exception as e:
            return f"Backup failed: {str(e)}", False
    
    def cleanup_old_backups(self, directory, keep_count=10):
        """Clean up old backup files"""
        try:
            backup_files = []
            for filename in os.listdir(directory):
                if filename.endswith('.zip'):
                    filepath = os.path.join(directory, filename)
                    backup_files.append((filepath, os.path.getctime(filepath)))
            
            # Sort by creation time (oldest first)
            backup_files.sort(key=lambda x: x[1])
            
            # Remove oldest files beyond keep_count
            for i in range(len(backup_files) - keep_count):
                os.remove(backup_files[i][0])
                
        except Exception as e:
            print(f"Backup cleanup warning: {e}")
    
    def list_backups(self, backup_type="all"):
        """List available backups"""
        backups = []
        
        if backup_type in ["all", "manual"]:
            for filename in os.listdir(self.backup_dir):
                if filename.endswith('.zip') and not filename.startswith('auto_'):
                    filepath = os.path.join(self.backup_dir, filename)
                    backups.append(self.get_backup_info(filepath))
        
        if backup_type in ["all", "auto"]:
            for filename in os.listdir(self.auto_backup_dir):
                if filename.endswith('.zip'):
                    filepath = os.path.join(self.auto_backup_dir, filename)
                    backups.append(self.get_backup_info(filepath))
        
        # Sort by timestamp (newest first)
        backups.sort(key=lambda x: x['timestamp'], reverse=True)
        return backups
    
    def get_backup_info(self, backup_path):
        """Get information about a backup file"""
        try:
            with zipfile.ZipFile(backup_path, 'r') as backup_zip:
                # Read metadata
                if 'backup_metadata.json' in backup_zip.namelist():
                    with backup_zip.open('backup_metadata.json') as f:
                        metadata = json.load(f)
                else:
                    # For old backups without metadata
                    metadata = {
                        "backup_type": "manual",
                        "timestamp": "unknown",
                        "database_size": 0,
                        "includes_attachments": False,
                        "version": "1.0"
                    }
            
            file_stats = os.stat(backup_path)
            return {
                'path': backup_path,
                'filename': os.path.basename(backup_path),
                'size': file_stats.st_size,
                'created': datetime.fromtimestamp(file_stats.st_ctime),
                **metadata
            }
            
        except Exception as e:
            return {
                'path': backup_path,
                'filename': os.path.basename(backup_path),
                'size': 0,
                'created': datetime.now(),
                'backup_type': 'unknown',
                'timestamp': 'unknown',
                'error': str(e)
            }
    
    def restore_backup(self, backup_path, restore_attachments=True):
        """Restore from a backup file"""
        try:
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = "."

            # Create restore backup (in case something goes wrong)
            restore_backup_path, success = self.create_backup("restore_point")
            if not success:
                return f"Failed to create restore point: {restore_backup_path}", False
            
            with zipfile.ZipFile(backup_path, 'r') as backup_zip:
                # Extract essential files
                files_to_extract = ['rentals.db', 'materials.csv']
                for file in files_to_extract:
                    if file in backup_zip.namelist():
                        backup_zip.extract(file, base_dir)
                
                # Extract attachments if requested
                if restore_attachments:
                    for member in backup_zip.namelist():
                        if member.startswith('reports/') or member.startswith('exports/'):
                            backup_zip.extract(member, base_dir)
            
            return "Restore completed successfully", True
            
        except Exception as e:
            # Try to restore from the restore point
            if os.path.exists(restore_backup_path):
                try:
                    with zipfile.ZipFile(restore_backup_path, 'r') as restore_zip:
                        if 'rentals.db' in restore_zip.namelist():
                            restore_zip.extract('rentals.db', base_dir)
                except:
                    pass
            
            return f"Restore failed: {str(e)}", False
    
    def create_backup_dialog(self, parent):
        """Create backup management dialog"""
        dialog = tk.Toplevel(parent)
        dialog.title("Backup & Restore Manager")
        dialog.geometry("700x500")
        dialog.transient(parent)
        dialog.grab_set()
        
        # Center the dialog
        dialog.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - dialog.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create Backup Tab
        backup_tab = ttk.Frame(notebook)
        notebook.add(backup_tab, text="Create Backup")
        
        self.setup_backup_tab(backup_tab)
        
        # Restore Tab
        restore_tab = ttk.Frame(notebook)
        notebook.add(restore_tab, text="Restore Backup")
        
        self.setup_restore_tab(restore_tab)
        
        # Cloud Backup Tab
        cloud_tab = ttk.Frame(notebook)
        notebook.add(cloud_tab, text="Cloud Backup")
        
        self.setup_cloud_tab(cloud_tab)
        
        return dialog
    
    def setup_backup_tab(self, parent):
        """Setup backup creation tab"""
        ttk.Label(parent, text="Create New Backup", 
                 font=("Segoe UI", 14, "bold")).pack(pady=10)
        
        # Backup options
        options_frame = ttk.LabelFrame(parent, text="Backup Options", padding=10)
        options_frame.pack(fill=tk.X, padx=10, pady=10)
        
        include_attachments_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Include PDF reports and exports",
                       variable=include_attachments_var).pack(anchor="w", pady=5)
        
        backup_type_var = tk.StringVar(value="manual")
        ttk.Radiobutton(options_frame, text="Manual Backup", 
                       variable=backup_type_var, value="manual").pack(anchor="w", pady=2)
        ttk.Radiobutton(options_frame, text="Auto Backup", 
                       variable=backup_type_var, value="auto").pack(anchor="w", pady=2)
        
        # Progress and status
        progress_frame = ttk.Frame(parent)
        progress_frame.pack(fill=tk.X, padx=10, pady=10)
        
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(progress_frame, variable=progress_var, maximum=100)
        progress_bar.pack(fill=tk.X)
        
        status_var = tk.StringVar(value="Ready for backup")
        ttk.Label(progress_frame, textvariable=status_var).pack(pady=5)
        
        def execute_backup():
            progress_var.set(10)
            status_var.set("Starting backup...")
            
            try:
                backup_path, success = self.create_backup(
                    backup_type_var.get(),
                    include_attachments_var.get()
                )
                
                if success:
                    progress_var.set(100)
                    status_var.set(f"Backup created: {os.path.basename(backup_path)}")
                    messagebox.showinfo("Backup Complete", 
                                      f"Backup created successfully!\n\n"
                                      f"Location: {backup_path}")
                else:
                    status_var.set("Backup failed!")
                    messagebox.showerror("Backup Failed", backup_path)
                    
            except Exception as e:
                status_var.set("Backup failed!")
                messagebox.showerror("Backup Error", f"Backup failed:\n{str(e)}")
        
        ttk.Button(parent, text="Create Backup", command=execute_backup,
                  style="Primary.TButton").pack(pady=10)
    
    def setup_restore_tab(self, parent):
        """Setup backup restoration tab"""
        ttk.Label(parent, text="Restore from Backup", 
                 font=("Segoe UI", 14, "bold")).pack(pady=10)
        
        # Backup list
        list_frame = ttk.LabelFrame(parent, text="Available Backups", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create treeview for backups
        columns = ("Filename", "Type", "Size", "Date", "Attachments")
        tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=8)
        
        for col in columns:
            tree.heading(col, text=col)
            if col == "Filename":
                tree.column(col, width=200)
            elif col == "Size":
                tree.column(col, width=80)
            else:
                tree.column(col, width=100)
        
        # Load backups
        backups = self.list_backups()
        for backup in backups:
            tree.insert("", "end", values=(
                backup['filename'],
                backup.get('backup_type', 'unknown'),
                f"{backup['size'] // 1024} KB",
                backup['created'].strftime("%Y-%m-%d %H:%M"),
                "Yes" if backup.get('includes_attachments', False) else "No"
            ), tags=(backup['path'],))
        
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side="left", fill=tk.BOTH, expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Restore options
        options_frame = ttk.Frame(parent)
        options_frame.pack(fill=tk.X, padx=10, pady=10)
        
        restore_attachments_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Restore PDF reports and exports",
                       variable=restore_attachments_var).pack(anchor="w", pady=5)
        
        def execute_restore():
            selection = tree.selection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a backup to restore")
                return
            
            backup_path = tree.item(selection[0], "tags")[0]
            
            if messagebox.askyesno("Confirm Restore", 
                                 "This will replace your current data with the backup.\n"
                                 "Make sure you have a recent backup!\n\n"
                                 "Continue?"):
                result, success = self.restore_backup(
                    backup_path, 
                    restore_attachments_var.get()
                )
                
                if success:
                    messagebox.showinfo("Restore Complete", 
                                      f"Restore completed successfully!\n\n"
                                      f"The application will now restart.")
                    # Restart application
                    os.execl(sys.executable, sys.executable, *sys.argv)
                else:
                    messagebox.showerror("Restore Failed", result)
        
        ttk.Button(parent, text="Restore Selected Backup", 
                  command=execute_restore, style="Danger.TButton").pack(pady=10)
    
    def setup_cloud_tab(self, parent):
        """Setup cloud backup tab"""
        ttk.Label(parent, text="Google Drive Backup", 
                 font=("Segoe UI", 14, "bold")).pack(pady=10)
        
        info_frame = ttk.LabelFrame(parent, text="Cloud Backup Information", padding=10)
        info_frame.pack(fill=tk.X, padx=10, pady=10)
        
        info_text = """Google Drive Backup allows you to securely store your data in the cloud.

Features:
• Automatic synchronization with Google Drive
• Secure encrypted transmission
• Access your data from anywhere
• Version history and recovery

Click 'Backup to Google Drive' to start the synchronization process."""
        
        ttk.Label(info_frame, text=info_text, justify=tk.LEFT).pack(anchor="w")
        
        progress_frame = ttk.Frame(parent)
        progress_frame.pack(fill=tk.X, padx=10, pady=10)
        
        cloud_progress_var = tk.DoubleVar()
        cloud_progress_bar = ttk.Progressbar(progress_frame, variable=cloud_progress_var, maximum=100)
        cloud_progress_bar.pack(fill=tk.X)
        
        cloud_status_var = tk.StringVar(value="Ready for cloud backup")
        ttk.Label(progress_frame, textvariable=cloud_status_var).pack(pady=5)
        
        def execute_cloud_backup():
            cloud_progress_var.set(25)
            cloud_status_var.set("Starting Google Drive backup...")
            
            try:
                # Create local backup first
                backup_path, success = self.create_backup("manual", True)
                if not success:
                    messagebox.showerror("Backup Failed", "Failed to create local backup")
                    return
                
                cloud_progress_var.set(50)
                cloud_status_var.set("Uploading to Google Drive...")
                
                # Upload to Google Drive
                gdrive_backup()
                
                cloud_progress_var.set(100)
                cloud_status_var.set("Cloud backup completed successfully!")
                messagebox.showinfo("Cloud Backup Complete", 
                                  "Data successfully backed up to Google Drive!")
                
            except Exception as e:
                cloud_status_var.set("Cloud backup failed!")
                messagebox.showerror("Cloud Backup Error", f"Google Drive backup failed:\n{str(e)}")
        
        ttk.Button(parent, text="Backup to Google Drive", 
                  command=execute_cloud_backup, style="Success.TButton").pack(pady=10)