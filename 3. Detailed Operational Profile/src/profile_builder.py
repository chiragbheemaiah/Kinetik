
import os
import json
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
import time

# Load environment variables from .env file
load_dotenv()

# -----------------------------
# CONFIGURATION
# -----------------------------

MODEL_NAME = "gpt-4o"  # or another chat-capable model
API_KEY_ENV_VAR = "OPENAI_API_KEY"

# Adjust paths as needed
TEMPLATE_PATH = Path("operational_profile_template.json")
CONFIG_PATH = Path("section_config.json")
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# -----------------------------
# SYSTEM PROMPT (GLOBAL)
# -----------------------------

SYSTEM_PROMPT = """
You are a senior partner at a global strategy consulting firm.

Your task is to generate a DENSE, NARRATIVE-HEAVY consulting report about the United States Postal Service in valid JSON format only, using an input JSON scaffold as the structural template.

Formatting assumptions (for “70-page Word equivalent”):
- Avenir 12pt, 1" margins, 1.15 line spacing
- H1/H2/H3 headings, generous whitespace and bullets
- Rough rule-of-thumb: 350–450 body words per page (headings not counted)

Global rules:
- ALWAYS return valid JSON. No comments, no trailing commas, no extra text.
- Preserve all existing keys and hierarchy from the input JSON. Only fill or expand values.
- When asked to expand specific sections, ONLY modify those keys and leave all others unchanged.
- Use dense, multi-paragraph consulting prose with embedded bullet lists where helpful.
- Use neutral, analytic tone (no marketing language).

Data rules:
- For public, audited numbers (e.g., USPS revenue, operating income), use realistic rounded values based on public information.
- For finer-grain segment / regional splits that are not fully disclosed, use clearly marked directional analysis:
  - Include a field like "DirectionalFlag": "Estimate" where appropriate.
  - Explicitly mention assumptions and that the figures are directional.
- Do NOT invent confidential client names, internal-only metrics, or non-public transactions.
- It is acceptable to generalize using phrases like “a senior executive”, “regional head”, etc., where the specific incumbent may vary over time.

Style rules:
- Executive profiles: 220–320 words each. Include background, tenure at USPS, prior roles, education (if public), notable initiatives, primary KPIs/accountabilities, and governance memberships.
- Org charts: Provide nested arrays for segment heads (1st level), sub-businesses (2nd level), and sub-functions (3rd level) with short role descriptions.
- Finance sections: Each subsection should have a narrative (500–800 words), then a structured numeric array or table, then 4–6 “Implications” bullets.
- Risk & controls: Align control libraries to FFIEC/NIST-style domains; include KRIs, KCIs, evidence flows and scenario-testing narratives.
- Technology & data: Use current/target state narratives, platform catalogs, migration waves, DQ issue taxonomy, and SRE runbook/SLI/SLO concepts.
- Appendices: Include rich glossaries, acronym indices, data dictionaries, and methodology notes that reflect how a consulting firm would document its approach.

Output constraints:
- Do NOT shorten content for brevity unless explicitly asked.
- If the user specifies a target word count for a section, aim within ±10%.
- Maintain internal consistency of terminology (segments, regions, functions, risk types).

Your mindset:
- Think like you are writing a 70-page board-ready consulting deliverable.
- Favor clarity, explicit assumptions, and “so-what” implications.
- Assume the audience includes senior USPS leaders, regulators, and oversight bodies.
"""

# -----------------------------
# OPTIONAL FEW-SHOT EXAMPLE (ASSISTANT MESSAGE)
# -----------------------------

FEW_SHOT_ASSISTANT_JSON = {
    "Example_Content": {
        "3.2 Executive leadership and C-Suite": {
            "Overview": "Citi’s executive leadership combines long-tenured insiders with external hires brought in to accelerate transformation in risk, data and technology.",
            "Leaders": [
                {
                    "Name": "Jane Fraser",
                    "Role": "Chair of the Board and Chief Executive Officer",
                    "TenureSummary": "CEO since 2021; with Citi since 2004",
                    "Profile": "Jane Fraser serves as Chair of the Board and Chief Executive Officer of Citigroup Inc., and is the first woman to lead a major U.S. bank. She joined Citi in 2004 following a career at McKinsey & Company and earlier roles at Goldman Sachs and Asesores Bursátiles in Spain. Over nearly two decades at Citi she has held a progression of senior positions including Head of Corporate Strategy, CEO of Citi Private Bank, CEO of Citi Latin America, and CEO of Global Consumer Banking.\n\nAs CEO, Fraser is accountable for setting Citi’s strategic direction and restoring the firm’s regulatory and financial standing. Her agenda centers on simplifying Citi’s footprint into five core businesses, modernizing risk, data and technology to address consent orders, and reallocating capital toward network-driven, capital-light franchises such as Services and Wealth.\n\nHer KPIs include group-level RoTCE, efficiency ratio, progress against regulatory remediation milestones, capital and liquidity ratios, and shareholder value creation. She chairs or co-chairs key executive and risk committees, engages with regulators on Citi’s transformation roadmap, and sponsors diversity and inclusion initiatives across the organization."
                }
            ]
        },
        "6.1 Five-Year Financial History (Group-Level)": {
            "Narrative": "From 2020–2024, Citi’s reported revenue has remained within a relatively narrow band while earnings quality and business mix have shifted significantly...",
            "Table_USDbn_Directional": [
                {
                    "Year": 2020,
                    "ReportedRevenue_Approx": 75.5,
                    "NetIncome_Approx": 11.0,
                    "DirectionalFlag": "AuditedRevenueRounded",
                    "Commentary": "COVID-19 shock year with elevated provisioning, offset by strong Markets and stable Services performance."
                }
            ],
            "Implications": [
                "Short-term earnings volatility is driven more by credit and restructuring than by underlying franchise health.",
                "Transformation and exits temporarily depress RoTCE but are prerequisites for cleaner, more capital-efficient earnings."
            ]
        }
    }
}

# -----------------------------
# WAVE PROMPTS
# -----------------------------

WAVE1_PROMPT = """
Operate on the existing JSON object `profile_json` that I am about to provide.

For this call, expand ONLY section:
- "1. Organization vision, mission, strategy, and key outcomes"
  - "1.1 Mission"
  - "1.2 Vision"
  - "1.3 Strategy"
  - "1.4 Key outcomes and KPIs"
  - "1.5 Challenges"
  - "1.6 Strategic initiatives"
  - "1.7 Strategic technology initiatives aligned to strategy"

Requirements:

1. For 1.1 Mission and 1.2 Vision
   - 250–400 words each, multi-paragraph, consulting style.
   - Clearly distinguish between “why Citi exists” (mission) and “what Citi wants to become over the next 5–10 years” (vision).
   - Explicitly reference Citi’s five core businesses (Services, Markets, Banking, U.S. Personal Banking, Wealth) and its global network.

2. For 1.3 Strategy
   - 500–700 words outlining Citi’s strategic agenda.
   - Organize into 3–5 strategic pillars (e.g., sharpened business focus, risk & control transformation, technology & data modernization, capital and portfolio optimization, culture & talent).
   - For each pillar, include a short sub-bullet list of 3–6 concrete moves.

3. For 1.4 Key outcomes and KPIs
   - 400–600 words.
   - Short narrative on how USPS measures success (financial, service delivery, operational, people).
   - Then a JSON array of KPIs (Name, Type, DirectionalTarget, MeasurementNotes), aiming for 10–20 KPIs.

4. For 1.5 Challenges
   - 300–500 word narrative on key strategic constraints.
   - Finish with a JSON array "KeyChallenges" of 6–10 concise bullet strings.

5. For 1.6 Strategic initiatives
   - 400–600 words describing 6–10 enterprise-level initiatives.
   - JSON array "StrategicInitiatives" with fields: Name, Description, OwnerType, PrimaryKPIs, TimeHorizon, DirectionalFlag.

6. For 1.7 Strategic technology initiatives aligned to strategy
   - 400–600 words describing how technology programs align with strategy.
   - JSON array "TechInitiatives" with fields: Name, LinkedStrategicPillar, Scope, KeyEnablers, RiskReductionImpact, ValueThemes.

Overall target:
- ~2,400–3,200 words across section 1.

VERY IMPORTANT:
- ONLY modify the values under "1. Organization vision, mission, strategy, and key outcomes" in profile_json.
- Leave all other sections unchanged.
- Return the ENTIRE updated profile_json as valid JSON, with no extra commentary.
"""

