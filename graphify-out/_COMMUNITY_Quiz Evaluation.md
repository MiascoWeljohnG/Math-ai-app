---
type: community
cohesion: 0.07
members: 42
---

# Quiz Evaluation

**Cohesion:** 0.07 - loosely connected
**Members:** 42 nodes

## Members
- [[12', '-3.5', '34' - an exact Fraction, so 0.75 and 34 match and 0.33 is not…]] - rationale - backend/routes/subjects_routes.py
- [[Flexible identification check numbers match by value ('5' = '5.0' = 'c = 5'),…]] - rationale - backend/routes/subjects_routes.py
- [[Fraction]] - code
- [[Identification answers as comparable words lower case, no punctuation, no…]] - rationale - backend/routes/subjects_routes.py
- [[Identification answers ignore case, a leading aanthe, spaces and trailing…]] - rationale - backend/routes/subjects_routes.py
- [[LessonQuiz]] - code - backend/models.py
- [[One quiz per lesson. `questions` is JSON {type mcqtfidnum, question,…]] - rationale - backend/models.py
- [[Quiz parsing, grading and endpoints. The model is faked (see conftest.py).]] - rationale - backend/tests/test_quiz.py
- [[Read the plain-text quiz format (TYPE  Q  A) B) C) D)  ANSWER  WHY).…]] - rationale - backend/routes/subjects_routes.py
- [[Turn one parsed block into a stored question, or None if the model got it wrong.]] - rationale - backend/routes/subjects_routes.py
- [[_finish_question()]] - code - backend/routes/subjects_routes.py
- [[_id_matches()]] - code - backend/routes/subjects_routes.py
- [[_is_correct()]] - code - backend/routes/subjects_routes.py
- [[_norm_text()]] - code - backend/routes/subjects_routes.py
- [[_parse_difficulty()]] - code - backend/routes/subjects_routes.py
- [[_parse_quiz()]] - code - backend/routes/subjects_routes.py
- [[_tf_value()]] - code - backend/routes/subjects_routes.py
- [[_to_number()]] - code - backend/routes/subjects_routes.py
- [[_words()]] - code - backend/routes/subjects_routes.py
- [[api()_5]] - code - backend/tests/test_quiz.py
- [[fixture_4]] - code
- [[parametrize_2]] - code
- [[score_with()]] - code - backend/tests/test_quiz.py
- [[spy()_1]] - code - backend/tests/test_quiz.py
- [[test_identification_accepts_short_form_even_if_ai_listed_only_the_full_term()]] - code - backend/tests/test_quiz.py
- [[test_identification_ignores_case_articles_and_spacing_and_accepts_alternatives()]] - code - backend/tests/test_quiz.py
- [[test_identification_with_a_numeric_answer_matches_by_value()]] - code - backend/tests/test_quiz.py
- [[test_numeric_answers_must_be_exactly_right()]] - code - backend/tests/test_quiz.py
- [[test_parse_drops_broken_questions_and_clamps_difficulty()]] - code - backend/tests/test_quiz.py
- [[test_parse_reads_all_four_types_and_difficulty()]] - code - backend/tests/test_quiz.py
- [[test_parse_without_type_lines_falls_back_to_multiple_choice()]] - code - backend/tests/test_quiz.py
- [[test_pass_mark_is_80_percent()]] - code - backend/tests/test_quiz.py
- [[test_prompt_asks_for_synonyms_and_single_number_answers()]] - code - backend/tests/test_quiz.py
- [[test_quiz.py]] - code - backend/tests/test_quiz.py
- [[test_quiz_payload_tells_the_page_the_pass_mark()]] - code - backend/tests/test_quiz.py
- [[test_student_generates_quiz_once_and_never_sees_answers()]] - code - backend/tests/test_quiz.py
- [[test_students_cannot_replace_a_quiz_but_teachers_can()]] - code - backend/tests/test_quiz.py
- [[test_submit_grades_on_the_server()]] - code - backend/tests/test_quiz.py
- [[test_true_false_and_multiple_choice_need_the_right_kind_of_value()]] - code - backend/tests/test_quiz.py
- [[test_unanswered_questions_score_zero_and_missing_quiz_is_404()]] - code - backend/tests/test_quiz.py
- [[test_unreadable_model_output_is_a_502_and_saves_nothing()]] - code - backend/tests/test_quiz.py
- [[types_namespace()]] - code - backend/tests/test_quiz.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Quiz_Evaluation
SORT file.name ASC
```

## Connections to other communities
- 22 edges to [[_COMMUNITY_Topic Classification]]
- 10 edges to [[_COMMUNITY_Subject Data Management]]
- 6 edges to [[_COMMUNITY_Practice Generation API]]
- 5 edges to [[_COMMUNITY_Authorization and Database Setup]]
- 3 edges to [[_COMMUNITY_Learning Progress Tests]]
- 2 edges to [[_COMMUNITY_Reminders and Learning API]]
- 2 edges to [[_COMMUNITY_Branch Classifier Tests]]
- 1 edge to [[_COMMUNITY_Adaptive Learning Tests]]
- 1 edge to [[_COMMUNITY_Materials Ingestion Tests]]
- 1 edge to [[_COMMUNITY_Application Startup and Migrations]]

## Top bridge nodes
- [[test_quiz.py]] - degree 36, connects to 8 communities
- [[LessonQuiz]] - degree 23, connects to 6 communities
- [[_is_correct()]] - degree 11, connects to 2 communities
- [[_parse_quiz()]] - degree 9, connects to 2 communities
- [[api()_5]] - degree 6, connects to 2 communities