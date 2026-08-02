from __future__ import annotations

import argparse
import json
from pathlib import Path

from faster_whisper import WhisperModel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("--output", type=Path, default=Path("transcript.json"))
    args = parser.parse_args()

    model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(
        str(args.audio),
        language="en",
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,
    )

    words: list[dict[str, object]] = []
    for segment in segments:
        for word in segment.words or []:
            text = word.word.strip()
            if text:
                words.append(
                    {
                        "text": text,
                        "start": round(float(word.start), 3),
                        "end": round(float(word.end), 3),
                    }
                )

    args.output.write_text(json.dumps(words, indent=2), encoding="utf-8")
    print(f"Wrote {len(words)} timestamped words to {args.output}")


if __name__ == "__main__":
    main()
