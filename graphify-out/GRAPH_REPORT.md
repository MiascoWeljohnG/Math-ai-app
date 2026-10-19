# Graph Report - Math-ai-app  (2026-10-20)

## Corpus Check
- 76 files · ~68,144 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 21 file(s) not represented in the graph (top: .bin 12, .css 5, (none) 1)

## Summary
- 1003 nodes · 2464 edges · 61 communities (46 shown, 15 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 293 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Topic Classification
- Subject Data Management
- Teacher Dashboard
- Administrator Dashboard
- Retrieval Augmented Generation
- Quiz Evaluation
- Materials Ingestion Tests
- Branch Classifier Tests
- Interactive Quiz Interface
- Administrator API
- Lesson Learning Flow
- Authorization and Database Setup
- Application Startup and Migrations
- User Chat API
- Student Chat Interface
- Materials and Subject Management
- Learning Progress Tests
- Adaptive Learning Tests
- Practice Generation API
- Reminders and Learning API
- Landing Page and Onboarding
- Materials Interface
- School Administration API
- Practice Session Interface
- Authentication and Schools
- School Management API
- Notification API
- User Progress Tracking
- Adaptive Difficulty Model
- School Admin Dashboard
- Authentication Interface
- Profile Management API
- School Admin Interface
- Material Upload API
- Navigation Drawer
- Learning Roadmap Interface
- Profile Editor Interface
- Topic Selection Interface
- Student Registry Interface
- Account Registration
- Branding and Logo Assets
- Material Table Interface
- Modal Dialogs
- Rankings Interface
- Reminder Interface
- Theme Switching
- Markdown Message Rendering
- Learning Activity Pages
- Code Quality Principles
- Administration Workflows
- Lesson Completion Experience
- Course Materials Experience
- AI Conversation Experience
- Graphify Workflow Documentation
- Password Visibility Icon
- Logo Eye Asset
- Brand Wordmark Asset
- Visibility Toggle Icon
- User Login Page
- User Profile Editor

## God Nodes (most connected - your core abstractions)
1. `User` - 126 edges
2. `Subject` - 56 edges
3. `Lesson` - 41 edges
4. `Material` - 32 edges
5. `LessonQuiz` - 23 edges
6. `QuizAttempt` - 23 edges
7. `get_db()` - 22 edges
8. `generate_text()` - 19 edges
9. `_visible_subject_or_404()` - 17 edges
10. `shared_subjects()` - 17 edges

## Surprising Connections (you probably didn't know these)
- `test_cannot_generate_into_someone_elses_or_a_shared_subject()` --uses--> `Subject`  [INFERRED]
  backend/tests/test_classifier.py → backend/models.py
- `test_outline_from_file_rejects_other_peoples_subjects()` --uses--> `Subject`  [INFERRED]
  backend/tests/test_classifier.py → backend/models.py
- `level_counts()` --uses--> `QuizAttempt`  [INFERRED]
  backend/adaptive.py → backend/models.py
- `get_current_user()` --uses--> `User`  [INFERRED]
  backend/auth.py → backend/models.py
- `require_admin()` --uses--> `User`  [INFERRED]
  backend/auth.py → backend/models.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Teacher Curriculum Authoring Workflow** — frontend_teacher_lesson_management, frontend_teacher_ai_lesson_drafting, frontend_teacher_course_outline_generation, frontend_teacher_file_based_lesson_generation [EXTRACTED 1.00]

## Communities (61 total, 15 thin omitted)

### Community 0 - "Topic Classification"
Cohesion: 0.06
Nodes (60): check_relevance(), choose_subject(), document_text(), _line_value(), parse_subject_choice(), read_upload(), relevant_text(), sample_text() (+52 more)

### Community 1 - "Subject Data Management"
Cohesion: 0.06
Nodes (45): Lesson, Subject, SubjectDeletionRequest, SubjectDeletionVote, rankings(), _admin_usernames(), decide(), Decision (+37 more)

### Community 2 - "Teacher Dashboard"
Cohesion: 0.07
Nodes (58): addFiles(), addSubject(), createSubject(), deleteLesson(), deleteSubjectBtn, deletionNote, draftBtn, draftLesson() (+50 more)

### Community 3 - "Administrator Dashboard"
Cohesion: 0.07
Nodes (46): addFiles(), addSchool(), allUsers, bellBadge, bellBtn, bellItem(), bellList, bellPanel (+38 more)

### Community 4 - "Retrieval Augmented Generation"
Cohesion: 0.08
Nodes (27): migrate_legacy_uploads(), _answer_source(), ask_stream(), _chunks_for_pages(), extract_text_by_page(), extract_text_from_bytes(), _gemini_generate(), _gemini_request() (+19 more)

### Community 5 - "Quiz Evaluation"
Cohesion: 0.07
Nodes (24): LessonQuiz, _finish_question(), _id_matches(), _is_correct(), _norm_text(), _parse_difficulty(), _parse_quiz(), _tf_value() (+16 more)

### Community 6 - "Materials Ingestion Tests"
Cohesion: 0.11
Nodes (21): db(), rag(), account(), api(), as_(), person(), school(), test_admin_and_teacher_accounts_are_made_for_a_school() (+13 more)

### Community 7 - "Branch Classifier Tests"
Cohesion: 0.08
Nodes (18): classify_branch(), parse_scores(), client(), FakeUpload, run_upload(), test_bad_inputs_are_400(), test_cannot_generate_into_someone_elses_or_a_shared_subject(), test_classify_branch() (+10 more)

### Community 8 - "Interactive Quiz Interface"
Cohesion: 0.14
Nodes (33): answers, api(), buildAnswer(), clock(), confirmSubmit(), describeTime(), fail(), generate() (+25 more)

### Community 9 - "Administrator API"
Cohesion: 0.12
Nodes (17): ingest_with_detection(), notify_admins(), add_registered(), add_registered_students(), clear_knowledge_base(), create_admin(), create_teacher(), CreateTeacherRequest (+9 more)

### Community 10 - "Lesson Learning Flow"
Cohesion: 0.10
Nodes (30): activeLessons, askReadyForQuiz(), buildCompleteFooter(), generateBox, generateBtn, generateFile, generateStatus, generateTopic (+22 more)

### Community 11 - "Authorization and Database Setup"
Cohesion: 0.12
Nodes (7): require_school_admin(), require_teacher(), require_teacher_or_admin(), get_db(), Material, UsageLog, api()

### Community 12 - "Application Startup and Migrations"
Cohesion: 0.12
Nodes (8): migrate_add_missing_columns(), root(), ingest_uploads(), _display_name(), get_material_file(), list_materials(), reindex_vault(), _vault_material_path()

### Community 13 - "User Chat API"
Cohesion: 0.16
Nodes (15): ChatMessage, Conversation, queue_status(), ask_question(), event_stream(), create_conversation(), delete_conversation(), get_conversation_messages() (+7 more)

### Community 14 - "Student Chat Interface"
Cohesion: 0.14
Nodes (25): addMessage(), attachImageBtn, authHeaders(), chat, clearPendingImage(), conversations, convoList, deleteConversation() (+17 more)

### Community 15 - "Materials and Subject Management"
Cohesion: 0.09
Nodes (24): Knowledge Base Deletion, Knowledge Base File Listing, Knowledge Base Upload and Ingestion, Math Branch Classification, Course Modules, File-Based Subject Generation, iChatbot, Math Branches (+16 more)

### Community 16 - "Learning Progress Tests"
Cohesion: 0.10
Nodes (5): get_current_user(), QuizAttempt, test_reported_time_is_capped_near_the_quiz_limit(), test_submit_saves_the_attempt_with_time_and_missed_questions(), test_teacher_preview_is_not_recorded()

### Community 17 - "Adaptive Learning Tests"
Cohesion: 0.24
Nodes (17): attempt(), practice_url(), roadmap(), test_a_bad_model_reply_is_rejected_and_nothing_is_saved(), test_a_new_attempt_gets_a_new_set(), test_deleting_a_lesson_removes_its_practice_sets(), test_failed_quiz_gets_an_easier_set_written_once(), test_mastered_student_gets_a_harder_set() (+9 more)

### Community 18 - "Practice Generation API"
Cohesion: 0.22
Nodes (9): PracticeSet, generate_practice(), get_practice(), _payload(), _saved(), _standing(), submit_practice(), SubmitPracticeRequest (+1 more)

### Community 19 - "Reminders and Learning API"
Cohesion: 0.18
Nodes (8): Reminder, create_reminder(), delete_reminder(), list_reminders(), _minutes(), ReminderRequest, roadmap(), _serialize_reminder()

### Community 20 - "Landing Page and Onboarding"
Cohesion: 0.20
Nodes (17): authHeader, coreSubjectIds, createLessonsFromFile(), firstNameOf(), getJson(), loadRoadmapSummary(), loadSubjectsAndProgress(), openBranch() (+9 more)

### Community 21 - "Materials Interface"
Cohesion: 0.18
Nodes (17): addAskMessage(), allFiles, askInput, askLog, askSendBtn, authHeaders(), BRANCH_FILTERS, branchFilterEl (+9 more)

### Community 22 - "School Administration API"
Cohesion: 0.21
Nodes (9): RegisteredStudent, delete_registered_student(), remove_registered(), add_school_students(), create_school_teacher(), delete_school_student(), list_school_students(), school_files() (+1 more)

### Community 23 - "Practice Session Interface"
Cohesion: 0.21
Nodes (12): api(), BLURB, buildQuestion(), fail(), init(), lessonId, node(), params (+4 more)

### Community 24 - "Authentication and Schools"
Cohesion: 0.28
Nodes (8): create_access_token(), hash_password(), verify_password(), School, login(), LoginRequest, register(), RegisterRequest

### Community 25 - "School Management API"
Cohesion: 0.21
Nodes (5): require_admin(), create_school(), list_schools(), SchoolRequest, signup_mode()

### Community 26 - "Notification API"
Cohesion: 0.32
Nodes (6): Notification, clear_notifications(), list_notifications(), mark_all_read(), mark_read(), _mine()

### Community 27 - "User Progress Tracking"
Cohesion: 0.23
Nodes (4): LessonCompletion, progress_for_user(), visible_subjects(), test_roadmap_marks_done_next_and_builds_a_study_plan()

### Community 28 - "Adaptive Difficulty Model"
Cohesion: 0.20
Nodes (5): level_counts(), mastery_level(), practice_kind(), test_mastery_level_rules(), test_which_practice_each_level_is_offered()

### Community 29 - "School Admin Dashboard"
Cohesion: 0.18
Nodes (11): Admin Account Creation, Admin Dashboard, Admin Notifications, Registered Student Registry, School Management, Teacher Account Creation, School Admin Dashboard, School File Listing (+3 more)

### Community 30 - "Authentication Interface"
Cohesion: 0.22
Nodes (6): authForm, homeFor(), openCal(), registerForm, renderCal(), requireRole()

### Community 31 - "Profile Management API"
Cohesion: 0.29
Nodes (5): _display_name(), get_profile(), ProfileUpdate, _serialize(), update_profile()

### Community 32 - "School Admin Interface"
Cohesion: 0.29
Nodes (9): allUsers, esc(), getHeaders(), loadFiles(), loadUsers(), renderUsers(), teacherFields, teacherModal (+1 more)

### Community 33 - "Material Upload API"
Cohesion: 0.25
Nodes (3): material_summary(), my_files(), teacher_upload()

### Community 34 - "Navigation Drawer"
Cohesion: 0.33
Nodes (3): currentPageName(), initNavDrawer(), NAV_ITEMS

### Community 35 - "Learning Roadmap Interface"
Cohesion: 0.38
Nodes (5): el(), headers, LEVEL_LABEL, renderReminders(), renderSubject()

### Community 36 - "Profile Editor Interface"
Cohesion: 0.60
Nodes (5): authHeaders(), fill(), load(), setSelect(), showMsg()

### Community 37 - "Topic Selection Interface"
Cohesion: 0.53
Nodes (5): askTopics(), postUpload(), TOPIC_CHOICES, topicHint(), uploadWithTopics()

### Community 38 - "Student Registry Interface"
Cohesion: 0.70
Nodes (4): addRegistered(), initRegistry(), loadRegistry(), removeRegistered()

### Community 39 - "Account Registration"
Cohesion: 0.40
Nodes (5): Account Credentials, Account Signup, School Selection, Student ID Registration, Terms and Privacy Consent

### Community 40 - "Branding and Logo Assets"
Cohesion: 0.50
Nodes (4): Division Symbol, Eye Motif, iSPNAYAN Logo, iSPNAYAN Wordmark

### Community 41 - "Material Table Interface"
Cohesion: 0.83
Nodes (3): downloadMaterial(), formatUploadDate(), renderMaterialRows()

### Community 42 - "Modal Dialogs"
Cohesion: 0.67
Nodes (3): openModal(), close(), onKey()

### Community 43 - "Rankings Interface"
Cohesion: 0.67
Nodes (3): initRankings(), load(), row()

### Community 44 - "Reminder Interface"
Cohesion: 0.83
Nodes (3): call(), loadReminders(), loadStudents()

### Community 47 - "Learning Activity Pages"
Cohesion: 0.67
Nodes (3): Practice Set, Interactive Quiz, Learning Roadmap

## Knowledge Gaps
- **151 isolated node(s):** `allUsers`, `schools`, `existingFileNames`, `dropZone`, `fileInput` (+146 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 359 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `User` connect `Topic Classification` to `Subject Data Management`, `Quiz Evaluation`, `Materials Ingestion Tests`, `Branch Classifier Tests`, `Administrator API`, `Authorization and Database Setup`, `Application Startup and Migrations`, `User Chat API`, `Learning Progress Tests`, `Adaptive Learning Tests`, `Practice Generation API`, `Reminders and Learning API`, `School Administration API`, `Authentication and Schools`, `School Management API`, `Notification API`, `User Progress Tracking`, `Profile Management API`, `Material Upload API`?**
  _High betweenness centrality (0.117) - this node is a cross-community bridge._
- **Why does `Subject` connect `Subject Data Management` to `Topic Classification`, `Quiz Evaluation`, `Materials Ingestion Tests`, `Branch Classifier Tests`, `Authorization and Database Setup`, `Application Startup and Migrations`, `Learning Progress Tests`, `Adaptive Learning Tests`, `Practice Generation API`, `Reminders and Learning API`, `School Management API`, `User Progress Tracking`?**
  _High betweenness centrality (0.019) - this node is a cross-community bridge._
- **Why does `Material` connect `Authorization and Database Setup` to `Topic Classification`, `Subject Data Management`, `Material Upload API`, `Retrieval Augmented Generation`, `Materials Ingestion Tests`, `Branch Classifier Tests`, `Administrator API`, `Application Startup and Migrations`, `User Chat API`, `School Administration API`?**
  _High betweenness centrality (0.012) - this node is a cross-community bridge._
- **Are the 98 inferred relationships involving `User` (e.g. with `get_current_user()` and `require_admin()`) actually correct?**
  _`User` has 98 INFERRED edges - model-reasoned connections that need verification._
- **Are the 35 inferred relationships involving `Subject` (e.g. with `progress_for_user()` and `rankings()`) actually correct?**
  _`Subject` has 35 INFERRED edges - model-reasoned connections that need verification._
- **Are the 26 inferred relationships involving `Lesson` (e.g. with `progress_for_user()` and `rankings()`) actually correct?**
  _`Lesson` has 26 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `Material` (e.g. with `clear_knowledge_base()` and `delete_file()`) actually correct?**
  _`Material` has 14 INFERRED edges - model-reasoned connections that need verification._