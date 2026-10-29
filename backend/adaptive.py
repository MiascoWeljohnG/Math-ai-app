"""Adaptive learning, in one place. A student's quiz history on a lesson becomes a mastery level, and the
level decides what the roadmap tells them to do and which practice set they are offered.

  new         no quiz attempt yet
  struggling  not passed, and either 2+ failed attempts or a best score under 60%
  developing  not passed, best score 60-79% (the pass mark is 80%)
  proficient  passed, but under 90% or it took 3+ attempts
  mastered    passed with 90%+ within the first 2 attempts

What each level changes:
  struggling  roadmap adds "review the previous lesson" and an easier practice set before the retake
  developing  roadmap adds an easier practice set before the retake
  mastered    the NEXT lesson is fast-tracked (quiz first, skip the reading if passed) and a harder set is offered
Edit the numbers below and the roadmap, the practice sets and the teacher table all follow."""
from typing import Optional

from models import QuizAttempt

MASTERED_PERCENT = 90
MASTERED_MAX_ATTEMPTS = 2
STRUGGLING_PERCENT = 60
STRUGGLING_FAILS = 2

LEVELS = ("struggling", "developing", "proficient", "mastered")


def mastery_level(attempts: int, best_percent: Optional[int], passed: bool) -> str:
    if not attempts:
        return "new"
    best = best_percent or 0
    if passed:
        return "mastered" if best >= MASTERED_PERCENT and attempts <= MASTERED_MAX_ATTEMPTS else "proficient"
    return "struggling" if best < STRUGGLING_PERCENT or attempts >= STRUGGLING_FAILS else "developing"


def practice_kind(level: str) -> Optional[str]:
    """The extra practice set a level is offered: easier while behind, harder once mastered."""
    return {"struggling": "easier", "developing": "easier", "mastered": "harder"}.get(level)


def level_counts(db, user_ids: list[int], lesson_ids: list[int]) -> dict[int, dict[str, int]]:
    """For each student: how many of these lessons sit at each level (the teacher table)."""
    tries: dict[tuple[int, int], list] = {}   # (student, lesson) -> [attempts, best percent, passed]
    for user_id, lesson_id, score, total, passed in (
        db.query(QuizAttempt.user_id, QuizAttempt.lesson_id, QuizAttempt.score, QuizAttempt.total, QuizAttempt.passed)
        .filter(QuizAttempt.user_id.in_(user_ids), QuizAttempt.lesson_id.in_(lesson_ids))
    ):
        t = tries.setdefault((user_id, lesson_id), [0, 0, False])
        t[0] += 1
        t[1] = max(t[1], round(score * 100 / max(total, 1)))
        t[2] = t[2] or passed
    counts = {user_id: {level: 0 for level in LEVELS} for user_id in user_ids}
    for (user_id, _), (attempts, best, passed) in tries.items():
        counts[user_id][mastery_level(attempts, best, passed)] += 1
    return counts
