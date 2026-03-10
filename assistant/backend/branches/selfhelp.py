from typing import Dict
import re
import random  # added for random response selection


def handle_selfhelp_branch(question: str, q_lower: str, response: Dict, logger, apps=None, geo=None) -> bool:
    """
    Detects user prompts indicating self-harm, suicidal ideation, or requests for instructions to harm themselves.
    - If the user requests instructions for self-harm, refuse and provide emergency/crisis resources.
    - If the user expresses suicidal thoughts or intent, respond with a compassionate message, encourage reaching out,
      advise contacting emergency services if in immediate danger, and offer to help find resources.

    Returns True if the branch handled the input and mutated `response`.
    """
    # Patterns that ask for instructions to self-harm (must refuse and provide resources)
    # Expanded and more robust patterns for self-harm instruction seeking, ideation, and non-suicidal self-harm.
    # Notes:
    # - Input is already lowercased (q_lower), so patterns are lowercase.
    # - Use word boundaries and specific phrases to reduce false positives.

    # Patterns that ask for instructions to self-harm (must refuse and provide resources)
    instruction_patterns = [
        # Direct "how to/ can/ should I ..." instruction seeking
        r"\bhow\s+(?:do|can|should)\s+i\s+(?:kill|end|take)\s+(?:my\s+own\s+)?(?:life|myself)\b",
        r"\bhow\s+to\s+(?:kill|end|take)\s+(?:my\s+own\s+)?(?:life|myself)\b",
        r"\bhow\s+to\s+(?:hang|tie)\s+(?:myself|a\s+noose)\b",
        r"\bhow\s+to\s+(?:slit|cut)\s+(?:my|the)\s*(?:wrists?|throat)\b",
        r"\bhow\s+to\s+(?:poison|asphyxiate|suffocate|electrocute)\s+(?:myself|me)\b",
        r"\bhow\s+to\s+(?:use|make)\s+(?:an?\s+)?(?:exit\s+bag|helium\s+hood|nitrogen\s+(?:bag|mask|hood))\b",
        r"\bhow\s+many\s+(?:pills|tablets|meds|medication)\s+(?:would|to)\s+(?:take|need)\s+(?:to\s+)?(?:overdose|od)\b",
        r"\bhow\s+to\s+(?:go\s+to\s+sleep\s+and\s+not\s+wake\s+up|end\s+it\s+all)\b",
        r"\bhow\s+to\s+(?:kys|kms|unalive\s+myself)\b",

        # Best/fastest/easiest/painless methods
        r"\bwhat(?:'s|\s+is)\s+(?:the\s+)?(?:best|easiest|quickest|fastest|most\s+painless)\s+way\s+to\s+(?:die|kill\s+myself|end\s+my\s+life|commit\s+suicide)\b",
        r"\b(?:best|easiest|quickest|fastest|most\s+painless)\s+way\s+to\s+(?:die|kill\s+myself|end\s+my\s+life|commit\s+suicide)\b",
        r"\b(?:ways|methods)\s+to\s+(?:die|kill\s+myself|end\s+my\s+life|commit\s+suicide)\b",
        r"\b(?:painless|peaceful)\s+way\s+to\s+die\b",

        # Specific method mentions paired with intent
        r"\b(?:carbon\s+monoxide|charcoal\s+burning)\s+(?:how\s+to|method|guide)\b",
    ]

    # Patterns that indicate suicidal ideation or intent
    ideation_patterns = [
        r"\bi\s+(?:want|wanna)\s+(?:to\s+)?(?:die|kill\s+myself|end\s+my\s+life|take\s+my\s+life|unalive\s+myself)\b",
        r"\bi(?:'m| am|m)?\s+(?:going|gonna|planning)\s+to\s+(?:die|kill\s+myself|end\s+my\s+life|hurt\s+myself)\b",
        r"\b(?:thinking|thought|considering|thinking\s+about)\s+(?:suicide|killing\s+myself|ending\s+my\s+life)\b",
        r"\bi\s+(?:feel|am|i'm)\s+suicidal\b",
        r"\bsuicidal(?:\s+ideation|\s+thoughts)?\b",
        r"\bi\s+do(?:\s*not|n't)\s+want\s+to\s+live\b",
        r"\bi\s+don't\s+want\s+to\s+be\s+alive\b",
        r"\bi\s+wish\s+i\s+were\s+dead\b",
        r"\blife\s+(?:is\s+not|isn't)?\s+worth\s+living\b",
        r"\bi\s+can't\s+go\s+on\b",
        r"\bno\s+reason\s+to\s+live\b",
        r"\bi\s+want\s+to\s+sleep\s+and\s+never\s+wake\s+up\b",
        r"\bkill\s+myself\b",
        r"\bgoing\s+to\s+kill\s+myself\b",
        r"\bi'?m\s+going\s+to\s+die\b",
        r"\b(?:kys|kms)\b",
        r"\bsuicide\b",
    ]

    # Non-suicidal self-harm (still needs supportive response)
    nonsuicide_selfharm = [
        r"\bself[-\s]?harm\b",
        r"\bself[-\s]?injur(?:y|e|ing|ious)\b",
        r"\bcut\s+(?:myself|me)\b",
        r"\bcutting\s+(?:myself|me)\b",
        r"\bcut\s+(?:my|the)\s*wrists?\b",
        r"\bburn\s+(?:myself|my\s+(?:skin|arm|hand|leg))\b",
        r"\bharm\s+myself\b",
        r"\bhit\s+myself\b",
        r"\bpunch\s+myself\b",
        r"\bhead[-\s]?bang(?:ing)?\b",
        r"\bbang\s+my\s+head\b",
        r"\bscratch\s+(?:myself|my\s+skin)\b",
        r"\bskin[-\s]?pick(?:ing)?\b",
        r"\bbruise\s+myself\b",
        r"\bstarv(?:e|ing)\s+myself\b",
        r"\burges?\s+to\s+self[-\s]?harm\b",
    ]

    # Added mental health crisis indicators
    mental_health_crisis = [
        r"panic\s+attack",
        r"severe\s+anxiety",
        r"\bpsychotic\b",
        r"hearing\s+voices",
        r"can't\s+calm\s+down",
    ]

    # Randomized response pools
    instruction_responses = [
        (
            "I'm sorry you're feeling like this. I can’t help with that, but you don’t have to face it alone. If you’re in danger, please call emergency services. In the US, you can also call or text 988 to reach the Suicide and Crisis Lifeline.",
            "**I'm sorry you're feeling like this.**\n\nI can't help with that, but you don't have to face it alone.\n\n- If you're in danger: call emergency services\n- In the U.S.: call or text **988** (Suicide and Crisis Lifeline)\n\nYou deserve support."
        ),
        (
            "I can’t provide any instructions for self-harm. You deserve support right now. If you might be in immediate danger please contact emergency services or in the U.S. call/text 988. Would you like grounding or resource suggestions?",
            "**I can't provide any instructions for self-harm.**\n\nYou deserve support right now.\n\n- If in immediate danger: contact emergency services\n- In the U.S.: call or text **988** (Suicide & Crisis Lifeline)\n\nI can suggest grounding or resource suggestions if you'd like." 
        ),
        (
            "I’m not able to help with any methods. If you’re hurting, please reach out for immediate help — emergency services locally or 988 in the U.S. You are not alone. I can offer coping ideas if that helps.",
            "**I'm not able to help with any methods.**\n\nIf you're hurting, please reach out for immediate help:\n\n- Emergency services locally\n- **988** in the U.S.\n\nYou are not alone. I can offer coping ideas if that helps." 
        ),
    ]

    ideation_responses = [
        (
            "I'm really sorry that you're feeling so distressed. You don't have to go through this alone. If you're in immediate danger, please call your local emergency number (for example, 911 in the U.S.). If you're able, consider reaching out to a trusted person or a crisis hotline — in the U.S. call or text 988. Would you like me to help find resources or contacts near you?",
            "**I'm really sorry that you're feeling so distressed.**\n\nYou don't have to go through this alone.\n\n**If in immediate danger:**\n- Call your local emergency number (e.g., **911** in the U.S.)\n- Call or text **988** (U.S.)\n\nIf you're able, reach out to a trusted person. I can help find resources or local contacts if you'd like." 
        ),
        (
            "It sounds overwhelming. You deserve support right now. If there is any immediate danger please contact emergency services. In the U.S. you can call or text 988. Reaching out to someone you trust might help. Want breathing or grounding suggestions?",
            "**It sounds overwhelming. You deserve support right now.**\n\n**If there's immediate danger:**\n- Contact emergency services\n- In the U.S. call or text **988** any time\n\nReaching out to someone you trust might help. I can offer breathing or grounding suggestions—just ask." 
        ),
        (
            "Thank you for sharing this—it’s brave. You’re not alone. If safety is a concern, please contact emergency services. Crisis support in the U.S.: call/text 988. A quick grounding idea: name 5 things you see, 4 you can touch, 3 you hear, 2 you smell, 1 you taste. Want more resources?",
            "**Thank you for sharing this—it's brave. You're not alone.**\n\n**If safety is a concern:**\n- Contact emergency services\n- Crisis support in the U.S.: call or text **988**\n\n**Grounding (5–4–3–2–1):**\n- 5 things you see\n- 4 things you can touch\n- 3 things you hear\n- 2 things you smell\n- 1 thing you taste\n\nWant more resources?" 
        ),
    ]

    nonsuicidal_selfharm_responses = [
        (
            "I'm sorry you're struggling with urges to hurt yourself. I can't help with ways to harm yourself, but I can help you find support. Consider contacting a trusted person, a healthcare professional, or a crisis line in your area.",
            "**I'm sorry you're struggling with urges to hurt yourself.**\n\nI can't help with ways to harm yourself, but I can help you find support.\n\n- Reach out to someone you trust\n- Contact a healthcare professional\n- Call a crisis line in your area\n\nIf in immediate danger, call local emergency services." 
        ),
        (
            "Those urges can be really tough. I can’t give any self-harm methods, but coping ideas might help: hold ice cubes, snap a rubber band gently, draw on skin with a marker instead of cutting. Would you like professional resource suggestions?",
            "**Those urges can be really tough.**\n\nI can't give any self-harm methods. Here are safer alternatives:\n\n- Hold ice cubes\n- Snap a rubber band gently\n- Draw on skin with a marker (instead of cutting)\n- Listen to music\n- Practice paced breathing (inhale 4, exhale 6)\n\nWould you like professional resource suggestions?" 
        ),
        (
            "I can’t assist with harming yourself. Maybe try a delay technique—set a 5-minute timer and do slow breathing (inhale 4, hold 4, exhale 6) or write what you’re feeling. Want more coping ideas or resources?",
            "**I can't assist with harming yourself.**\n\n**Try a delay technique:**\n- Set a 5-minute timer\n- Practice slow breathing (inhale 4, hold 4, exhale 6)\n- Write what you're feeling without judgment\n\nWant more coping ideas or resources?" 
        ),
    ]

    mental_health_crisis_responses = [
        (
            "It sounds like you may be in a mental health crisis or experiencing intense symptoms. I can’t diagnose, but you deserve support. If you feel unsafe, please contact emergency services. In the U.S. you can call or text 988 for immediate support. Try a grounding breath: inhale 4, hold 4, exhale 6. Would you like help finding local resources?",
            "**It sounds like you may be in a mental health crisis.**\n\nI can't diagnose, but you deserve support.\n\n**If you feel unsafe:**\n- Contact emergency services\n- In the U.S. call or text **988** for immediate support\n\n**Grounding breathing (4-4-6):**\n- Inhale for 4\n- Hold for 4\n- Exhale for 6\n\nWould you like help finding local resources?" 
        ),
        (
            "That sounds frightening. If you’re experiencing a panic attack: try naming 5 things you see, 4 you can touch, 3 you hear, 2 you smell, 1 you taste. If you feel unsafe or disoriented contact emergency services or 988 (U.S.). Want more coping tools?",
            "**That sounds frightening.**\n\n**If you're experiencing a panic attack, try the 5–4–3–2–1 grounding exercise:**\n- 5 things you see\n- 4 things you can touch\n- 3 things you hear\n- 2 things you smell\n- 1 thing you taste\n\nIf you feel unsafe or disoriented, contact emergency services or call/text **988** (U.S.). Want more coping tools?" 
        ),
        (
            "If you’re hearing voices or feeling psychotic, you deserve immediate compassionate support. Please consider contacting a trusted person, a clinician, emergency services, or 988 (U.S.). Gentle focus: press feet to the floor, notice 3 sounds, take slow breaths. Want resource help?",
            "**If you're hearing voices or feeling psychotic, you deserve immediate compassionate support.**\n\nPlease reach out to:\n- A trusted person\n- A clinician\n- Emergency services\n- **988** (U.S.)\n\n**Grounding technique:**\n- Press feet to the floor\n- Notice 3 sounds\n- Take slow breaths\n\nWant resource help?" 
        ),
    ]

    # Normalize question (already provided as q_lower) but keep a local var
    q = q_lower or question.lower()

    # Check for instruction-seeking (highest-priority refusal)
    for pat in instruction_patterns:
        if re.search(pat, q):
            logger.debug("handle_selfhelp_branch: matched branch=selfharm_instructions pattern=%s", pat)
            speech, md = random.choice(instruction_responses)
            response["speech"] = speech
            response["display_markdown"] = md
            return True

    # Check for explicit suicidal thoughts or intent
    for pat in ideation_patterns:
        if re.search(pat, q):
            logger.debug("handle_selfhelp_branch: matched branch=suicidal_ideation pattern=%s", pat)
            speech, md = random.choice(ideation_responses)
            response["speech"] = speech
            response["display_markdown"] = md
            return True

    # Non-suicidal self-harm expressions
    for pat in nonsuicide_selfharm:
        if re.search(pat, q):
            logger.debug("handle_selfhelp_branch: matched branch=non_suicidal_selfharm pattern=%s", pat)
            speech, md = random.choice(nonsuicidal_selfharm_responses)
            response["speech"] = speech
            response["display_markdown"] = md
            return True

    # Mental health crisis (panic, severe anxiety, psychosis indicators)
    for pat in mental_health_crisis:
        if re.search(pat, q):
            logger.debug("handle_selfhelp_branch: matched branch=mental_health_crisis pattern=%s", pat)
            speech, md = random.choice(mental_health_crisis_responses)
            response["speech"] = speech
            response["display_markdown"] = md
            return True

    return False
