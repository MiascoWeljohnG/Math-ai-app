---
source_file: "backend/models.py"
type: "code"
community: "School Administration API"
location: "L15"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/School_Administration_API
---

# RegisteredStudent

## Connections
- [[A student number the school has registered. Once any exist, only these numbers…]] - `rationale_for` [EXTRACTED]
- [[Base]] - `inherits` [EXTRACTED]
- [[add_registered()]] - `calls` [EXTRACTED]
- [[admin_routes.py]] - `imports` [EXTRACTED]
- [[auth_routes.py]] - `imports` [EXTRACTED]
- [[delete_registered_student()]] - `uses` [INFERRED]
- [[delete_school_student()]] - `uses` [INFERRED]
- [[list_registered_students()]] - `uses` [INFERRED]
- [[list_school_students()]] - `uses` [INFERRED]
- [[models.py]] - `contains` [EXTRACTED]
- [[register()]] - `uses` [INFERRED]
- [[remove_registered()]] - `uses` [INFERRED]
- [[school_admin_routes.py]] - `imports` [EXTRACTED]
- [[schools_routes.py]] - `imports` [EXTRACTED]
- [[signup_mode()]] - `uses` [INFERRED]

#graphify/code #graphify/EXTRACTED #community/School_Administration_API