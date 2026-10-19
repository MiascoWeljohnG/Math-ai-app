---
source_file: "backend/routes/subjects_routes.py"
type: "code"
community: "Topic Classification"
location: "L902"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/Topic_Classification
---

# submit_quiz()

## Connections
- [[LessonQuiz]] - `uses` [INFERRED]
- [[QuizAttempt]] - `uses` [INFERRED]
- [[Session]] - `references` [EXTRACTED]
- [[SubmitQuizRequest]] - `references` [EXTRACTED]
- [[User]] - `uses` [INFERRED]
- [[_display_answer()]] - `calls` [EXTRACTED]
- [[_is_correct()]] - `calls` [EXTRACTED]
- [[_lesson_in_subject_or_404()]] - `calls` [EXTRACTED]
- [[_visible_subject_or_404()]] - `calls` [EXTRACTED]
- [[post]] - `references` [EXTRACTED]
- [[subjects_routes.py]] - `contains` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/Topic_Classification