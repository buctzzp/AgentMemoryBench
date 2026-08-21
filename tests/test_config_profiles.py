"""配置 profile 加载测试。

本文件验证 TOML profile 读取、严格字段校验、`profile_name` 自动填充，以及
OpenAI 配置的延迟加载行为。测试不会暴露任何密钥信息。
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path

import pytest

from memory_benchmark.config.profiles import load_typed_profile
from memory_benchmark.config.settings import (
    CHAT_COMPLETIONS_JUDGE_TRANSPORT,
    OPENCODEGO_API_PROVIDER,
    RESPONSES_JUDGE_TRANSPORT,
    OpenAISettings,
    load_openai_settings,
    load_path_settings,
    resolve_api_provider_for_profile,
    resolve_answer_llm_settings,
)
from memory_benchmark.core import ConfigurationError
from memory_benchmark.methods.mem0_adapter import Mem0Config
from memory_benchmark.methods.memoryos_adapter import MemoryOSPaperConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_toml(path: Path, content: str) -> None:
    """写入格式化后的 TOML 测试内容。"""

    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def test_load_typed_profile_builds_mem0_smoke_profile_from_section(tmp_path: Path) -> None:
    """TOML 的 `[smoke]` section 应能构造 `Mem0Config.smoke()`。"""

    toml_path = tmp_path / "mem0.toml"
    _write_toml(
        toml_path,
        """
        [smoke]
        extraction_model = "muse-spark-1.2-contributor"
        embedding_provider = "huggingface"
        embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
        embedding_dimensions = 384
        reader_model = "muse-spark-1.2-contributor"
        top_k = 20
        max_workers = 1
        ingestion_chunk_size = 1
        infer = true
        """,
    )

    config = load_typed_profile(toml_path, "smoke", Mem0Config)

    assert config == Mem0Config.smoke()


def test_load_typed_profile_requires_requested_section(tmp_path: Path) -> None:
    """请求不存在的 profile 时应抛出配置异常。"""

    toml_path = tmp_path / "mem0.toml"
    _write_toml(
        toml_path,
        """
        [official-full]
        extraction_model = "gpt-4o-mini"
        embedding_model = "text-embedding-3-small"
        embedding_dimensions = 1536
        reader_model = "gpt-4o-mini"
        top_k = 200
        max_workers = 10
        ingestion_chunk_size = 1
        infer = true
        """,
    )

    with pytest.raises(ConfigurationError, match="smoke"):
        load_typed_profile(toml_path, "smoke", Mem0Config)


def test_load_typed_profile_rejects_unknown_key(tmp_path: Path) -> None:
    """TOML section 中出现 dataclass 未定义的 key 时应显式失败。"""

    toml_path = tmp_path / "mem0.toml"
    _write_toml(
        toml_path,
        """
        [smoke]
        extraction_model = "gpt-4o-mini"
        embedding_model = "text-embedding-3-small"
        embedding_dimensions = 1536
        reader_model = "gpt-4o-mini"
        top_k = 200
        max_workers = 1
        ingestion_chunk_size = 1
        infer = true
        unexpected = "value"
        """,
    )

    with pytest.raises(ConfigurationError, match="unexpected"):
        load_typed_profile(toml_path, "smoke", Mem0Config)


def test_load_typed_profile_rejects_framework_method_field_ownership_overlap(
    tmp_path: Path,
) -> None:
    """method dataclass 不得重新声明 framework-owned answer_builder。"""

    @dataclass(frozen=True)
    class _InvalidMethodConfig:
        """故意抢占 framework 字段的反例 config。"""

        profile_name: str
        answer_builder: str

    toml_path = tmp_path / "invalid.toml"
    _write_toml(
        toml_path,
        """
        [smoke]
        answer_builder = "benchmark"
        """,
    )

    with pytest.raises(ConfigurationError, match="must not also be method config"):
        load_typed_profile(toml_path, "smoke", _InvalidMethodConfig)


def test_load_typed_profile_rejects_wrong_field_type(tmp_path: Path) -> None:
    """字段类型不匹配时应包装为 `ConfigurationError`。"""

    toml_path = tmp_path / "mem0.toml"
    _write_toml(
        toml_path,
        """
        [smoke]
        extraction_model = "gpt-4o-mini"
        embedding_model = "text-embedding-3-small"
        embedding_dimensions = "1536"
        reader_model = "gpt-4o-mini"
        top_k = 200
        max_workers = 1
        ingestion_chunk_size = 1
        infer = true
        """,
    )

    with pytest.raises(ConfigurationError, match="embedding_dimensions"):
        load_typed_profile(toml_path, "smoke", Mem0Config)


def test_load_typed_profile_autofills_profile_name_and_rejects_duplicate(tmp_path: Path) -> None:
    """`profile_name` 应由 section 名自动填充，且 TOML 不得重复声明。"""

    toml_path = tmp_path / "mem0.toml"
    _write_toml(
        toml_path,
        """
        [smoke]
        extraction_model = "gpt-4o-mini"
        embedding_model = "text-embedding-3-small"
        embedding_dimensions = 1536
        reader_model = "gpt-4o-mini"
        top_k = 200
        max_workers = 1
        ingestion_chunk_size = 1
        infer = true
        profile_name = "custom"
        """,
    )

    with pytest.raises(ConfigurationError, match="profile_name"):
        load_typed_profile(toml_path, "smoke", Mem0Config)


def test_load_typed_profile_rejects_root_without_section(tmp_path: Path) -> None:
    """TOML 顶层如果不是 section/table，应拒绝加载。"""

    toml_path = tmp_path / "mem0.toml"
    _write_toml(
        toml_path,
        """
        extraction_model = "gpt-4o-mini"
        embedding_model = "text-embedding-3-small"
        embedding_dimensions = 1536
        reader_model = "gpt-4o-mini"
        top_k = 200
        max_workers = 1
        ingestion_chunk_size = 1
        infer = true
        """,
    )

    with pytest.raises(ConfigurationError, match="section"):
        load_typed_profile(toml_path, "smoke", Mem0Config)


def test_load_openai_settings_reads_key_and_base_url_from_env_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`load_openai_settings()` 应从指定 `.env` 延迟读取密钥和 base URL。"""

    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_KEY=sk-test-from-file\nBASE_URL=https://example.test/v1\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    settings = load_openai_settings(project_root=tmp_path, env_file=env_file)

    assert settings.api_key == "sk-test-from-file"
    assert settings.base_url == "https://example.test/v1"
    assert settings.model == "gpt-4o-mini"