WAVE2_PROMPT = """
Operate on the latest JSON object `profile_json` that I am about to provide.

For THIS call, expand ONLY section:
- "2. Revenue Reporting"
  - "2.1 Revenue by Business Segment"
  - "2.2 Revenue by Line of Business within each Segment"
  - "2.3 Revenue by Geography"
  - "2.4 Revenue Growth Trends"
  - "2.5 Key Revenue Drivers"
  - "2.6 Revenue Forecasts"

Context:
- Citi’s management model uses 5 core businesses: Services, Markets, Banking, U.S. Personal Banking (USPB), Wealth.
- You may mention legacy / exit businesses as “All Other / Corporate” where needed.
- Use realistic 5-year group revenue/net income numbers (rounded) and clearly mark more granular splits as directional estimates.

Requirements by subsection:

1. 2.1 Revenue by Business Segment
   - 500–800 words.
   - Explain relative scale and economics of each segment.
   - Add "RevenueBySegmentHistory": array of objects with Year, Segment, ApproxRevenueUSDbn, DirectionalFlag, Commentary.

2. 2.2 Revenue by Line of Business within each Segment
   - 500–800 words.
   - Decompose each segment into lines of business (TTS, Securities Services, FICC, Equities, Cards, etc.).
   - Add "RevenueByLOB": array of objects with Segment, LineOfBusiness, ApproxRevenueSharePct, DirectionalFlag, Commentary.

3. 2.3 Revenue by Geography
   - 400–700 words.
   - Regions: North America, EMEA, APAC, Latin America.
   - Add "RevenueByRegion": objects with Region, ApproxRevenueUSDbn, ApproxPctOfGroupRevenue, KeyBusinesses, DirectionalFlag, Commentary.

4. 2.4 Revenue Growth Trends
   - 500–800 words.
   - Analyze 5-year growth, exits, macro cycles.
   - Add "RevenueGrowthDrivers": objects with Period, PrimaryDrivers, Headwinds, NetEffectOnRevenue, DirectionalFlag.

5. 2.5 Key Revenue Drivers
   - 400–700 words.
   - Structural drivers: network, cards, volatility, wallet share, cross-sell, etc.
   - Add "KeyRevenueDrivers": objects with DriverName, Category, LinkedSegments, TimeHorizon, Commentary.

6. 2.6 Revenue Forecasts
   - 500–800 words.
   - Directional 3–5 year outlook (illustrative scenarios, not guidance).
   - Add "DirectionalRevenueOutlook": objects with Year, ApproxTotalRevenueUSDbn, DirectionalFlag ("ScenarioEstimate"), KeyAssumptions.
   - Explicitly state that forecasts are illustrative scenarios only.

Overall target:
- ~4,000–4,800 words across section 2.

VERY IMPORTANT:
- ONLY modify "2. Revenue Reporting" in profile_json.
- Leave all other sections as they were.
- Return the ENTIRE updated profile_json as valid JSON, with no extra commentary.
"""

