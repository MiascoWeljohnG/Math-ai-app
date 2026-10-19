---
type: community
cohesion: 0.21
members: 17
---

# School Administration API

**Cohesion:** 0.21 - loosely connected
**Members:** 17 nodes

## Members
- [[A student number the school has registered. Once any exist, only these numbers…]] - rationale - backend/models.py
- [[RegisteredStudent]] - code - backend/models.py
- [[Session_7]] - code
- [[The files this school's teachers uploaded.]] - rationale - backend/routes/school_admin_routes.py
- [[The school admin's own page everything here is limited to the admin's school,…]] - rationale - backend/routes/school_admin_routes.py
- [[add_school_students()]] - code - backend/routes/school_admin_routes.py
- [[create_school_teacher()]] - code - backend/routes/school_admin_routes.py
- [[delete_3]] - code
- [[delete_registered_student()]] - code - backend/routes/admin_routes.py
- [[delete_school_student()]] - code - backend/routes/school_admin_routes.py
- [[get_8]] - code
- [[list_school_students()]] - code - backend/routes/school_admin_routes.py
- [[post_6]] - code
- [[remove_registered()]] - code - backend/routes/admin_routes.py
- [[school_admin_routes.py]] - code - backend/routes/school_admin_routes.py
- [[school_files()]] - code - backend/routes/school_admin_routes.py
- [[school_users()]] - code - backend/routes/school_admin_routes.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/School_Administration_API
SORT file.name ASC
```

## Connections to other communities
- 19 edges to [[_COMMUNITY_Administrator API]]
- 9 edges to [[_COMMUNITY_Authorization and Database Setup]]
- 8 edges to [[_COMMUNITY_Topic Classification]]
- 3 edges to [[_COMMUNITY_Application Startup and Migrations]]
- 2 edges to [[_COMMUNITY_Authentication and Schools]]
- 2 edges to [[_COMMUNITY_School Management API]]
- 2 edges to [[_COMMUNITY_Material Upload API]]
- 1 edge to [[_COMMUNITY_Subject Data Management]]
- 1 edge to [[_COMMUNITY_Materials Ingestion Tests]]

## Top bridge nodes
- [[school_admin_routes.py]] - degree 28, connects to 6 communities
- [[RegisteredStudent]] - degree 15, connects to 5 communities
- [[school_files()]] - degree 7, connects to 3 communities
- [[remove_registered()]] - degree 7, connects to 2 communities
- [[add_school_students()]] - degree 6, connects to 2 communities