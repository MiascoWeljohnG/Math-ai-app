---
type: community
cohesion: 0.23
members: 12
---

# User Progress Tracking

**Cohesion:** 0.23 - loosely connected
**Members:** 12 nodes

## Members
- [[A student marked a lesson as complete. This is what the progress bars count.]] - rationale - backend/models.py
- [[LessonCompletion]] - code - backend/models.py
- [[Real progress lessons this user marked complete  all lessons, per subject…]] - rationale - backend/progress.py
- [[SQL filter those, plus the user's personal subjects.]] - rationale - backend/school.py
- [[Session_11]] - code
- [[What same school means, in one place. school_id None is the main pool…]] - rationale - backend/school.py
- [[progress.py]] - code - backend/progress.py
- [[progress_for_user()]] - code - backend/progress.py
- [[school.py]] - code - backend/school.py
- [[sqlalchemy]] - concept
- [[test_roadmap_marks_done_next_and_builds_a_study_plan()]] - code - backend/tests/test_learning.py
- [[visible_subjects()]] - code - backend/school.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/User_Progress_Tracking
SORT file.name ASC
```

## Connections to other communities
- 16 edges to [[_COMMUNITY_Subject Data Management]]
- 12 edges to [[_COMMUNITY_Topic Classification]]
- 9 edges to [[_COMMUNITY_Authorization and Database Setup]]
- 6 edges to [[_COMMUNITY_Reminders and Learning API]]
- 4 edges to [[_COMMUNITY_User Chat API]]
- 2 edges to [[_COMMUNITY_Learning Progress Tests]]
- 2 edges to [[_COMMUNITY_School Management API]]
- 1 edge to [[_COMMUNITY_Application Startup and Migrations]]

## Top bridge nodes
- [[school.py]] - degree 15, connects to 6 communities
- [[LessonCompletion]] - degree 16, connects to 5 communities
- [[progress.py]] - degree 13, connects to 5 communities
- [[sqlalchemy]] - degree 8, connects to 5 communities
- [[progress_for_user()]] - degree 12, connects to 4 communities