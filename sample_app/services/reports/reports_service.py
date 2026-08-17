def generate_report(report_type):
    database_query_timeout = True

    if database_query_timeout:
        raise TimeoutError("Report database query timed out")

    return {"status": "GENERATED", "type": report_type}
