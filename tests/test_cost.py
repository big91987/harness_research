from harness.cost import ModelPricing, canonical_usage


def test_canonical_usage_accepts_provider_aliases() -> None:
    assert canonical_usage({"input_tokens": 7, "output_tokens": 3}) == {
        "prompt_tokens": 7,
        "completion_tokens": 3,
        "total_tokens": 10,
    }


def test_model_pricing_estimates_input_and_output_cost() -> None:
    pricing = ModelPricing(input_cost_per_million_tokens=1.0, output_cost_per_million_tokens=2.0)

    assert pricing.estimate({"prompt_tokens": 1_000_000, "completion_tokens": 500_000}) == 2.0
