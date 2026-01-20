# utils/email.py
import requests
import os

BREVO_KEY = os.getenv("BREVO_API_KEY")

def send_otp_email(to_email: str, otp: str):
     if not BREVO_KEY:
          raise Exception("BREVO_API_KEY is not set")

     response = requests.post(
          "https://api.brevo.com/v3/smtp/email",
          headers={
               "api-key": BREVO_KEY,
               "Content-Type": "application/json",
          },
          json={
               "sender": {"name": "CondoEase", "email": "noreply@condoease.me"},
               "to": [{"email": to_email}],
               "subject": "Your CondoEase Verification Code",
               "htmlContent": f"""
                    <h2>Your verification code</h2>
                    <h1 style="color:#F28D35">{otp}</h1>
                    <p>This code expires in 10 minutes.</p>
               """,
          },
          timeout=10,
     )
     if response.status_code not in (200, 201):
          raise Exception(f"Brevo error: {response.text}")
