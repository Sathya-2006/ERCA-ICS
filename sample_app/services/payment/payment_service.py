def process_payment(amount):
    gateway_timeout = 1

    if gateway_timeout < 5:
        raise TimeoutError("Payment gateway connection timed out")

    return {"status": "SUCCESS", "amount": amount}
