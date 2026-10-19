---
type: community
cohesion: 0.28
members: 13
---

# Authentication and Schools

**Cohesion:** 0.28 - loosely connected
**Members:** 13 nodes

## Members
- [[BaseModel_5]] - code
- [[LoginRequest]] - code - backend/routes/auth_routes.py
- [[One school (A, B ...). Accounts, subjects, files and reminders belong to a…]] - rationale - backend/models.py
- [[RegisterRequest]] - code - backend/routes/auth_routes.py
- [[School]] - code - backend/models.py
- [[Session_8]] - code
- [[auth_routes.py]] - code - backend/routes/auth_routes.py
- [[create_access_token()]] - code - backend/auth.py
- [[hash_password()]] - code - backend/auth.py
- [[login()_1]] - code - backend/routes/auth_routes.py
- [[post_7]] - code
- [[register()]] - code - backend/routes/auth_routes.py
- [[verify_password()]] - code - backend/auth.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Authentication_and_Schools
SORT file.name ASC
```

## Connections to other communities
- 10 edges to [[_COMMUNITY_Authorization and Database Setup]]
- 6 edges to [[_COMMUNITY_Administrator API]]
- 4 edges to [[_COMMUNITY_School Management API]]
- 3 edges to [[_COMMUNITY_Topic Classification]]
- 3 edges to [[_COMMUNITY_Materials Ingestion Tests]]
- 3 edges to [[_COMMUNITY_Application Startup and Migrations]]
- 2 edges to [[_COMMUNITY_School Administration API]]
- 1 edge to [[_COMMUNITY_Subject Data Management]]
- 1 edge to [[_COMMUNITY_Adaptive Difficulty Model]]

## Top bridge nodes
- [[auth_routes.py]] - degree 21, connects to 7 communities
- [[School]] - degree 15, connects to 5 communities
- [[hash_password()]] - degree 6, connects to 3 communities
- [[register()]] - degree 8, connects to 2 communities
- [[login()_1]] - degree 8, connects to 1 community