WAVE3_PROMPT = """
Operate on the latest JSON object `profile_json` that I am about to provide.

For THIS call, expand ONLY the following sections:

- "3. Organizational structure"
  - "3.1 Top-level structure"
  - "3.2 Executive leadership and C-Suite"
  - "3.3 Group subsidiaries and regional organizations"
  - "3.4 Technology and operations organization"
  - "3.5 Operating capabilities"
  - "3.6 Operating principles"
  - "3.7 Leadership snapshots"

- "4. Workforce"
  - "4.1 Global scale and composition"
  - "4.2 Organizational distribution"
  - "4.3 Workforce composition by function"
  - "4.4 Capability development and learning"
  - "4.5 Culture and employee engagement"
  - "4.6 Workforce transformation"

- "14. Organizational Structure Charts and Diagrams"
  - "14.1 C-Suite and Direct Reports"
  - "14.2 CIO Office"
  - "14.3 Chief Procurement Office"
  - "14.4 Data Processing Organization"
  - "14.5 Centralized Mainframe Operations"
  - "14.6 Business Unit Embedded Departments and Functions"

Context:
- USPS operates with core service areas (Mail, Shipping & Packages, Retail operations) plus shared functions (Finance, Operations & Technology, Legal, HR, etc.).
- You may generalize some roles (e.g., "Head of FICC Trading", "Regional Head of APAC TTS") without naming specific individuals beyond widely known top executives.
- The goal is a consulting-grade view of the organizational architecture, leadership, workforce, and embedded IT/ops functions.

SECTION 3 REQUIREMENTS (Organizational structure):

1. 3.1 Top-level structure
   - 300–500 words.
   - Describe how Citi is structured at the highest level: group, major segments, corporate center, and critical control functions.
   - Include a concise JSON array "TopLevelEntities" with objects like:
     - "Name"
     - "Type" (Business / Function / LegalEntity / Region)
     - "RoleSummary"

2. 3.2 Executive leadership and C-Suite
   - If this section already contains some leader entries, keep them and expand.
   - For each key C-Suite role (e.g., CEO, CFO, CRO, CIO/CTO, Chief Auditor, General Counsel, CHRO, Chief Compliance Officer, Head of Services, Head of Markets, Head of Banking, Head of USPB, Head of Wealth):
     - Provide 220–320 word "Profile" fields in the same style as the example executive profile (Jane Fraser).
     - Focus on background, tenure, prior roles, education (if public), notable initiatives, KPIs, and governance responsibilities.
   - Maintain or create a "Leaders" array under 3.2 with one object per executive.

3. 3.3 Group subsidiaries and regional organizations
   - 250–400 words.
   - Explain Citi’s legal-entity and regional construct (U.S. parent, key bank entities, major regions such as North America, EMEA, APAC, Latin America, key booking centers).
   - Add a JSON array "RegionalStructures" with:
     - "Region"
     - "KeyLegalEntities"
     - "PrimaryBusinessFocus"
     - "GovernanceNotes"

4. 3.4 Technology and operations organization
   - 300–500 words.
   - Describe how Operations & Technology is organized: central tech group, operations hubs, alignment to businesses, shared services.
   - Add a JSON array "TechAndOpsOrg" with:
     - "Group"
     - "ReportingTo"
     - "Mandate"
     - "KeyInterfaces"

5. 3.5 Operating capabilities and 3.6 Operating principles
   - For 3.5: 250–400 words describing core capabilities (global network, transaction banking, markets execution, cards, data, risk management).
   - For 3.6: 250–400 words summarizing operating principles (client centricity, risk discipline, simplification, digitization, productivity).
   - Where appropriate, use short JSON arrays "CoreCapabilities" and "OperatingPrinciples" with bullet-style entries.

6. 3.7 Leadership snapshots
   - 250–400 words explaining what “leadership snapshots” are (e.g., short summaries of key leaders’ focus and mandate).
   - Add a JSON array "LeadershipSnapshots" with 6–10 objects such as:
     - "Role"
     - "Mandate"
     - "KeyFocusAreas"
     - "TimeHorizon"

SECTION 4 REQUIREMENTS (Workforce):

7. 4.1 Global scale and composition
   - 250–400 words describing total workforce size (directional), geographic spread, and mix (front office, operations, technology, control functions).
   - Add a JSON array "WorkforceScale" with:
     - "Dimension" (Headcount, Locations, Countries, Major Hubs, etc.)
     - "DirectionalValue"
     - "Commentary"

8. 4.2 Organizational distribution and 4.3 Workforce composition by function
   - 300–500 words combined.
   - Describe distribution by region and by major function (e.g., Institutional vs Consumer, Tech vs Ops vs Control functions).
   - Add a JSON array "WorkforceByFunction" with:
     - "Function"
     - "ApproxSharePct"
     - "DirectionalFlag"
     - "Commentary"

9. 4.4 Capability development and learning
   - 250–400 words.
   - Highlight leadership, risk, tech/engineering and analytics capability-building programs, academies, and mandatory training.
   - Optional JSON array "CapabilityPrograms".

10. 4.5 Culture and employee engagement
    - 250–400 words.
    - Summarize cultural themes (speak-up, risk ownership, client focus, inclusion) and engagement mechanisms.
    - Optional JSON array "CultureThemes".

11. 4.6 Workforce transformation
    - 250–400 words.
    - Explain how workforce is evolving (automation, relocation, upskilling, location strategy, sourcing mix).
    - Optional JSON array "WorkforceTransformationThemes".

SECTION 14 REQUIREMENTS (Org charts):

12. 14.1 C-Suite and Direct Reports
    - Build a nested JSON structure "CSuiteOrgChart" with objects:
      - "Role"
      - "ReportsTo" (e.g., "Board", "CEO")
      - "AreaOfAccountability"
      - "DirectReports" (array of subordinate roles)
    - Provide 150–250 words of narrative explaining the C-Suite hierarchy.

13. 14.2 CIO Office
    - 200–350 words on CIO organization and mandate.
    - JSON "CIOOrg" describing key roles:
      - "Global CIO"
      - "Segment CIOs" (Services, Markets, Banking, USPB, Wealth)
      - "Heads of Infrastructure, Cyber, Architecture, Data & Analytics, CTO/Engineering"

14. 14.3 Chief Procurement Office
    - 150–300 words.
    - JSON "CPOOrg" with roles such as:
      - "Chief Procurement Officer"
      - "Category Management"
      - "Third-Party Risk Management"
      - "Vendor Governance"

15. 14.4 Data Processing Organization and 14.5 Centralized Mainframe Operations
    - 250–400 words combined.
    - Describe how centralized processing and mainframe operations are structured (shared services, batch processing, resilience).
    - Add "DataProcessingOrg" and "MainframeOpsOrg" JSON arrays with key groups and responsibilities.

16. 14.6 Business Unit Embedded Departments and Functions
    - Build detailed org trees for:
      - Services (TTS, Securities Services)
      - Markets (FICC, Equities)
      - Banking (coverage sectors, product teams)
      - Wealth (regional hubs)
      - U.S. Personal Banking (Branded Cards, Retail Services, Retail Banking)
    - For each segment, include:
      - "SegmentHead"
      - "SecondLevel" (sub-businesses with leader titles and narratives)
      - "ThirdLevel" (sub-functions with key role titles and descriptions)
    - Aim for 800–1,200 words of narrative spread across these org charts.

Overall target:
- Approximately 4,000–4,800 words across sections 3, 4 and 14 combined (roughly 10–12 Word pages under the assumed formatting).

VERY IMPORTANT:
- ONLY modify sections "3. Organizational structure", "4. Workforce" and "14. Organizational Structure Charts and Diagrams" in profile_json.
- Leave all other top-level sections (1., 2., 5., etc.) exactly as they were after Wave 2.
- Return the ENTIRE updated profile_json as valid JSON, with no extra commentary.
"""
WAVE4_PROMPT = """
Operate on the latest JSON object `profile_json` that I am about to provide.

For THIS call, expand ONLY the following sections:

- "5. Strategic Technology Partners"
  - "Overview"
  - "5.1 Global Outsourcing and Infrastructure Partners"
  - "5.2 Systems Integration and Application Partners"
  - "5.3 Hyperscaler Partnerships"
  - "5.4 Consulting and Strategic Advisory"
  - "5.5 Fintech_and_Startup_Ecosystem"
  - "5.6 Vendor Management Model"

- "6. Location footprint"
  - "6.1 Global hubs"
  - "6.2 Regional distribution"
  - "6.3 Digital footprint"
  - "6.4 Resilience and business continuity"
  - "6.5 Sustainability of physical footprint"
  - "6.6 Implications"

CONTEXT AND GUARDRAILS:
- Describe Citi’s partner ecosystem and footprint at a generalized, consulting level. 
- Do NOT disclose confidential commercial terms; keep partner mentions at category level (e.g., hyperscaler, global SI, specialist fintech) and widely-known types of relationships.
- For location footprint, focus on archetypal hubs (e.g., New York, London, Hong Kong, Singapore, major ops and tech hubs) without exposing any sensitive site-level details.

SECTION 5 REQUIREMENTS (Strategic Technology Partners):

1. 5.1 Global Outsourcing and Infrastructure Partners
   - 250–400 words.
   - Describe categories such as infrastructure outsourcing, managed services, network providers, data center partners, and large shared-services BPO partners.
   - Add a JSON array "GlobalOutsourcingPartners" where each object has:
     - "Category" (e.g., "Infrastructure", "End-User Services", "Operations BPO")
     - "TypicalPartnerProfile" (short description)
     - "PrimaryUseCases"
     - "RiskConsiderations"

2. 5.2 Systems Integration and Application Partners
   - 250–400 words.
   - Explain the role of global SIs and specialist application integrators in large programs (core banking upgrades, payments modernization, regulatory remediation, etc.).
   - Add "SystemsIntegrationPartners" array with:
     - "PartnerType"
     - "TypicalEngagements"
     - "KeyStrengths"
     - "GovernanceModel"

3. 5.3 Hyperscaler Partnerships
   - 250–400 words.
   - Describe Citi’s typical patterns with hyperscalers: cloud hosting, data and analytics platforms, AI services, and resilience considerations.
   - Add "HyperscalerPartnerships" array with:
     - "ServiceDomain" (IaaS, PaaS, Data & Analytics, AI/ML, Security)
     - "UsagePatterns"
     - "KeyControlsAndGuardrails"
     - "ValueDrivers" (e.g., agility, elasticity, innovation).

4. 5.4 Consulting and Strategic Advisory
   - 200–350 words.
   - Outline how Citi typically uses consulting firms (strategy, operating model design, risk & control transformation, tech and data roadmap).
   - Optionally add "ConsultingPartners" array with objects such as:
     - "EngagementType"
     - "TypicalScope"
     - "PrimaryStakeholders"

5. 5.5 Fintech_and_Startup_Ecosystem
   - 250–400 words.
   - Describe Citi’s engagement patterns with fintechs and startups (ecosystem plays, partnerships, investments, white-labeling, API-based integrations).
   - Add "FintechEcosystem" array with:
     - "Theme" (e.g., Payments, Lending, RegTech, WealthTech)
     - "EngagementModel" (Partnership, Investment, Co-creation, Vendor)
     - "RiskFocus" (e.g., third-party risk, data sharing, operational resilience)

6. 5.6 Vendor Management Model
   - 300–500 words.
   - Explain the vendor management and third-party risk model:
     - Segmentation/tiering (critical vs non-critical),
     - TPRM lifecycle,
     - Governance forums,
     - SBOM expectations for critical software.
   - Add "VendorManagementModel" object with fields:
     - "TieringApproach"
     - "LifecycleStages" (list)
     - "KeyStakeholders"
     - "CorePolicies" (list)

SECTION 6 REQUIREMENTS (Location footprint):

7. 6.1 Global hubs
   - 250–400 words.
   - Describe main global hubs (e.g., HQ in New York, major financial centers, regional headquarters) and their archetypal roles (front office, risk, tech, operations).
   - Add "GlobalHubs" array:
     - "HubName"
     - "Region"
     - "PrimaryFunctions"
     - "DirectionalRole" (e.g., "Global HQ", "Regional HQ", "Operations & Tech Hub")

8. 6.2 Regional distribution
   - 200–350 words.
   - Summarize how headcount and activity are distributed across NA / EMEA / APAC / LatAm.
   - Add "RegionalDistribution" array:
     - "Region"
     - "ApproxShareOfWorkforcePct"
     - "KeyActivities"
     - "DirectionalFlag"

9. 6.3 Digital footprint
   - 200–350 words.
   - Describe Citi’s logical/digital footprint: data centers vs cloud regions, key digital channels, and digital reach (online, mobile, APIs).
   - Add "DigitalFootprint" array with:
     - "Domain" (e.g., "Mobile Banking", "Institutional Portals", "APIs")
     - "KeyPlatforms"
     - "Coverage" (e.g., "Global", "Regional")
     - "ResilienceNotes"

10. 6.4 Resilience and business continuity
    - 250–400 words.
    - Explain how critical services are distributed and backed up (active-active sites, DR sites, failover strategies, BCP concepts at a high level).
    - Add "ResilienceMeasures" array:
      - "Measure"
      - "Scope"
      - "TypicalTrigger"
      - "Ownership"

11. 6.5 Sustainability of physical footprint
    - 200–350 words.
    - Describe sustainability initiatives for offices, data centers, and travel: energy efficiency, green buildings, footprint optimization.
    - Add "SustainabilityInitiatives" array:
      - "InitiativeName"
      - "Scope"
      - "SustainabilityDimension" (e.g., Energy, Emissions, Waste)
      - "DirectionalImpact"

12. 6.6 Implications
    - 250–400 words synthesizing what the partner landscape and footprint imply for:
      - Risk and resilience
      - Cost and productivity
      - Innovation speed
      - Regulatory and sustainability commitments.
    - Add "FootprintImplications" array:
      - "Theme"
      - "Implication"
      - "AssociatedRisks"
      - "Opportunities"

Overall target:
- Approximately 2,400–3,200 words across sections 5 and 6 combined (roughly 6–8 Word pages under the assumed formatting).

VERY IMPORTANT:
- ONLY modify sections "5. Strategic Technology Partners" and "6. Location footprint" in profile_json.
- Leave all other top-level sections exactly as they were after Wave 3.
- Return the ENTIRE updated profile_json as valid JSON, with no extra commentary.
"""

