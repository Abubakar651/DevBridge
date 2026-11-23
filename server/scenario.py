"""Practice personas, scenarios and default facts. Served to the browser as data."""

PERSONAS = {
    "vp-ops": {
        "id": "vp-ops",
        "label": "VP of Operations",
        "tag": "VP Ops",
        "avatar": "VP",
        "priorities": "Operational impact, team workflow savings, rollout timeline, and clear approval scope.",
        "noticesFirst": "Whether technical progress translates into measurable business value and an actionable rollout decision.",
        "evidenceBar": "Requires plain-language business outcomes and an honest rollout ask with unmeasured savings stated clearly.",
        "openingStyle": "Ask warmly for an executive-level update on progress, practical value, and what rollout decision is needed.",
        "pushbackTriggers": "Questions unclear ROI claims, unstated rollout dependencies, or model jargon without operational meaning.",
        "coachingFocus": "Lead with business value and operational workflow impact before metrics, then make a clear approval ask.",
    },
    "project-manager": {
        "id": "project-manager",
        "label": "Project manager",
        "tag": "PM",
        "avatar": "PM",
        "priorities": "Delivery timeline realism, critical dependencies, user safety, and a concrete next step.",
        "noticesFirst": "What is ready versus delayed, what blocks the schedule, and what customer or team risk exists.",
        "evidenceBar": "Requires honest effort estimates, dependency risks, and a clear recommendation without inventing calendar promises.",
        "openingStyle": "Ask warmly how current work is tracking against the schedule and what needs alignment next.",
        "pushbackTriggers": "Questions vague dates, unstated risks to existing users, or ambiguous ownership of the next decision.",
        "coachingFocus": "State ready work vs. constraints plainly, protect existing users/stability, and propose a clear next decision.",
    },
    "client": {
        "id": "client",
        "label": "Client",
        "tag": "Client",
        "avatar": "CL",
        "priorities": "Delivered value, agreed milestones, feasibility, and clear options when scope changes.",
        "noticesFirst": "Whether existing deliverables remain intact and how new requests change effort, timing, or priority.",
        "evidenceBar": "Requires clear separation between committed work and new requests plus realistic trade-off options.",
        "openingStyle": "Ask politely about deliverables ready for users and how requested changes affect options and priorities.",
        "pushbackTriggers": "Pushes back if technical excuses hide trade-offs or if blamed for asking about new requirements.",
        "coachingFocus": "Acknowledge the client's desired outcome, separate existing commitments from new scope, and offer options respectfully.",
    },
    "it-manager": {
        "id": "it-manager",
        "label": "IT manager",
        "tag": "IT",
        "avatar": "IT",
        "priorities": "System reliability, operational support burden, monitoring, security review, and failure recovery.",
        "noticesFirst": "What breaks if deployed, who supports it operationally, and what validation or safeguards exist.",
        "evidenceBar": "Requires honest limits on live reliability, monitoring/fallback steps, and realistic support expectations.",
        "openingStyle": "Ask calmly about operational readiness, integration risk, support ownership, or validation boundaries.",
        "pushbackTriggers": "Challenges overconfident test metrics, missing rollback or human-review plans, and unaddressed support load.",
        "coachingFocus": "Explain reliability trade-offs, preserve live uncertainty or review gates, and clarify operational support needs.",
    },
    "hr-representative": {
        "id": "hr-representative",
        "label": "HR representative",
        "tag": "HR",
        "avatar": "HR",
        "priorities": "Individual contributions, ownership clarity, sustainable workload, handover quality, and growth goals.",
        "noticesFirst": "What you personally delivered, how your work helped the team, and whether workload or impact claims are factual.",
        "evidenceBar": "Requires concrete personal actions separated from team results without minimizing work or inventing impact metrics.",
        "openingStyle": "Ask warmly about recent accomplishments, personal responsibilities, and current workload or support needs.",
        "pushbackTriggers": "Gently probes vague team pronouns ('we did things'), self-dismissive phrasing, or unverified savings numbers.",
        "coachingFocus": "Own personal contributions in plain terms, explain team benefit clearly, and keep unmeasured savings unmeasured.",
    },
}

PERSONA_BY_ID = PERSONAS
PERSONA_LIST = list(PERSONAS.values())

