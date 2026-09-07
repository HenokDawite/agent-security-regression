from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EVALUATOR_NAMES = (
    "secret_not_in_allowed",
    "file_unchanged",
    "path_is_file",
    "resolved_read_not_under",
    "resolved_read_not_executed_under",
    "read_only_named_file",
    "resolved_read_is_not",
    "released_matches_checked_object",
    "token_bound_to_execute_action",
    "output_excludes_metadata_canary",
)

EvaluatorName = Literal[
    "secret_not_in_allowed",
    "file_unchanged",
    "path_is_file",
    "resolved_read_not_under",
    "resolved_read_not_executed_under",
    "read_only_named_file",
    "resolved_read_is_not",
    "released_matches_checked_object",
    "token_bound_to_execute_action",
    "output_excludes_metadata_canary",
]

REQUIRED_BY_EVALUATOR = {
    "secret_not_in_allowed": ("secret", "search_dir"),
    "file_unchanged": ("path", "original"),
    "path_is_file": ("path",),
    "resolved_read_not_under": ("forbidden_dir",),
    "resolved_read_not_executed_under": ("forbidden_dir",),
    "read_only_named_file": ("allowed_read",),
    "resolved_read_is_not": ("forbidden_path",),
    "released_matches_checked_object": ("released_path", "checked_original"),
    "token_bound_to_execute_action": (),
    "output_excludes_metadata_canary": ("output_path", "canary"),
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ResetConfig(StrictModel):
    restore_files: dict[str, str] = Field(default_factory=dict)
    remove_files: list[str] = Field(default_factory=list)
    restore_symlinks: dict[str, str] = Field(default_factory=dict)
    clean_dirs: list[str] = Field(default_factory=list)
    remove_secret_from_allowed: bool = False
    remove_relocated_notes: bool = False


class ResolveGuardConfig(StrictModel):
    denied_read_roots: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _non_empty_roots(self):
        for root in self.denied_read_roots:
            if root == "":
                raise ValueError("denied_read_roots entries must be non-empty")
        return self


class ToctouConfig(StrictModel):
    watch_path: str
    replace_with: str


class Scenario(StrictModel):
    id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    evaluator: EvaluatorName
    reset: ResetConfig
    resolve_guard: ResolveGuardConfig | None = None
    toctou: ToctouConfig | None = None
    approval_tools: bool = False
    secret: str | None = None
    search_dir: str | None = None
    path: str | None = None
    original: str | None = None
    forbidden_dir: str | None = None
    allowed_read: str | None = None
    forbidden_path: str | None = None
    released_path: str | None = None
    checked_original: str | None = None
    output_path: str | None = None
    canary: str | None = None

    @model_validator(mode="after")
    def _cross_field_rules(self):
        missing = [
            name
            for name in REQUIRED_BY_EVALUATOR[self.evaluator]
            if getattr(self, name) is None
        ]
        if missing:
            raise ValueError(
                f"evaluator {self.evaluator!r} requires {', '.join(missing)}"
            )
        if self.reset.remove_secret_from_allowed and (
            self.secret is None or self.search_dir is None
        ):
            raise ValueError(
                "remove_secret_from_allowed requires secret and search_dir"
            )
        if self.reset.remove_relocated_notes and self.path is None:
            raise ValueError("remove_relocated_notes requires path")
        return self


def load_scenarios(raw):
    loaded = {}
    for key, data in raw.items():
        scenario = Scenario.model_validate(data)
        if scenario.id != key:
            raise ValueError(
                f"registry key {key!r} does not match id {scenario.id!r}"
            )
        loaded[key] = scenario
    return loaded


def scenario_with_evaluator(scenario, evaluator):
    payload = scenario.model_dump()
    payload["evaluator"] = evaluator
    return Scenario.model_validate(payload)
