from __future__ import annotations

from techradar.jarvis.skill_impl.briefing import speak_briefing
from techradar.jarvis.skill_impl.exams import speak_exam_status
from techradar.jarvis.skill_impl.help import speak_help
from techradar.jarvis.skill_impl.library import speak_library_summary
from techradar.jarvis.skill_impl.planner import speak_daily_plan
from techradar.jarvis.skill_impl.practice import speak_practice_due
from techradar.jarvis.skill_impl.search import speak_search_result
from techradar.jarvis.skill_impl.status import speak_system_status
from techradar.jarvis.skill_impl.voice import speak_voice_feedback
from techradar.jarvis.skill_impl.world import speak_world_update

__all__ = [
    "speak_briefing",
    "speak_daily_plan",
    "speak_exam_status",
    "speak_help",
    "speak_library_summary",
    "speak_practice_due",
    "speak_search_result",
    "speak_system_status",
    "speak_voice_feedback",
    "speak_world_update",
]