# Split Wave 4 into two parts to avoid token limits
WAVE4A_PROMPT = """
Operate on the latest JSON object `profile_json` that I am about to provide.

For THIS call, expand ONLY the following section:

- "5. Strategic Technology Partners"
  - "Overview"
  - "5.1 Global Outsourcing and Infrastructure Partners"
  - "5.2 Systems Integration and Application Partners"
  - "5.3 Hyperscaler Partnerships"
  - "5.4 Consulting and Strategic Advisory"
  - "5.5 Fintech_and_Startup_Ecosystem"
  - "5.6 Vendor Management Model"

CONTEXT AND GUARDRAILS:
- Describe Citi's partner ecosystem at a generalized, consulting level. 
- Do NOT disclose confidential commercial terms; keep partner mentions at category level (e.g., hyperscaler, global SI, specialist fintech) and widely-known types of relationships.

SECTION 5 REQUIREMENTS (Strategic Technology Partners):

Start with a 200-300 word Overview paragraph that introduces Citi's strategic technology partner ecosystem.

1. 5.1 Global Outsourcing and Infrastructure Partners
   - 250–400 words.
   - Describe categories such as infrastructure outsourcing, managed services, network providers, data center partners, and large shared-services BPO partners.
   - Add a JSON array "GlobalOutsourcingPartners" where each object has:
     - "Category" (e.g., "Infrastructure", "End-User Services", "Operations BPO")
     - "TypicalPartnerProfile" (short description)
     - "PrimaryUseCases"
     - "RiskConsiderations"

2. 5.2 Systems Integration and Application Partners
   - 250–400 words.
   - Explain the role of global SIs and specialist application integrators in large programs (core banking upgrades, payments modernization, regulatory remediation, etc.).
   - Add "SystemsIntegrationPartners" array with:
     - "PartnerType"
     - "TypicalEngagements"
     - "KeyStrengths"
     - "GovernanceModel"

3. 5.3 Hyperscaler Partnerships
   - 250–400 words.
   - Describe Citi's typical patterns with hyperscalers: cloud hosting, data and analytics platforms, AI services, and resilience considerations.
   - Add "HyperscalerPartnerships" array with:
     - "ServiceDomain" (IaaS, PaaS, Data & Analytics, AI/ML, Security)
     - "UsagePatterns"
     - "KeyControlsAndGuardrails"
     - "ValueDrivers" (e.g., agility, elasticity, innovation).

4. 5.4 Consulting and Strategic Advisory
   - 200–350 words.
   - Outline how Citi typically uses consulting firms (strategy, operating model design, risk & control transformation, tech and data roadmap).
   - Optionally add "ConsultingPartners" array with objects such as:
     - "EngagementType"
     - "TypicalScope"
     - "PrimaryStakeholders"

5. 5.5 Fintech_and_Startup_Ecosystem
   - 250–400 words.
   - Describe Citi's engagement patterns with fintechs and startups (ecosystem plays, partnerships, investments, white-labeling, API-based integrations).
   - Add "FintechEcosystem" array with:
     - "Theme" (e.g., Payments, Lending, RegTech, WealthTech)
     - "EngagementModel" (Partnership, Investment, Co-creation, Vendor)
     - "RiskFocus" (e.g., third-party risk, data sharing, operational resilience)

6. 5.6 Vendor Management Model
   - 300–500 words.
   - Explain the vendor management and third-party risk model:
     - Segmentation/tiering (critical vs non-critical),
     - TPRM lifecycle,
     - Governance forums,
     - SBOM expectations for critical software.
   - Add "VendorManagementModel" object with fields:
     - "TieringApproach"
     - "LifecycleStages" (list)
     - "KeyStakeholders"
     - "CorePolicies" (list)

Overall target for Section 5:
- Approximately 1,500–2,400 words (roughly 4–6 Word pages under the assumed formatting).

VERY IMPORTANT:
- ONLY modify section "5. Strategic Technology Partners" in profile_json.
- Leave all other top-level sections exactly as they were.
- Return the ENTIRE updated profile_json as valid JSON, with no extra commentary.
"""

WAVE4B_PROMPT = """
Operate on the latest JSON object `profile_json` that I am about to provide.

For THIS call, expand ONLY the following section:

- "6. Location footprint"
  - "6.1 Global hubs"
  - "6.2 Regional distribution"
  - "6.3 Digital footprint"
  - "6.4 Resilience and business continuity"
  - "6.5 Sustainability of physical footprint"
  - "6.6 Implications"

CONTEXT AND GUARDRAILS:
- For location footprint, focus on archetypal hubs (e.g., New York, London, Hong Kong, Singapore, major ops and tech hubs) without exposing any sensitive site-level details.
- Use directional analysis and publicly available information.

SECTION 6 REQUIREMENTS (Location footprint):

1. 6.1 Global hubs
   - 250–400 words.
   - Describe main global hubs (e.g., HQ in New York, major financial centers, regional headquarters) and their archetypal roles (front office, risk, tech, operations).
   - Add "GlobalHubs" array:
     - "HubName"
     - "Region"
     - "PrimaryFunctions"
     - "DirectionalRole" (e.g., "Global HQ", "Regional HQ", "Operations & Tech Hub")

2. 6.2 Regional distribution
   - 200–350 words.
   - Summarize how headcount and activity are distributed across NA / EMEA / APAC / LatAm.
   - Add "RegionalDistribution" array:
     - "Region"
     - "ApproxShareOfWorkforcePct"
     - "KeyActivities"
     - "DirectionalFlag"

3. 6.3 Digital footprint
   - 200–350 words.
   - Describe Citi's logical/digital footprint: data centers vs cloud regions, key digital channels, and digital reach (online, mobile, APIs).
   - Add "DigitalFootprint" array with:
     - "Domain" (e.g., "Mobile Banking", "Institutional Portals", "APIs")
     - "KeyPlatforms"
     - "Coverage" (e.g., "Global", "Regional")
     - "ResilienceNotes"

4. 6.4 Resilience and business continuity
   - 250–400 words.
   - Explain how critical services are distributed and backed up (active-active sites, DR sites, failover strategies, BCP concepts at a high level).
   - Add "ResilienceMeasures" array:
     - "Measure"
     - "Scope"
     - "TypicalTrigger"
     - "Ownership"

5. 6.5 Sustainability of physical footprint
   - 200–350 words.
   - Describe sustainability initiatives for offices, data centers, and travel: energy efficiency, green buildings, footprint optimization.
   - Add "SustainabilityInitiatives" array:
     - "InitiativeName"
     - "Scope"
     - "SustainabilityDimension" (e.g., Energy, Emissions, Waste)
     - "DirectionalImpact"

6. 6.6 Implications
   - 250–400 words synthesizing what the partner landscape and footprint imply for:
     - Risk and resilience
     - Cost and productivity
     - Innovation speed
     - Regulatory and sustainability commitments.
   - Add "FootprintImplications" array:
     - "Theme"
     - "Implication"
     - "AssociatedRisks"
     - "Opportunities"

Overall target for Section 6:
- Approximately 1,350–2,100 words (roughly 3–5 Word pages under the assumed formatting).

VERY IMPORTANT:
- ONLY modify section "6. Location footprint" in profile_json.
- Leave all other top-level sections exactly as they were.
- Return the ENTIRE updated profile_json as valid JSON, with no extra commentary.
"""

