def search_products(query):
    search_timeout = True

    if search_timeout:
        raise TimeoutError("Search service request timed out")

    return {"query": query, "results": []}
