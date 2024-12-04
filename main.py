import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime


class InventoryManager:
    def __init__(self, db_name="inventory.db"):
        self.conn = sqlite3.connect(db_name)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()

        # Devices table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Devices (
                uid TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                production_date DATE,
                calibration_date DATE,
                location TEXT,
                status TEXT DEFAULT 'In Stock'
            )
        ''')

        # Shipments table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Shipments (
                shipment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_type TEXT,
                shipment_date DATE,
                destination TEXT,
                quantity INTEGER
            )
        ''')

        # Updated BOM table to include device-specific quantities
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS BOM (
                item_name TEXT,
                device_type TEXT,
                required_per_unit INTEGER,
                total_quantity INTEGER DEFAULT 0,
                PRIMARY KEY (item_name, device_type)
            )
        ''')

        # Expanded BOM items with device-specific requirements
        bom_items = [
            # VH-specific items
            ("CT Coil", "VH", 2),
            ("Rogowski Coil", "VH", 3),
            ("Power Adapter", "VH", 1),
            ("BeagleBone", "VH", 1),
            ("Light Pipe", "VH", 9),
            ("PCB", "VH", 1),
            ("JB-55 Case Home", "VH", 1),
            ("Antenna", "VH", 1),
            ("GPS Module", "VH", 1),

            # VP-specific items
            ("CT Coil", "VP", 1),
            ("Rogowski Coil", "VP", 2),
            ("Power Adapter", "VP", 1),
            ("BeagleBone", "VP", 1),
            ("Light Pipe", "VP", 6),
            ("PCB", "VP", 1),
            ("JB-55 Case Pro", "VP", 1),
            ("Cellular Modem", "VP", 1),
            ("Bluetooth Module", "VP", 1)
        ]
        cursor.executemany(
            "INSERT OR IGNORE INTO BOM (item_name, device_type, required_per_unit) VALUES (?, ?, ?)", 
            bom_items
        )
        self.conn.commit()

    def add_devices(self, device_type, production_date, calibration_date, location, quantity):
        cursor = self.conn.cursor()
        success_count = 0
        for i in range(quantity):
            uid = f"{device_type}_{int(datetime.now().timestamp() * 1000)}_{i}"
            try:
                cursor.execute('''
                    INSERT INTO Devices (uid, type, production_date, calibration_date, location)
                    VALUES (?, ?, ?, ?, ?)
                ''', (uid, device_type, production_date, calibration_date, location))
                success_count += 1
            except sqlite3.IntegrityError:
                continue
        self.conn.commit()
        return success_count

    def log_shipment(self, device_type, quantity, destination):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM Devices WHERE type = ? AND status = 'In Stock'
        ''', (device_type,))
        available = cursor.fetchone()[0]

        if available < quantity:
            return False, f"Not enough stock! Available: {available}, Requested: {quantity}"

        # Use a subquery to update the specific rows
        cursor.execute('''
            UPDATE Devices 
            SET status = 'Shipped', location = ? 
            WHERE rowid IN (
                SELECT rowid FROM Devices 
                WHERE type = ? AND status = 'In Stock' 
                LIMIT ?
            )
        ''', (destination, device_type, quantity))
        
        cursor.execute('''
            INSERT INTO Shipments (device_type, shipment_date, destination, quantity)
            VALUES (?, ?, ?, ?)
        ''', (device_type, datetime.now().strftime("%Y-%m-%d"), destination, quantity))
        
        self.conn.commit()
        return True, "Shipment logged successfully."

    def get_device_summary(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT 
                type, 
                location, 
                production_date, 
                calibration_date, 
                COUNT(*) as count,
                MIN(production_date) as earliest_production,
                MAX(production_date) as latest_production,
                MIN(calibration_date) as earliest_calibration,
                MAX(calibration_date) as latest_calibration
            FROM Devices
            WHERE status = 'In Stock'
            GROUP BY type, location, production_date, calibration_date
            ORDER BY type, location
        ''')
        return cursor.fetchall()

    def purchase_bom_items(self, item_name, quantity):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE BOM SET total_quantity = total_quantity + ? WHERE item_name = ?
        ''', (quantity, item_name))
        self.conn.commit()

    def get_bom_inventory(self, device_type=None):
        cursor = self.conn.cursor()
        if device_type:
            cursor.execute('''
                SELECT item_name, device_type, required_per_unit, total_quantity 
                FROM BOM 
                WHERE device_type = ?
                ORDER BY item_name
            ''', (device_type,))
        else:
            cursor.execute('''
                SELECT item_name, device_type, required_per_unit, total_quantity 
                FROM BOM 
                ORDER BY device_type, item_name
            ''')
        return cursor.fetchall()

    def calculate_buildable_units(self, device_type):
        cursor = self.conn.cursor()
        if device_type == "VH":
            requirements = {
                "CT Coil": 2,
                "Power Adapter": 1,
                "Light Pipe": 9,
                "PCB": 1,
                "JB-55 Case Home": 1
            }
        elif device_type == "VP":
            requirements = {
                "Rogowski Coil": 3,
                "Power Adapter": 1,
                "Light Pipe": 9,
                "PCB": 1,
                "JB-55 Case Pro": 1
            }
        else:
            return 0

        buildable = float('inf')
        for item, required in requirements.items():
            cursor.execute('SELECT total_quantity FROM BOM WHERE item_name = ?', (item,))
            available = cursor.fetchone()[0] or 0
            buildable = min(buildable, available // required)

        return buildable


class InventoryApp:
    def __init__(self, root):
        self.manager = InventoryManager()
        self.root = root
        self.root.title("Inventory Management System")

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(expand=1, fill="both")

        self.create_add_device_tab()
        self.create_log_shipment_tab()
        self.create_bom_tab()
        self.create_device_info_tab()
        self.create_purchase_bom_tab()

    def create_add_device_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Add Device")

        ttk.Label(tab, text="Device Type").grid(row=0, column=0)
        ttk.Label(tab, text="Production Date (default: today)").grid(row=1, column=0)
        ttk.Label(tab, text="Calibration Date (default: today)").grid(row=2, column=0)
        ttk.Label(tab, text="Location").grid(row=3, column=0)
        ttk.Label(tab, text="Quantity").grid(row=4, column=0)

        device_type = ttk.Combobox(tab, values=["VH", "VP", "VR40"])
        device_type.grid(row=0, column=1)

        prod_date = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        prod_date_entry = ttk.Entry(tab, textvariable=prod_date)
        prod_date_entry.grid(row=1, column=1)

        calib_date = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        calib_date_entry = ttk.Entry(tab, textvariable=calib_date)
        calib_date_entry.grid(row=2, column=1)

        location = ttk.Entry(tab)
        location.grid(row=3, column=1)

        quantity = ttk.Entry(tab)
        quantity.grid(row=4, column=1)

        def add_devices():
            try:
                qty = int(quantity.get())
                if qty < 1:
                    raise ValueError("Quantity must be at least 1.")
                success_count = self.manager.add_devices(
                    device_type.get(), prod_date.get(), calib_date.get(), location.get(), qty
                )
                messagebox.showinfo("Result", f"Added {success_count} devices successfully.")
            except ValueError as e:
                messagebox.showerror("Error", f"Invalid input: {e}")

        ttk.Button(tab, text="Add Devices", command=add_devices).grid(row=5, column=0, columnspan=2)

    def create_log_shipment_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Log Shipment")

        # Input Section
        input_frame = ttk.LabelFrame(tab, text="Log New Shipment")
        input_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        input_frame.columnconfigure(1, weight=1)

        ttk.Label(input_frame, text="Device Type").grid(row=0, column=0, sticky="w")
        ttk.Label(input_frame, text="Quantity").grid(row=1, column=0, sticky="w")
        ttk.Label(input_frame, text="Destination").grid(row=2, column=0, sticky="w")

        device_type = ttk.Combobox(input_frame, values=["VH", "VP", "VR40"])
        device_type.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        quantity = ttk.Entry(input_frame)
        quantity.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        destination = ttk.Entry(input_frame)
        destination.grid(row=2, column=1, sticky="ew", padx=5, pady=5)

        def log_shipment():
            try:
                qty = int(quantity.get())
                success, msg = self.manager.log_shipment(device_type.get(), qty, destination.get())
                if success:
                    messagebox.showinfo("Success", msg)
                    refresh_shipments_table()  # Refresh the shipments table after logging
                    # Clear input fields
                    device_type.set('')
                    quantity.delete(0, 'end')
                    destination.delete(0, 'end')
                else:
                    messagebox.showerror("Error", msg)
            except ValueError:
                messagebox.showerror("Error", "Invalid quantity!")

        ttk.Button(input_frame, text="Log Shipment", command=log_shipment).grid(row=3, column=0, columnspan=2, pady=10)

        # Shipments Table Section
        table_frame = ttk.LabelFrame(tab, text="Shipment History")
        table_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        # Treeview for displaying shipments
        columns = ("ID", "Device Type", "Date", "Destination", "Quantity")
        shipments_table = ttk.Treeview(table_frame, columns=columns, show="headings")
        
        # Define headings
        for col in columns:
            shipments_table.heading(col, text=col)
            shipments_table.column(col, anchor="center")
        
        # Scrollbar for the table
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=shipments_table.yview)
        shipments_table.configure(yscroll=scrollbar.set)

        # Position the treeview and scrollbar
        shipments_table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Function to refresh shipments table
        def refresh_shipments_table():
            # Clear existing items
            for i in shipments_table.get_children():
                shipments_table.delete(i)
            
            # Fetch shipments from database
            cursor = self.manager.conn.cursor()
            cursor.execute('''
                SELECT shipment_id, device_type, shipment_date, destination, quantity 
                FROM Shipments 
                ORDER BY shipment_date DESC
            ''')
            
            # Insert shipments into the table
            for row in cursor.fetchall():
                shipments_table.insert("", "end", values=row)

        # Initial population of the table
        refresh_shipments_table()

        # Configure grid weights to make the table expandable
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        return tab

    def create_bom_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="BOM Inventory")

        # Configure grid
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)

        # Columns with more descriptive names
        columns = ("Item Name", "Device Type", "Required per Unit", "Total Quantity")
        
        # Treeview with improved styling
        tree = ttk.Treeview(tab, columns=columns, show="headings")
        tree.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # Add scrollbars
        vsb = ttk.Scrollbar(tab, orient="vertical", command=tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        
        tree.configure(yscrollcommand=vsb.set)

        # Configure column headings
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, anchor="center")

        # Frame for device type selection and calculation
        control_frame = ttk.Frame(tab)
        control_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="ew")

        # Device Type Selection
        ttk.Label(control_frame, text="Select Device Type:").pack(side="left", padx=5)
        device_type = ttk.Combobox(control_frame, values=["VH", "VP"], width=10)
        device_type.pack(side="left", padx=5)

        # Summary Label
        summary_label = ttk.Label(control_frame, text="")
        summary_label.pack(side="right", padx=10)

        # Load Data Function
        def load_data(specific_type=None):
            # Clear existing items
            for row in tree.get_children():
                tree.delete(row)
            
            # Fetch and insert data
            for bom in self.manager.get_bom_inventory(specific_type):
                tree.insert("", "end", values=bom)
            
            # Update summary
            if specific_type:
                buildable = self.manager.calculate_buildable_units(specific_type)
                summary_label.config(text=f"Buildable {specific_type} Units: {buildable}")
            else:
                summary_label.config(text="")

        # Bind device type selection to load data
        def on_device_type_select(event):
            selected_type = device_type.get()
            if selected_type:
                load_data(selected_type)

        device_type.bind("<<ComboboxSelected>>", on_device_type_select)

        # Initial load of all data
        load_data()

        # Refresh Button
        refresh_button = ttk.Button(control_frame, text="Show All", command=lambda: load_data())
        refresh_button.pack(side="left", padx=5)

        return tab

    def create_device_info_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Devices Information")

        # Main frame with grid configuration
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)

        # Columns with more descriptive names
        columns = (
            "Device Type", 
            "Location", 
            "Count", 
            "Production Date", 
            "Calibration Date"
        )

        # Treeview with improved styling
        tree = ttk.Treeview(tab, columns=columns, show="headings")
        tree.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # Add scrollbars
        vsb = ttk.Scrollbar(tab, orient="vertical", command=tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb = ttk.Scrollbar(tab, orient="horizontal", command=tree.xview)
        hsb.grid(row=1, column=0, sticky="ew")

        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # Configure column headings and widths
        column_widths = [100, 150, 70, 150, 150]
        for i, col in enumerate(columns):
            tree.heading(col, text=col, command=lambda c=i: self.sort_column(tree, c, False))
            tree.column(col, width=column_widths[i], anchor="center")

        # Function to load and display data
        def load_data():
            # Clear existing data
            for row in tree.get_children():
                tree.delete(row)
            
            # Fetch and insert new data
            for device in self.manager.get_device_summary():
                # Format dates to be more readable
                production_date = device[2] if device[2] else "N/A"
                calibration_date = device[3] if device[3] else "N/A"
                
                # Insert row with formatted data
                tree.insert("", "end", values=(
                    device[0],  # Type
                    device[1],  # Location
                    device[4],  # Count
                    production_date,
                    calibration_date
                ))

        # Additional Information Frame
        info_frame = ttk.LabelFrame(tab, text="Device Summary")
        info_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="ew")

        # Labels for additional insights
        summary_label = ttk.Label(info_frame, text="")
        summary_label.pack(padx=10, pady=10)

        # Function to update summary information
        def update_summary():
            # Calculate total devices
            total_devices = sum(int(tree.item(item)['values'][2]) for item in tree.get_children())
            
            # Get unique device types and locations
            device_types = set(tree.item(item)['values'][0] for item in tree.get_children())
            locations = set(tree.item(item)['values'][1] for item in tree.get_children())

            # Update summary text
            summary_text = (
                f"Total Devices in Stock: {total_devices}\n"
                f"Unique Device Types: {len(device_types)}\n"
                f"Unique Locations: {len(locations)}"
            )
            summary_label.config(text=summary_text)

        # Method for sorting columns
        def sort_column(tree, col, reverse):
            # Get column data
            l = [(tree.set(k, col), k) for k in tree.get_children('')]
            
            # Try to convert to numeric if possible
            try:
                l = [(int(val), k) if val.isdigit() else (val, k) for val, k in l]
            except:
                pass
            
            # Sort and rearrange items
            l.sort(reverse=reverse)
            for index, (val, k) in enumerate(l):
                tree.move(k, '', index)
            
            # Toggle sort direction
            tree.heading(col, command=lambda: sort_column(tree, col, not reverse))

        # Buttons frame
        buttons_frame = ttk.Frame(tab)
        buttons_frame.grid(row=3, column=0, columnspan=2, padx=10, pady=10)

        # Refresh button
        refresh_button = ttk.Button(buttons_frame, text="Refresh Data", command=lambda: [load_data(), update_summary()])
        refresh_button.pack(side="left", padx=5)

        # Export button (placeholder - you might want to implement actual export functionality)
        export_button = ttk.Button(buttons_frame, text="Export to CSV", state="disabled")
        export_button.pack(side="left", padx=5)

        # Initial data load and summary update
        load_data()
        update_summary()

        return tab

    def create_purchase_bom_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Purchase BOM Items")

        ttk.Label(tab, text="Item Name").grid(row=0, column=0)
        ttk.Label(tab, text="Quantity").grid(row=1, column=0)

        item_name = ttk.Combobox(tab, values=[
            "CT Coil", "Rogowski Coil", "Power Adapter", "BeagleBone", "Light Pipe", "PCB", "JB-55 Case Home", "JB-55 Case Pro"
        ])
        item_name.grid(row=0, column=1)
        quantity = ttk.Entry(tab)
        quantity.grid(row=1, column=1)

        def purchase_items():
            try:
                qty = int(quantity.get())
                self.manager.purchase_bom_items(item_name.get(), qty)
                messagebox.showinfo("Success", "Items purchased successfully.")
            except ValueError:
                messagebox.showerror("Error", "Invalid quantity!")

        ttk.Button(tab, text="Purchase", command=purchase_items).grid(row=2, column=0, columnspan=2)

if __name__ == "__main__":
    root = tk.Tk()
    app = InventoryApp(root)
    root.mainloop()