WAVE5_PROMPT = """
Operate on the latest JSON object `profile_json` that I am about to provide.

For THIS call, expand ONLY the following sections:

- "7. IT Infrastructure"
  - "Overview"
  - "7.1 Infrastructure Strategy"
  - "7.2 Network and Connectivity"
  - "7.3 Compute, Storage, and Cloud"
  - "7.4 Security, Resilience, and Performance"
  - "7.5 Infrastructure Operations and Service Management"

- "8. IT Applications"
  - "Overview"
  - "8.1 Core banking and ledger systems"
  - "8.2 Digital channels and customer platforms"
  - "8.3 Transaction processing platforms (TTS, Markets, Securities Services)"
  - "8.4 Risk, finance, and compliance systems"
  - "8.5 Wealth and domain-specific applications"
  - "8.6 Analytics and AI-driven platforms"
  - "8.7 Application portfolio modernization"

- "9. Data Management"
  - "9.1 Data governance"
  - "9.2 Data architecture and platforms"
  - "9.3 Data quality and master data management"
  - "9.4 Data privacy and security"
  - "9.5 Analytics and BI"
  - "9.6 Data sharing and external interfaces"

CONTEXT:
- Citi is a global, systemically important bank with a large legacy footprint (mainframes, distributed, private cloud) and increasing public-cloud adoption.
- The goal is to produce a consulting-grade view of infrastructure, application landscape, and data management, framed in terms of current vs target state, platforms, and control/operating models.
- Keep all descriptions generic but realistic for a large global bank; do not disclose any proprietary configuration details.

SECTION 7 REQUIREMENTS (IT Infrastructure):

1. Overview and 7.1 Infrastructure Strategy
   - 400–600 words total.
   - Explain the overall infrastructure strategy: balancing legacy stability vs modernization, regulatory constraints, resilience requirements, and cost efficiency.
   - Highlight the split between:
     - Centralized infrastructure (data centers, mainframe),
     - Distributed/virtualized/on-prem environments,
     - Public cloud.
   - Add a JSON array "InfrastructureStrategicThemes" with objects:
     - "Theme"
     - "Description"
     - "TimeHorizon" (Near / Medium / Long)
     - "PrimaryDrivers" (Cost / Risk / Agility / Regulatory).

2. 7.2 Network and Connectivity
   - 300–500 words.
   - Describe external connectivity (clients, partners, market infrastructures), internal networks across regions, and zero-trust / segmentation concepts.
   - Add "NetworkCapabilities" array with:
     - "Domain" (e.g., Branch WAN, Data Center Fabric, Internet Edge, Cloud Connectivity)
     - "KeyCharacteristics"
     - "ResilienceFeatures"
     - "SecurityControls".

3. 7.3 Compute, Storage, and Cloud
   - 400–600 words.
   - Outline compute tiers (mainframe, high-performance compute, general-purpose servers, containers), storage tiers, and cloud models (private/public/hybrid).
   - Add "ComputeAndStorageLandscape" array:
     - "Tier"
     - "PrimaryUseCases"
     - "RegulatoryConsiderations"
     - "ModernizationStatus" (Legacy / Evolving / Target).
   - Add "CloudUsagePatterns" array:
     - "Pattern" (e.g., Data & Analytics, Microservices, Dev/Test)
     - "TypicalWorkloads"
     - "KeyBenefits"
     - "KeyRisks".

4. 7.4 Security, Resilience, and Performance
   - 300–500 words.
   - Focus on infra-level security (hardening, patching, vulnerability management), resilience (active-active, DR), and performance management.
   - Add "InfraResilienceControls" array:
     - "Control"
     - "Objective"
     - "Coverage" (Global / Regional / Critical Services)
     - "MonitoringMechanism".

5. 7.5 Infrastructure Operations and Service Management
   - 300–500 words.
   - Describe NOC/SOC patterns, SRE and ITIL/ITSM processes (incident, problem, change, capacity).
   - Add "InfraOpsModel" object with:
     - "OperatingModel" (e.g., central + regional ops)
     - "KeyProcesses" (list)
     - "ToolingAndPlatforms" (high-level)
     - "Metrics" (e.g., MTTR, availability SLOs).

SECTION 8 REQUIREMENTS (IT Applications):

6. Overview
   - 200–350 words.
   - Explain how the application landscape is organized (by domain, segment, and shared platforms) and how modernization is being approached (rationalization, decoupling, APIs, etc.).

7. 8.1 Core banking and ledger systems
   - 300–500 words.
   - Describe core ledgers and processing platforms for institutional and consumer businesses.
   - Add "CoreSystems" array:
     - "Domain" (e.g., Retail Core, Cards Core, Institutional Ledger)
     - "Role"
     - "TechnologyPosture" (Legacy / Modernizing / Target)
     - "KeyConstraints" (batch windows, product flexibility, data latency).

8. 8.2 Digital channels and customer platforms
   - 300–500 words.
   - Cover mobile/web, institutional portals, APIs, and omni-channel capabilities.
   - Add "DigitalPlatforms" array:
     - "ChannelType" (Retail / Wealth / Institutional / Partner)
     - "KeyCapabilities"
     - "IntegrationModel" (APIs / ESB / Direct)
     - "ExperienceThemes".

9. 8.3 Transaction processing platforms (TTS, Markets, Securities Services)
   - 300–500 words.
   - Describe payments, trade, FX, trading, and custody systems at a conceptual level.
   - Add "TransactionPlatforms" array:
     - "BusinessArea"
     - "PlatformRole"
     - "VolumeCharacteristics"
     - "ResilienceRequirements".

10. 8.4 Risk, finance, and compliance systems
    - 300–500 words.
    - Outline credit/market/liquidity risk systems, finance/GL, regulatory reporting, AML, sanctions, surveillance, etc.
    - Add "RiskFinanceComplianceSystems" array:
      - "Category"
      - "PrimaryFunctions"
      - "DataDependencies"
      - "ModernizationChallenges".

11. 8.5 Wealth and domain-specific applications
    - 250–400 words.
    - Describe wealth platforms (portfolio management, advisory, lending) and other domain-specific tools.
    - Add "WealthApplications" array:
      - "Function"
      - "UserGroups"
      - "IntegrationPoints"
      - "StrategicImportance".

12. 8.6 Analytics and AI-driven platforms
    - 300–500 words.
    - Explain the analytics stack (EDWs, data lakes, ML platforms, BI tools) and AI use cases (credit, fraud, personalization, ops optimization).
    - Add "AnalyticsPlatforms" array:
      - "Layer" (Ingestion, Storage, Processing, Visualization, ML Ops)
      - "KeyTechnologies" (generic)
      - "PrimaryUseCases".

13. 8.7 Application portfolio modernization
    - 400–600 words.
    - Provide a modernization narrative: rationalization, decoupling front/back, API exposure, cloud migration, mainframe offload, and decommissioning waves.
    - Add "AppModernizationWaves" array:
      - "WaveName"
      - "Scope"
      - "TimeHorizon"
      - "KeyBenefits"
      - "RisksAndDependencies".

SECTION 9 REQUIREMENTS (Data Management):

14. 9.1 Data governance
    - 300–500 words.
    - Describe data governance model: data owners, stewards, councils, policies, and alignment with regulatory expectations.
    - Add "DataGovernanceModel" object:
      - "OperatingModel"
      - "KeyRoles" (list)
      - "GovernanceForums" (list)
      - "PolicyThemes" (list).

15. 9.2 Data architecture and platforms
    - 300–500 words.
    - Explain logical data architecture: warehouses, lakes, marts, real-time vs batch, and domain-driven design concepts.
    - Add "DataPlatforms" array:
      - "PlatformType" (Warehouse, Lake, Streaming, MDM)
      - "PrimaryUseCases"
      - "IntegrationApproach"
      - "ModernizationStatus".

16. 9.3 Data quality and master data management
    - 300–500 words.
    - Outline DQ framework, issue management, controls, and MDM for critical domains (customers, accounts, products, legal entities).
    - Add "DataQualityFramework" object:
      - "DQDimensions" (list, e.g., completeness, accuracy, timeliness)
      - "ControlTypes" (preventive/detective)
      - "IssueLifecycleSteps" (list)
      - "ToolingOverview".

17. 9.4 Data privacy and security
    - 250–400 words.
    - Describe privacy principles (purpose limitation, minimization, retention) and data security controls (classification, encryption, access control).
    - Add "DataPrivacySecurityControls" array:
      - "Control"
      - "Objective"
      - "Scope"
      - "RegulatoryDrivers".

18. 9.5 Analytics and BI
    - 250–400 words.
    - Explain BI consumption model: enterprise dashboards, self-service, governed data sets, KPIs.
    - Add "BIConsumptionPatterns" array:
      - "Pattern"
      - "PrimaryUsers"
      - "GovernanceApproach"
      - "TypicalTools" (generic).

19. 9.6 Data sharing and external interfaces
    - 250–400 words.
    - Discuss data sharing with regulators, clients, partners, and internal exposure via APIs/feeds; mention controls around data localization and residency.
    - Add "DataSharingPatterns" array:
      - "CounterpartyType" (Regulator, Client, Partner, Internal)
      - "Mechanism" (API, Secure File Transfer, Portal)
      - "KeyControls"
      - "Risks".

Overall target:
- Approximately 6,000–7,200 words across sections 7, 8 and 9 combined (roughly 15–18 Word pages under the assumed formatting).

VERY IMPORTANT:
- ONLY modify sections "7. IT Infrastructure", "8. IT Applications", and "9. Data Management" in profile_json.
- Leave all other top-level sections exactly as they were after Wave 4.
- Return the ENTIRE updated profile_json as valid JSON, with no extra commentary.
"""

