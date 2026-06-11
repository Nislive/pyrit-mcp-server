"""MCP tools for PyRIT attack strategies.

Single-turn attacks run synchronously and return results immediately.
Multi-turn attacks (red_team, crescendo, pair, tap) are long-running and
return a job_id immediately. Use get_job_status / list_jobs to poll.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from pyrit_mcp_server.core import JobManager, TargetRegistry, ensure_memory

# ---------------------------------------------------------------------------
# Hard limits — prevents runaway token consumption
# ---------------------------------------------------------------------------
MAX_TURNS_LIMIT = 30
MAX_TREE_WIDTH_LIMIT = 10
MAX_TREE_DEPTH_LIMIT = 15
MAX_BRANCHING_LIMIT = 5


def _clamp(value: int, upper: int) -> int:
    return max(1, min(value, upper))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_groups_from_objective(objective: str):  # noqa: ANN202
    from pyrit.models.seeds.seed_attack_group import SeedAttackGroup
    from pyrit.models.seeds.seed_objective import SeedObjective

    return [SeedAttackGroup(seeds=[SeedObjective(value=objective)])]


def _make_atomic(*, attack, seed_groups, name: str = "mcp_attack"):  # noqa: ANN001, ANN202
    from pyrit.scenario.core.atomic_attack import AtomicAttack
    from pyrit.scenario.core.attack_technique import AttackTechnique

    return AtomicAttack(
        atomic_attack_name=name,
        attack_technique=AttackTechnique(attack=attack),
        seed_groups=seed_groups,
    )


async def _run_atomic(atomic) -> list[dict[str, Any]]:  # noqa: ANN001
    from pyrit.executor.attack import AttackExecutor

    result = await atomic.run_async(executor=AttackExecutor(max_concurrency=1))
    out = []
    for r in result.completed_results:
        out.append({
            "outcome": r.outcome.value,
            "objective": r.objective,
            "last_response": r.last_response.converted_value if r.last_response else None,
            "executed_turns": r.executed_turns,
            "execution_time_ms": r.execution_time_ms,
            "score": {
                "value": r.last_score.score_value,
                "type": r.last_score.score_type,
                "rationale": r.last_score.score_rationale,
            } if r.last_score else None,
        })
    return out


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register(mcp: FastMCP) -> None:
    """Register attack tools on the MCP server."""

    # ------------------------------------------------------------------
    # Job management (for long-running attacks)
    # ------------------------------------------------------------------

    @mcp.tool()
    async def get_job_status(job_id: str) -> dict[str, Any]:
        """Check the status of a background attack job.

        Args:
            job_id: The job ID returned by a multi-turn attack tool.

        Returns:
            Dict with job status (pending/running/completed/failed) and results when done.
        """
        return JobManager.get(job_id)

    @mcp.tool()
    async def list_jobs() -> dict[str, Any]:
        """List all background attack jobs.

        Returns:
            Dict with list of all jobs and their statuses.
        """
        return {"status": "success", "jobs": JobManager.list_all()}

    @mcp.tool()
    async def wait_for_job(
        job_id: str,
        timeout_seconds: int = 900,
        poll_interval_seconds: int = 5,
    ) -> dict[str, Any]:
        """Block until a background attack job finishes, then return its result.

        Call this ONCE after launching a multi-turn attack (red_team, crescendo,
        pair, tap) instead of calling get_job_status in a loop. The server waits
        internally and returns only when the job reaches 'completed' / 'failed',
        or when timeout_seconds elapses. The background attack keeps running while
        this waits, so no LLM tokens are spent polling.

        If it returns with status still 'running' (timed_out=True), the job is not
        finished — call wait_for_job again with the same job_id to keep waiting.

        Args:
            job_id: The job ID returned by a multi-turn attack tool.
            timeout_seconds: Max seconds to block (default 900, hard cap 1800).
            poll_interval_seconds: Seconds between internal status checks (default 5).
        """
        timeout = max(1, min(timeout_seconds, 1800))
        interval = max(1, min(poll_interval_seconds, 60))
        waited = 0
        while True:
            status = JobManager.get(job_id)
            # Terminal states: completed, failed, or error (job not found).
            if status.get("status") in ("completed", "failed", "error"):
                return status
            if waited >= timeout:
                status["timed_out"] = True
                status["waited_seconds"] = waited
                return status
            await asyncio.sleep(interval)
            waited += interval

    # ------------------------------------------------------------------
    # Single-turn attacks (synchronous — return immediately)
    # ------------------------------------------------------------------

    @mcp.tool()
    async def send_prompt(
        objective: str,
        target_id: str,
    ) -> dict[str, Any]:
        """Single-turn prompt sending attack (PromptSendingAttack).

        Sends the objective directly to the target and returns the response.
        This is synchronous and returns immediately.

        Args:
            objective: The text/objective to send.
            target_id: ID of a registered target.
        """
        try:
            ensure_memory()
            from pyrit.executor.attack import PromptSendingAttack

            target = TargetRegistry.get(target_id)
            attack = PromptSendingAttack(objective_target=target)
            atomic = _make_atomic(
                attack=attack,
                seed_groups=_seed_groups_from_objective(objective),
                name="mcp_send_prompt",
            )
            results = await _run_atomic(atomic)
            return {"status": "success", "results": results}
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}

    @mcp.tool()
    async def run_skeleton_key_attack(
        objective: str,
        target_id: str,
    ) -> dict[str, Any]:
        """Skeleton Key attack — single-turn jailbreak technique.

        Synchronous — returns immediately.

        Args:
            objective: The attack objective.
            target_id: ID of the target to attack.
        """
        try:
            ensure_memory()
            from pyrit.executor.attack import SkeletonKeyAttack

            target = TargetRegistry.get(target_id)
            attack = SkeletonKeyAttack(objective_target=target)
            atomic = _make_atomic(
                attack=attack,
                seed_groups=_seed_groups_from_objective(objective),
                name="mcp_skeleton_key",
            )
            results = await _run_atomic(atomic)
            return {"status": "success", "strategy": "skeleton_key", "results": results}
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}

    @mcp.tool()
    async def run_flip_attack(
        objective: str,
        target_id: str,
    ) -> dict[str, Any]:
        """Flip attack — reversal-based single-turn jailbreak.

        Synchronous — returns immediately.

        Args:
            objective: The attack objective.
            target_id: ID of the target to attack.
        """
        try:
            ensure_memory()
            from pyrit.executor.attack import FlipAttack

            target = TargetRegistry.get(target_id)
            attack = FlipAttack(objective_target=target)
            atomic = _make_atomic(
                attack=attack,
                seed_groups=_seed_groups_from_objective(objective),
                name="mcp_flip",
            )
            results = await _run_atomic(atomic)
            return {"status": "success", "strategy": "flip", "results": results}
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}

    @mcp.tool()
    async def run_role_play_attack(
        objective: str,
        target_id: str,
        adversarial_chat_id: str,
        scenario: str = "video_game",
    ) -> dict[str, Any]:
        """Role Play attack — persona-based single-turn jailbreak.

        Synchronous — returns immediately. Requires an adversarial LLM to
        rephrase the objective into a role-play scenario.

        Args:
            objective: The attack objective.
            target_id: ID of the target to attack.
            adversarial_chat_id: ID of the LLM target used to rephrase the objective.
            scenario: Role-play scenario type. One of: video_game, movie_script,
                trivia_game, persuasion_script, persuasion_script_written.
        """
        try:
            ensure_memory()
            from pyrit.executor.attack import RolePlayAttack
            from pyrit.executor.attack.core.attack_config import AttackAdversarialConfig
            from pyrit.executor.attack.single_turn.role_play import RolePlayPaths

            scenarios_map = {
                "video_game": RolePlayPaths.VIDEO_GAME,
                "movie_script": RolePlayPaths.MOVIE_SCRIPT,
                "trivia_game": RolePlayPaths.TRIVIA_GAME,
                "persuasion_script": RolePlayPaths.PERSUASION_SCRIPT,
                "persuasion_script_written": RolePlayPaths.PERSUASION_SCRIPT_WRITTEN,
            }
            rp_path = scenarios_map.get(scenario)
            if not rp_path:
                return {
                    "status": "error",
                    "error": f"Unknown scenario '{scenario}'. Available: {list(scenarios_map.keys())}",
                }

            target = TargetRegistry.get(target_id)
            adv = TargetRegistry.get(adversarial_chat_id)
            attack = RolePlayAttack(
                objective_target=target,
                attack_adversarial_config=AttackAdversarialConfig(target=adv),
                role_play_definition_path=rp_path.value,
            )
            atomic = _make_atomic(
                attack=attack,
                seed_groups=_seed_groups_from_objective(objective),
                name="mcp_role_play",
            )
            results = await _run_atomic(atomic)
            return {"status": "success", "strategy": "role_play", "scenario": scenario, "results": results}
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}

    # ------------------------------------------------------------------
    # Multi-turn attacks (background job — returns job_id immediately)
    # ------------------------------------------------------------------

    @mcp.tool()
    async def run_red_team_attack(
        objective: str,
        target_id: str,
        adversarial_chat_id: str,
        max_turns: int = 10,
    ) -> dict[str, Any]:
        """Multi-turn red teaming attack (RedTeamingAttack). BACKGROUND JOB.

        Returns a job_id immediately. Use get_job_status to poll for results.
        An adversarial LLM iteratively generates prompts to achieve the objective.

        Args:
            objective: The attack objective.
            target_id: ID of the target to attack.
            adversarial_chat_id: ID of the target to use as adversarial LLM.
            max_turns: Maximum conversation turns (default 10, hard limit 30).
        """
        try:
            ensure_memory()
            turns = _clamp(max_turns, MAX_TURNS_LIMIT)

            from pyrit.executor.attack import (
                AttackAdversarialConfig,
                AttackScoringConfig,
                RedTeamingAttack,
                RTASystemPromptPaths,
            )
            from pyrit.score import SelfAskTrueFalseScorer, TrueFalseQuestionPaths

            target = TargetRegistry.get(target_id)
            adv = TargetRegistry.get(adversarial_chat_id)
            scorer_target = TargetRegistry._new_instance(adversarial_chat_id)

            objective_scorer = SelfAskTrueFalseScorer(
                chat_target=scorer_target,
                true_false_question_path=TrueFalseQuestionPaths.TASK_ACHIEVED.value,
            )

            attack = RedTeamingAttack(
                objective_target=target,
                attack_adversarial_config=AttackAdversarialConfig(
                    target=adv,
                    system_prompt_path=RTASystemPromptPaths.TEXT_GENERATION.value,
                ),
                attack_scoring_config=AttackScoringConfig(
                    objective_scorer=objective_scorer,
                ),
                max_turns=turns,
            )
            atomic = _make_atomic(
                attack=attack,
                seed_groups=_seed_groups_from_objective(objective),
                name="mcp_red_team",
            )

            job_id = JobManager.create(strategy="red_team", objective=objective)
            JobManager.start(job_id, _run_atomic(atomic))

            return {
                "status": "accepted",
                "job_id": job_id,
                "message": f"Red team attack started (max_turns={turns}). Poll with get_job_status.",
            }
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}

    @mcp.tool()
    async def run_crescendo_attack(
        objective: str,
        target_id: str,
        adversarial_chat_id: str,
        max_turns: int = 10,
        max_backtracks: int = 10,
    ) -> dict[str, Any]:
        """Crescendo attack — progressive escalation. BACKGROUND JOB.

        Returns a job_id immediately. Use get_job_status to poll for results.

        Args:
            objective: The attack objective.
            target_id: ID of the target to attack.
            adversarial_chat_id: ID of the adversarial LLM target.
            max_turns: Maximum turns (default 10, hard limit 30).
            max_backtracks: Maximum backtracks on refusal (default 10, hard limit 30).
        """
        try:
            ensure_memory()
            turns = _clamp(max_turns, MAX_TURNS_LIMIT)
            backtracks = _clamp(max_backtracks, MAX_TURNS_LIMIT)

            from pyrit.executor.attack import (
                AttackAdversarialConfig,
                CrescendoAttack,
            )

            target = TargetRegistry.get(target_id)
            adv = TargetRegistry.get(adversarial_chat_id)

            attack = CrescendoAttack(
                objective_target=target,
                attack_adversarial_config=AttackAdversarialConfig(target=adv),
                max_turns=turns,
                max_backtracks=backtracks,
            )
            atomic = _make_atomic(
                attack=attack,
                seed_groups=_seed_groups_from_objective(objective),
                name="mcp_crescendo",
            )

            job_id = JobManager.create(strategy="crescendo", objective=objective)
            JobManager.start(job_id, _run_atomic(atomic))

            return {
                "status": "accepted",
                "job_id": job_id,
                "message": f"Crescendo attack started (max_turns={turns}). Poll with get_job_status.",
            }
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}

    @mcp.tool()
    async def run_pair_attack(
        objective: str,
        target_id: str,
        adversarial_chat_id: str,
        tree_width: int = 3,
        tree_depth: int = 5,
    ) -> dict[str, Any]:
        """PAIR attack — Prompt Automatic Iterative Refinement. BACKGROUND JOB.

        Returns a job_id immediately. Use get_job_status to poll for results.

        Args:
            objective: The attack objective.
            target_id: ID of the target to attack.
            adversarial_chat_id: ID of the adversarial LLM target.
            tree_width: Parallel streams (default 3, hard limit 10).
            tree_depth: Iterations per stream (default 5, hard limit 15).
        """
        try:
            ensure_memory()
            width = _clamp(tree_width, MAX_TREE_WIDTH_LIMIT)
            depth = _clamp(tree_depth, MAX_TREE_DEPTH_LIMIT)

            from pyrit.executor.attack import (
                AttackAdversarialConfig,
                PAIRAttack,
                TAPSystemPromptPaths,
            )

            target = TargetRegistry.get(target_id)
            adv = TargetRegistry.get(adversarial_chat_id)

            attack = PAIRAttack(
                objective_target=target,
                attack_adversarial_config=AttackAdversarialConfig(
                    target=adv,
                    system_prompt_path=TAPSystemPromptPaths.TEXT_GENERATION.value,
                ),
                tree_width=width,
                tree_depth=depth,
            )
            atomic = _make_atomic(
                attack=attack,
                seed_groups=_seed_groups_from_objective(objective),
                name="mcp_pair",
            )

            job_id = JobManager.create(strategy="pair", objective=objective)
            JobManager.start(job_id, _run_atomic(atomic))

            return {
                "status": "accepted",
                "job_id": job_id,
                "message": f"PAIR attack started (width={width}, depth={depth}). Poll with get_job_status.",
            }
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}

    @mcp.tool()
    async def run_tap_attack(
        objective: str,
        target_id: str,
        adversarial_chat_id: str,
        tree_width: int = 3,
        tree_depth: int = 5,
        branching_factor: int = 3,
    ) -> dict[str, Any]:
        """TAP attack — Tree of Attacks with Pruning. BACKGROUND JOB.

        Returns a job_id immediately. Use get_job_status to poll for results.
        WARNING: TAP is the most expensive strategy. width=3 x depth=5 x branching=3
        can produce 45+ nodes, each requiring multiple LLM calls.

        Args:
            objective: The attack objective.
            target_id: ID of the target to attack.
            adversarial_chat_id: ID of the adversarial LLM target.
            tree_width: Root nodes (default 3, hard limit 10).
            tree_depth: Max depth (default 5, hard limit 15).
            branching_factor: Children per node (default 3, hard limit 5).
        """
        try:
            ensure_memory()
            width = _clamp(tree_width, MAX_TREE_WIDTH_LIMIT)
            depth = _clamp(tree_depth, MAX_TREE_DEPTH_LIMIT)
            branching = _clamp(branching_factor, MAX_BRANCHING_LIMIT)

            estimated_nodes = width * (branching ** depth - 1) // (branching - 1) if branching > 1 else width * depth
            estimated_calls = estimated_nodes * 3  # target + adversarial + scorer

            from pyrit.executor.attack import (
                AttackAdversarialConfig,
                TAPAttack,
                TAPSystemPromptPaths,
            )

            target = TargetRegistry.get(target_id)
            adv = TargetRegistry.get(adversarial_chat_id)

            attack = TAPAttack(
                objective_target=target,
                attack_adversarial_config=AttackAdversarialConfig(
                    target=adv,
                    system_prompt_path=TAPSystemPromptPaths.TEXT_GENERATION.value,
                ),
                tree_width=width,
                tree_depth=depth,
                branching_factor=branching,
            )
            atomic = _make_atomic(
                attack=attack,
                seed_groups=_seed_groups_from_objective(objective),
                name="mcp_tap",
            )

            job_id = JobManager.create(strategy="tap", objective=objective)
            JobManager.start(job_id, _run_atomic(atomic))

            return {
                "status": "accepted",
                "job_id": job_id,
                "estimated_max_llm_calls": estimated_calls,
                "message": f"TAP attack started (width={width}, depth={depth}, branching={branching}). Poll with get_job_status.",
            }
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}
