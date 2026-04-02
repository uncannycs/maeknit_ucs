{
    "name": "QOC CRM Customization",
    "version": "18.0.1.0",
    "category": "CRM",
    "description": """
    Adds custom fields and parent-child relationship to CRM Leads
    """,
    "summary": "Customize the CRM Leads",
    "depends": ["crm", "sale_crm"],
    "data": [
        "security/ir.model.access.csv",
        "views/crm_lead_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
    "author": "QOC Innovations",
    "website": "https://qocinnovations.com",
}
