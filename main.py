import sqlite3
from functions.data_manager import open_excel_to_table_sql

class DatabaseManager:
    def __init__(self, db_name):
        self.connection = sqlite3.connect(db_name)
        self.cursor = self.connection.cursor()

    def create_table(self):
        create_table_query = """
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL
        );
        """
        self.cursor.execute(create_table_query)
        self.connection.commit()

    def insert_data(self, name, quantity):
        insert_query = "INSERT INTO inventory (name, quantity) VALUES (?, ?)"
        self.cursor.execute(insert_query, (name, quantity))
        self.connection.commit()

    def fetch_data(self):
        self.cursor.execute("SELECT * FROM inventory")
        return self.cursor.fetchall()

    def close(self):
        self.connection.close()

def main():
    db = DatabaseManager('inventory.db')
    db.create_table()
    db.insert_data('Apples', 10)
    db.insert_data('Oranges', 20)
    results = db.fetch_data()
    for row in results:
        print(row)
    db.close()
    name = str(input("Enter file name name:"))
    open_excel_to_table_sql(name)

if __name__ == "__main__":
    main()