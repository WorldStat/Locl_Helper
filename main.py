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

        # Create BOM table to track unique items
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS BOM (
                item_name TEXT PRIMARY KEY,
                total_quantity INTEGER DEFAULT 0
            )
        ''')

        # Create a Device_BOM_Mapping table to track device-specific requirements
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS BOM_Requirements (
            device_type TEXT,
            item_name TEXT,
            required_per_unit INTEGER,
            PRIMARY KEY (device_type, item_name),
            FOREIGN KEY (item_name) REFERENCES BOM(item_name)
        );
        ''')

        # Insert new BOM items
        bom_items = [
            "Small Black Box",
            "Square Foam",
            "Power Supply Box",
            "Power Supply w/ NA Blade",
            "CT200 Coil Box",
            "CT200 Coil",
            "WiFi Extender w/ manual",
            "BeagleBone",
            "PCB",
            "VH Front Case",
            "Back Case",
            "Side Cases (Top & Bottom)",
            "Light Pipe",
            "PCB Screws",
            "Case Screws",
            "USB Jumper",
            "Zip-Ties",
            "Velcro (Pairs)",
            "QC Sticker",
            "Ethernet Cable",
            "Plastic Bag sm."
        ]

        cursor.executemany(
            "INSERT OR IGNORE INTO BOM (item_name) VALUES (?)", 
            [(item,) for item in bom_items]
        )

        # Define BOM requirements for each device type
        bom_requirements = [
            ("VH", "Small Black Box", 1),
            ("VH", "Square Foam", 1),
            ("VH", "Power Supply Box", 1),
            ("VH", "Power Supply w/ NA Blade", 1),
            ("VH", "CT200 Coil Box", 1),
            ("VH", "CT200 Coil", 2),
            ("VH", "WiFi Extender w/ manual", 1),
            ("VH", "BeagleBone", 1),
            ("VH", "PCB", 1),
            ("VH", "VH Front Case", 1),
            ("VH", "Back Case", 1),
            ("VH", "Side Cases (Top & Bottom)", 1),
            ("VH", "Light Pipe", 9),
            ("VH", "PCB Screws", 4),
            ("VH", "Case Screws", 4),
            ("VH", "USB Jumper", 1),
            ("VH", "Zip-Ties", 2),
            ("VH", "Velcro (Pairs)", 4),
            ("VH", "QC Sticker", 1),
            ("VH", "Ethernet Cable", 1),
            ("VH", "Plastic Bag sm.", 1),


            ("VP", "Rogowski Coil", 3),
            ("VP", "Power Adapter", 1),
            ("VP", "Light Pipe", 9),
            ("VP", "PCB", 1),
            ("VP", "JB-55 Case Pro", 1)
        ]

        cursor.executemany('''
            INSERT OR IGNORE INTO BOM_Requirements (device_type, item_name, required_per_unit)
            VALUES (?, ?, ?)
        ''', bom_requirements)
        self.conn.commit()

        # BOM Purchases table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS BOM_Purchases (
                purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
                purchase_date DATE,
                buyer_name TEXT,
                item_name TEXT,
                quantity INTEGER,
                price REAL,
                currency TEXT CHECK(currency IN ('CAD', 'USD')),
                tax REAL,
                purchase_url TEXT,
                FOREIGN KEY (item_name) REFERENCES BOM (item_name)
            )
        ''')
        self.conn.commit()

    def add_devices(self, device_type, production_date, calibration_date, location, quantity):
        cursor = self.conn.cursor()
        
        # Retrieve BOM requirements for the device type
        cursor.execute('''
            SELECT item_name, required_per_unit 
            FROM BOM_Requirements 
            WHERE device_type = ?
        ''', (device_type,))
        bom_requirements = cursor.fetchall()
        
        # Check if there are enough materials to build the devices
        insufficient_items = []
        for item_name, required_per_unit in bom_requirements:
            cursor.execute('SELECT total_quantity FROM BOM WHERE item_name = ?', (item_name,))
            available_quantity = cursor.fetchone()[0] or 0
            if available_quantity < required_per_unit * quantity:
                insufficient_items.append((item_name, available_quantity))
        
        if insufficient_items:
            error_message = "Not enough materials to build devices. Shortages:\n" + "\n".join(
                [f"{item}: {available} available, need {required_per_unit * quantity}" for item, available in insufficient_items]
            )
            return 0, error_message  # Return 0 devices added and error message
        
        # Deduct materials from the BOM
        for item_name, required_per_unit in bom_requirements:
            cursor.execute('''
                UPDATE BOM
                SET total_quantity = total_quantity - ?
                WHERE item_name = ?
            ''', (required_per_unit * quantity, item_name))
        
        # Add devices to the Devices table
        success_count = 0
        for i in range(quantity):
            uid = f"{device_type}_{int(datetime.now().timestamp() * 1000)}_{i}"
            try:
                cursor.execute('''
                    INSERT INTO Devices (uid, type, production_date, calibration_date, location, status)
                    VALUES (?, ?, ?, ?, ?, 'In Stock')
                ''', (uid, device_type, production_date, calibration_date, location))
                success_count += 1
            except sqlite3.IntegrityError:
                continue

        self.conn.commit()
        return success_count, f"Successfully added {success_count} devices."

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

    def purchase_bom_items(self, purchase_date, buyer_name, item_name, quantity, price, currency, tax, purchase_url):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO BOM_Purchases (purchase_date, buyer_name, item_name, quantity, price, currency, tax, purchase_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (purchase_date, buyer_name, item_name, quantity, price, currency, tax, purchase_url))
        
        # Update BOM inventory
        cursor.execute('''
            UPDATE BOM 
            SET total_quantity = total_quantity + ? 
            WHERE item_name = ?
        ''', (quantity, item_name))
        
        self.conn.commit()

    def get_bom_inventory(self, device_type=None):
        cursor = self.conn.cursor()
        if device_type:
            cursor.execute('''
                SELECT item_name, required_per_unit, total_quantity 
                FROM BOM 
                WHERE device_type = ?
                ORDER BY item_name
            ''', (device_type,))
        else:
            cursor.execute('''
                SELECT item_name, total_quantity 
                FROM BOM 
                ORDER BY item_name
            ''')
        return cursor.fetchall()

    def get_bom_inventory_summary(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT 
                item_name,
                SUM(total_quantity) AS total_quantity
            FROM BOM
            GROUP BY item_name
            ORDER BY item_name
        ''')
        return cursor.fetchall()

    def calculate_buildable_units(self, device_type):
        cursor = self.conn.cursor()
        
        # Retrieve BOM requirements for the device type
        cursor.execute('''
            SELECT item_name, required_per_unit 
            FROM BOM_Requirements 
            WHERE device_type = ?
        ''', (device_type,))
        bom_requirements = cursor.fetchall()

        if not bom_requirements:
            return 0  # No BOM requirements for the device type

        # Calculate buildable units based on current BOM inventory
        buildable_units = float('inf')
        for item_name, required_per_unit in bom_requirements:
            cursor.execute('SELECT total_quantity FROM BOM WHERE item_name = ?', (item_name,))
            available_quantity = cursor.fetchone()[0] or 0
            buildable_units = min(buildable_units, available_quantity // required_per_unit)

        return buildable_units


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

        # Input fields
        ttk.Label(tab, text="Purchase Date").grid(row=0, column=0)
        ttk.Label(tab, text="Buyer Name").grid(row=1, column=0)
        ttk.Label(tab, text="Item Name").grid(row=2, column=0)
        ttk.Label(tab, text="Quantity").grid(row=3, column=0)
        ttk.Label(tab, text="Price").grid(row=4, column=0)
        ttk.Label(tab, text="Currency").grid(row=5, column=0)
        ttk.Label(tab, text="Tax").grid(row=6, column=0)
        ttk.Label(tab, text="Purchase URL").grid(row=7, column=0)

        purchase_date = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Entry(tab, textvariable=purchase_date).grid(row=0, column=1)

        buyer_name = ttk.Entry(tab)
        buyer_name.grid(row=1, column=1)

        item_name = ttk.Combobox(tab, values=[item[0] for item in self.manager.get_bom_inventory()])
        item_name.grid(row=2, column=1)

        quantity = ttk.Entry(tab)
        quantity.grid(row=3, column=1)

        price = ttk.Entry(tab)
        price.grid(row=4, column=1)

        currency = ttk.Combobox(tab, values=["CAD", "USD"])
        currency.grid(row=5, column=1)

        tax = ttk.Combobox(tab, values=["0", "0.13"])
        tax.grid(row=6, column=1)

        purchase_url = ttk.Entry(tab)
        purchase_url.grid(row=7, column=1)

        def log_purchase():
            try:
                self.manager.purchase_bom_items(
                    purchase_date.get(),
                    buyer_name.get(),
                    item_name.get(),
                    int(quantity.get()),
                    float(price.get()),
                    currency.get(),
                    float(tax.get()),
                    purchase_url.get()
                )
                messagebox.showinfo("Success", "Purchase logged successfully.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to log purchase: {e}")

        ttk.Button(tab, text="Log Purchase", command=log_purchase).grid(row=8, column=0, columnspan=2)

    def create_bom_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="BOM Inventory")

        # Add dropdown for device type selection
        device_label = ttk.Label(tab, text="Select Device Type:")
        device_label.pack(pady=5)

        device_type_var = tk.StringVar(value="VH")  # Default to "VH"
        device_dropdown = ttk.Combobox(tab, textvariable=device_type_var, values=["VH", "VP"])
        device_dropdown.pack(pady=5)

        # Display buildable units
        buildable_units_label = ttk.Label(tab, text="Buildable Units: 0")
        buildable_units_label.pack(pady=5)

        # BOM Table for detailed inventory
        columns = ("Item Name", "Required per Unit", "Available Quantity", "Buildable Units")
        bom_table = ttk.Treeview(tab, columns=columns, show="headings")

        for col in columns:
            bom_table.heading(col, text=col)
            bom_table.column(col, anchor="center")

        bom_table.pack(fill="both", expand=True)

        def refresh_bom_table():
            # Clear the table
            for i in bom_table.get_children():
                bom_table.delete(i)

            # Calculate buildable units and update the label
            device_type = device_type_var.get()
            buildable_units = self.manager.calculate_buildable_units(device_type)
            buildable_units_label.config(text=f"Buildable Units: {buildable_units}")

            # Populate the BOM table with item details
            cursor = self.manager.conn.cursor()
            cursor.execute('''
                SELECT 
                    br.item_name, 
                    br.required_per_unit, 
                    b.total_quantity, 
                    b.total_quantity / br.required_per_unit AS buildable_units
                FROM BOM_Requirements br
                LEFT JOIN BOM b ON br.item_name = b.item_name
                WHERE br.device_type = ?
                ORDER BY br.item_name
            ''', (device_type,))
            rows = cursor.fetchall()
            for row in rows:
                bom_table.insert("", "end", values=row)

        # Refresh the BOM table whenever the device type is changed
        device_dropdown.bind("<<ComboboxSelected>>", lambda e: refresh_bom_table())

        # Initial refresh
        refresh_bom_table()

if __name__ == "__main__":
    root = tk.Tk()
    app = InventoryApp(root)
    root.mainloop()