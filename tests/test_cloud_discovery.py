"""Tests for cloud discovery state providers."""

from sqlit.shared.app.services import MockCloudStateProvider


class DummyProvider:
    def __init__(self, provider_id: str) -> None:
        self.id = provider_id


def test_mock_cloud_state_provider_filters_known_ids():
    """Test mock provider returns states only for known providers."""
    providers = [DummyProvider("azure"), DummyProvider("unknown")]
    provider = MockCloudStateProvider()
    states = provider(providers)
    assert states is not None
    assert "azure" in states
    assert "unknown" not in states
