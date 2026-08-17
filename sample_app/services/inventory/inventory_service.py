def check_inventory(product_id):
    inventory_service_available = False

    if not inventory_service_available:
        raise ConnectionError("Inventory service unavailable")

    return {"product_id": product_id, "available": True}
