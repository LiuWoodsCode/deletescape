def handle_open_branch(question, q_lower, response, logger, apps=None, geo=None):
    """
    Handle 'open' branch: if an app listed in `apps` is mentioned in the question,
    set launch_app; otherwise set url to open browser. Returns True when handled.
    """
    apps = apps or []
    for app_name in apps:
        try:
            if app_name and app_name.lower() in q_lower:
                response["speech"] = f"Opening {app_name}."
                response["display_markdown"] = f"**Launching app:** {app_name}"
                response["launch_app"] = app_name
                return True
        except Exception:
            # keep behavior conservative if an app name is malformed
            logger.exception("handle_open_branch: error checking app_name=%r", app_name)

    # fallback: open browser
    response["speech"] = "Opening browser."
    response["display_markdown"] = "Opening [Bing](https://www.bing.com)"
    response["url"] = "https://www.bing.com"
    return True