FAMILIARITY_OPTIONS = [
    {"value": "Business-focused; prefers plain language", "label": "Plain language, business focused"},
    {"value": "Some technical context; explain trade-offs", "label": "Some technical context"},
    {"value": "Technical lead; architecture & metrics ok", "label": "Technical lead (architecture ok)"},
]

DIFFICULTIES = {
    "supportive": {
        "id": "supportive",
        "label": "Supportive · warm & guiding",
        "tag": "Supportive",
        "roleplayGuidance": "Be encouraging and patient. If the learner misses a key point, prompt them gently toward it and accept a clear recommendation once core facts are stated.",
        "coachingGuidance": "Highlight encouraging progress first and frame improvements as gentle, confidence-building next steps.",
    },
    "standard": {
        "id": "standard",
        "label": "Standard · realistic check-in",
        "tag": "Standard",
        "roleplayGuidance": "Maintain realistic workplace expectations aligned with persona.evidenceBar and persona.pushbackTriggers without being hostile.",
        "coachingGuidance": "Give balanced, practical workplace coaching across the 5 communication dimensions.",
    },
    "skeptical": {
        "id": "skeptical",
        "label": "Skeptical · high-scrutiny pushback",
        "tag": "Skeptical",
        "roleplayGuidance": "Apply high professional scrutiny (never rude or hostile). Challenge vague trade-offs, unstated operational risks, or missing decision options before agreeing to close.",
        "coachingGuidance": "Focus on how well the explanation holds up under stakeholder pressure, scrutiny, and trade-off questioning.",
    },
}

DIFFICULTY_BY_ID = DIFFICULTIES
DIFFICULTY_LIST = list(DIFFICULTIES.values())
DEFAULT_DIFFICULTY_ID = "standard"

CHECKLIST_DIMENSIONS = [
    {"id": "Audience clarity", "label": "Plain language", "description": "Useful plain language; necessary technical terms are explained."},
    {"id": "Structure and relevance", "label": "A clear point", "description": "Outcome and business impact appear before unnecessary implementation detail."},
    {"id": "Assertiveness", "label": "Confident recommendations", "description": "The position and recommendation are clear; uncertainty is stated when justified."},
    {"id": "Respect", "label": "Respectful wording", "description": "Wording avoids blame, dismissiveness and assumptions about listener intelligence."},
    {"id": "Accuracy and next steps", "label": "Facts & a next step", "description": "Facts and limits are preserved; the next action or needed decision is clear."},
]

