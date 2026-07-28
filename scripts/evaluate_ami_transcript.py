import argparse
import re
from pathlib import Path

from datasets import load_dataset
from jiwer import cer, wer


DATASET_NAME = "knkarthick/AMI"


def normalize_text(text):
    text = text.lower()
    text = re.sub(r"speaker\s+[a-z]:", " ", text)
    text = re.sub(r"[^a-z0-9\s']", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def read_transcript(path):
    text = Path(path).read_text(encoding="utf-8")
    marker = "FULL TRANSCRIPTION"
    if marker in text:
        text = text.split(marker, 1)[1]
        text = text.split("TIMESTAMPED SEGMENTS", 1)[0]
    return text.strip()


def main():
    parser = argparse.ArgumentParser(
        description="Compare a transcript text file with one AMI dialogue reference."
    )
    parser.add_argument("--transcript", default="recordings/transcription.txt")
    parser.add_argument("--split", default="test", choices=["train", "validation", "test"])
    parser.add_argument("--index", type=int, default=0)
    args = parser.parse_args()

    dataset = load_dataset(DATASET_NAME, split=args.split)
    reference = normalize_text(dataset[args.index]["dialogue"])
    prediction = normalize_text(read_transcript(args.transcript))

    print(f"Dataset: {DATASET_NAME}")
    print(f"Reference: {args.split}[{args.index}]")
    print(f"Transcript: {args.transcript}")
    print(f"WER: {wer(reference, prediction):.4f}")
    print(f"CER: {cer(reference, prediction):.4f}")


if __name__ == "__main__":
    main()
