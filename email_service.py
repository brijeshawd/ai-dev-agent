import smtplib
from email.mime.text import MIMEText

def send_email(to_email, subject, body):
    from_email = "uktk20@gmail.com"
    app_password = "rlurnjthihmgoixg"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(from_email, app_password)
        server.sendmail(from_email, to_email, msg.as_string())
        server.quit()
        print("✅ Email sent successfully")
    except Exception as e:
        print(f"❌ Email send failed: {e}")
