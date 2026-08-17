def send_email(recipient, message):
    email_provider_available = False

    if not email_provider_available:
        raise ConnectionError("Email provider unavailable")

    return {"status": "SENT", "recipient": recipient}
