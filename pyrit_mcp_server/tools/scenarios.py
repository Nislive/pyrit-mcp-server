"""MCP tools for PyRIT pre-built scenarios (AIRT, Garak, etc.)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from pyrit_mcp_server.core import TargetRegistry, ensure_memory


def register(mcp: FastMCP) -> None:
    """Register scenario tools on the MCP server."""

    @mcp.tool()
    async def list_scenarios() -> dict[str, Any]:
        """List available pre-built PyRIT scenarios.

        Returns:
            Dict with scenario names and descriptions.
        """
        scenarios = {
            "airt.ContentHarms": "AIRT content harms scenario — tests for harmful content generation across multiple categories.",
            "airt.Jailbreak": "AIRT jailbreak scenario — tests jailbreak resistance with various techniques.",
            "airt.Cyber": "AIRT cyber scenario — tests for cyber-attack assistance.",
            "airt.Leakage": "AIRT leakage scenario — tests for data/prompt leakage vulnerabilities.",
            "airt.Psychosocial": "AIRT psychosocial scenario — tests for psychosocial harm generation.",
            "airt.Scam": "AIRT scam scenario — tests for scam content generation.",
            "airt.RapidResponse": "AIRT rapid response scenario — tests rapid response capabilities.",
            "garak.Encoding": "Garak encoding scenario — tests encoding-based evasion techniques.",
            "foundry.RedTeamAgent": "Foundry Red Team Agent scenario.",
        }
        return {"status": "success", "scenarios": scenarios}

    @mcp.tool()
    async def run_scenario(
        scenario_name: str,
        target_id: str,
        adversarial_chat_id: str = "",
        scorer_target_id: str = "",
        max_objectives: int = 5,
        strategies: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run a pre-built PyRIT scenario against a target.

        Args:
            scenario_name: Scenario to run (e.g. "airt.ContentHarms").
                Use list_scenarios to see available options.
            target_id: ID of the target to test.
            adversarial_chat_id: ID of adversarial LLM target (for multi-turn scenarios).
            scorer_target_id: ID of LLM target for scoring. Defaults to adversarial_chat_id.
            max_objectives: Maximum number of objectives to test (default 5).
            strategies: Optional list of strategy names to limit the run (e.g. ["base64"]
                for garak.Encoding). Each scenario defaults to running ALL strategies, which
                can be very expensive; pass a subset to keep runs short.

        Returns:
            Dict with scenario execution results.
        """
        try:
            ensure_memory()

            target = TargetRegistry.get(target_id)

            # Scenario classes are imported from pyrit.scenario.scenarios.*
            scenario_map = {
                "airt.ContentHarms": ("pyrit.scenario.scenarios.airt", "ContentHarms"),
                "airt.Jailbreak": ("pyrit.scenario.scenarios.airt", "Jailbreak"),
                "airt.Cyber": ("pyrit.scenario.scenarios.airt", "Cyber"),
                "airt.Leakage": ("pyrit.scenario.scenarios.airt", "Leakage"),
                "airt.Psychosocial": ("pyrit.scenario.scenarios.airt", "Psychosocial"),
                "airt.Scam": ("pyrit.scenario.scenarios.airt", "Scam"),
                "airt.RapidResponse": ("pyrit.scenario.scenarios.airt", "RapidResponse"),
                "garak.Encoding": ("pyrit.scenario.scenarios.garak", "Encoding"),
            }

            entry = scenario_map.get(scenario_name)
            if not entry:
                return {
                    "status": "error",
                    "error": f"Unknown scenario '{scenario_name}'. Available: {list(scenario_map.keys())}",
                }

            import importlib

            module = importlib.import_module(entry[0])
            scenario_cls = getattr(module, entry[1])

            # PyRIT 0.14.0: scenario constructors take an objective_scorer (NOT a target);
            # the target is supplied later via initialize_async(objective_target=...).
            ctor_kwargs: dict[str, Any] = {}

            # Most airt scenarios default to an Azure-Content-Filter scorer that is
            # unavailable offline. When a local LLM target is given, use a self-ask
            # refusal scorer (a TrueFalseScorer) so the scenario runs against Ollama/etc.
            scorer_id = scorer_target_id or adversarial_chat_id
            if scorer_id:
                from pyrit.score import SelfAskRefusalScorer

                ctor_kwargs["objective_scorer"] = SelfAskRefusalScorer(
                    chat_target=TargetRegistry.get(scorer_id)
                )

            scenario = scenario_cls(**ctor_kwargs)

            # Honour max_objectives by clamping the scenario's default dataset size
            # (the constructors don't expose an objective-count parameter directly).
            cfg = getattr(scenario, "_default_dataset_config", None)
            if cfg is not None and getattr(cfg, "max_dataset_size", None) is not None:
                if cfg.max_dataset_size > max_objectives:
                    cfg.max_dataset_size = max_objectives

            # The scenario resolves its objectives from seed datasets stored in
            # CentralMemory. With ephemeral (:memory:) memory those tables are empty,
            # so load the scenario's required datasets first (idempotent per process).
            if cfg is not None:
                from pyrit.datasets import SeedDatasetProvider
                from pyrit.memory import CentralMemory

                memory = CentralMemory.get_memory_instance()
                needed = [
                    n for n in cfg.get_default_dataset_names()
                    if not memory.get_seeds(dataset_name=n)
                ]
                if needed:
                    loaded = await SeedDatasetProvider.fetch_datasets_async(dataset_names=needed)
                    await memory.add_seed_datasets_to_memory_async(
                        datasets=loaded, added_by="mcp_run_scenario"
                    )

            # Resolve optional strategy subset against the scenario's own strategy enum
            # (each member is keyed by its lowercase value, e.g. "base64").
            scenario_strategies = None
            if strategies:
                strat_cls = scenario._strategy_class
                resolved = []
                for name in strategies:
                    try:
                        resolved.append(strat_cls(name))
                    except ValueError:
                        return {
                            "status": "error",
                            "error": f"Unknown strategy '{name}' for {scenario_name}. "
                            f"Valid: {[m.value for m in strat_cls]}",
                        }
                scenario_strategies = resolved

            await scenario.initialize_async(
                objective_target=target,
                scenario_strategies=scenario_strategies,
                max_concurrency=2,
                max_retries=0,
            )

            result = await scenario.run_async()

            # Summarize results — ScenarioResult.attack_results is a list of AttackResult.
            summary = []
            for r in getattr(result, "attack_results", []) or []:
                outcome = getattr(r, "outcome", None)
                last = getattr(r, "last_response", None)
                summary.append({
                    "outcome": outcome.value if hasattr(outcome, "value") else str(outcome),
                    "objective": getattr(r, "objective", None),
                    "last_response": last.converted_value if last is not None else None,
                })

            try:
                achieved_rate = result.objective_achieved_rate()
            except Exception:
                achieved_rate = None

            return {
                "status": "success",
                "scenario": scenario_name,
                "objective_achieved_rate": achieved_rate,
                "total_results": len(summary),
                "results": summary[:50],  # cap output size
            }
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}
