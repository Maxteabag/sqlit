"""Data generation helpers for mock connections."""

from __future__ import annotations


def generate_fake_data(row_count: int) -> tuple[list[str], list[tuple]]:
    """Generate fake data rows using Faker if available, otherwise basic data.

    Args:
        row_count: Number of rows to generate.

    Returns:
        Tuple of (columns, rows).
    """
    try:
        from faker import Faker

        fake = Faker()
        Faker.seed(42)  # Reproducible results

        columns = ["id", "name", "email", "phone", "address", "created_at"]
        rows = []
        for i in range(row_count):
            rows.append(
                (
                    i + 1,
                    fake.name(),
                    fake.email(),
                    fake.phone_number(),
                    fake.address().replace("\n", ", "),
                    fake.date_time().isoformat(),
                )
            )
        return columns, rows

    except ImportError:
        # Faker not installed - generate simple data
        columns = ["id", "name", "email", "value", "status", "created_at"]
        rows = []
        statuses = ["active", "inactive", "pending", "archived"]
        for i in range(row_count):
            rows.append(
                (
                    i + 1,
                    f"User {i + 1}",
                    f"user{i + 1}@example.com",
                    f"{round((i * 17.5) % 1000, 2):.2f}",  # Pseudo-random values
                    statuses[i % len(statuses)],
                    f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
                )
            )
        return columns, rows


def generate_long_text_data(row_count: int) -> tuple[list[str], list[tuple]]:
    """Generate data with long varchar columns for testing truncation.

    Creates columns with varying text lengths to test UI truncation behavior.
    Useful for verifying how long text fields are displayed/truncated.

    Args:
        row_count: Number of rows to generate.

    Returns:
        Tuple of (columns, rows).
    """
    # Column lengths designed to test truncation boundaries
    text_lengths = {
        "short_text": 15,       # Short, no truncation expected
        "medium_text": 50,      # Around typical column width
        "long_text": 150,       # Definitely needs truncation
        "very_long_text": 500,  # Very long content
        "description": 300,     # Realistic long field
    }

    columns = ["id", "name"] + list(text_lengths.keys())
    rows = []

    for i in range(row_count):
        row: list[object] = [i + 1, f"Row {i + 1}"]
        for col_name, length in text_lengths.items():
            # Generate text with visible pattern showing row number and column
            base = f"[R{i + 1}:{col_name[:6]}]"
            # Fill with Lorem-style content
            filler = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
            text = base + (filler * ((length // len(filler)) + 1))
            text = text[:length]
            row.append(text)
        rows.append(tuple(row))

    return columns, rows
