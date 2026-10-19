---
type: community
cohesion: 0.08
members: 34
---

# Branch Classifier Tests

**Cohesion:** 0.08 - loosely connected
**Members:** 34 nodes

## Members
- [[dot-__init__()]] - code - backend/tests/test_classifier.py
- [[dot-read()]] - code - backend/tests/test_classifier.py
- [[Algebra 80' lines - {label share of the total}. Empty dict if nothing usable.]] - rationale - backend/classifier.py
- [[FakeUpload]] - code - backend/tests/test_classifier.py
- [[classify_branch()]] - code - backend/classifier.py
- [[client()]] - code - backend/tests/test_classifier.py
- [[fastapi_testclient]] - concept
- [[fixture_7]] - code
- [[json]] - concept
- [[parametrize_3]] - code
- [[parse_scores()]] - code - backend/classifier.py
- [[run_upload()]] - code - backend/tests/test_classifier.py
- [[test_bad_inputs_are_400()]] - code - backend/tests/test_classifier.py
- [[test_cannot_generate_into_someone_elses_or_a_shared_subject()]] - code - backend/tests/test_classifier.py
- [[test_classifier.py]] - code - backend/tests/test_classifier.py
- [[test_classify_branch()]] - code - backend/tests/test_classifier.py
- [[test_confident_file_is_saved_under_detected_branch()]] - code - backend/tests/test_classifier.py
- [[test_explicit_branch_still_works_like_before()]] - code - backend/tests/test_classifier.py
- [[test_force_skips_the_check_and_typed_topic_is_the_title()]] - code - backend/tests/test_classifier.py
- [[test_mixed_batch_saves_the_sure_ones_and_asks_about_the_rest()]] - code - backend/tests/test_classifier.py
- [[test_outline_from_file_rejects_other_peoples_subjects()]] - code - backend/tests/test_classifier.py
- [[test_outline_from_file_returns_clean_titles()]] - code - backend/tests/test_classifier.py
- [[test_parse_scores_garbage_is_empty()]] - code - backend/tests/test_classifier.py
- [[test_parse_scores_normalises_and_tolerates_markdown()]] - code - backend/tests/test_classifier.py
- [[test_related_file_generates_a_lesson()]] - code - backend/tests/test_classifier.py
- [[test_sample_text_keeps_start_middle_and_end()]] - code - backend/tests/test_classifier.py
- [[test_suggest_fills_title_and_description()]] - code - backend/tests/test_classifier.py
- [[test_suggest_rejects_unreadable_and_unparseable()]] - code - backend/tests/test_classifier.py
- [[test_suggest_truncates_to_the_subject_limits()]] - code - backend/tests/test_classifier.py
- [[test_threshold_is_exactly_70()]] - code - backend/tests/test_classifier.py
- [[test_unrelated_file_warns_and_creates_nothing()]] - code - backend/tests/test_classifier.py
- [[test_unsure_file_is_not_saved_and_is_reported()]] - code - backend/tests/test_classifier.py
- [[test_uploader_pick_is_used_without_asking_the_model()]] - code - backend/tests/test_classifier.py
- [[{branch, confidence (0-1), scores, reason}. `reason` is None when the…]] - rationale - backend/classifier.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Branch_Classifier_Tests
SORT file.name ASC
```

## Connections to other communities
- 11 edges to [[_COMMUNITY_Topic Classification]]
- 6 edges to [[_COMMUNITY_Subject Data Management]]
- 6 edges to [[_COMMUNITY_Authorization and Database Setup]]
- 2 edges to [[_COMMUNITY_Administrator API]]
- 2 edges to [[_COMMUNITY_Learning Progress Tests]]
- 2 edges to [[_COMMUNITY_Adaptive Learning Tests]]
- 2 edges to [[_COMMUNITY_Quiz Evaluation]]
- 2 edges to [[_COMMUNITY_Materials Ingestion Tests]]
- 1 edge to [[_COMMUNITY_User Chat API]]
- 1 edge to [[_COMMUNITY_Practice Generation API]]
- 1 edge to [[_COMMUNITY_Retrieval Augmented Generation]]

## Top bridge nodes
- [[json]] - degree 10, connects to 8 communities
- [[fastapi_testclient]] - degree 7, connects to 6 communities
- [[test_classifier.py]] - degree 34, connects to 4 communities
- [[classify_branch()]] - degree 7, connects to 2 communities
- [[client()]] - degree 4, connects to 2 communities