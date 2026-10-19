---
type: community
cohesion: 0.10
members: 22
---

# Learning Progress Tests

**Cohesion:** 0.10 - loosely connected
**Members:** 22 nodes

## Members
- [[Every graded quiz attempt by a student. Feeds the leaderboard, the roadmap and…]] - rationale - backend/models.py
- [[Quiz attempts, failed-quiz breakdown, leaderboard, roadmapstudy plan and…]] - rationale - backend/tests/test_learning.py
- [[QuizAttempt]] - code - backend/models.py
- [[Session_4]] - code
- [[__init__.py]] - code - backend/routes/__init__.py
- [[get_current_user()]] - code - backend/auth.py
- [[test_breakdown_model_failure_is_a_502_and_can_be_retried()]] - code - backend/tests/test_learning.py
- [[test_breakdown_needs_a_failed_attempt()]] - code - backend/tests/test_learning.py
- [[test_failed_lesson_stays_next_and_plan_says_to_review()]] - code - backend/tests/test_learning.py
- [[test_failed_quiz_gets_an_ai_breakdown_that_is_saved()]] - code - backend/tests/test_learning.py
- [[test_leaderboard_ranks_best_attempt_then_speed_and_marks_you()]] - code - backend/tests/test_learning.py
- [[test_learning.py]] - code - backend/tests/test_learning.py
- [[test_notification_model_exists_and_routes_import()]] - code - backend/tests/test_learning.py
- [[test_rankings_filter_by_branch()]] - code - backend/tests/test_learning.py
- [[test_rankings_order_by_lessons_passed_then_average_then_time()]] - code - backend/tests/test_learning.py
- [[test_reminder_rules()]] - code - backend/tests/test_learning.py
- [[test_reported_time_is_capped_near_the_quiz_limit()]] - code - backend/tests/test_learning.py
- [[test_student_outside_the_top_still_sees_their_own_rank()]] - code - backend/tests/test_learning.py
- [[test_submit_saves_the_attempt_with_time_and_missed_questions()]] - code - backend/tests/test_learning.py
- [[test_teacher_preview_is_not_recorded()]] - code - backend/tests/test_learning.py
- [[test_teacher_reminders_reach_the_right_students()]] - code - backend/tests/test_learning.py
- [[test_teachers_see_usernames_and_attempts_but_students_do_not()]] - code - backend/tests/test_learning.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Learning_Progress_Tests
SORT file.name ASC
```

## Connections to other communities
- 11 edges to [[_COMMUNITY_Subject Data Management]]
- 9 edges to [[_COMMUNITY_Authorization and Database Setup]]
- 8 edges to [[_COMMUNITY_Topic Classification]]
- 5 edges to [[_COMMUNITY_Adaptive Learning Tests]]
- 4 edges to [[_COMMUNITY_Reminders and Learning API]]
- 4 edges to [[_COMMUNITY_Practice Generation API]]
- 4 edges to [[_COMMUNITY_Materials Ingestion Tests]]
- 3 edges to [[_COMMUNITY_Quiz Evaluation]]
- 3 edges to [[_COMMUNITY_Application Startup and Migrations]]
- 2 edges to [[_COMMUNITY_Adaptive Difficulty Model]]
- 2 edges to [[_COMMUNITY_User Progress Tracking]]
- 2 edges to [[_COMMUNITY_Branch Classifier Tests]]
- 1 edge to [[_COMMUNITY_Profile Management API]]
- 1 edge to [[_COMMUNITY_User Chat API]]
- 1 edge to [[_COMMUNITY_Administrator API]]
- 1 edge to [[_COMMUNITY_Notification API]]

## Top bridge nodes
- [[test_learning.py]] - degree 43, connects to 11 communities
- [[get_current_user()]] - degree 15, connects to 11 communities
- [[QuizAttempt]] - degree 23, connects to 7 communities
- [[__init__.py]] - degree 7, connects to 6 communities