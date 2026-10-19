---
source_file: "backend/routes/subjects_routes.py"
type: "code"
community: "Topic Classification"
location: "L144"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/Topic_Classification
---

# _delete_lesson_children()

## Connections
- [[LessonCompletion]] - `uses` [INFERRED]
- [[LessonQuiz]] - `uses` [INFERRED]
- [[PracticeSet]] - `uses` [INFERRED]
- [[Session]] - `references` [EXTRACTED]
- [[delete_lesson()]] - `calls` [EXTRACTED]
- [[delete_subject_cascade()]] - `calls` [EXTRACTED]
- [[subjects_routes.py]] - `contains` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/Topic_Classification