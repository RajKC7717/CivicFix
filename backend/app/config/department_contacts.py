"""Pune Municipal Corporation department contact information.

Publicly available contact details for civic complaint routing.
These are representative PMC department emails for the hackathon demo.
"""

from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class DepartmentContact:
    department_code: str
    department_name: str
    email: str
    designation: str
    office: str
    phone: str  # public helpline

DEPARTMENT_CONTACTS: tuple[DepartmentContact, ...] = (
    DepartmentContact("roads", "Road & Bridges Department", "road.dept@punecorporation.org", "Executive Engineer, Road Department", "PMC Main Building, Shivajinagar, Pune", "020-25501000"),
    DepartmentContact("swm", "Solid Waste Management Department", "swm@punecorporation.org", "Deputy Commissioner, SWM", "PMC SWM Cell, Shivajinagar, Pune", "020-25501213"),
    DepartmentContact("electrical", "Electrical Department", "electrical@punecorporation.org", "Executive Engineer, Electrical", "PMC Electrical Section, Shivajinagar, Pune", "020-25501300"),
    DepartmentContact("sewerage", "Sewerage & Drainage Department", "sewerage@punecorporation.org", "Executive Engineer, Drainage", "PMC Drainage Division, Shivajinagar, Pune", "020-25501400"),
    DepartmentContact("water", "Water Supply Department", "water.supply@punecorporation.org", "Superintendent Engineer, Water Supply", "PMC Water Supply Department, Pune", "020-25501500"),
    DepartmentContact("veterinary", "Veterinary & Animal Welfare Cell", "veterinary@punecorporation.org", "Veterinary Officer", "PMC Animal Welfare Cell, Pune", "020-25501600"),
    DepartmentContact("encroachment", "Anti-Encroachment & Traffic Cell", "encroachment@punecorporation.org", "Anti-Encroachment Officer", "PMC Anti-Encroachment Cell, Pune", "020-25501700"),
    DepartmentContact("garden", "Garden & Tree Authority", "garden@punecorporation.org", "Superintendent, Garden Department", "PMC Garden Department, Pune", "020-25501800"),
    DepartmentContact("central", "Central Grievance Cell", "grievance@punecorporation.org", "Deputy Commissioner, Grievance Cell", "PMC Main Building, Shivajinagar, Pune", "020-25501000"),
)

CONTACT_BY_DEPARTMENT: dict[str, DepartmentContact] = {c.department_code: c for c in DEPARTMENT_CONTACTS}
