---
type: community
cohesion: 0.12
members: 28
---

# Authorization and Database Setup

**Cohesion:** 0.12 - loosely connected
**Members:** 28 nodes

## Members
- [[Material]] - code - backend/models.py
- [[One uploaded course file, tagged with the math branch it belongs to. `filename`…]] - rationale - backend/models.py
- [[Teachers see only the files they uploaded; admins see every file, with who…]] - rationale - backend/tests/test_materials.py
- [[The admin bell. notify_admins() writes one Notification row per admin;…]] - rationale - backend/notifications.py
- [[UsageLog]] - code - backend/models.py
- [[api()_3]] - code - backend/tests/test_materials.py
- [[auth.py]] - code - backend/auth.py
- [[create_admin.py]] - code - backend/create_admin.py
- [[database.py]] - code - backend/database.py
- [[datetime]] - code
- [[fastapi_security]] - concept
- [[fixture_3]] - code
- [[get_db()]] - code - backend/database.py
- [[jose]] - concept
- [[migrations.py]] - code - backend/migrations.py
- [[models.py]] - code - backend/models.py
- [[notifications.py]] - code - backend/notifications.py
- [[passlib_context]] - concept
- [[require_school_admin()]] - code - backend/auth.py
- [[require_teacher()]] - code - backend/auth.py
- [[require_teacher_or_admin()]] - code - backend/auth.py
- [[sqlalchemy_orm]] - concept
- [[sqlite3]] - concept
- [[teacher_routes.py]] - code - backend/routes/teacher_routes.py
- [[test_admin_sees_every_file_with_uploader_and_date()]] - code - backend/tests/test_materials.py
- [[test_materials.py]] - code - backend/tests/test_materials.py
- [[test_only_the_right_role_can_list_files()]] - code - backend/tests/test_materials.py
- [[test_teacher_sees_only_their_own_files_newest_first()]] - code - backend/tests/test_materials.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Authorization_and_Database_Setup
SORT file.name ASC
```

## Connections to other communities
- 25 edges to [[_COMMUNITY_Subject Data Management]]
- 21 edges to [[_COMMUNITY_Application Startup and Migrations]]
- 19 edges to [[_COMMUNITY_Topic Classification]]
- 16 edges to [[_COMMUNITY_Administrator API]]
- 10 edges to [[_COMMUNITY_Authentication and Schools]]
- 9 edges to [[_COMMUNITY_Materials Ingestion Tests]]
- 9 edges to [[_COMMUNITY_School Administration API]]
- 9 edges to [[_COMMUNITY_User Chat API]]
- 9 edges to [[_COMMUNITY_Learning Progress Tests]]
- 9 edges to [[_COMMUNITY_User Progress Tracking]]
- 8 edges to [[_COMMUNITY_Reminders and Learning API]]
- 7 edges to [[_COMMUNITY_Notification API]]
- 6 edges to [[_COMMUNITY_Branch Classifier Tests]]
- 6 edges to [[_COMMUNITY_Practice Generation API]]
- 6 edges to [[_COMMUNITY_School Management API]]
- 5 edges to [[_COMMUNITY_Retrieval Augmented Generation]]
- 5 edges to [[_COMMUNITY_Material Upload API]]
- 5 edges to [[_COMMUNITY_Quiz Evaluation]]
- 5 edges to [[_COMMUNITY_Profile Management API]]
- 5 edges to [[_COMMUNITY_Adaptive Learning Tests]]
- 3 edges to [[_COMMUNITY_Adaptive Difficulty Model]]

## Top bridge nodes
- [[models.py]] - degree 47, connects to 19 communities
- [[database.py]] - degree 26, connects to 17 communities
- [[get_db()]] - degree 22, connects to 17 communities
- [[auth.py]] - degree 39, connects to 16 communities
- [[sqlalchemy_orm]] - degree 18, connects to 13 communities