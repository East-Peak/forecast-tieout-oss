"""The raw record schemas: the interface between the generator and the evidence loader.

One JSON Lines file per object, named `<Object>.jsonl`. Salesforce and HubSpot
objects use the vendor's standard API field names where a standard field exists.
Custom Salesforce fields end in `__c` and each is listed in CUSTOM_FIELDS_NOTE.
"""

from .schema import Field as F
from .schema import ObjectSchema

SALESFORCE, HUBSPOT, PEOPLE, SPEND, PLAN = (
    "salesforce",
    "hubspot",
    "people_system",
    "spend_sheet",
    "plan_file",
)

STAGES_NOTE = (
    "StageName is an open string; the catalog maps it. Closed stages are "
    "Closed Won and Closed Lost, which set IsClosed (and IsWon for Closed Won)."
)
CUSTOM_FIELDS_NOTE = {
    "Opportunity.Sourcing_User__c": "User.Id of the person who sourced the deal (BDR or self-sourcing AE); null when marketing sourced it. Distinct from OwnerId, who books it.",
    "Lead.Sales_Offered_Date__c": "Date the lead was offered to sales. Every new value, tracked in LeadHistory, starts a demand episode (key lead_id, offer_seq). Marketing and outbound (BDR) demand both use it; no MQL is required.",
    "Lead.MQL_Date__c": "Optional. Date the lead became marketing qualified; links a marketing episode to its MQL. Outbound demand has none.",
    "Lead.Disposition__c": "What sales did with the current offer: Admitted, Rejected, Expired; null while open. Changes after an offer and before the next offer are that episode's outcome; a reset to null on re-offer is not an outcome.",
    "Lead.Disposition_Reason__c": "Why: for Rejected a fit reason (not_a_fit), for Expired a capacity reason (no_capacity); null when open.",
    "Lead.Tier__c": "Tier of the prospective account at lead time (Tier 1, Tier 2, Tier 3); the catalog maps tier to segment.",
    "Account.Tier__c": "Account tier (Tier 1, Tier 2, Tier 3); the catalog maps tier to segment. Carries no field history in the fixture estate.",
}

ID = "Salesforce record id (opaque string)"


def _sf(name, key, fields, doc):
    return ObjectSchema(name, SALESFORCE, key, tuple(fields), doc)


