import re
from datetime import datetime

# Mock financial groups
financial_groups= {
    '0': 'DOW 30 STOCKS', 
    '1': 'NASDAQ 100 STOCKS', 
    '2': 'S&P 500 STOCKS', 
    '3': 'RUSSELL 1000 STOCKS', 
    '4': 'WILSHIRE 5000', 
    '5': 'INDICES COMMON', 
    '6': 'INDICES ALL', 
    '7': 'FUTURES & COMMODITIES', 
    '8': 'FOREX ALL', 
    '9': 'FOREX LIQUID', 
    '10': 'GOVERNMENT BONDS', 
    '11': 'ETFs', 
    '12': 'LONDON EXCHANGE', 
    '13': 'TORONTO STOCKS', 
    '14': 'KOREA EXCHANGE', 
    '15': 'KOREA KOSDAQ', 
    '16': 'CRYPTO CURRENCIES'
    }

#-------------------------------------------------------------------------------------------------------------------
def parse_date(user_message):
    """
    Parse the date from the user's input message.
    If no date is found, defaults to today's date.
    """
    date_match = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d+)",
        user_message,
        re.IGNORECASE,
    )
    if date_match:
        month, day = date_match.groups()
        # Convert abbreviated month to full month name
        month = datetime.strptime(month[:3], "%b").strftime("%B")
        return month, day

    # Default to today's date if no date is provided
    today = datetime.now()
    return today.strftime("%B"), str(today.day)

#-------------------------------------------------------------------------------------------------------------------

def construct_day_range(user_message):
    """
    Construct the day range parameter based on user input.
    Handles phrases like 'shorter than X days' or 'less than X days'.
    """
    user_message_lower = user_message.lower()

    # Handle "shorter than X days" or "less than X days"
    less_than_match = re.search(r"(?:shorter than|less than) (\d+) days", user_message_lower)
    if less_than_match:
        max_days = less_than_match.group(1)
        return f"2-{max_days}"  # Default min length to 2 days

    # Handle "min length X and max length Y days" or "between X and Y days"
    min_max_match = re.search(
        r"(?:min length (\d+) and max length (\d+)|between (\d+) and (\d+)) days",
        user_message_lower,
    )
    if min_max_match:
        min_days = min_max_match.group(1) or min_max_match.group(3)
        max_days = min_max_match.group(2) or min_max_match.group(4)
        return f"{min_days}-{max_days}"

    # Default to "-" if no range is specified
    return "-"



#-------------------------------------------------------------------------------------------------------------------

def get_resource_id(user_message):
    """
    Match financial group from user input. Handles variations like 's&p500', 's and p',
    'sandp500', and accounts for singular/plural forms like 'ETF' and 'ETFs'.
    """
    # Normalize user message
    user_message_lower = user_message.lower().replace("&", "and").replace("stocks", "").strip()

    # Handle special cases
    special_cases = {
        "s and p": "s&p 500",
        "sandp": "s&p 500",
        "sandp500": "s&p 500",
    }
    for key, value in special_cases.items():
        if key in user_message_lower:
            user_message_lower = user_message_lower.replace(key, value)

    user_keywords = set(user_message_lower.split())  # Split into individual keywords

    # Handle singular/plural normalization for user input
    user_keywords = {word.rstrip('s') if word.endswith('s') else word + 's' for word in user_keywords}

    best_match = None
    highest_match_score = 0  # Track the best match score

    for rid, group_name in financial_groups.items():
        # Normalize the group name
        group_name_lower = group_name.lower().replace("&", "and").replace("stocks", "").strip()
        group_keywords = set(group_name_lower.split())  # Split into individual keywords

        # Handle singular/plural normalization for group keywords
        group_keywords = {word.rstrip('s') if word.endswith('s') else word + 's' for word in group_keywords}

        # Calculate the match score as the number of overlapping keywords
        match_score = len(user_keywords & group_keywords)

        # Update the best match if this group has a higher score
        if match_score > highest_match_score:
            best_match = rid
            highest_match_score = match_score

    # Return the best match or default to Wilshire 5000 if no match found
    return best_match if best_match else "4"






#-------------------------------------------------------------------------------------------------------------------
# Main test script
if __name__ == "__main__":
    # Test messages
    test_messages = [
        "get the opportunities for dow industrial that are less than 60 days long for jul 11",
        "get the patterns in nasdaq that are between 10 and 22 days long",
        "get the opps for S&P that are less than 150 days long",
        "get the top opportunities for ETFs - I like short-term trade patterns less than 55 days",
        "Show me opportunities for ETFs  with length less than 40 days  on December 20",
        "get the top opportunities in S&P 500 for today",
        "find patterns in sandp",
        "what are the best trades in s and p",
        "Get opportunities in Wilshire 5000 shorter than 40 days for December 26"
    ]

    for message in test_messages:
        print(f"Message: {message}")
        # Extract resource_id
        resource_id = get_resource_id(message)
        print(f"Resource ID: {resource_id} ({financial_groups[resource_id]})")

        # Extract day_range
        day_range = construct_day_range(message)
        print(f"Day Range: {day_range}")

        # Extract date
        month, day = parse_date(message)
        print(f"Date: {month} {day}")
        print("-" * 50)
