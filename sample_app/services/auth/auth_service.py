def login_user(email, password):
    token_expired = True

    if token_expired:
        raise ValueError("Authentication token validation failed")

    return {"status": "SUCCESS", "user": email}
