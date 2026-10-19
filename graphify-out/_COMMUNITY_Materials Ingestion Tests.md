---
type: community
cohesion: 0.11
members: 35
---

# Materials Ingestion Tests

**Cohesion:** 0.11 - loosely connected
**Members:** 35 nodes

## Members
- [[School A and B, each with a teacher, a student and an admin, plus the main…]] - rationale - backend/tests/test_schools.py
- [[Schools accounts, subjects, files, reminders and deletion requests are…]] - rationale - backend/tests/test_schools.py
- [[Tests run without OllamaChroma `rag` is replaced by a small fake whose model…]] - rationale - backend/tests/conftest.py
- [[account()]] - code - backend/tests/test_schools.py
- [[api()_6]] - code - backend/tests/test_schools.py
- [[as_()]] - code - backend/tests/test_schools.py
- [[ask_stream()_1]] - code - backend/tests/conftest.py
- [[conftest.py]] - code - backend/tests/conftest.py
- [[db()]] - code - backend/tests/conftest.py
- [[extract_text_from_bytes()_1]] - code - backend/tests/conftest.py
- [[fixture_5]] - code
- [[fixture_6]] - code
- [[generate_text()_1]] - code - backend/tests/conftest.py
- [[ingest_uploaded_materials()_1]] - code - backend/tests/conftest.py
- [[person()]] - code - backend/tests/test_schools.py
- [[pytest]] - concept
- [[rag()]] - code - backend/tests/conftest.py
- [[school()]] - code - backend/tests/test_schools.py
- [[sys]] - concept
- [[test_admin_and_teacher_accounts_are_made_for_a_school()]] - code - backend/tests/test_schools.py
- [[test_admin_registers_student_numbers_and_signup_follows_the_list()]] - code - backend/tests/test_schools.py
- [[test_deletion_requests_are_listed_per_school_and_the_main_admin_sees_all()]] - code - backend/tests/test_schools.py
- [[test_main_admin_adds_a_school_with_the_starting_subjects()]] - code - backend/tests/test_schools.py
- [[test_only_the_default_admin_creates_admins()]] - code - backend/tests/test_schools.py
- [[test_only_the_main_admin_adds_schools()]] - code - backend/tests/test_schools.py
- [[test_reminders_for_everyone_stay_in_the_school()]] - code - backend/tests/test_schools.py
- [[test_school_admin_only_reaches_their_own_school()]] - code - backend/tests/test_schools.py
- [[test_school_admin_registers_students_for_their_own_school_only()]] - code - backend/tests/test_schools.py
- [[test_schools.py]] - code - backend/tests/test_schools.py
- [[test_students_pick_a_school_once_schools_exist()]] - code - backend/tests/test_schools.py
- [[test_subjects_are_separate_per_school()]] - code - backend/tests/test_schools.py
- [[test_teachers_only_see_their_schools_students()]] - code - backend/tests/test_schools.py
- [[test_uploaded_files_are_separate_per_school()]] - code - backend/tests/test_schools.py
- [[two_schools()]] - code - backend/tests/test_schools.py
- [[types]] - concept

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Materials_Ingestion_Tests
SORT file.name ASC
```

## Connections to other communities
- 9 edges to [[_COMMUNITY_Authorization and Database Setup]]
- 7 edges to [[_COMMUNITY_Topic Classification]]
- 6 edges to [[_COMMUNITY_Subject Data Management]]
- 5 edges to [[_COMMUNITY_Application Startup and Migrations]]
- 4 edges to [[_COMMUNITY_Learning Progress Tests]]
- 3 edges to [[_COMMUNITY_Authentication and Schools]]
- 2 edges to [[_COMMUNITY_Adaptive Learning Tests]]
- 2 edges to [[_COMMUNITY_Branch Classifier Tests]]
- 1 edge to [[_COMMUNITY_Reminders and Learning API]]
- 1 edge to [[_COMMUNITY_School Administration API]]
- 1 edge to [[_COMMUNITY_School Management API]]
- 1 edge to [[_COMMUNITY_Quiz Evaluation]]
- 1 edge to [[_COMMUNITY_Administrator API]]

## Top bridge nodes
- [[test_schools.py]] - degree 44, connects to 11 communities
- [[pytest]] - degree 8, connects to 6 communities
- [[types]] - degree 6, connects to 4 communities
- [[conftest.py]] - degree 11, connects to 1 community
- [[person()]] - degree 6, connects to 1 community