from datasets import load_dataset


DATASET_NAME = "knkarthick/AMI"


def main():
    dataset = load_dataset(DATASET_NAME)

    print(f"Downloaded {DATASET_NAME}")
    for split_name, split in dataset.items():
        print(f"{split_name}: {len(split)} rows")

    sample = dataset["train"][0]
    print("\nColumns:", ", ".join(dataset["train"].column_names))
    print("\nSample dialogue:")
    print(sample["dialogue"][:1000].strip())
    print("\nSample summary:")
    print(sample["summary"].strip())


if __name__ == "__main__":
    main()
