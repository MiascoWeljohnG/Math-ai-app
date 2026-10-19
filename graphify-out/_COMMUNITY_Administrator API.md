---
type: community
cohesion: 0.12
members: 33
---

# Administrator API

**Cohesion:** 0.12 - loosely connected
**Members:** 33 nodes

## Members
- [[Add a bell entry for every admin (except `exclude`, usually the person who did…]] - rationale - backend/notifications.py
- [[BaseModel_8]] - code
- [[CreateTeacherRequest]] - code - backend/routes/admin_routes.py
- [[Delete one uploaded file its record, the original on disk, and the AI's chunks…]] - rationale - backend/routes/admin_routes.py
- [[Every uploaded file with who uploaded it and when (newest first).]] - rationale - backend/routes/admin_routes.py
- [[Only the default 'admin' account makes admins (the page hides the button from…]] - rationale - backend/routes/admin_routes.py
- [[Register the student numbers in `raw` for one school. Bad or duplicate numbers…]] - rationale - backend/routes/admin_routes.py
- [[RegisteredNumbersRequest]] - code - backend/routes/admin_routes.py
- [[Session_15]] - code
- [[Session_16]] - code
- [[Shared body of adminupload and teacherupload. `branch` is a real branch (as…]] - rationale - backend/classifier.py
- [[UploadFile_3]] - code
- [[Validate and save one staff account (teacher, school admin or main admin).…]] - rationale - backend/routes/admin_routes.py
- [[Wipes the vector store, uploaded files, and their branch records together, so…]] - rationale - backend/routes/admin_routes.py
- [[add_registered()]] - code - backend/routes/admin_routes.py
- [[add_registered_students()]] - code - backend/routes/admin_routes.py
- [[admin_routes.py]] - code - backend/routes/admin_routes.py
- [[clear_knowledge_base()]] - code - backend/routes/admin_routes.py
- [[create_admin()]] - code - backend/routes/admin_routes.py
- [[create_teacher()]] - code - backend/routes/admin_routes.py
- [[delete_5]] - code
- [[delete_file()]] - code - backend/routes/admin_routes.py
- [[get_12]] - code
- [[ingest_with_detection()]] - code - backend/classifier.py
- [[list_files()]] - code - backend/routes/admin_routes.py
- [[list_registered_students()]] - code - backend/routes/admin_routes.py
- [[list_users()]] - code - backend/routes/admin_routes.py
- [[new_account()]] - code - backend/routes/admin_routes.py
- [[notify_admins()]] - code - backend/notifications.py
- [[post_11]] - code
- [[registry_items()]] - code - backend/routes/admin_routes.py
- [[school_or_400()]] - code - backend/routes/admin_routes.py
- [[upload_documents()]] - code - backend/routes/admin_routes.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Administrator_API
SORT file.name ASC
```

## Connections to other communities
- 19 edges to [[_COMMUNITY_School Administration API]]
- 16 edges to [[_COMMUNITY_Authorization and Database Setup]]
- 13 edges to [[_COMMUNITY_Topic Classification]]
- 6 edges to [[_COMMUNITY_Authentication and Schools]]
- 6 edges to [[_COMMUNITY_Application Startup and Migrations]]
- 3 edges to [[_COMMUNITY_Material Upload API]]
- 2 edges to [[_COMMUNITY_School Management API]]
- 2 edges to [[_COMMUNITY_Branch Classifier Tests]]
- 1 edge to [[_COMMUNITY_Notification API]]
- 1 edge to [[_COMMUNITY_Retrieval Augmented Generation]]
- 1 edge to [[_COMMUNITY_Learning Progress Tests]]
- 1 edge to [[_COMMUNITY_Materials Ingestion Tests]]
- 1 edge to [[_COMMUNITY_Adaptive Difficulty Model]]

## Top bridge nodes
- [[admin_routes.py]] - degree 47, connects to 10 communities
- [[ingest_with_detection()]] - degree 14, connects to 5 communities
- [[notify_admins()]] - degree 10, connects to 3 communities
- [[new_account()]] - degree 10, connects to 3 communities
- [[list_files()]] - degree 7, connects to 3 communities