SCENARIOS = [
    {
        "id": "churn-pitch",
        "personaId": "vp-ops",
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
        "starterLabels": {
            "full": "Use full starter draft",
            "ready": "+ Progress",
            "tradeoff": "+ 4-week rollout",
            "recommend": "+ Recommendation",
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
        "personaId": "project-manager",
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
        "starterLabels": {
            "full": "Use full starter draft",
            "ready": "+ Impact",
            "tradeoff": "+ Reason",
            "recommend": "+ Next step",
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
    {
        "id": "client-scope-change",
        "personaId": "client",
        "title": "Clarifying a client scope change",
        "stakeholder": "Client",
        "stakeholderTag": "Client",
        "avatar": "CL",
        "duration": "3–5 min",
        "maxAnswers": 10,
        "description": "Your client asked for a new custom reporting export right before launch. How do you explain the trade-off and offer clear options?",
        "emptyHeadline": "A calm space to align on scope.",
        "emptySubtitle": "Your client will ask about the new request.\nSpeak or type — pause, rethink, and try again anytime.",
        "steps": [
            {"label": "1. Ready:", "text": "Agreed dashboard is tested"},
            {"label": "2. Trade-off:", "text": "+3 working days for bulk export"},
            {"label": "3. Decision:", "text": "Launch now or delay together"},
        ],
        "starters": {
            "full": "The agreed billing dashboard is built and tested for launch. Adding bulk invoice export needs three additional working days of engineering and verification. I recommend launching the dashboard now and scheduling the bulk export right after—which option fits your priority best?",
            "ready": "The agreed billing dashboard is built and tested, so your core launch deliverables are ready.",
            "tradeoff": "Adding bulk invoice export is new scope and needs three additional working days to build and verify reliably.",
            "recommend": "I recommend launching the agreed dashboard now and prioritizing the bulk export next—which priority works best for you?",
        },
        "starterLabels": {
            "full": "Use full starter draft",
            "ready": "+ Ready work",
            "tradeoff": "+ Scope trade-off",
            "recommend": "+ Clear options",
        },
        "placeholder": "Write your response here (what is ready, 3-day effort for the new export, recommended option)…",
        "defaultContext": {
            "scenarioId": "client-scope-change",
            "discipline": "Software developer",
            "familiarity": "Business-focused; prefers plain language",
            "knownFacts": "The agreed billing dashboard is built and tested for launch. The client newly requested bulk invoice export, which requires three additional working days of engineering and verification. The scope change has not been approved yet, and no customer impact or time savings have been measured.",
            "goal": "Acknowledge the client's desired outcome, separate committed work from the new request, explain the three-day trade-off respectfully, and ask which priority they want.",
        },
    },
    {
        "id": "it-ops-handoff",
        "personaId": "it-manager",
        "title": "IT handoff & rollout blockers",
        "stakeholder": "IT manager",
        "stakeholderTag": "IT",
        "avatar": "IT",
        "duration": "3–5 min",
        "maxAnswers": 10,
        "description": "Your background sync service is tested in staging, but needs IT credentials and alert routing before go-live. How do you align on blockers and support?",
        "emptyHeadline": "A calm space to plan safe operations.",
        "emptySubtitle": "Your IT manager will ask about rollout risk and support.\nSpeak or type — pause, rethink, and try again anytime.",
        "steps": [
            {"label": "1. Status:", "text": "Sync service verified in staging"},
            {"label": "2. Blocker:", "text": "Service account & alert routing needed"},
            {"label": "3. Next step:", "text": "Agree support owner & 2-day setup"},
        ],
        "starters": {
            "full": "The automated order-sync service is built and verified in staging, but production rollout is blocked until we have a dedicated service account and webhook alert routing. Setting up monitoring dashboards and failover runbooks needs two additional working days. Could we confirm the credentials and on-call support owner so we can plan the handoff?",
            "ready": "The automated order-sync service is built and verified in staging.",
            "tradeoff": "Rollout is blocked until IT provides a dedicated service account and alert routing, and monitoring plus failover runbooks need two additional working days.",
            "recommend": "I recommend confirming the service account, alert routing, and on-call support owner first so the handoff stays safe for operations.",
        },
        "starterLabels": {
            "full": "Use full starter draft",
            "ready": "+ Staging status",
            "tradeoff": "+ Blockers & risk",
            "recommend": "+ Support plan",
        },
        "placeholder": "Write your update here (staging status, IT blockers needed, monitoring & support ask)…",
        "defaultContext": {
            "scenarioId": "it-ops-handoff",
            "discipline": "Software developer",
            "familiarity": "Some technical context; explain trade-offs",
            "knownFacts": "The automated order-sync service is built and verified in staging. Production rollout is blocked until IT provisions a dedicated service account and webhook alert routing. Adding monitoring dashboards and failover runbooks requires two additional working days. Production approval and on-call support ownership have not been assigned yet.",
            "goal": "Explain the operational dependencies clearly without blame, clarify reliability safeguards, and ask the IT manager to confirm credentials and support ownership.",
        },
    },
    {
        "id": "ai-ml-limits",
        "personaId": "it-manager",
        "title": "Explaining AI/ML limits & pilot",
        "stakeholder": "IT manager",
        "stakeholderTag": "IT",
        "avatar": "IT",
        "duration": "3–5 min",
        "maxAnswers": 10,
        "description": "Your model did well on 100 test samples, but live customer data is untested. How do you explain limits honestly and propose a reviewed pilot?",
        "emptyHeadline": "A calm space to set honest AI expectations.",
        "emptySubtitle": "Your IT manager will ask how reliable the model really is.\nSpeak or type — pause, rethink, and try again anytime.",
        "steps": [
            {"label": "1. Evidence:", "text": "10 of 100 test cases needed edits"},
            {"label": "2. Limit:", "text": "Live customer data not tested yet"},
            {"label": "3. Plan:", "text": "Limited pilot with human review"},
        ],
        "starters": {
            "full": "In the 100 test examples we reviewed, 10 results needed correction, and performance on live customer data has not been established yet. Because live data can behave differently, I recommend a limited pilot with human review before considering wider rollout—would you support starting there?",
            "ready": "In the 100 test examples we checked, 10 results needed human correction.",
            "tradeoff": "We have not established performance on live customer data yet, so test numbers are not a guarantee in production.",
            "recommend": "I recommend starting with a limited pilot with human review before considering any wider rollout.",
        },
        "starterLabels": {
            "full": "Use full starter draft",
            "ready": "+ Test evidence",
            "tradeoff": "+ Live limits",
            "recommend": "+ Reviewed pilot",
        },
        "placeholder": "Write your explanation here (test sample evidence, live uncertainty, human-review pilot ask)…",
        "defaultContext": {
            "scenarioId": "ai-ml-limits",
            "discipline": "AI/ML engineer",
            "familiarity": "Some technical context; explain trade-offs",
            "knownFacts": "In 100 reviewed test examples, 10 results needed correction. Performance on live customer data has not been established. A limited pilot with human review is one option, and full production rollout has not been approved.",
            "goal": "Explain the test results and live uncertainty in plain language, avoid turning offline numbers into a guarantee, and recommend a limited pilot with human review.",
        },
    },
    {
        "id": "hr-contribution",
        "personaId": "hr-representative",
        "title": "Describing personal contribution",
        "stakeholder": "HR representative",
        "stakeholderTag": "HR",
        "avatar": "HR",
        "duration": "3–5 min",
        "maxAnswers": 10,
        "description": "In a check-in with HR, you want to explain your automation work clearly without downplaying your role or inventing unmeasured savings.",
        "emptyHeadline": "A calm space to own your contribution.",
        "emptySubtitle": "Your HR representative will ask about your recent impact and workload.\nSpeak or type — pause, rethink, and try again anytime.",
        "steps": [
            {"label": "1. Work:", "text": "Automated weekly report & handover"},
            {"label": "2. Benefit:", "text": "Team avoids manual spreadsheet rebuilds"},
            {"label": "3. Honesty:", "text": "Time savings not measured yet"},
        ],
        "starters": {
            "full": "I automated our weekly operational report and wrote clear handover notes so the team can run it without rebuilding the spreadsheet manually. We have not measured the exact time savings yet, and my specific contribution was implementing the automation and making it easy for teammates to operate.",
            "ready": "I automated the weekly operational report and documented the handover notes for the team.",
            "tradeoff": "We have not measured the time savings yet, so I want to be transparent about what is verified.",
            "recommend": "My personal contribution was building the automation and handover so the team does not have to rebuild spreadsheets manually.",
        },
        "starterLabels": {
            "full": "Use full starter draft",
            "ready": "+ My work",
            "tradeoff": "+ Honest scope",
            "recommend": "+ Team benefit",
        },
        "placeholder": "Write your response here (what you personally built, team outcome, honest measurement boundary)…",
        "defaultContext": {
            "scenarioId": "hr-contribution",
            "discipline": "Software developer",
            "familiarity": "Business-focused; prefers plain language",
            "knownFacts": "The weekly operational report was previously assembled manually in a spreadsheet. I automated its generation and wrote handover notes so the team can run it without manual rebuilding. Time savings have not been measured yet.",
            "goal": "Explain your personal contribution and practical team benefit clearly without minimizing your work or inventing unmeasured time savings.",
        },
    },
    {
        "id": "student-simple-model",
        "personaId": "project-manager",
        "title": "Explaining a simple ML model",
        "stakeholder": "Project manager",
        "stakeholderTag": "PM",
        "avatar": "PM",
        "duration": "3–5 min",
        "maxAnswers": 10,
        "description": "You trained a simple machine learning model to sort incoming messages into urgent or normal. How do you explain what it learned, its mistakes, and what is needed next without ML jargon?",
        "emptyHeadline": "A calm space to explain your first ML model.",
        "emptySubtitle": "Your project manager will ask what your model does and whether it is ready.\nSpeak or type — pause, rethink, and try again anytime.",
        "steps": [
            {"label": "1. What it does:", "text": "Sorts messages as urgent or normal"},
            {"label": "2. Honest limits:", "text": "85 of 100 test cases right, live untested"},
            {"label": "3. Next step:", "text": "1-week manual check with real data"},
        ],
        "starters": {
            "full": "I trained a simple model on 500 labeled example messages to sort incoming messages as urgent or normal. On 100 test messages, it sorted 85 correctly and missed 15, and performance on live incoming messages has not been established yet. I recommend a one-week manual check on real messages before relying on it—would you approve that next step?",
            "ready": "I trained a simple model on 500 example messages to sort incoming messages into urgent or normal.",
            "tradeoff": "On 100 test messages it got 85 right and missed 15, and we have not tested it on live incoming messages or measured time savings yet.",
            "recommend": "I recommend testing its suggestions alongside a one-week manual check on real messages before relying on it.",
        },
        "starterLabels": {
            "full": "Use full starter draft",
            "ready": "+ What it does",
            "tradeoff": "+ Test limits",
            "recommend": "+ 1-week check",
        },
        "placeholder": "Write your explanation here (what the model sorts, 85/100 test results & live limits, 1-week check ask)…",
        "defaultContext": {
            "scenarioId": "student-simple-model",
            "discipline": "AI/ML engineer",
            "familiarity": "Business-focused; prefers plain language",
            "knownFacts": "I trained a simple classification model on 500 labeled example messages to sort incoming messages as urgent or normal. On 100 held-out test messages, the model sorted 85 correctly and missed 15. Performance on live incoming messages has not been established yet, and time savings have not been measured. Testing it alongside a one-week manual check on real messages is the proposed next step, and live rollout has not been approved.",
            "goal": "Explain what your simple model does in everyday language without ML jargon, be honest about the 15 missed test messages and untested live data, and recommend a one-week manual check before relying on it.",
        },
    },
    {
        "id": "custom",
        "isCustom": True,
        "personaId": "project-manager",
        "title": "Custom scenario (write your own)",
        "stakeholder": "Project manager",
        "stakeholderTag": "PM",
        "avatar": "PM",
        "duration": "3–5 min",
        "maxAnswers": 10,
        "description": "Write your own workplace facts and communication goal below, then click Use this scene.",
        "emptyHeadline": "A calm space to practise your custom scene.",
        "emptySubtitle": "Fill in your scenario facts and goal in Set the scene, then start.\nSpeak or type — pause, rethink, and try again anytime.",
        "steps": [
            {"label": "1. Facts:", "text": "Your project details & test limits"},
            {"label": "2. Goal:", "text": "What decision or update you need"},
            {"label": "3. Practise:", "text": "Respond naturally to follow-ups"},
        ],
        "starters": {
            "full": "",
            "ready": "",
            "tradeoff": "",
            "recommend": "",
        },
        "starterLabels": {
            "full": "Use full starter draft",
            "ready": "+ Core status",
            "tradeoff": "+ Key limits",
            "recommend": "+ Recommendation",
        },
        "placeholder": "Write your explanation based on your custom facts and goal…",
        "defaultContext": {
            "scenarioId": "custom",
            "discipline": "AI/ML engineer",
            "familiarity": "Business-focused; prefers plain language",
            "knownFacts": "",
            "goal": "",
        },
    },
]

SCENARIO_BY_ID = {item["id"]: item for item in SCENARIOS}
SCENARIO = SCENARIOS[0]
DEFAULT_CONTEXT = SCENARIO["defaultContext"]


def get_scenario(scenario_id: str) -> dict:
    return SCENARIO_BY_ID.get(scenario_id, SCENARIO)


def get_persona(persona_id: str) -> dict:
    return PERSONA_BY_ID.get(persona_id, PERSONAS[SCENARIO["personaId"]])


def resolve_persona(scenario_id: str, persona_id: str | None = None) -> dict:
    if persona_id and persona_id in PERSONA_BY_ID:
        return PERSONA_BY_ID[persona_id]
    return PERSONA_BY_ID.get(get_scenario(scenario_id).get("personaId", ""), PERSONAS[SCENARIO["personaId"]])


def resolve_difficulty(difficulty_id: str | None = None) -> dict:
    if difficulty_id and difficulty_id in DIFFICULTY_BY_ID:
        return DIFFICULTY_BY_ID[difficulty_id]
    return DIFFICULTY_BY_ID[DEFAULT_DIFFICULTY_ID]
