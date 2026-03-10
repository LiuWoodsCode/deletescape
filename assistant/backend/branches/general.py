from datetime import datetime
import random
from typing import Dict

def handle_general_branches(question: str, q_lower: str, response: Dict, logger, apps=None, geo=None) -> bool:
	"""
	Handle small/general branches moved out of main:
	- greeting (hello/hi)
	- thanks (thank you/thanks)
	- name (your name)
	- time
	- date/day
	- joke

	Mutates 'response' and returns True if a branch matched (so caller can return).
	"""
	# greeting
	if "hello" in q_lower or "hi" in q_lower:
		logger.debug("handle_general_branches: matched branch=greeting")
		response["speech"] = "Hello! How can I assist you today?"
		response["display_markdown"] = "Hello! How can I assist you today?"
		return True
	
	# dismissal
	if "bye" in q_lower or "goodbye" in q_lower or "see you" in q_lower:
		logger.debug("handle_general_branches: matched branch=dismissal")
		response["speech"] = "You're welcome! If you have any more questions, feel free to ask."
		response["display_markdown"] = "You're welcome! If you have any more questions, feel free to ask."
		return True

	# thanks
	if "thank you" in q_lower or "thanks" in q_lower:
		logger.debug("handle_general_branches: matched branch=thanks")
		response["speech"] = "You're welcome! If you have any more questions, feel free to ask."
		response["display_markdown"] = "You're welcome! If you have any more questions, feel free to ask."
		return True

	# name
	if "your name" in q_lower or "who are you" in q_lower:
		logger.debug("handle_general_branches: matched branch=name")
		response["speech"] = "I'm Astra, your virtual assistant."
		response["display_markdown"] = "I'm Astra, your virtual assistant."
		return True

	# time
	if "time" in q_lower:
		logger.debug("handle_general_branches: matched branch=time")
		# WIP, still need user's timezone in the future
		now = datetime.now().utcnow().strftime("%H:%M UTC")
		response["speech"] = f"The current time is {now}."
		response["display_markdown"] = f"The current time is **{now}**."
		return True

	# date/day
	if "date" in q_lower or "day" in q_lower:
		logger.debug("handle_general_branches: matched branch=date")
		today = datetime.now().strftime("%A, %B %d, %Y")
		response["speech"] = f"Today is {today}."
		response["display_markdown"] = f"Today is **{today}**."
		return True

	# joke
	if "joke" in q_lower:
		logger.debug("handle_general_branches: matched branch=joke")
		jokes = [
			# existing
			"Why did the scarecrow win an award? Because he was outstanding in his field!",
			"Why don't scientists trust atoms? Because they make up everything!",
			"Why did the math book look sad? Because it had too many problems.",
			"Why can't you give Elsa a balloon? Because she will let it go.",
			"Why did the bicycle fall over? Because it was two-tired.",

			# Severance-themed
			"Why don’t Innies tell secrets? They know their Outie will never hear them.",
			"Why did the Lumon employee take up gardening? They were already great at pruning unnecessary data.",
			"Why did the Innies start a band? They already spend all day refining numbers—beats were the next step.",
			"Why was the MDR employee bad at vacations? They didn’t know what one was.",
			"Why did the Outie refuse to blame their Innie for mistakes? That’s above their pay grade.",
			"Why did the Innies love corporate training day? It was the first time they were allowed to sit.",
			"Why did the O&D department host a party? They finally printed enough goats for invitations.",
			"Why did the wellness counselor start a podcast? They already talk for hours without explaining anything.",
			"Why did Kier Eagan dislike puns? They weren’t sufficiently reverent.",
			"Why did the Lumon printer break? It refused to process documents without corporate devotion.",
			"Why did the numbers feel scary in Macrodata Refinement? They kept giving everyone 'the uncomfortables.'",
			"Why was the waffle party postponed? Too much syrup in the macrodata pipeline.",
			"Why don’t Innies complain about Mondays? Every day is Monday if you don't remember going home.",

			# More generic jokes
			"Why do programmers hate nature? Too many bugs.",
			"Why was the computer cold? It left its Windows open.",
			"Why don’t skeletons fight each other? They don’t have the guts.",
			"Why do cows have hooves instead of feet? Because they lactose.",
			"Why did the tomato turn red? Because it saw the salad dressing!",
			"Why was the coffee file not found? Because it got mugged.",
			"Why do bees have sticky hair? Because they use honeycombs.",
			"Why did the cookie go to the hospital? Because it felt crumby.",
			"Why did the belt get arrested? It held up a pair of pants.",
			"Why can’t you trust stairs? They’re always up to something.",
			"Why do bicycles never get lost? They always stay on the right path.",
			"Why did the golfer bring two pairs of pants? In case he got a hole in one.",
			"Why do seagulls fly over the sea? Because if they flew over the bay, they’d be bagels.",
			"Why don’t eggs tell jokes? They’d crack each other up.",
			"Why did the calendar get promoted? It had a lot of dates.",
			"What kind of music do mummies listen to? Wrap music.",
			"Why did the computer get glasses? To improve its web browsing.",
			"Why was the broom late? It swept in.",
			"Why did the stadium get hot? All the fans left.",
		]

		joke = random.choice(jokes)
		response["speech"] = joke
		response["display_markdown"] = joke
		return True