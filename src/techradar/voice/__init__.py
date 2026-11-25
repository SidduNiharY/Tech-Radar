"""Voice Coach (Phase 6).

Import the submodule you need (`techradar.voice.intake`, `techradar.voice.retention`, ...). This
package imports nothing itself: `audio`, `pronounce` and `pitch` need numpy, and the bot image
(which imports `voice.intake` and `voice.retention`) and the worker image may not have it.
"""
