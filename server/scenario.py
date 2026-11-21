"""Practice scenarios and default facts. Served to the browser as data."""

SCENARIOS = [
    {
        "id": "churn-pitch",
        "title": "Customer churn prediction pitch",
        "stakeholder": "VP of Operations",
        "stakeholderTag": "VP Ops",
        "avatar": "VP",
        "duration": "3–5 min",
        "maxAnswers": 10,
        "description": "Four weeks in, leadership wants to see usable results. How do you explain progress and justify a 4-week CRM rollout?",
        "emptyHeadline": "A calm space to practise your pitch.",
        "emptySubtitle": "Your VP of Operations will ask for an update.\nSpeak or type — pause, rethink, and try again anytime.",
        "steps": [
            {"label": "1. Progress:", "text": "Data organized & model tested"},
            {"label": "2. Plan:", "text": "4 weeks for CRM alerts"},
            {"label": "3. Ask:", "text": "Approve rollout phase"},
        ],
        "starters": {
            "full": "Over the last four weeks, we organized your historical customer data and built a working model that spots customers likely to cancel. We need four more weeks to connect it directly to your CRM so your support team gets automatic alerts without manual exports. Would you like to approve that four-week rollout?",
            "ready": "We spent the last four weeks organizing your customer data and building a model that spots customers at risk of cancelling.",
            "tradeoff": "Connecting it to your CRM takes four more weeks so your support team receives automatic alerts without manual spreadsheets.",
            "recommend": "I recommend approving the four-week integration phase so your team can act on at-risk customers directly in the CRM.",
        },
        "placeholder": "Write your pitch here (progress so far, 4-week CRM rollout outcome, approval question)…",
        "defaultContext": {
            "scenarioId": "churn-pitch",
            "discipline": "AI/ML engineer",
            "familiarity": "Business-focused; prefers plain language",
            "knownFacts": "We spent the first four weeks organizing historical customer data and building a churn prediction model. The model can identify customers likely to cancel, achieving an 0.84 F1-score and 89% precision in offline testing. Integrating automated at-risk alerts into the CRM requires four additional working weeks. The deployment phase has not been approved yet, and live revenue or retention savings have not been measured.",
            "goal": "Explain progress without technical jargon, justify the four-week CRM integration plan in terms of team outcomes, and ask for approval to proceed.",
        },
    },
    {
        "id": "two-day-delay",
        "title": "Explaining a 2-day delay",
        "stakeholder": "Project manager",
        "stakeholderTag": "PM",
        "avatar": "PM",
        "duration": "3–5 min",
        "maxAnswers": 10,
        "description": "You hit an unexpected roadblock connecting an older module safely. How do you explain the 2-day impact clearly?",
        "emptyHeadline": "A calm space to practise your update.",
        "emptySubtitle": "Your project manager will ask for an update.\nSpeak or type — pause, rethink, and try again anytime.",
        "steps": [
            {"label": "1. Impact:", "text": "+2 working days needed"},
            {"label": "2. Reason:", "text": "Safe bridge to older module"},
            {"label": "3. Next step:", "text": "Confirm revised target"},
        ],
        "starters": {
            "full": "The new feature screens are built, but connecting them safely to our older account module needs two extra working days so existing sign-ins stay unaffected. I am prioritizing that connection now and recommend confirming a two-day shift on the release target—does that work for your plan?",
            "ready": "The new feature work is built, and we hit an unexpected roadblock connecting it to an older module.",
            "tradeoff": "Bridging it safely needs two additional working days so we do not risk breaking existing user sign-ins.",
            "recommend": "I recommend taking those two working days to verify stability before release—should we adjust the release target accordingly?",
        },
        "placeholder": "Write your update here (the 2-day impact, plain-language reason, next step)…",
        "defaultContext": {
            "scenarioId": "two-day-delay",
            "discipline": "Software developer",
            "familiarity": "Business-focused; prefers plain language",
            "knownFacts": "Core feature screens are built and tested. Connecting the feature safely to an older customer-account module requires two additional working days so existing sign-ins do not break. The revised delivery estimate has not been signed off yet, and no customer downtime has occurred.",
            "goal": "Explain the two-day delay in plain language, reassure your project manager that existing users stay safe, and propose a clear next step.",
        },
    },
]

SCENARIO_BY_ID = {item["id"]: item for item in SCENARIOS}
SCENARIO = SCENARIOS[0]
DEFAULT_CONTEXT = SCENARIO["defaultContext"]


def get_scenario(scenario_id: str) -> dict:
    return SCENARIO_BY_ID.get(scenario_id, SCENARIO)
