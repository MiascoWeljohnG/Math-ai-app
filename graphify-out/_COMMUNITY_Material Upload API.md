---
type: community
cohesion: 0.25
members: 8
---

# Material Upload API

**Cohesion:** 0.25 - loosely connected
**Members:** 8 nodes

## Members
- [[One uploaded file as the teacher and admin file tables show it.]] - rationale - backend/routes/materials_routes.py
- [[Only the files this teacher uploaded. The filter is here, not in the page, so a…]] - rationale - backend/routes/teacher_routes.py
- [[Session_13]] - code
- [[UploadFile_2]] - code
- [[material_summary()]] - code - backend/routes/materials_routes.py
- [[my_files()]] - code - backend/routes/teacher_routes.py
- [[post_10]] - code
- [[teacher_upload()]] - code - backend/routes/teacher_routes.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Material_Upload_API
SORT file.name ASC
```

## Connections to other communities
- 5 edges to [[_COMMUNITY_Authorization and Database Setup]]
- 3 edges to [[_COMMUNITY_Administrator API]]
- 2 edges to [[_COMMUNITY_Topic Classification]]
- 2 edges to [[_COMMUNITY_Subject Data Management]]
- 2 edges to [[_COMMUNITY_Application Startup and Migrations]]
- 2 edges to [[_COMMUNITY_School Administration API]]

## Top bridge nodes
- [[material_summary()]] - degree 10, connects to 4 communities
- [[my_files()]] - degree 7, connects to 3 communities
- [[teacher_upload()]] - degree 6, connects to 3 communities
- [[Session_13]] - degree 3, connects to 1 community