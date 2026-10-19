---
type: community
cohesion: 0.21
members: 13
---

# School Management API

**Cohesion:** 0.21 - loosely connected
**Members:** 13 nodes

## Members
- [[BaseModel_6]] - code
- [[SchoolRequest]] - code - backend/routes/schools_routes.py
- [[Schools the main admin adds them, anyone can list them (the sign-up form needs…]] - rationale - backend/routes/schools_routes.py
- [[Session_9]] - code
- [[True once any student number is registered sign-up then needs a registered…]] - rationale - backend/routes/schools_routes.py
- [[create_school()]] - code - backend/routes/schools_routes.py
- [[get_9]] - code
- [[list_schools()]] - code - backend/routes/schools_routes.py
- [[post_8]] - code
- [[pydantic]] - concept
- [[require_admin()]] - code - backend/auth.py
- [[schools_routes.py]] - code - backend/routes/schools_routes.py
- [[signup_mode()]] - code - backend/routes/schools_routes.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/School_Management_API
SORT file.name ASC
```

## Connections to other communities
- 6 edges to [[_COMMUNITY_Authorization and Database Setup]]
- 4 edges to [[_COMMUNITY_Subject Data Management]]
- 4 edges to [[_COMMUNITY_Authentication and Schools]]
- 2 edges to [[_COMMUNITY_Topic Classification]]
- 2 edges to [[_COMMUNITY_School Administration API]]
- 2 edges to [[_COMMUNITY_Administrator API]]
- 2 edges to [[_COMMUNITY_Application Startup and Migrations]]
- 2 edges to [[_COMMUNITY_User Progress Tracking]]
- 1 edge to [[_COMMUNITY_Notification API]]
- 1 edge to [[_COMMUNITY_User Chat API]]
- 1 edge to [[_COMMUNITY_Practice Generation API]]
- 1 edge to [[_COMMUNITY_Reminders and Learning API]]
- 1 edge to [[_COMMUNITY_Materials Ingestion Tests]]
- 1 edge to [[_COMMUNITY_Profile Management API]]

## Top bridge nodes
- [[pydantic]] - degree 9, connects to 8 communities
- [[schools_routes.py]] - degree 20, connects to 7 communities
- [[require_admin()]] - degree 6, connects to 5 communities
- [[create_school()]] - degree 6, connects to 2 communities
- [[signup_mode()]] - degree 5, connects to 1 community