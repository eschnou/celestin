import pytest

from app.domain.errors import ProviderUnavailable
from tests.fixtures.fake_completion import FakeCompletion, data, text


async def test_scripted_results_in_order_and_recorded_calls():
    fake = FakeCompletion([text("# T"), data({"title": "T"}), ProviderUnavailable()])
    first = await fake.complete(role="authoring", instructions=["A"], input=[{"role": "user", "content": "x"}], max_output_tokens=1)
    second = await fake.complete(role="authoring", instructions=["B"], input=[], schema=dict, max_output_tokens=1)  # type: ignore[arg-type]
    assert first.text == "# T" and second.data == {"title": "T"}
    assert fake.calls[0]["instructions"] == ["A"] and fake.calls[1]["schema"] is dict
    with pytest.raises(ProviderUnavailable):
        await fake.complete(role="authoring", instructions=[], input=[], max_output_tokens=1)
    with pytest.raises(AssertionError):
        await fake.complete(role="authoring", instructions=[], input=[], max_output_tokens=1)


async def test_the_fake_accepts_the_progress_callback_of_the_protocol():
    fake = FakeCompletion([text("# T")])
    result = await fake.complete(
        role="authoring", instructions=[], input=[], max_output_tokens=1, on_progress=lambda snapshot: None
    )
    assert result.text == "# T"
