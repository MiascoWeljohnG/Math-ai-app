---
source_file: "backend/routes/practice_routes.py"
type: "code"
community: "Practice Generation API"
location: "L27"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/Practice_Generation_API
---

# _standing()

## Connections
- [[(level, kind of practice offered, the student's latest attempt) from their quiz…]] - `rationale_for` [EXTRACTED]
- [[QuizAttempt]] - `uses` [INFERRED]
- [[Session_5]] - `references` [EXTRACTED]
- [[User]] - `uses` [INFERRED]
- [[generate_practice()]] - `calls` [EXTRACTED]
- [[get_practice()]] - `calls` [EXTRACTED]
- [[mastery_level()]] - `calls` [EXTRACTED]
- [[practice_kind()]] - `calls` [EXTRACTED]
- [[practice_routes.py]] - `contains` [EXTRACTED]
- [[submit_practice()]] - `calls` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/Practice_Generation_API