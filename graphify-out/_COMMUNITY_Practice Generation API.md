---
type: community
cohesion: 0.22
members: 19
---

# Practice Generation API

**Cohesion:** 0.22 - loosely connected
**Members:** 19 nodes

## Members
- [[(level, kind of practice offered, the student's latest attempt) from their quiz…]] - rationale - backend/routes/practice_routes.py
- [[Adaptive practice sets. After a weak quiz the AI writes an EASIER set on the…]] - rationale - backend/routes/practice_routes.py
- [[BaseModel_3]] - code
- [[PracticeSet]] - code - backend/models.py
- [[Session_5]] - code
- [[SubmitPracticeRequest]] - code - backend/routes/practice_routes.py
- [[The adaptive practice set a student was given for a lesson easier after a weak…]] - rationale - backend/models.py
- [[The stored set, but only if it was written for the student's latest attempt and…]] - rationale - backend/routes/practice_routes.py
- [[What the page needs. Answers are left out on purpose.]] - rationale - backend/routes/practice_routes.py
- [[_display_answer()]] - code - backend/routes/subjects_routes.py
- [[_payload()]] - code - backend/routes/practice_routes.py
- [[_saved()]] - code - backend/routes/practice_routes.py
- [[_standing()]] - code - backend/routes/practice_routes.py
- [[generate_practice()]] - code - backend/routes/practice_routes.py
- [[get_6]] - code
- [[get_practice()]] - code - backend/routes/practice_routes.py
- [[post_4]] - code
- [[practice_routes.py]] - code - backend/routes/practice_routes.py
- [[submit_practice()]] - code - backend/routes/practice_routes.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Practice_Generation_API
SORT file.name ASC
```

## Connections to other communities
- 22 edges to [[_COMMUNITY_Topic Classification]]
- 6 edges to [[_COMMUNITY_Authorization and Database Setup]]
- 6 edges to [[_COMMUNITY_Quiz Evaluation]]
- 6 edges to [[_COMMUNITY_Adaptive Difficulty Model]]
- 5 edges to [[_COMMUNITY_Subject Data Management]]
- 5 edges to [[_COMMUNITY_Adaptive Learning Tests]]
- 4 edges to [[_COMMUNITY_Learning Progress Tests]]
- 2 edges to [[_COMMUNITY_Application Startup and Migrations]]
- 1 edge to [[_COMMUNITY_Branch Classifier Tests]]
- 1 edge to [[_COMMUNITY_Retrieval Augmented Generation]]
- 1 edge to [[_COMMUNITY_School Management API]]

## Top bridge nodes
- [[practice_routes.py]] - degree 37, connects to 11 communities
- [[PracticeSet]] - degree 13, connects to 4 communities
- [[_standing()]] - degree 10, connects to 3 communities
- [[generate_practice()]] - degree 14, connects to 2 communities
- [[submit_practice()]] - degree 11, connects to 2 communities