_OBJECTS = [
    _sf(
        "Opportunity",
        ("Id",),
        [
            F("Id", "id", ID),
            F("AccountId", "id", "Account the deal belongs to", ref="Account"),
            F("OwnerId", "id", "User who owns and books the deal", ref="User"),
            F("CreatedById", "id", "User who created the record", ref="User"),
            F(
                "Sourcing_User__c",
                "id",
                "Sourcing person (see CUSTOM_FIELDS_NOTE)",
                nullable=True,
                ref="User",
            ),
            F(
                "CampaignId",
                "id",
                "Primary campaign source",
                nullable=True,
                ref="Campaign",
            ),
            F(
                "LeadSource",
                "string",
                "Standard lead source picklist value",
                nullable=True,
            ),
            F(
                "Type",
                "string",
                "New Business, Renewal or Expansion; only New Business counts toward bookings",
                choices=("New Business", "Renewal", "Expansion"),
            ),
            F("StageName", "string", "Current stage. " + STAGES_NOTE),
            F(
                "Amount",
                "dollars",
                "Deal amount in dollars; the bookings_amount field of the catalog",
                nullable=True,
            ),
            F(
                "CloseDate",
                "date",
                "Effective close date: expected while open, actual once closed",
            ),
            F("IsClosed", "bool", "True when StageName is a closed stage"),
            F("IsWon", "bool", "True when StageName is Closed Won"),
            F("CreatedDate", "datetime", "When the record was created"),
            F("SystemModstamp", "datetime", "Last system modification of any field"),
        ],
        "A deal. Bookings are Amount of New Business opportunities with IsWon, by CloseDate.",
    ),
    _sf(
        "OpportunityHistory",
        ("Id",),
        [
            F("Id", "id", ID),
            F("OpportunityId", "id", "Deal this row belongs to", ref="Opportunity"),
            F("StageName", "string", "Stage after the change"),
            F("Amount", "dollars", "Amount after the change", nullable=True),
            F("CloseDate", "date", "CloseDate after the change"),
            F(
                "CreatedDate",
                "datetime",
                "System time of the change: the row's knowledge time",
            ),
        ],
        "A full image of StageName, Amount and CloseDate written whenever any of the three changes. Source for those three fields.",
    ),
    _sf(
        "OpportunityFieldHistory",
        ("Id",),
        [
            F("Id", "id", ID),
            F("OpportunityId", "id", "Deal this row belongs to", ref="Opportunity"),
            F("Field", "string", "API name of the changed field (for example OwnerId)"),
            F("OldValue", "string", "Prior value as text", nullable=True),
            F("NewValue", "string", "New value as text", nullable=True),
            F(
                "CreatedDate",
                "datetime",
                "System time of the change: the row's knowledge time",
            ),
            F("CreatedById", "id", "User who made the change", ref="User"),
        ],
        "One row per tracked-field change, for fields OpportunityHistory does not carry.",
    ),
    _sf(
        "Lead",
        ("Id",),
        [
            F("Id", "id", ID),
            F("OwnerId", "id", "User working the lead", ref="User"),
            F("CreatedById", "id", "User who created the record", ref="User"),
            F(
                "LeadSource",
                "string",
                "Standard lead source picklist value",
                nullable=True,
            ),
            F(
                "Tier__c",
                "string",
                "Prospective account tier (see CUSTOM_FIELDS_NOTE)",
                nullable=True,
            ),
            F(
                "Sales_Offered_Date__c",
                "date",
                "Date of the latest offer to sales; each new Sales_Offered_Date__c value in LeadHistory starts an episode (see CUSTOM_FIELDS_NOTE)",
                nullable=True,
            ),
            F(
                "MQL_Date__c",
                "date",
                "Optional MQL date (see CUSTOM_FIELDS_NOTE)",
                nullable=True,
            ),
            F(
                "Disposition__c",
                "string",
                "Outcome of offered demand (see CUSTOM_FIELDS_NOTE)",
                nullable=True,
                choices=("Admitted", "Rejected", "Expired"),
            ),
            F(
                "Disposition_Reason__c",
                "string",
                "Reason for the disposition (see CUSTOM_FIELDS_NOTE)",
                nullable=True,
            ),
            F(
                "IsConverted",
                "bool",
                "True once converted to an account and opportunity",
            ),
            F("ConvertedDate", "date", "Conversion date", nullable=True),
            F(
                "ConvertedOpportunityId",
                "id",
                "Opportunity created by conversion",
                nullable=True,
                ref="Opportunity",
            ),
            F(
                "ConvertedAccountId",
                "id",
                "Account created or matched by conversion",
                nullable=True,
                ref="Account",
            ),
            F("CreatedDate", "datetime", "When the record was created"),
            F("SystemModstamp", "datetime", "Last system modification of any field"),
        ],
        "A prospect. Each offer to sales (Sales_Offered_Date__c) is a demand episode; MQL_Date__c is optional.",
    ),
    _sf(
        "LeadHistory",
        ("Id",),
        [
            F("Id", "id", ID),
            F("LeadId", "id", "Lead this row belongs to", ref="Lead"),
            F(
                "Field",
                "string",
                "API name of the changed field (Sales_Offered_Date__c, MQL_Date__c, Disposition__c, Disposition_Reason__c, OwnerId)",
            ),
            F("OldValue", "string", "Prior value as text", nullable=True),
            F("NewValue", "string", "New value as text", nullable=True),
            F(
                "CreatedDate",
                "datetime",
                "System time of the change: the row's knowledge time",
            ),
            F("CreatedById", "id", "User who made the change", ref="User"),
        ],
        "One row per tracked-field change on a lead.",
    ),
    _sf(
        "Account",
        ("Id",),
        [
            F("Id", "id", ID),
            F("Name", "string", "Account name"),
            F(
                "Tier__c",
                "string",
                "Account tier (see CUSTOM_FIELDS_NOTE)",
                nullable=True,
            ),
            F(
                "BillingCountry",
                "string",
                "Country as the vendor defines it: free text, a name or a code, whatever the user typed; the catalog maps it to region",
                nullable=True,
            ),
            F(
                "BillingCountryCode",
                "string",
                "Optional standardized country code where the org has one",
                nullable=True,
            ),
            F("CreatedDate", "datetime", "When the record was created"),
            F("SystemModstamp", "datetime", "Last system modification of any field"),
        ],
        "A customer or prospect company.",
    ),
    _sf(
        "Campaign",
        ("Id",),
        [
            F("Id", "id", ID),
            F("Name", "string", "Campaign name"),
            F(
                "Type",
                "string",
                "Program type (for example Paid Search, Trade Show); the catalog maps type to source",
            ),
            F("StartDate", "date", "First day", nullable=True),
            F("EndDate", "date", "Last day", nullable=True),
            F("IsActive", "bool", "Whether the campaign is active"),
            F("CreatedDate", "datetime", "When the record was created"),
            F("SystemModstamp", "datetime", "Last system modification of any field"),
        ],
        "A marketing program. Spend is a separate object.",
    ),
    _sf(
        "CampaignMember",
        ("Id",),
        [
            F("Id", "id", ID),
            F("CampaignId", "id", "Campaign", ref="Campaign"),
            F(
                "LeadId",
                "id",
                "Lead touched (contacts are out of scope in this build)",
                ref="Lead",
            ),
            F("Status", "string", "Member status (for example Sent, Responded)"),
            F("FirstRespondedDate", "date", "First response", nullable=True),
            F("CreatedDate", "datetime", "When the touch was recorded"),
            F("SystemModstamp", "datetime", "Last system modification of any field"),
        ],
        "A touch: one lead in one campaign.",
    ),
    _sf(
        "User",
        ("Id",),
        [
            F("Id", "id", ID),
            F("Name", "string", "Full name"),
            F("Email", "string", "Work email; the declared key to the people system"),
            F("Title", "string", "Job title", nullable=True),
            F("IsActive", "bool", "Whether the user can log in"),
            F("CreatedDate", "datetime", "When the record was created"),
            F("SystemModstamp", "datetime", "Last system modification of any field"),
        ],
        "A Salesforce user.",
    ),
    ObjectSchema(
        "contacts",
        HUBSPOT,
        ("hs_object_id",),
        (
            F("hs_object_id", "id", "HubSpot record id"),
            F("email", "string", "Contact email", nullable=True),
            F(
                "lifecyclestage",
                "string",
                "Current lifecycle stage (lead, marketingqualifiedlead, ...)",
                nullable=True,
            ),
            F("createdate", "datetime", "When the contact was created"),
            F(
                "hs_lifecyclestage_marketingqualifiedlead_date",
                "datetime",
                "When the contact reached MQL",
                nullable=True,
            ),
            F("lastmodifieddate", "datetime", "Last modification"),
            F(
                "salesforce_lead_id",
                "id",
                "Declared link to Lead.Id; null when unlinked",
                nullable=True,
                ref="Lead",
            ),
        ),
        "Contact lifecycle only. HubSpot contributes no counts of leads or deals.",
    ),
    ObjectSchema(
        "deals",
        HUBSPOT,
        ("hs_object_id",),
        (
            F("hs_object_id", "id", "HubSpot record id"),
            F("dealname", "string", "Deal name"),
            F("dealstage", "string", "Stage id", nullable=True),
            F("amount", "dollars", "Amount in dollars", nullable=True),
            F("closedate", "datetime", "Close date", nullable=True),
            F("createdate", "datetime", "When the deal was created"),
            F("hs_lastmodifieddate", "datetime", "Last modification"),
            F(
                "salesforce_opportunity_id",
                "id",
                "Declared link to Opportunity.Id; linked deals are mirrors and never counted",
                nullable=True,
                ref="Opportunity",
            ),
        ),
        "A HubSpot deal. Mirrors of Salesforce opportunities are linked, never counted.",
    ),
    ObjectSchema(
        "people",
        PEOPLE,
        ("person_id",),
        (
            F("person_id", "id", "People-system id"),
            F("name", "string", "Full name"),
            F("email", "string", "Work email; matches User.Email (the declared key)"),
            F(
                "role",
                "string",
                "Function",
                choices=("AE", "BDR", "Marketing", "Manager"),
            ),
            F("team", "string", "Team name; AE teams are the carrying-capacity pools"),
            F(
                "segment",
                "string",
                "Segment coverage, when the role has one",
                nullable=True,
            ),
            F("region", "string", "Region coverage", nullable=True),
            F("start_date", "date", "First day"),
            F("end_date", "date", "Last day; null while employed", nullable=True),
        ),
        "A roster entry. The source of heads, tenure (ramp) and attrition.",
    ),
    ObjectSchema(
        "requisitions",
        PEOPLE,
        ("req_id",),
        (
            F("req_id", "id", "Requisition id"),
            F("team", "string", "Team the hire joins"),
            F(
                "role",
                "string",
                "Function",
                choices=("AE", "BDR", "Marketing", "Manager"),
            ),
            F(
                "planned_start",
                "date",
                "Planned start date (slip is actual start minus this)",
            ),
            F(
                "status",
                "string",
                "open, filled or cancelled",
                choices=("open", "filled", "cancelled"),
            ),
            F(
                "person_id",
                "id",
                "Person hired, once filled",
                nullable=True,
                ref="people",
            ),
            F("opened_date", "date", "When the requisition opened"),
            F("closed_date", "date", "When it filled or was cancelled", nullable=True),
        ),
        "A hiring requisition.",
    ),
    ObjectSchema(
        "spend",
        SPEND,
        ("spend_id",),
        (
            F("spend_id", "id", "Spend row id"),
            F("campaign_id", "id", "Campaign the spend funds", ref="Campaign"),
            F("month", "date", "First day of the month"),
            F("amount_cents", "cents", "Program spend for the month in integer cents"),
        ),
        "Monthly program spend by campaign.",
    ),
    ObjectSchema(
        "plan_lines",
        PLAN,
        ("plan_version", "metric", "lane", "period", "role"),
        (
            F("plan_version", "string", "Frozen plan version, for example FY25-v1"),
            F("metric", "string", "Catalog metric id"),
            F(
                "lane",
                "string",
                "Lane key: dimension=member pairs sorted by dimension and joined by ';', or * for all",
            ),
            F("period", "date", "First day of the month the value is for"),
            F("value", "number", "Stated value in the metric's unit (cents for money)"),
            F(
                "unit",
                "string",
                "cents, count, ratio or days",
                choices=("cents", "count", "ratio", "days"),
            ),
            F(
                "role",
                "string",
                "input drives evaluation, target is what was promised, check is compared but never used",
                choices=("input", "target", "check"),
            ),
            F("author", "string", "Who stated the line"),
            F("recorded_at", "datetime", "When the line was stated"),
        ),
        "One stated plan line.",
    ),
]

SCHEMAS = {s.name: s for s in _OBJECTS}
SYSTEMS: dict[str, tuple[str, ...]] = {}
for _s in _OBJECTS:
    SYSTEMS[_s.system] = (*SYSTEMS.get(_s.system, ()), _s.name)
