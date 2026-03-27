from flask import Flask, jsonify, request
import mysql.connector

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta

from twilio.twiml.messaging_response import MessagingResponse

from twilio.rest import Client

import os

account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
auth_token = os.environ.get("TWILIO_AUTH_TOKEN")

client = Client(account_sid, auth_token)


user_states = {}

app = Flask(__name__)

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Ajas2004*",
        database="healthsync"
    )

@app.route("/patients", methods=["GET"])
def get_patients():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM patients")
    patients = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(patients)
@app.route("/patients", methods=["POST"])
def add_patient():
    data = request.get_json()

    name = data.get("name")
    phone = data.get("phone")
    age = data.get("age")
    gender = data.get("gender")

    if not name or not phone:
        return jsonify({"error": "Name and phone are required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    sql = """
    INSERT INTO patients (name, phone, age, gender)
    VALUES (%s, %s, %s, %s)
    """

    try:
        cursor.execute(sql, (name, phone, age, gender))
        conn.commit()
        return jsonify({"message": "Patient added successfully"}), 201

    except mysql.connector.IntegrityError:
        return jsonify({"error": "Patient with this phone already exists"}), 409

    finally:
        cursor.close()
        conn.close()

@app.route("/appointments", methods=["POST"])
def add_appointment():
    data = request.get_json()

    patient_id = data.get("patient_id")
    doctor_id = data.get("doctor_id")
    date = data.get("date")
    time = data.get("time")

    if not patient_id or not doctor_id or not date or not time:
        return jsonify({"error": "All fields are required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        sql = """
        INSERT INTO appointments (patient_id, doctor_id, date, time)
        VALUES (%s, %s, %s, %s)
        """
        cursor.execute(sql, (patient_id, doctor_id, date, time))
        conn.commit()

        return jsonify({"message": "Appointment booked successfully"}), 201

    except mysql.connector.Error as e:
        return jsonify({"error": str(e)}), 500

    finally:
        cursor.close()
        conn.close()


@app.route("/appointments", methods=["GET"])
def get_appointments():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
    SELECT 
        a.id,
        p.name AS patient_name,
        p.phone,
        d.name AS doctor_name,
        a.date,
        a.time,
        a.reminded
    FROM appointments a
    JOIN patients p ON a.patient_id = p.id
    JOIN doctors d ON a.doctor_id = d.id
    """

    cursor.execute(query)
    appointments = cursor.fetchall()

    for a in appointments:
        a["date"] = str(a["date"])
        a["time"] = str(a["time"])

    cursor.close()
    conn.close()

    return jsonify(appointments)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
SELECT 
    a.id,
    p.name,
    p.phone,
    d.name AS doctor_name,
    a.date,
    a.time,
    a.reminded
FROM appointments a
JOIN patients p ON a.patient_id = p.id
JOIN doctors d ON a.doctor_id = d.id
WHERE a.reminded = FALSE
"""

    cursor.execute(query)
    appointments = cursor.fetchall()

    # 🔥 FIX: convert time + date
    for a in appointments:
        a["date"] = str(a["date"])
        a["time"] = str(a["time"])

    cursor.close()
    conn.close()

    return jsonify(appointments)

def check_appointments():
    print("🔄 Checking for upcoming appointments...", flush=True)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    now = datetime.now()
    next_10_minutes = now + timedelta(minutes=10)

    query = """
    SELECT 
        a.id,
        p.name AS patient_name,
        p.phone,
        d.name AS doctor_name,
        a.date,
        a.time,
        a.reminded
    FROM appointments a
    JOIN patients p ON a.patient_id = p.id
    JOIN doctors d ON a.doctor_id = d.id
    WHERE a.reminded = FALSE
    """

    cursor.execute(query)
    appointments = cursor.fetchall()

    for a in appointments:

        appointment_datetime = datetime.combine(
            a["date"], (datetime.min + a["time"]).time()
        )

        if now <= appointment_datetime <= next_10_minutes:

            print(f"🔔 Sending reminder to {a['phone']}", flush=True)

            try:
                message = client.messages.create(
                    body=f"Reminder: {a['patient_name']}, you have an appointment at {a['time']} with {a['doctor_name']}",
                    from_="whatsapp:+14155238886",
                    to=f"whatsapp:{a['phone']}"
                )

                print("✅ Message sent", flush=True)

                # ✅ Mark as reminded
                cursor.execute(
                    "UPDATE appointments SET reminded = TRUE WHERE id = %s",
                    (a["id"],)
                )
                conn.commit()

            except Exception as e:
                print("❌ Error:", e, flush=True)

    cursor.close()
    conn.close()
    print("🔄 Checking for upcoming appointments...")


@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    from_number = request.form.get("From").replace("whatsapp:", "")
    incoming_msg = request.form.get("Body").lower()

    print("📩", from_number, ":", incoming_msg, flush=True)

    resp = MessagingResponse()
    msg = resp.message()

    state = user_states.get(from_number, {})

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 🔍 Check if patient exists
    cursor.execute("SELECT * FROM patients WHERE phone = %s", (from_number,))
    patient = cursor.fetchone()

    # 🟢 STEP 1 — Start booking
    if "book" in incoming_msg:

        if patient:
            user_states[from_number] = {
                "step": "ask_time",
                "patient_id": patient["id"]
            }
            msg.body("⏰ Enter preferred time (e.g., 17:30):")

        else:
            user_states[from_number] = {"step": "ask_name"}
            msg.body("👤 Enter your name:")

    # 🟡 STEP 2 — New patient name
    elif state.get("step") == "ask_name":

        name = incoming_msg

        # Insert new patient
        insert_sql = """
        INSERT INTO patients (name, phone)
        VALUES (%s, %s)
        """
        cursor.execute(insert_sql, (name, from_number))
        conn.commit()

        patient_id = cursor.lastrowid

        user_states[from_number] = {
            "step": "ask_time",
            "patient_id": patient_id
        }

        msg.body("⏰ Enter preferred time (e.g., 17:30):")

    # 🔵 STEP 3 — Book appointment
    elif state.get("step") == "ask_time":

        time = incoming_msg
        patient_id = state.get("patient_id")

        sql = """
        INSERT INTO appointments (patient_id, doctor_id, date, time)
        VALUES (%s, %s, CURDATE(), %s)
        """

        cursor.execute(sql, (patient_id, 1, time))
        conn.commit()

        user_states.pop(from_number, None)

        msg.body(f"✅ Appointment booked at {time}")

    else:
        msg.body("❓ Send 'book' to start booking")

    cursor.close()
    conn.close()

    return str(resp)
    from_number = request.form.get("From")
    incoming_msg = request.form.get("Body").lower()

    print("📩", from_number, ":", incoming_msg, flush=True)

    resp = MessagingResponse()
    msg = resp.message()

    # Get user state
    state = user_states.get(from_number, {})

    # STEP 1 → User says "book"
    if "book" in incoming_msg:
        user_states[from_number] = {"step": "ask_name"}
        msg.body("👤 Enter your name:")

    # STEP 2 → Ask name
    elif state.get("step") == "ask_name":
        user_states[from_number] = {
            "step": "ask_time",
            "name": incoming_msg
        }
        msg.body("⏰ Enter preferred time (e.g., 17:30):")

    # STEP 3 → Ask time
    elif state.get("step") == "ask_time":
        name = state.get("name")
        time = incoming_msg

        conn = get_db_connection()
        cursor = conn.cursor()

        patient_id = 1
        doctor_id = 1

        sql = """
        INSERT INTO appointments (patient_id, doctor_id, date, time)
        VALUES (%s, %s, CURDATE(), %s)
        """

        cursor.execute(sql, (patient_id, doctor_id, time))
        conn.commit()

        cursor.close()
        conn.close()

        user_states.pop(from_number, None)

        msg.body(f"✅ Appointment booked for {name} at {time}")

    else:
        msg.body("❓ Send 'book' to start booking")

    return str(resp)
    incoming_msg = request.form.get("Body").lower()

    print("📩 Message received:", incoming_msg, flush=True)

    resp = MessagingResponse()
    msg = resp.message()

    if "book" in incoming_msg:

        conn = get_db_connection()
        cursor = conn.cursor()

        patient_id = 1
        doctor_id = 1

        sql = """
        INSERT INTO appointments (patient_id, doctor_id, date, time)
        VALUES (%s, %s, CURDATE(), ADDTIME(CURTIME(), '00:10:00'))
        """

        cursor.execute(sql, (patient_id, doctor_id))
        conn.commit()

        cursor.close()
        conn.close()

        msg.body("✅ Appointment booked successfully!")

    else:
        msg.body("❓ Send 'book' to create appointment")

    return str(resp)

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_appointments, 'interval', seconds=10)  # faster testing
    scheduler.start()

    app.run(debug=True, use_reloader=False)
