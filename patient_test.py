import mysql.connector

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Ajas2004*",
    database="healthsync"
)

cursor = conn.cursor()

sql = """
INSERT INTO patients (name, phone, age, gender)
VALUES (%s, %s, %s, %s)
"""

data = ("Arun Kumar", "9876543211", 35, "Male")

try:
    cursor.execute(sql, data)
    conn.commit()
    print("Patient inserted successfully!")
except mysql.connector.IntegrityError:
    print("Patient already exists. Skipping insert.")

cursor.close()

# -------- FETCH --------
cursor = conn.cursor(dictionary=True)
cursor.execute("SELECT * FROM patients")

patients = cursor.fetchall()

for p in patients:
    print(p)

cursor.close()
conn.close()
