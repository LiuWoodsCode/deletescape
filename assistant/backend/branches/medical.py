from typing import Dict
import re


def handle_medical_branch(question: str, q_lower: str, response: Dict, logger, apps=None, geo=None) -> bool:
    """
    Detects potential medical emergencies and provides concise, safety-focused guidance.
    The assistant does not provide detailed medical instructions; it encourages contacting
    emergency services immediately and offers brief, high-level safety pointers.

    Returns True if this branch handles the query.
    """
    q = q_lower or question.lower()

    categories = {
        "cardiac": [
            r"\bheart\s+attack\b",
            r"\bchest\s+pain\b",
            r"\bpressure\s+in\s+(?:my\s+)?chest\b",
            r"\bchest\s+tightness\b",
            r"\bpain\s+in\s+(?:left\s+)?arm\b",
            # added
            r"\bmy\s+chest\s+hurts\b",
            r"\bacute\s+coronary\b",
            r"\bpressure\s+in\s+my\s+shoulder\b",
        ],
        "stroke": [
            r"\bstroke\b",
            r"\bface\s+droop(?:ing)?\b",
            r"\bslurred\s+speech\b",
            r"\bweakness\s+on\s+one\s+side\b",
            # added
            r"\bfacial\s+droop\b",
            r"\bdifficulty\s+speaking\b",
            r"\barm\s+drift\b",
        ],
        "breathing": [
            r"\bnot\s+breathing\b",
            r"\bcan'?t\s+breathe\b",
            r"\btrouble\s+breathing\b",
            r"\bshort(?:ness)?\s+of\s+breath\b",
            r"\bchok(?:e|ing)\b",
            # added
            r"\bgasping\b",
            r"\bwheez(?:e|ing)\b",
            r"\bblue\s+lip(?:s)?\b",
            r"\bcyanotic\b",
        ],
        "unresponsive": [
            r"\bunconscious\b",
            r"\bunresponsive\b",
            r"\bpassed\s+out\b",
            r"\bfainted\b",
            # added
            r"\bnot\s+responsive\b",
            r"\bno\s+response\b",
        ],
        "bleeding": [
            r"\bsevere\s+bleeding\b",
            r"\bbleeding\s+heavily\b",
            r"\bspurting\s+blood\b",
            r"\bbleeding\s+won'?t\s+stop\b",
            # added
            r"\bblood\s+everywhere\b",
            r"\bhemorrhag(?:e|ing)\b",
        ],
        "seizure": [
            r"\bseizure\b",
            r"\bconvulsion\b",
            r"\bepileptic\b",
            # added
            r"\bshaking\s+uncontrollably\b",
            r"\bgrand\s+mal\b",
            r"\btonic\s+clonic\b",
        ],
        "allergic": [
            r"\ballergic\s+reaction\b",
            r"\banaphylaxis\b",
            r"\bthroat\s+(?:closing|swelling)\b",
            r"\bswelling\s+of\s+the\s+face\b",
            r"\bhives\s+with\s+breathing\s+trouble\b",
            # added
            r"\bcan't\s+swallow\b",
            r"\bdifficulty\s+swallowing\b",
            r"\bwidespread\s+hives\b",
            r"\bpeanut\s+allergy\b",
        ],
        "overdose": [
            r"\boverdose\b",
            r"\bod\b",
            r"\bpoison(?:ed|ing)?\b",
            # added
            r"\btoo\s+many\s+pills\b",
            r"\bopioid\b",
            r"\bnarcotic\b",
            r"\btook\s+all\s+my\s+meds\b",
        ],
    }

    # Add gunshot and self-harm detections
    categories.update({
        "gunshot": [
            r"\bgunshot\b",
            r"\b(?:got|been)\s+shot\b",
            r"\bshot\s+(?:in|through)\b",
            r"\bbullet\s+wound\b",
            r"\bshot\s+wound\b",
            # added
            r"\bgun\s+wound\b",
            r"\bshot\s+him\b",
        ],
        "self_harm": [
            r"\battempt(?:ed)?\s+suicide\b",
            r"\btried\s+to\s+kill\s+myself\b",
            r"\bcut\s+my\s+wrists?\b",
            r"\bslit\s+my\s+wrists?\b",
            r"\bhanged?\s+myself\b",
            r"\bjumped\s+off\b",
            r"\bdrank\s+bleach\b",
            r"\bpoisoned\s+myself\b",
            # added
            r"\bi\s+want\s+to\s+die\b",
            r"\bending\s+my\s+life\b",
            r"\bkilling\s+myself\b",
            r"\bsuicidal\b",
            r"\bself[-\s]?harm\b",
            r"\bhurt\s+myself\b",
            r"\bthinking\s+of\s+suicide\b",
        ],
        # new categories
        "diabetic": [
            r"\blow\s+blood\s+sugar\b",
            r"\bhigh\s+blood\s+sugar\b",
            r"\bdiabetic\s+emergency\b",
            r"\bhyperglyc(?:emia|emic)\b",
            r"\bhypoglyc(?:emia|emic)\b",
            r"\binsulin\s+shock\b",
            r"\bdiabetic\s+ketoacidosis\b",
        ],
        "drowning": [
            r"\bdrowning\b",
            r"\bnear\s+drowning\b",
            r"\bcan't\s+swim\b",
            r"\bunder\s+water\b",
        ],
        "burns": [
            r"\bsevere\s+burn\b",
            r"\bthird\s+degree\s+burn\b",
            r"\bburned\s+my\b",
            r"\bchemical\s+burn\b",
            r"\belectrical\s+burn\b",
        ],
        "electrocution": [
            r"\belectrocuted\b",
            r"\bgot\s+electrocuted\b",
            r"\belectric\s+shock\b",
        ],
        "head_injury": [
            r"\bhead\s+injury\b",
            r"\bsevere\s+head\s+pain\b",
            r"\bhead\s+trauma\b",
            r"\bhit\s+my\s+head\b",
            r"\blost\s+consciousness\b",
        ],
        "spinal_injury": [
            r"\bspinal\s+injury\b",
            r"\bneck\s+injury\b",
            r"\bcan't\s+move\s+my\s+legs\b",
            r"\bparalyzed\b",
            r"\bsevere\s+back\s+injury\b",
        ],
        "abdominal": [
            r"\bsevere\s+abdominal\s+pain\b",
            r"\bstomach\s+pain\s+sharp\b",
            r"\brigid\s+abdomen\b",
            r"\babdominal\s+pain\b",
            r"\bpain\s+lower\s+right\b",
        ],
        "pregnancy": [
            r"\bpregnant\b",
            r"\bpregnancy\s+emergency\b",
            r"\bsevere\s+abdominal\s+pain\s+pregnant\b",
            r"\bbleeding\s+pregnant\b",
            r"\bno\s+fetal\s+movement\b",
        ],
        "labor": [
            r"\bin\s+labor\b",
            r"\bcontractions\b",
            r"\bbaby\s+crowning\b",
            r"\bgiving\s+birth\b",
            r"\bwater\s+broke\b",
        ]
    })

    matched_category = None
    for cat, pats in categories.items():
        for pat in pats:
            if re.search(pat, q):
                matched_category = cat
                break
        if matched_category:
            break

    if not matched_category:
        return False

    logger.debug("handle_medical_branch: matched category=%s", matched_category)

    # Generic, concise emergency guidance
    speech = (
        "This may be a medical emergency. Call your local emergency number now (for example, 911 in the U.S.). "
        "If you are with the person, follow the dispatcher’s instructions and ask someone nearby to help."
    )

    extra_lines = {
        "cardiac": "Possible cardiac emergency.",
        "stroke": "Possible stroke (use FAST: Face, Arms, Speech, Time).",
        "breathing": "Breathing emergency.",
        "unresponsive": "Person is unresponsive.",
        "bleeding": "Severe bleeding — apply firm pressure with a clean cloth while waiting for help.",
        "seizure": "Protect from injury, don’t restrain, and note the time if safe to do so.",
        "allergic": "Severe allergic reaction.",
        "overdose": "Possible poisoning or overdose; contact emergency services or local poison control if available.",
    }

    # Add guidance lines for new categories
    extra_lines.update({
        "gunshot": "Gunshot wound — ensure scene safety; if safe, control bleeding with firm pressure.",
        "self_harm": "Self-harm or suicide attempt — ensure immediate safety and call emergency services.",
        "diabetic": "Possible diabetic emergency — follow dispatcher guidance; do not give anything by mouth if unconscious.",
        "drowning": "Possible drowning — ensure airway is clear; follow dispatcher instructions.",
        "burns": "Severe burn — cool briefly with room-temperature water if safe; do not apply creams.",
        "electrocution": "Electrical injury — ensure power source is off; do not touch victim until safe.",
        "head_injury": "Head injury — keep person still; watch for confusion or vomiting.",
        "spinal_injury": "Possible spinal injury — do not move the person unless in immediate danger.",
        "abdominal": "Severe abdominal pain — keep person still; await emergency services.",
        "pregnancy": "Pregnancy-related emergency — seek immediate medical help.",
        "labor": "Active labor — call emergency services; follow dispatcher guidance.",
        "mental_health_crisis": "Mental health crisis — ensure safety, speak calmly, seek emergency help.",
    })

    brief = extra_lines.get(matched_category, None)

    response["speech"] = speech
    response["display_markdown"] = (
        (f"**{brief}**\n\n" if brief else "") +
        "This may be a medical emergency. Please call your local emergency number now (e.g., **911** in the U.S.).\n\n"
        "If you are with the person, follow the dispatcher’s instructions and ask someone nearby to help."
    )

    return True
