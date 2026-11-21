"""The initial exercise and its default facts. Served to the browser as data."""

SCENARIO = {
    "id": "release-update",
    "title": "The release update",
    "stakeholder": "Project manager",
    "duration": "3-5 minutes",
    "maxAnswers": 10,
}
DEFAULT_CONTEXT = {
    "scenarioId": SCENARIO["id"],
    "discipline": "Software developer",
    "familiarity": "Business-focused; prefers plain language",
    "knownFacts": "Search is ready for the Friday release. PDF export was newly proposed and needs two additional working days. The scope change has not been approved. No customer impact or time savings have been measured.",
    "goal": "Explain what is ready, make the scope trade-off clear, and recommend a realistic release plan without sounding defensive.",
}