def test_load_openai_settings_reads_explicit_opencodego_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """opencodego 默认选择 economy slot，并公开 chat-only judge 身份。"""

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                "opencode_go_key=unit-test-opencode-key",
                "opencode_base_url=https://opencode.example/v1",
                "opencode_model_name=deepseek-v4-flash",
                "opencode_model_name_2=muse-spark-1.2-contributor",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    for key in (
        "opencode_go_key",
        "OPENCODE_GO_KEY",
        "opencode_base_url",
        "OPENCODE_BASE_URL",
        "opencode_model_name",
        "OPENCODE_MODEL_NAME",
        "opencode_model_name_2",
        "OPENCODE_MODEL_NAME_2",
        "opencode_model_name_3",
        "OPENCODE_MODEL_NAME_3",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = load_openai_settings(
        project_root=tmp_path,
        env_file=env_file,
        api_provider=OPENCODEGO_API_PROVIDER,
    )

    assert settings.provider == "opencodego"
    assert settings.model == "muse-spark-1.2-contributor"
    assert settings.judge_transport == CHAT_COMPLETIONS_JUDGE_TRANSPORT
    runtime = settings.to_runtime_manifest_dict()
    assert runtime["provider"] == "opencodego"
    assert runtime["model"] == "muse-spark-1.2-contributor"
    assert runtime["judge_transport"] == "chat_completions"
    assert runtime["contract_version"] == "v2"
    assert runtime["thinking_mode"] == "disabled"
    assert settings.chat_completions_request_overrides() == {
        "extra_body": {"thinking": {"type": "disabled"}}
    }
    assert "unit-test-opencode-key" not in repr(runtime)
    assert "opencode.example" not in repr(runtime)


def test_load_openai_settings_can_reopen_legacy_opencodego_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """evaluate 应能按旧 manifest 精确选择 legacy slot，不能被新默认覆盖。"""

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                "opencode_go_key=unit-test-opencode-key",
                "opencode_base_url=https://opencode.example/v1",
                "opencode_model_name=deepseek-v4-flash",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    for key in (
        "opencode_go_key",
        "OPENCODE_GO_KEY",
        "opencode_base_url",
        "OPENCODE_BASE_URL",
        "opencode_model_name",
        "OPENCODE_MODEL_NAME",
        "opencode_model_name_2",
        "OPENCODE_MODEL_NAME_2",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = load_openai_settings(
        project_root=tmp_path,
        env_file=env_file,
        api_provider=OPENCODEGO_API_PROVIDER,
        expected_model="deepseek-v4-flash",
    )

    assert settings.model == "deepseek-v4-flash"


def test_load_openai_settings_rejects_unconfigured_expected_opencodego_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """manifest 模型不在任一显式 slot 时必须在调用 API 前失败。"""

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                "opencode_go_key=unit-test-opencode-key",
                "opencode_base_url=https://opencode.example/v1",
                "opencode_model_name_2=muse-spark-1.2-contributor",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    for key in (
        "opencode_go_key",
        "OPENCODE_GO_KEY",
        "opencode_base_url",
        "OPENCODE_BASE_URL",
        "opencode_model_name",
        "OPENCODE_MODEL_NAME",
        "opencode_model_name_2",
        "OPENCODE_MODEL_NAME_2",
        "opencode_model_name_3",
        "OPENCODE_MODEL_NAME_3",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ConfigurationError, match="not present"):
        load_openai_settings(
            project_root=tmp_path,
            env_file=env_file,
            api_provider=OPENCODEGO_API_PROVIDER,
            expected_model="missing-model",
        )


@pytest.mark.parametrize(
    ("provider", "judge_transport"),
    (
        ("opencodego", RESPONSES_JUDGE_TRANSPORT),
        ("primary", CHAT_COMPLETIONS_JUDGE_TRANSPORT),
    ),
)
def test_openai_settings_rejects_provider_transport_contradiction(
    provider: str,
    judge_transport: str,
) -> None:
    """provider 与 transport 必须构成单一 runtime 身份，不能各自漂移。"""

    with pytest.raises(ConfigurationError, match="requires judge transport"):
        OpenAISettings(
            api_key="sk-test",
            model="test-model",
            provider=provider,
            judge_transport=judge_transport,
        )


@pytest.mark.parametrize(
    "profile_name",
    ("official-full", "official_full", "author-locomo", "author_locomo"),
)
def test_formal_and_author_profiles_use_primary_provider(profile_name: str) -> None:
    """正式主表与作者校准不能因 smoke 预算路由而切到 opencodego。"""

    assert resolve_api_provider_for_profile(profile_name) == "primary"


def test_load_typed_profile_builds_memoryos_official_full_profile_from_project_toml() -> None:
    """项目内的 MemoryOS official_full profile 应加载为固定论文参数。"""

    config = load_typed_profile(
        PROJECT_ROOT / "configs" / "methods" / "memoryos.toml",
        "official_full",
        MemoryOSPaperConfig,
    )

    assert config.profile_name == "official_full"
    assert config.short_term_capacity == 10
    assert config.mid_term_capacity == 2000
    assert config.top_k_sessions == 5
    assert config.retrieval_queue_capacity == 7
    assert config.max_workers == 10
    assert config.longmemeval_prompt_profile == "memoryos-pypi-retrieve-v1"


def test_load_typed_profile_builds_matching_memoryos_smoke_and_official_profiles() -> None:
    """MemoryOS 两 profile 只允许 budget LLM、并发与 profile 身份不同。"""

    toml_path = PROJECT_ROOT / "configs" / "methods" / "memoryos.toml"
    smoke = load_typed_profile(toml_path, "smoke", MemoryOSPaperConfig)
    official_full = load_typed_profile(toml_path, "official_full", MemoryOSPaperConfig)

    assert smoke.profile_name == "smoke"
    assert official_full.profile_name == "official_full"
    assert smoke.llm_model == "muse-spark-1.2-contributor"
    assert official_full.llm_model == "gpt-4o-mini"
    assert smoke.embedding_model_name == "sentence-transformers/all-MiniLM-L6-v2"
    assert official_full.embedding_model_name == "sentence-transformers/all-MiniLM-L6-v2"
    assert smoke.longmemeval_prompt_profile == "memoryos-pypi-retrieve-v1"
    assert official_full.longmemeval_prompt_profile == "memoryos-pypi-retrieve-v1"
    assert {
        key: value
        for key, value in smoke.to_manifest().items()
        if key not in {"profile_name", "max_workers", "llm_model"}
    } == {
        key: value
        for key, value in official_full.to_manifest().items()
        if key not in {"profile_name", "max_workers", "llm_model"}
    }


def test_load_path_settings_exposes_phase_e_project_roots() -> None:
    """`load_path_settings(PROJECT_ROOT)` 应暴露 Phase E 需要的 data 和 third_party 目录。"""

    paths = load_path_settings(PROJECT_ROOT)

    assert paths.project_root == PROJECT_ROOT
    assert paths.data_root == PROJECT_ROOT / "data"
    assert paths.third_party_benchmarks_root == PROJECT_ROOT / "third_party" / "benchmarks"
    assert paths.third_party_methods_root == PROJECT_ROOT / "third_party" / "methods"


@pytest.mark.parametrize(
    "method_name",
    ["mem0", "memoryos", "amem", "lightmem", "simplemem", "custom"],
)
def test_membench_answer_llm_settings_are_method_independent(
    method_name: str,
) -> None:
    """MemBench answer LLM 参数应按 benchmark 归一，跨 method 一致。"""

    settings = resolve_answer_llm_settings(
        method_name=method_name,
        benchmark_name="membench",
        model="gpt-4o-mini",
    )

    assert settings.model == "gpt-4o-mini"
    assert settings.message_role == "user"
    assert settings.temperature == 0.0
    # 官方 answer LLM 参数不可考（benchutils 外部依赖）→ 按 ws02.6 规则用
    # API 默认；小上限会截断非顺从模型的回答导致字母无机会出现（公平性）。
    assert settings.max_tokens is None
    assert settings.top_p is None
    assert settings.timeout_seconds == 60
    assert settings.max_retries == 8


@pytest.mark.parametrize(
    "method_name",
    ["mem0", "memoryos", "amem", "lightmem", "simplemem", "custom"],
)
def test_beam_answer_llm_settings_are_method_independent(method_name: str) -> None:
    """BEAM answer 配置按 benchmark 归一，只采用官方明确的 temperature=0。"""

    settings = resolve_answer_llm_settings(
        method_name=method_name,
        benchmark_name="beam",
        model="gpt-4o-mini",
    )

    assert settings.model == "gpt-4o-mini"
    assert settings.message_role == "user"
    assert settings.temperature == 0.0
    assert settings.max_tokens is None
    assert settings.top_p is None
    assert settings.timeout_seconds == 60
    assert settings.max_retries == 8


@pytest.mark.parametrize(
    "method_name",
    ["mem0", "memoryos", "amem", "lightmem", "simplemem", "custom"],
)
def test_halumem_answer_llm_settings_are_method_independent(method_name: str) -> None:
    """HaluMem answer 配置按 benchmark 归一，官方未设采样项走 API 默认。"""

    settings = resolve_answer_llm_settings(
        method_name=method_name,
        benchmark_name="halumem",
        model="gpt-4o-mini",
    )

    assert settings.model == "gpt-4o-mini"
    assert settings.message_role == "user"
    assert settings.temperature is None
    assert settings.max_tokens is None
    assert settings.top_p is None
    assert settings.to_request_kwargs() == {}
    assert settings.timeout_seconds == 60
    assert settings.max_retries == 8


@pytest.mark.parametrize(
    "method_name",
    ["mem0", "memoryos", "amem", "lightmem", "simplemem", "custom"],
)
def test_longmemeval_answer_llm_settings_are_method_independent(
    method_name: str,
) -> None:
    """LongMemEval answer LLM 参数应按 benchmark 归一到官方非 CoT 配置。"""

    settings = resolve_answer_llm_settings(
        method_name=method_name,
        benchmark_name="longmemeval",
        model="gpt-4o-mini",
    )

    assert settings.model == "gpt-4o-mini"
    assert settings.message_role == "user"
    assert settings.temperature == 0.0
    assert settings.max_tokens == 500
    assert settings.top_p is None
    assert settings.timeout_seconds == 60
    assert settings.max_retries == 8


@pytest.mark.parametrize(
    "method_name",
    ["mem0", "memoryos", "amem", "lightmem", "simplemem", "custom"],
)
def test_locomo_answer_llm_settings_are_method_independent(
    method_name: str,
) -> None:
    """LoCoMo answer LLM 参数必须跨 method 字节级一致（公平性冻结，见 plan Task 5）。

    官方来源：`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:283-289`、
    `global_methods.py:92-127`（role=user、temperature=0、max_tokens=32）；
    top-p 官方代码未显式传，论文 Appendix C.2 记为 1。
    """

    settings = resolve_answer_llm_settings(
        method_name=method_name,
        benchmark_name="locomo",
        model="gpt-4o-mini",
    )

    assert settings.model == "gpt-4o-mini"
    assert settings.message_role == "user"
    assert settings.temperature == 0.0
    assert settings.max_tokens == 32
    assert settings.top_p == 1.0
    assert settings.timeout_seconds == 60
    assert settings.max_retries == 8
