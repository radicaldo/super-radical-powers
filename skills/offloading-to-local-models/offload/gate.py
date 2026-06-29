from dataclasses import dataclass

ELIGIBLE, INELIGIBLE, NEEDS_REVIEW = "eligible", "ineligible", "needs_review"


@dataclass
class GateResult:
    verdict: str
    reason: str


def evaluate(task: dict, config: dict) -> GateResult:
    """Apply hard rules in order, returning the first decisive verdict:
    1. task.offload_eligible is False                         -> INELIGIBLE
    2. not task.verify_command                                -> INELIGIBLE
    3. len(task.target_files) != 1                            -> INELIGIBLE
    4. task.is_modify and max_existing_lines > line_threshold -> INELIGIBLE
    5. task.category in config.excluded_categories            -> INELIGIBLE
    6. task.offload_eligible is True                          -> ELIGIBLE
    7. task.category in config.allowed_categories             -> ELIGIBLE
    8. task.category is None                                  -> NEEDS_REVIEW
    9. else                                                   -> INELIGIBLE
    """
    hint = task.get("offload_eligible")
    verify = task.get("verify_command", "")
    target_files = task.get("target_files", [])
    is_modify = task.get("is_modify", False)
    max_lines = task.get("max_existing_lines")
    category = task.get("category")

    line_threshold = config["line_threshold"]
    excluded = config["excluded_categories"]
    allowed = config["allowed_categories"]

    # Rule 1: plan explicitly marked ineligible
    if hint is False:
        return GateResult(INELIGIBLE, "plan marked offloadEligible=false")

    # Rule 2: no verify command
    if not verify:
        return GateResult(INELIGIBLE, "no verifyCommand")

    # Rule 3: not a single-file task
    if len(target_files) != 1:
        return GateResult(INELIGIBLE, "not a single-file task")

    # Rule 4: modify target too large (only block when max_lines is a number > threshold)
    if is_modify and isinstance(max_lines, (int, float)) and max_lines > line_threshold:
        return GateResult(INELIGIBLE, "modify target too large")

    # Rule 5: excluded category
    if category in excluded:
        return GateResult(INELIGIBLE, f"excluded category: {category}")

    # Rule 6: plan hint explicitly true — trust it
    if hint is True:
        return GateResult(ELIGIBLE, "plan hint offloadEligible=true")

    # Rule 7: known allowed category
    if category in allowed:
        return GateResult(ELIGIBLE, f"allowed category: {category}")

    # Rule 8: category unknown — let orchestrator decide
    if category is None:
        return GateResult(NEEDS_REVIEW, "category unknown; orchestrator must classify")

    # Rule 9: category set but not allowed (and not excluded — already caught above)
    return GateResult(INELIGIBLE, f"category not allowed: {category}")
