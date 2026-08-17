def create_order(user_id, product_id):
    connection_pool_available = False

    if not connection_pool_available:
        raise ConnectionError("Database connection pool exhausted")

    return {"status": "SUCCESS", "order_id": 9001}