WAVE6_PROMPT = """
Operate on the latest JSON object `profile_json` that I am about to provide.

For THIS call, expand ONLY the following sections:

- "10. IT Organization"
  - "Overview"
  - "10.1 Global IT Leadership"
  - "10.2 Organizational Model"
  - "10.3 Security and Compliance Organization"
  - "10.4 Project Delivery and Governance"
  - "10.5 Talent and Capability Development"
  - "10.6 Centralized IT vs. Decentralized IT"
  - "10.7 Centralized IT and Shared Services Departments and Functions"
  - "10.8 Business Unit Aligned IT Departments and Functions"

- "11. IT Organization Innovation Themes and Strategic Initiatives"
  - "11.1 Data and AI"
  - "11.2 Modernization"
  - "11.3 Observability"
  - "11.4 Security, Risk and Compliance"
  - "11.5 Cloud Computing"
  - "11.6 Agile and DevOps"
  - "11.7 Automation and Orchestration"
  - "11.8 Mainframe Evolution"

CONTEXT:
- Think of a large, global universal bank with a Group CIO / CTO leading a federated technology organization: central platforms plus business-aligned CIOs.
- This wave focuses on: IT org structure, leadership, delivery governance, talent, and the portfolio of innovation themes.

SECTION 10 REQUIREMENTS (IT Organization):

1. Overview
   - 200–350 words summarizing how Citi’s IT organization is positioned: central group functions, business-aligned CIOs, global delivery and ops hubs.

2. 10.1 Global IT Leadership
   - 250–400 words.
   - Describe key leadership roles (e.g., Group CIO/CTO, Segment CIOs, Heads of Infrastructure, Cyber, Data, Architecture, Enterprise PMO).
   - Add "GlobalITLeadership" array:
     - "Role"
     - "ReportingLine"
     - "PrimaryAccountabilities"
     - "KeyCommittees".

3. 10.2 Organizational Model
   - 300–500 words.
   - Explain the operating model (central platform teams, product-aligned engineering teams, regional delivery, shared services).
   - Add "ITOrgModel" object:
     - "DesignPrinciples" (list)
     - "MajorDomains" (list)
     - "AlignmentToBusiness" (narrative).

4. 10.3 Security and Compliance Organization
   - 250–400 words.
   - Describe where CISO / cyber sits, how security engineering and operations are organized, how they interact with compliance and risk.
   - Add "SecurityOrg" object:
     - "CISOReportingLine"
     - "KeyTeams" (list)
     - "CoreResponsibilities" (list)
     - "InterfacesWith" (Risk, Compliance, Business, Regulators).

5. 10.4 Project Delivery and Governance
   - 300–500 words.
   - Explain portfolio / project governance, investment committees, PMO, and risk/architecture gates.
   - Add "DeliveryGovernanceModel" object:
     - "FundingApproach" (e.g., project vs product; run vs change)
     - "GovernanceForums" (list)
     - "StageGates" (list)
     - "KeyMetrics" (on-time, on-budget, value realization).

6. 10.5 Talent and Capability Development
   - 250–400 words.
   - Cover engineering talent strategy, skill frameworks, learning programs, and career paths.
   - Add "ITCapabilityPrograms" array:
     - "ProgramName"
     - "TargetAudience"
     - "CapabilitiesBuilt"
     - "MeasurementApproach".

7. 10.6 Centralized IT vs. Decentralized IT
   - 250–400 words.
   - Explain the trade-offs between central and BU-aligned teams; which services are centralized vs decentralized.
   - Add "CentralVsDecentralized" array:
     - "Domain"
     - "CentralizedOrDecentralized"
     - "Rationale"
     - "RisksAndMitigations".

8. 10.7 Centralized IT and Shared Services Departments and Functions
   - 250–400 words.
   - Describe shared functions: infrastructure, data & analytics platforms, tooling, developer experience, enterprise architecture, testing services.
   - Add "SharedITFunctions" array:
     - "Function"
     - "Mandate"
     - "KeyConsumers"
     - "ValueProposition".

9. 10.8 Business Unit Aligned IT Departments and Functions
   - 250–400 words.
   - Summarize how IT is aligned to Services, Markets, Banking, USPB, Wealth.
   - Add "BusinessAlignedIT" array:
     - "Segment"
     - "ITLeadershipRole"
     - "ScopeOfResponsibility"
     - "KeyInterfaces".

SECTION 11 REQUIREMENTS (Innovation Themes & Strategic Initiatives):

10. 11.1 Data and AI
    - 300–500 words.
    - Describe the data & AI innovation agenda: data platforms, AI use cases, model governance, and adoption at scale.
    - Add "DataAndAIInitiatives" array:
      - "InitiativeName"
      - "UseCaseCategory" (Risk, Fraud, Personalization, Ops, etc.)
      - "Maturity" (Pilot / Scaling / Industrialized)
      - "KeyRisks".

11. 11.2 Modernization
    - 300–500 words.
    - Provide narrative about core modernization, app rationalization, decommissioning, and target architecture.
    - Add "ModernizationPrograms" array:
      - "ProgramName"
      - "Scope"
      - "TimeHorizon"
      - "KeyDependencies"
      - "ValueLevers".

12. 11.3 Observability
    - 250–400 words.
    - Explain observability strategy (logging, metrics, tracing, user-experience monitoring).
    - Add "ObservabilityPractices" array:
      - "Practice"
      - "ToolsAndPlatforms" (generic)
      - "PrimaryConsumers"
      - "OutcomeMetrics".

13. 11.4 Security, Risk and Compliance
    - 300–500 words.
    - Build on prior risk/governance content to describe security and compliance innovation themes (zero trust, enhanced monitoring, reg tech).
    - Add "SecurityRiskComplianceThemes" array:
      - "Theme"
      - "Objectives"
      - "KeyEnablers"
      - "RegulatoryDrivers".

14. 11.5 Cloud Computing
    - 250–400 words.
    - Describe cloud strategy and guardrails: multi-cloud, sovereignty, landing zones, patterns, and accelerators.
    - Add "CloudStrategicInitiatives" array:
      - "InitiativeName"
      - "CloudPattern" (Rehost / Refactor / SaaS / Data & AI)
      - "TargetUseCases"
      - "RiskControls".

15. 11.6 Agile and DevOps
    - 250–400 words.
    - Explain Agile adoption model (product teams, backlogs, ceremonies) and DevOps practices (CI/CD, trunk-based, automated testing).
    - Add "AgileDevOpsPractices" array:
      - "Practice"
      - "Scope"
      - "KeyBenefits"
      - "Challenges".

16. 11.7 Automation and Orchestration
    - 250–400 words.
    - Describe automation in infra, apps, and ops: Infrastructure-as-Code, pipelines, RPA where relevant.
    - Add "AutomationThemes" array:
      - "Domain"
      - "AutomationType" (IaC, Pipelines, RPA, Workflow)
      - "UseCases"
      - "ImpactType" (Cost, Risk, Speed, Experience).

17. 11.8 Mainframe Evolution
    - 300–500 words.
    - Outline how mainframe is treated: optimization, offloading workloads, API enablement, or progressive replacement.
    - Add "MainframeEvolutionPlan" object:
      - "StrategicOptions" (list)
      - "PriorityDomains"
      - "Risks"
      - "DependenciesOnOtherPrograms".

Overall target:
- Approximately 4,000–4,800 words across sections 10 and 11 combined (roughly 10–12 Word pages under the assumed formatting).

VERY IMPORTANT:
- ONLY modify sections "10. IT Organization" and "11. IT Organization Innovation Themes and Strategic Initiatives" in profile_json.
- Leave all other top-level sections exactly as they were after Wave 5.
- Return the ENTIRE updated profile_json as valid JSON, with no extra commentary.
"""

WAVE6_PROMPT = """
Operate on the latest JSON object `profile_json` that I am about to provide.

For THIS call, expand ONLY the following sections:

- "10. IT Organization"
  - "Overview"
  - "10.1 Global IT Leadership"
  - "10.2 Organizational Model"
  - "10.3 Security and Compliance Organization"
  - "10.4 Project Delivery and Governance"
  - "10.5 Talent and Capability Development"
  - "10.6 Centralized IT vs. Decentralized IT"
  - "10.7 Centralized IT and Shared Services Departments and Functions"
  - "10.8 Business Unit Aligned IT Departments and Functions"

- "11. IT Organization Innovation Themes and Strategic Initiatives"
  - "11.1 Data and AI"
  - "11.2 Modernization"
  - "11.3 Observability"
  - "11.4 Security, Risk and Compliance"
  - "11.5 Cloud Computing"
  - "11.6 Agile and DevOps"
  - "11.7 Automation and Orchestration"
  - "11.8 Mainframe Evolution"

CONTEXT:
- Think of a large, global universal bank with a Group CIO / CTO leading a federated technology organization: central platforms plus business-aligned CIOs.
- This wave focuses on: IT org structure, leadership, delivery governance, talent, and the portfolio of innovation themes.

SECTION 10 REQUIREMENTS (IT Organization):

1. Overview
   - 200–350 words summarizing how Citi’s IT organization is positioned: central group functions, business-aligned CIOs, global delivery and ops hubs.

2. 10.1 Global IT Leadership
   - 250–400 words.
   - Describe key leadership roles (e.g., Group CIO/CTO, Segment CIOs, Heads of Infrastructure, Cyber, Data, Architecture, Enterprise PMO).
   - Add "GlobalITLeadership" array:
     - "Role"
     - "ReportingLine"
     - "PrimaryAccountabilities"
     - "KeyCommittees".

3. 10.2 Organizational Model
   - 300–500 words.
   - Explain the operating model (central platform teams, product-aligned engineering teams, regional delivery, shared services).
   - Add "ITOrgModel" object:
     - "DesignPrinciples" (list)
     - "MajorDomains" (list)
     - "AlignmentToBusiness" (narrative).

4. 10.3 Security and Compliance Organization
   - 250–400 words.
   - Describe where CISO / cyber sits, how security engineering and operations are organized, how they interact with compliance and risk.
   - Add "SecurityOrg" object:
     - "CISOReportingLine"
     - "KeyTeams" (list)
     - "CoreResponsibilities" (list)
     - "InterfacesWith" (Risk, Compliance, Business, Regulators).

5. 10.4 Project Delivery and Governance
   - 300–500 words.
   - Explain portfolio / project governance, investment committees, PMO, and risk/architecture gates.
   - Add "DeliveryGovernanceModel" object:
     - "FundingApproach" (e.g., project vs product; run vs change)
     - "GovernanceForums" (list)
     - "StageGates" (list)
     - "KeyMetrics" (on-time, on-budget, value realization).

6. 10.5 Talent and Capability Development
   - 250–400 words.
   - Cover engineering talent strategy, skill frameworks, learning programs, and career paths.
   - Add "ITCapabilityPrograms" array:
     - "ProgramName"
     - "TargetAudience"
     - "CapabilitiesBuilt"
     - "MeasurementApproach".

7. 10.6 Centralized IT vs. Decentralized IT
   - 250–400 words.
   - Explain the trade-offs between central and BU-aligned teams; which services are centralized vs decentralized.
   - Add "CentralVsDecentralized" array:
     - "Domain"
     - "CentralizedOrDecentralized"
     - "Rationale"
     - "RisksAndMitigations".

8. 10.7 Centralized IT and Shared Services Departments and Functions
   - 250–400 words.
   - Describe shared functions: infrastructure, data & analytics platforms, tooling, developer experience, enterprise architecture, testing services.
   - Add "SharedITFunctions" array:
     - "Function"
     - "Mandate"
     - "KeyConsumers"
     - "ValueProposition".

9. 10.8 Business Unit Aligned IT Departments and Functions
   - 250–400 words.
   - Summarize how IT is aligned to Services, Markets, Banking, USPB, Wealth.
   - Add "BusinessAlignedIT" array:
     - "Segment"
     - "ITLeadershipRole"
     - "ScopeOfResponsibility"
     - "KeyInterfaces".

SECTION 11 REQUIREMENTS (Innovation Themes & Strategic Initiatives):

10. 11.1 Data and AI
    - 300–500 words.
    - Describe the data & AI innovation agenda: data platforms, AI use cases, model governance, and adoption at scale.
    - Add "DataAndAIInitiatives" array:
      - "InitiativeName"
      - "UseCaseCategory" (Risk, Fraud, Personalization, Ops, etc.)
      - "Maturity" (Pilot / Scaling / Industrialized)
      - "KeyRisks".

11. 11.2 Modernization
    - 300–500 words.
    - Provide narrative about core modernization, app rationalization, decommissioning, and target architecture.
    - Add "ModernizationPrograms" array:
      - "ProgramName"
      - "Scope"
      - "TimeHorizon"
      - "KeyDependencies"
      - "ValueLevers".

12. 11.3 Observability
    - 250–400 words.
    - Explain observability strategy (logging, metrics, tracing, user-experience monitoring).
    - Add "ObservabilityPractices" array:
      - "Practice"
      - "ToolsAndPlatforms" (generic)
      - "PrimaryConsumers"
      - "OutcomeMetrics".

13. 11.4 Security, Risk and Compliance
    - 300–500 words.
    - Build on prior risk/governance content to describe security and compliance innovation themes (zero trust, enhanced monitoring, reg tech).
    - Add "SecurityRiskComplianceThemes" array:
      - "Theme"
      - "Objectives"
      - "KeyEnablers"
      - "RegulatoryDrivers".

14. 11.5 Cloud Computing
    - 250–400 words.
    - Describe cloud strategy and guardrails: multi-cloud, sovereignty, landing zones, patterns, and accelerators.
    - Add "CloudStrategicInitiatives" array:
      - "InitiativeName"
      - "CloudPattern" (Rehost / Refactor / SaaS / Data & AI)
      - "TargetUseCases"
      - "RiskControls".

15. 11.6 Agile and DevOps
    - 250–400 words.
    - Explain Agile adoption model (product teams, backlogs, ceremonies) and DevOps practices (CI/CD, trunk-based, automated testing).
    - Add "AgileDevOpsPractices" array:
      - "Practice"
      - "Scope"
      - "KeyBenefits"
      - "Challenges".

16. 11.7 Automation and Orchestration
    - 250–400 words.
    - Describe automation in infra, apps, and ops: Infrastructure-as-Code, pipelines, RPA where relevant.
    - Add "AutomationThemes" array:
      - "Domain"
      - "AutomationType" (IaC, Pipelines, RPA, Workflow)
      - "UseCases"
      - "ImpactType" (Cost, Risk, Speed, Experience).

17. 11.8 Mainframe Evolution
    - 300–500 words.
    - Outline how mainframe is treated: optimization, offloading workloads, API enablement, or progressive replacement.
    - Add "MainframeEvolutionPlan" object:
      - "StrategicOptions" (list)
      - "PriorityDomains"
      - "Risks"
      - "DependenciesOnOtherPrograms".

Overall target:
- Approximately 4,000–4,800 words across sections 10 and 11 combined (roughly 10–12 Word pages under the assumed formatting).

VERY IMPORTANT:
- ONLY modify sections "10. IT Organization" and "11. IT Organization Innovation Themes and Strategic Initiatives" in profile_json.
- Leave all other top-level sections exactly as they were after Wave 5.
- Return the ENTIRE updated profile_json as valid JSON, with no extra commentary.
"""

