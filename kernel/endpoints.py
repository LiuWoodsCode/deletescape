import traceback

ENDPOINTS = {}

def endpoint(name=None):
    def wrapper(func):
        ENDPOINTS[name or func.__name__] = func
        return func
    return wrapper


def dispatch(request):
    try:
        ep = request.get("endpoint")
        data = request.get("data", {})

        if ep not in ENDPOINTS:
            return {
                "status": "error",
                "error": f"Unknown endpoint: {ep}"
            }

        result = ENDPOINTS[ep](**data)

        return {
            "status": "ok",
            "result": result
        }

    except Exception:
        return {
            "status": "error",
            "error": traceback.format_exc()
        }