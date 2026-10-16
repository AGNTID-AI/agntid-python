from pathlib import Path


README = Path(__file__).resolve().parents[2] / "examples" / "README.md"


def test_shared_setup_matches_current_runtime_registration_and_demo_flow() -> None:
    guide = " ".join(README.read_text(encoding="utf-8").split())

    checkpoints = (
        "Generate Bootstrap Token",
        "Edit runtime name",
        "Enable demos",
        "Catalog verified",
        "Review Actions",
        "Approve Classification",
        "baseline allow policy automatically",
        "runtime scope synchronization to show **Applied**",
    )
    positions = [guide.index(checkpoint) for checkpoint in checkpoints]

    assert positions == sorted(positions)
    assert "Name the runtime, generate its one-time bootstrap token" not in guide
    assert "Setup completion does not enable demo servers" in guide
    assert "do not create a second baseline policy" in guide