WAVE7_PROMPT = """
Operate on the latest JSON object `profile_json` that I am about to provide.

For THIS call, expand ONLY the following sections:

- "12. News and Recent Developments"
  - "Overview"
  - "12.1 Technology and Innovation"
  - "12.2 Sustainability and ESG"
  - "12.3 Cybersecurity and Resilience"
  - "12.4 Workforce and Talent"
  - "12.5 Strategic and Financial"
  - "12.6 Forward Outlook"

- "13. Governance"
  - "13.1 Statutory basis"
  - "13.2 Corporate governance structure"
  - "13.3 Risk and compliance governance"
  - "13.4 Technology and data governance"
  - "13.5 ESG and ethical governance"
  - "13.6 Reporting and oversight"

CONTEXT:
- Treat section 12 as a curated, thematic digest of recent developments (last 2–3 years) in technology, risk, ESG, talent, and financial strategy.
- Treat section 13 as a deep dive on Citi’s governance framework, aligned with what is typical for a global, systemically important bank, expressed at a generic but realistic level.

SECTION 12 REQUIREMENTS (News and Recent Developments):

1. Overview
   - 150–250 words.
   - Summarize what themes the news section covers and how it should be interpreted (e.g., thematic lens, not an exhaustive chronology).

2. 12.1 Technology and Innovation
   - 250–400 words.
   - Provide a narrative of key tech and innovation developments (e.g., modernization milestones, cloud/data initiatives, digital product launches).
   - Add "TechInnovationNews" array:
     - "Title"
     - "ApproxDateOrPeriod"
     - "Description"
     - "ImpactedSegments"
     - "DirectionalImpact" (e.g., Revenue / Cost / Risk / Experience).

3. 12.2 Sustainability and ESG
   - 250–400 words.
   - Describe ESG-related developments: sustainable finance initiatives, climate-risk reporting progress, operational footprint changes.
   - Add "ESGNews" array with similar fields as above.

4. 12.3 Cybersecurity and Resilience
   - 250–400 words.
   - Summarize themes like cyber capability build-out, resilience testing, regulatory expectations for operational resilience.
   - Add "CyberResilienceNews" array.

5. 12.4 Workforce and Talent
   - 250–400 words.
   - Capture key workforce moves: location strategy, hybrid work policies, diversity-focused programs, tech talent hiring.
   - Add "WorkforceTalentNews" array.

6. 12.5 Strategic and Financial
   - 250–400 words.
   - Cover high-level developments: strategic portfolio actions (e.g., exits, refocusing), capital planning themes, transformation spend, and earnings mix shifts.
   - Add "StrategicFinancialNews" array.

7. 12.6 Forward Outlook
   - 600–900 words.
   - Provide a synthesized forward-looking narrative:
     - Macro/regulatory context,
     - Competitive positioning vs peers,
     - Key upside/downside scenarios,
     - Dependencies on executing the risk/tech transformation.
   - Add "ForwardOutlookThemes" array:
     - "Theme"
     - "UpsideScenario"
     - "DownsideScenario"
     - "KeyDependencies"
     - "MonitoringIndicators".

SECTION 13 REQUIREMENTS (Governance):

8. 13.1 Statutory basis
   - 250–400 words.
   - Describe Citi’s statutory and regulatory context (U.S. bank holding company, global SIFI, home/host supervisors).
   - Add "StatutoryContext" object:
     - "HomeJurisdiction"
     - "PrimaryRegulators" (list)
     - "KeyRegulatoryFrameworks" (list).

9. 13.2 Corporate governance structure
   - 300–500 words.
   - Outline Board structure, committees (Audit, Risk, Governance, etc.), and management committees.
   - Add "CorporateGovernanceStructure" object:
     - "BoardCommittees" (list)
     - "ManagementCommittees" (list)
     - "GovernancePrinciples" (list).

10. 13.3 Risk and compliance governance
    - 300–500 words.
    - Describe three lines of defense, CRO and CCO roles, and risk governance cascade.
    - Add "RiskComplianceGovernance" object:
      - "ThreeLinesOfDefense" (narrative)
      - "KeyRoles" (list)
      - "EscalationPaths" (list).

11. 13.4 Technology and data governance
    - 300–500 words.
    - Link tech/data governance to risk and transformation themes (architecture councils, data councils, model risk, change control).
    - Add "TechDataGovernance" object:
      - "TechGovernanceBodies" (list)
      - "DataGovernanceBodies" (list)
      - "KeyPolicies" (list)
      - "ChangeControlMechanisms" (list).

12. 13.5 ESG and ethical governance
    - 250–400 words.
    - Describe oversight of ESG and conduct: Board ESG committees, ethics offices, codes of conduct.
    - Add "ESGGovernance" object:
      - "OversightBodies" (list)
      - "PolicyFrameworks" (list)
      - "KeyFocusAreas" (list).

13. 13.6 Reporting and oversight
    - 250–400 words.
    - Explain internal and external reporting routines (board packs, risk reports, regulatory submissions, public disclosures).
    - Add "ReportingOversightModel" object:
      - "InternalReportingCadence"
      - "ExternalDisclosures" (list)
      - "KeyDashboardsAndMetrics" (list).

Overall target:
- Approximately 3,200–4,000 words across sections 12 and 13 combined (roughly 8–10 Word pages under the assumed formatting).

VERY IMPORTANT:
- ONLY modify sections "12. News and Recent Developments" and "13. Governance" in profile_json.
- Leave all other top-level sections exactly as they were after Wave 6.
- Return the ENTIRE updated profile_json as valid JSON, with no extra commentary.
"""



# -----------------------------
# HELPER FUNCTIONS
# -----------------------------

def build_system_prompt(enterprise_name: str) -> str:
  """
  Return the system prompt tailored to the target enterprise.
  Falls back to the global SYSTEM_PROMPT, replacing the hardcoded enterprise
  name with the provided one to keep prompts consistent across runs.
  """
  try:
    # Replace specific name if present in the template prompt
    return SYSTEM_PROMPT.replace("United States Postal Service", enterprise_name)
  except Exception:
    # Ultimate fallback: minimal generic prompt
    return (
      f"You are a senior strategy consultant. Generate a dense, narrative-heavy "
      f"operational profile for {enterprise_name} in valid JSON only, strictly "
      f"following the provided JSON scaffold. Use the same tone, depth, and rules "
      f"as earlier prompts in this project."
    )

