from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def source_path(name):
    paths = {
        "voiceover-ax-observer.swift": "src/swift/VoiceOver/voiceover-ax-observer.swift",
        "voiceover-link-verbosity.swift": "src/swift/VoiceOver/voiceover-link-verbosity.swift",
        "probe-simulator-voiceover-activation.m": "src/objc/VoiceOver/probe-simulator-voiceover-activation.m",
    }
    return ROOT / paths[name]
