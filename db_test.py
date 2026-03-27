import mysql.connector

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Ajas2004*",
    database="healthsync"
)

print("Connected to MySQL successfully!")

conn.close()
