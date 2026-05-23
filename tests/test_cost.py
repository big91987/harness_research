from harness.cost import ModelPricing, RuntimeBudget, canonical_usage


def test_canonical_usage_accepts_provider_aliases() -> None:
    assert canonical_usage({"input_tokens": 7, "output_tokens": 3}) == {
        "prompt_tokens": 7,
        "completion_tokens": 3,
        "total_tokens": 10,
    }


def test_model_pricing_estimates_input_and_output_cost() -> None:
    pricing = ModelPricing(input_cost_per_million_tokens=1.0, output_cost_per_million_tokens=2.0)

    assert pricing.estimate({"prompt_tokens": 1_000_000, "completion_tokens": 500_000}) == 2.0


def test_runtime_budget_reports_exceeded_limits() -> None:
    budget = RuntimeBudget(max_total_tokens=100, max_cost_usd=0.05)

    assert budget.check(total_tokens=101, cost_usd=0.03) == "total tokens 101 exceeded limit 100"
    assert budget.check(total_tokens=99, cost_usd=0.06) == "cost 0.060000 exceeded limit 0.050000"
    assert budget.check(total_tokens=99, cost_usd=0.03) is None
