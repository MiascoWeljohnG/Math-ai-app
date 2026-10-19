---
source_file: "backend/tests/test_classifier.py"
type: "code"
community: "Branch Classifier Tests"
location: "L1"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/Branch_Classifier_Tests
---

# test_classifier.py

## Connections
- [[FakeUpload]] - `contains` [EXTRACTED]
- [[Material]] - `imports` [EXTRACTED]
- [[Subject]] - `imports` [EXTRACTED]
- [[User]] - `imports` [EXTRACTED]
- [[classifier.py]] - `imports` [EXTRACTED]
- [[client()]] - `contains` [EXTRACTED]
- [[fastapi_testclient]] - `imports_from` [EXTRACTED]
- [[get_db()]] - `imports` [EXTRACTED]
- [[json]] - `imports` [EXTRACTED]
- [[models.py]] - `imports_from` [EXTRACTED]
- [[pytest]] - `imports` [EXTRACTED]
- [[run_upload()]] - `contains` [EXTRACTED]
- [[subjects_routes.py]] - `imports_from` [EXTRACTED]
- [[test_bad_inputs_are_400()]] - `contains` [EXTRACTED]
- [[test_cannot_generate_into_someone_elses_or_a_shared_subject()]] - `contains` [EXTRACTED]
- [[test_classify_branch()]] - `contains` [EXTRACTED]
- [[test_confident_file_is_saved_under_detected_branch()]] - `contains` [EXTRACTED]
- [[test_explicit_branch_still_works_like_before()]] - `contains` [EXTRACTED]
- [[test_force_skips_the_check_and_typed_topic_is_the_title()]] - `contains` [EXTRACTED]
- [[test_mixed_batch_saves_the_sure_ones_and_asks_about_the_rest()]] - `contains` [EXTRACTED]
- [[test_outline_from_file_rejects_other_peoples_subjects()]] - `contains` [EXTRACTED]
- [[test_outline_from_file_returns_clean_titles()]] - `contains` [EXTRACTED]
- [[test_parse_scores_garbage_is_empty()]] - `contains` [EXTRACTED]
- [[test_parse_scores_normalises_and_tolerates_markdown()]] - `contains` [EXTRACTED]
- [[test_related_file_generates_a_lesson()]] - `contains` [EXTRACTED]
- [[test_relevant_text_finds_the_pages_about_the_topic()]] - `contains` [EXTRACTED]
- [[test_sample_text_keeps_start_middle_and_end()]] - `contains` [EXTRACTED]
- [[test_suggest_fills_title_and_description()]] - `contains` [EXTRACTED]
- [[test_suggest_rejects_unreadable_and_unparseable()]] - `contains` [EXTRACTED]
- [[test_suggest_truncates_to_the_subject_limits()]] - `contains` [EXTRACTED]
- [[test_threshold_is_exactly_70()]] - `contains` [EXTRACTED]
- [[test_unrelated_file_warns_and_creates_nothing()]] - `contains` [EXTRACTED]
- [[test_unsure_file_is_not_saved_and_is_reported()]] - `contains` [EXTRACTED]
- [[test_uploader_pick_is_used_without_asking_the_model()]] - `contains` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/Branch_Classifier_Tests