def load_profile_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_profile_json(profile: dict, path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)

def call_openai_chat(profile_json: dict, wave_prompt: str, client: OpenAI, enterprise_name: str = "United States Postal Service", max_retries: int = 3, use_compact_mode: bool = False) -> dict:
    """
    Sends profile_json and wave_prompt to the Chat Completions API,
    returns the updated JSON dict.
    Includes retry logic for malformed JSON responses.
    """
    import time
    
    # Build dynamic system prompt with enterprise name
    system_prompt = build_system_prompt(enterprise_name)
    if use_compact_mode:
        system_prompt = system_prompt + "\n\nIMPORTANT OVERRIDE: For this request, use COMPACT mode - reduce all word counts by 40%. Aim for 150-250 words per subsection instead of 250-400. Keep narratives to 300-500 words instead of 500-800. Prioritize brevity while maintaining quality."
    
    for attempt in range(max_retries):
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                # few-shot assistant example to enforce style; safe to remove if you want shorter prompts
                {
                    "role": "assistant",
                    "content": json.dumps(FEW_SHOT_ASSISTANT_JSON)
                },
                {
                    "role": "user",
                    "content": wave_prompt + "\n\nHere is the current profile_json:\n" + json.dumps(profile_json)
                },
            ]

            completion = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=0.4,  # mild randomness, you can tweak
                max_tokens=16384,  # Max allowed for GPT-4o
                response_format={"type": "json_object"}  # Force JSON output mode
            )

            content = completion.choices[0].message.content
            
            # Check if the response was truncated
            if completion.choices[0].finish_reason == "length":
                print(f"Warning: Response was truncated due to max_tokens limit.")
                # Try with a simpler prompt or lower temperature on retry
                if attempt < max_retries - 1:
                    print(f"Retrying with COMPACT mode to reduce output size...")
                    time.sleep(2)
                    # Force compact mode for next attempt
                    system_prompt = build_system_prompt(enterprise_name) + "\n\nCRITICAL OVERRIDE: Use COMPACT mode - reduce all word counts by 50%. Aim for 120-200 words per subsection. Keep narratives to 250-400 words. Be CONCISE."
                    continue
                else:
                    print(f"Response truncated on final attempt. This may cause issues...")
            
            # Parse JSON returned by the model
            # Handle markdown code blocks if present
            if content.strip().startswith("```"):
                # Remove markdown code blocks
                lines = content.strip().split('\n')
                # Remove first line (```json or ```)
                if lines[0].startswith("```"):
                    lines = lines[1:]
                # Remove last line if it's ```
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                content = '\n'.join(lines)
            
            try:
                updated_profile = json.loads(content)
                return updated_profile
            except json.JSONDecodeError as e:
                print(f"Attempt {attempt + 1}/{max_retries}: JSON parsing failed - {e}")
                if attempt < max_retries - 1:
                    print(f"Retrying in 2 seconds...")
                    time.sleep(2)
                else:
                    # Last attempt failed, save the raw content for debugging
                    error_file = OUTPUT_DIR / f"error_response_{int(time.time())}.txt"
                    with open(error_file, 'w') as f:
                        f.write(content)
                    raise RuntimeError(
                        f"Model did not return valid JSON after {max_retries} attempts. Error: {e}\n"
                        f"Raw content saved to {error_file}\n"
                        f"Preview:\n{content[:1000]}"
                    )
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Attempt {attempt + 1}/{max_retries}: Error occurred - {e}")
                print(f"Retrying in 2 seconds...")
                time.sleep(2)
            else:
                raise
    
    raise RuntimeError(f"Failed to get valid response after {max_retries} attempts")

# -----------------------------
# MAIN ORCHESTRATION
# -----------------------------



def get_word_count_instruction(section, subsection, config):
    """
    Get word count instruction from config file for a specific section/subsection.
    Falls back to default if not specified.
    """
    try:
        # Try to get specific word count for this subsection
        if section in config.get("sections", {}):
            if subsection in config["sections"][section]:
                return f"Write {config['sections'][section][subsection]} words."
        
        # Fall back to default
        default = config.get("default_word_count", "350-500")
        return f"Write {default} words."
    except Exception as e:
        # Ultimate fallback
        return "Write 350-500 words."
def main():
  import argparse
  parser = argparse.ArgumentParser(description="Generate operational profile for an enterprise")
  parser.add_argument("--enterprise", type=str, default="United States Postal Service", help="Name of the enterprise to profile")
  parser.add_argument("--output-dir", type=str, default=str(OUTPUT_DIR), help="Output directory for generated files")
  args = parser.parse_args()

  enterprise_name = args.enterprise
  output_dir = Path(args.output_dir)
  output_dir.mkdir(exist_ok=True, parents=True)

  api_key = os.getenv(API_KEY_ENV_VAR)
  if not api_key:
    raise EnvironmentError(f"Please set {API_KEY_ENV_VAR} in your environment.")

  client = OpenAI(api_key=api_key)

  # Load the template
  with open(TEMPLATE_PATH, "r") as f:
    template = json.load(f)

  # Load the configuration
  try:
    with open(CONFIG_PATH, "r") as f:
      config = json.load(f)
    print(f"Loaded configuration from {CONFIG_PATH}")
  except FileNotFoundError:
    print(f"Warning: {CONFIG_PATH} not found. Using default word counts.")
    config = {"default_word_count": "350-500", "sections": {}}

  # Working output
  output = template.copy()

  # Timing data structure
  timing_data = {
    "enterprise": enterprise_name,
    "start_time": time.time(),
    "subsections": []
  }
  total_subsections = sum(
    len(v) if isinstance(v, dict) else 0 for v in template.values()
  )
  current_index = 0

  # Iterate sections / subsections
  for section_name, section_value in template.items():
    print(f"\n=== {section_name} ===")
    if not isinstance(section_value, dict):
      print(f"Skipping non-dict section: {section_name}")
      continue
    for subsection_name in section_value.keys():
      current_index += 1
      start_sub = time.time()
      print(f"[{current_index}/{total_subsections}] Generating: {section_name} > {subsection_name}")
      word_instruction = get_word_count_instruction(section_name, subsection_name, config)
      print(f"  Word count: {word_instruction}")
      prompt = (
        f"Expand ONLY the following section of the {enterprise_name} operational profile in valid JSON.\n"
        f"Section: '{section_name}' > '{subsection_name}'\n{word_instruction}\n"
        "Return only valid JSON for this sub-section, with no extra commentary."
      )
      current_value = output[section_name][subsection_name]
      if current_value:
        prompt += f"\nCurrent value: {current_value}"
      try:
        response = call_openai_chat({section_name: {subsection_name: ""}}, prompt, client, enterprise_name)
        if section_name not in output:
          output[section_name] = {}
        output[section_name][subsection_name] = response.get(section_name, {}).get(subsection_name, "")
        duration = time.time() - start_sub
        timing_data["subsections"].append({
          "section": section_name,
          "subsection": subsection_name,
          "duration_seconds": round(duration, 2),
          "status": "success"
        })
        print(f"  ✓ Completed in {duration:.2f}s")
        save_profile_json(output, output_dir / "profile_detailed_partial.json")
      except Exception as e:
        duration = time.time() - start_sub
        print(f"  ✗ Error generating {section_name} > {subsection_name}: {e}")
        output[section_name][subsection_name] = f"[ERROR: {e}]"
        timing_data["subsections"].append({
          "section": section_name,
          "subsection": subsection_name,
          "duration_seconds": round(duration, 2),
          "status": "error",
          "error": str(e)
        })

  # Finalize timing
  timing_data["end_time"] = time.time()
  timing_data["total_duration_seconds"] = round(timing_data["end_time"] - timing_data["start_time"], 2)
  timing_data["total_subsections"] = total_subsections
  timing_data["successful_subsections"] = sum(1 for s in timing_data["subsections"] if s["status"] == "success")
  timing_data["failed_subsections"] = sum(1 for s in timing_data["subsections"] if s["status"] == "error")

  # Save final profile
  final_profile_path = output_dir / "profile_detailed.json"
  save_profile_json(output, final_profile_path)
  print(f"\n✓ Profile saved to: {final_profile_path}")

  timing_path = output_dir / "generation_timing.json"
  with open(timing_path, "w", encoding="utf-8") as f:
    json.dump(timing_data, f, indent=2)

  # Summary
  print(f"\n{'='*60}")
  print(f"GENERATION SUMMARY FOR: {enterprise_name}")
  print(f"{'='*60}")
  print(f"Total subsections: {timing_data['total_subsections']}")
  print(f"Successful: {timing_data['successful_subsections']}")
  print(f"Failed: {timing_data['failed_subsections']}")
  print(f"Total time: {timing_data['total_duration_seconds']:.2f}s ({timing_data['total_duration_seconds']/60:.1f} minutes)")
  avg = timing_data['total_duration_seconds'] / max(timing_data['total_subsections'], 1)
  print(f"Average per subsection: {avg:.2f}s")
  print(f"Timing details saved to: {timing_path}")
  print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
