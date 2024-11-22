import pandas as pd
import sqlite3

name = "telus_business_case.xlsx"

# Step 2: Connect to SQLite database (or create it)
conn = sqlite3.connect('my_database.db')
cursor = conn.cursor()

# Step 3: Read Excel data
df = pd.read_excel(name, sheet_name=0)

# Step 4: Create a table with the correct column names and types
columns = ', '.join([f'"{col}" TEXT' for col in df.columns])
create_table_query = f'CREATE TABLE IF NOT EXISTS "{name}" ({columns})'
cursor.execute(create_table_query)
conn.commit()

# Step 5: Load data into the SQL table with column names from the DataFrame
df.to_sql(name, conn, if_exists='replace', index=False)

# Step 6: (Optional) Query the table
cursor.execute(f'SELECT * FROM "{name}" ORDER BY 4 DESC LIMIT 5')
rows = cursor.fetchall()
for row in rows:
    print(row)

# Step 7: Close the connection
conn.close()