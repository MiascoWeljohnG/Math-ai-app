---
type: community
cohesion: 0.06
members: 70
---

# Subject Data Management

**Cohesion:** 0.06 - loosely connected
**Members:** 70 nodes

## Members
- [[A teacheradmin asked to delete a shared subject. It only disappears once EVERY…]] - rationale - backend/models.py
- [[Base]] - code
- [[BaseModel_1]] - code
- [[Decision]] - code - backend/routes/subject_deletion_routes.py
- [[Deleting a shared subject needs every admin's approval. teacheradmin POST…]] - rationale - backend/routes/subject_deletion_routes.py
- [[Deleting a shared subject needs every admin's approval; lessons can be…]] - rationale - backend/tests/test_subject_workflow.py
- [[DeletionRequest]] - code - backend/routes/subject_deletion_routes.py
- [[Lesson]] - code - backend/models.py
- [[One admin's answer to a deletion request (approve=TrueFalse). One row per…]] - rationale - backend/models.py
- [[Remove a subject with its lessons, quizzes and completion records. The caller…]] - rationale - backend/routes/subjects_routes.py
- [[SQL filter rows of one school. NULL needs IS NULL, `== None` would be wrong in…]] - rationale - backend/school.py
- [[SQL filter the shared (teacher-made) subjects of the user's own school.]] - rationale - backend/school.py
- [[Session_1]] - code
- [[Settle a pending request after a vote. Returns its new status. The caller has…]] - rationale - backend/routes/subject_deletion_routes.py
- [[Student ranking for the landing page (students) and the monitor on the teacher…]] - rationale - backend/routes/learning_routes.py
- [[Subject]] - code - backend/models.py
- [[SubjectDeletionRequest]] - code - backend/models.py
- [[SubjectDeletionVote]] - code - backend/models.py
- [[The students of this teacher's school, each with their real progress per math…]] - rationale - backend/routes/teacher_routes.py
- [[_admin_usernames()]] - code - backend/routes/subject_deletion_routes.py
- [[_attempt()]] - code - backend/tests/test_learning.py
- [[_iso()]] - code - backend/routes/subject_deletion_routes.py
- [[_resolve()]] - code - backend/routes/subject_deletion_routes.py
- [[_serialize()]] - code - backend/routes/subject_deletion_routes.py
- [[_votes()]] - code - backend/routes/subject_deletion_routes.py
- [[analyze()]] - code - backend/tests/test_subject_workflow.py
- [[api()]] - code - backend/tests/test_adaptive.py
- [[api()_1]] - code - backend/tests/test_learning.py
- [[api()_2]] - code - backend/tests/test_subject_workflow.py
- [[as_user()]] - code - backend/tests/test_subject_workflow.py
- [[choice()]] - code - backend/tests/test_subject_workflow.py
- [[decide()]] - code - backend/routes/subject_deletion_routes.py
- [[delete_subject_cascade()]] - code - backend/routes/subjects_routes.py
- [[fixture]] - code
- [[fixture_1]] - code
- [[fixture_2]] - code
- [[get_1]] - code
- [[get_2]] - code
- [[in_school()]] - code - backend/school.py
- [[list_pending_requests()]] - code - backend/routes/subject_deletion_routes.py
- [[list_students()]] - code - backend/routes/teacher_routes.py
- [[login()]] - code - backend/tests/test_learning.py
- [[parametrize]] - code
- [[post_1]] - code
- [[ranked()]] - code - backend/tests/test_learning.py
- [[rankings()]] - code - backend/routes/learning_routes.py
- [[request_subject_deletion()]] - code - backend/routes/subject_deletion_routes.py
- [[shared_subjects()]] - code - backend/school.py
- [[subject_deletion_routes.py]] - code - backend/routes/subject_deletion_routes.py
- [[subject_exists()]] - code - backend/tests/test_subject_workflow.py
- [[test_admin_can_change_their_vote_while_pending()]] - code - backend/tests/test_subject_workflow.py
- [[test_admin_requester_counts_as_approved()]] - code - backend/tests/test_subject_workflow.py
- [[test_an_admin_added_later_must_approve_too()]] - code - backend/tests/test_subject_workflow.py
- [[test_analyze_existing_subject_returns_titles()]] - code - backend/tests/test_subject_workflow.py
- [[test_analyze_new_branch_saves_nothing()]] - code - backend/tests/test_subject_workflow.py
- [[test_analyze_not_math_and_model_failure()]] - code - backend/tests/test_subject_workflow.py
- [[test_analyze_unknown_file_is_404()]] - code - backend/tests/test_subject_workflow.py
- [[test_new_branch_then_lesson_generated_from_the_file()]] - code - backend/tests/test_subject_workflow.py
- [[test_one_rejection_keeps_the_subject()]] - code - backend/tests/test_subject_workflow.py
- [[test_other_students_personal_subject_is_hidden()]] - code - backend/tests/test_quiz.py
- [[test_parse_subject_choice()]] - code - backend/tests/test_subject_workflow.py
- [[test_personal_or_missing_subjects_cannot_be_requested()]] - code - backend/tests/test_subject_workflow.py
- [[test_personal_subjects_never_appear_in_rankings()]] - code - backend/tests/test_learning.py
- [[test_request_is_pending_and_subject_stays()]] - code - backend/tests/test_subject_workflow.py
- [[test_second_request_for_same_subject_is_refused()]] - code - backend/tests/test_subject_workflow.py
- [[test_shared_subject_names_are_unique_and_teacher_only()]] - code - backend/tests/test_subject_workflow.py
- [[test_sole_admin_deletes_immediately()]] - code - backend/tests/test_subject_workflow.py
- [[test_students_cannot_request_and_teachers_cannot_decide()]] - code - backend/tests/test_subject_workflow.py
- [[test_subject_is_deleted_only_after_all_admins_approve()]] - code - backend/tests/test_subject_workflow.py
- [[test_subject_workflow.py]] - code - backend/tests/test_subject_workflow.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Subject_Data_Management
SORT file.name ASC
```

## Connections to other communities
- 57 edges to [[_COMMUNITY_Topic Classification]]
- 25 edges to [[_COMMUNITY_Authorization and Database Setup]]
- 16 edges to [[_COMMUNITY_User Progress Tracking]]
- 12 edges to [[_COMMUNITY_Reminders and Learning API]]
- 11 edges to [[_COMMUNITY_Learning Progress Tests]]
- 10 edges to [[_COMMUNITY_Quiz Evaluation]]
- 7 edges to [[_COMMUNITY_Application Startup and Migrations]]
- 6 edges to [[_COMMUNITY_Materials Ingestion Tests]]
- 6 edges to [[_COMMUNITY_Branch Classifier Tests]]
- 5 edges to [[_COMMUNITY_Practice Generation API]]
- 4 edges to [[_COMMUNITY_School Management API]]
- 4 edges to [[_COMMUNITY_User Chat API]]
- 3 edges to [[_COMMUNITY_Adaptive Learning Tests]]
- 2 edges to [[_COMMUNITY_Adaptive Difficulty Model]]
- 2 edges to [[_COMMUNITY_Material Upload API]]
- 1 edge to [[_COMMUNITY_School Administration API]]
- 1 edge to [[_COMMUNITY_Authentication and Schools]]
- 1 edge to [[_COMMUNITY_Notification API]]

## Top bridge nodes
- [[Subject]] - degree 56, connects to 12 communities
- [[Base]] - degree 17, connects to 11 communities
- [[test_subject_workflow.py]] - degree 45, connects to 8 communities
- [[Lesson]] - degree 41, connects to 8 communities
- [[subject_deletion_routes.py]] - degree 35, connects to 7 communities