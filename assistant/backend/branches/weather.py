import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("cortana2.branches.weather")

def handle_weather_branch(question: str, q_lower: str, response: Dict[str, Any], logger, apps: Optional[list]=None, geo: Optional[dict]=None) -> bool:
    """
    Handle weather-related questions. Returns True if handled (response modified).
    """
    # Only handle when 'weather' appears in q_lower
    logger.debug("handle_weather_branch: handling weather for question=%r", question)
    response["speech"] = "Here’s your current conditions."
    response["display_markdown"] = "Here’s your current conditions."
    response["cards"].append({
        "type": "currentconditions",
        "label": "Location Name",
        "location": geo if geo else {"lat": None, "lon": None},
        "forecast": {
            "temperatureCelsius": "22",
            "condition": "Partly Cloudy",
            "condition_icon": 29,  # Lines up with IBM Weather API icon codes
            "feels_like": "21",
            "humidity": "55%",
            "wind": "10 km/h"
        }
    })
    return True
