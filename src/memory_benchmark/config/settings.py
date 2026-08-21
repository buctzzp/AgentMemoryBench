"""项目配置读取和校验。

本模块集中处理本地路径、OpenAI API key、base URL 和固定模型名。它只返回
结构化配置对象，不打印敏感信息，也不直接发起网络请求。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from memory_benchmark.core import ConfigurationError


DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
PRIMARY_API_PROVIDER = "primary"
OPENCODEGO_API_PROVIDER = "opencodego"
OPENCODEGO_SMOKE_MODEL = "mimo-v2.5"
SUPPORTED_API_PROVIDERS = frozenset(
    {PRIMARY_API_PROVIDER, OPENCODEGO_API_PROVIDER}
)
RESPONSES_JUDGE_TRANSPORT = "responses"
CHAT_COMPLETIONS_JUDGE_TRANSPORT = "chat_completions"
SUPPORTED_JUDGE_TRANSPORTS = frozenset(
    {RESPONSES_JUDGE_TRANSPORT, CHAT_COMPLETIONS_JUDGE_TRANSPORT}
)
# 统一网络兜底：框架 client 与 answer LLM client 使用同一档超时/重试，避免 full
# 长跑时框架侧只重试 2 次被瞬时抖动打断而白烧前置成本（ws02.6）。
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RETRIES = 8
DEFAULT_ANSWER_TIMEOUT_SECONDS = 60.0
DEFAULT_ANSWER_MAX_RETRIES = 8
SUPPORTED_ANSWER_MESSAGE_ROLES = frozenset({"system", "user"})


@dataclass(frozen=True)
class PathSettings:
    """项目路径配置。

    字段:
        project_root: 项目根目录。
        data_root: adapter 运行时读取 canonical dataset 的目录。
        models_root: 本地模型和 NLP 资源目录。
        outputs_root: 后续 runner 保存 prediction、metric 和日志的目录。
        third_party_root: 第三方源码根目录。
        third_party_benchmarks_root: 官方 benchmark 仓库根目录，只用于事实核验和源码参考。
        third_party_methods_root: 第三方 method 仓库根目录。
    """

    project_root: Path
    data_root: Path
    models_root: Path
    outputs_root: Path
    third_party_root: Path
    third_party_benchmarks_root: Path
    third_party_methods_root: Path

    def resolve_third_party_method_path(
        self,
        method_directory: str | Path,
        *relative_parts: str | Path,
    ) -> Path:
        """解析第三方 method 目录下的安全路径。

        输入:
            method_directory: 第三方 method 的根目录名，例如 `MemoryOS-main`。
            relative_parts: method 根目录下的相对路径片段，例如 `eval/runner.py`。

        输出:
            Path: 解析后的目标路径。目标文件本身可以不存在。

        异常:
            ConfigurationError: method 根目录不存在，或目标路径逃逸出该 method 根目录。
        """

        method_path = Path(method_directory)
        if (
            method_path.is_absolute()
            or len(method_path.parts) != 1
            or method_path.name in {"", ".", ".."}
        ):
            raise ConfigurationError(
                f"Third-party method directory must be a single name: {method_directory}"
            )

        methods_root = self.third_party_methods_root.resolve()
        method_root = (self.third_party_methods_root / method_path).resolve()
        if not _path_is_within(methods_root, method_root):
            raise ConfigurationError(f"Third-party method path escapes methods root: {method_root}")
        if not method_root.is_dir():
            raise ConfigurationError(f"Third-party method directory missing: {method_root}")

        target_path = (method_root / Path(*relative_parts)).resolve(strict=False)
        if not _path_is_within(method_root, target_path):
            raise ConfigurationError(f"Third-party method path escapes method root: {target_path}")
        return target_path


@dataclass(frozen=True)
class OpenAISettings:
    """OpenAI 调用配置。

    字段:
        api_key: OpenAI 或 OpenAI-compatible 服务的 API key。不能写入日志。
        base_url: API base URL，例如 `https://api.openai.com/v1` 或兼容网关地址。
        model: 当前 runtime profile 实际使用的模型名。
        provider: 不含 secret 的稳定 provider 身份。
        judge_transport: judge 使用 Responses API 或 Chat Completions API。
        timeout_seconds: 单次 API 请求超时时间。
        max_retries: OpenAI SDK 内部最大重试次数。
    """

    api_key: str
    base_url: str | None = None
    model: str = DEFAULT_OPENAI_MODEL
    provider: str = PRIMARY_API_PROVIDER
    judge_transport: str = RESPONSES_JUDGE_TRANSPORT
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES

    def __post_init__(self) -> None:
        """强校验 provider runtime，避免 secret 之外的实验身份含糊。"""

        if not self.api_key.strip():
            raise ConfigurationError("API key must not be blank")
        if self.base_url is not None and not self.base_url.strip():
            raise ConfigurationError("API base_url must be None or non-blank")
        if not self.model.strip():
            raise ConfigurationError("API model must not be blank")
        if self.provider not in SUPPORTED_API_PROVIDERS:
            raise ConfigurationError(
                f"Unsupported API provider: {self.provider!r}"
            )
        if self.judge_transport not in SUPPORTED_JUDGE_TRANSPORTS:
            raise ConfigurationError(
                f"Unsupported judge transport: {self.judge_transport!r}"
            )
        expected_transport = (
            CHAT_COMPLETIONS_JUDGE_TRANSPORT
            if self.provider == OPENCODEGO_API_PROVIDER
            else RESPONSES_JUDGE_TRANSPORT
        )
        if self.judge_transport != expected_transport:
            raise ConfigurationError(
                f"API provider {self.provider!r} requires judge transport "
                f"{expected_transport!r}; got {self.judge_transport!r}"
            )
        if self.timeout_seconds <= 0:
            raise ConfigurationError("API timeout_seconds must be positive")
        if self.max_retries < 0:
            raise ConfigurationError("API max_retries must be non-negative")

    def to_client_kwargs(self) -> dict[str, object]:
        """转换为 OpenAI SDK client 参数。

        输入:
            无，使用当前配置对象字段。

        输出:
            dict[str, object]: 可传给 `openai.OpenAI(**kwargs)` 的参数字典。
        """

        kwargs: dict[str, object] = {
            "api_key": self.api_key,
            "timeout": self.timeout_seconds,
            "max_retries": self.max_retries,
        }
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return kwargs

    def to_safe_dict(self) -> dict[str, object]:
        """转换为可写入日志的安全配置摘要。

        输入:
            无，使用当前配置对象字段。

        输出:
            dict[str, object]: API key 已脱敏的配置摘要。
        """

        return {
            "api_key": _redact_secret(self.api_key),
            "base_url": self.base_url,
            "model": self.model,
            "provider": self.provider,
            "judge_transport": self.judge_transport,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
        }

    def chat_completions_request_overrides(self) -> dict[str, object]:
        """返回 provider 专属、且必须进入实验身份的 Chat Completions 参数。"""

        if self.provider == OPENCODEGO_API_PROVIDER:
            return {"extra_body": {"thinking": {"type": "disabled"}}}
        return {}

    def to_runtime_manifest_dict(self) -> dict[str, object]:
        """返回不含 key/base URL 明文、可参与 resume 的 runtime 身份。"""

        return build_api_runtime_manifest(
            provider=self.provider,
            model=self.model,
        )


def build_api_runtime_manifest(
    *,
    provider: str,
    model: str,
) -> dict[str, object]:
    """从非 secret 的 provider/model 构造可在 preflight 前使用的运行身份。"""

    normalized_provider = provider.strip().lower()
    normalized_model = model.strip()
    if normalized_provider not in SUPPORTED_API_PROVIDERS:
        raise ConfigurationError(
            f"Unsupported API provider: {provider!r}"
        )
    if not normalized_model:
        raise ConfigurationError("API runtime model must not be blank")
    judge_transport = (
        CHAT_COMPLETIONS_JUDGE_TRANSPORT
        if normalized_provider == OPENCODEGO_API_PROVIDER
        else RESPONSES_JUDGE_TRANSPORT
    )
    return {
        "contract_version": "v2",
        "provider": normalized_provider,
        "model": normalized_model,
        "answer_transport": CHAT_COMPLETIONS_JUDGE_TRANSPORT,
        "judge_transport": judge_transport,
        "thinking_mode": (
            "disabled"
            if normalized_provider == OPENCODEGO_API_PROVIDER
            else "provider_default"
        ),
    }


@dataclass(frozen=True)
class AnswerLLMSettings:
    """framework answer LLM 的显式调用参数。

    字段:
        model: answer LLM 的模型名，Phase 1 默认为 `gpt-4o-mini`。
        message_role: 完整 answer prompt 放入 chat messages 时使用的角色。
        temperature: 采样温度；None 表示不向 SDK 传该参数。
        max_tokens: 最大输出 token；None 表示不向 SDK 传该参数。
        top_p: nucleus sampling 参数；None 表示不向 SDK 传该参数。
        timeout_seconds: answer LLM client 请求超时。
        max_retries: answer LLM client SDK 最大重试次数。
    """

    model: str = DEFAULT_OPENAI_MODEL
    message_role: str = "user"
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    timeout_seconds: float = DEFAULT_ANSWER_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_ANSWER_MAX_RETRIES

    def __post_init__(self) -> None:
        """强校验公开 answer LLM 参数，避免实验身份含糊。"""

        if not self.model.strip():
            raise ConfigurationError("answer LLM model must not be blank")
        if self.message_role not in SUPPORTED_ANSWER_MESSAGE_ROLES:
            raise ConfigurationError(
                "answer LLM message_role must be one of "
                f"{sorted(SUPPORTED_ANSWER_MESSAGE_ROLES)}"
            )
        if self.temperature is not None and not (0 <= self.temperature <= 2):
            raise ConfigurationError("answer LLM temperature must be between 0 and 2")
        if self.max_tokens is not None and self.max_tokens < 1:
            raise ConfigurationError("answer LLM max_tokens must be at least 1")
        if self.top_p is not None and not (0 <= self.top_p <= 1):
            raise ConfigurationError("answer LLM top_p must be between 0 and 1")
        if self.timeout_seconds <= 0:
            raise ConfigurationError("answer LLM timeout_seconds must be positive")
        if self.max_retries < 0:
            raise ConfigurationError("answer LLM max_retries must be non-negative")

    def to_client_kwargs(self, api_settings: OpenAISettings) -> dict[str, object]:
        """转换为 OpenAI SDK client 参数，复用 API key/base URL。"""

        kwargs: dict[str, object] = {
            "api_key": api_settings.api_key,
            "timeout": self.timeout_seconds,
            "max_retries": self.max_retries,
        }
        if api_settings.base_url:
            kwargs["base_url"] = api_settings.base_url
        return kwargs

    def to_request_kwargs(self) -> dict[str, object]:
        """转换为 chat completions 可选请求参数，只包含显式配置项。"""

        kwargs: dict[str, object] = {}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if self.max_tokens is not None:
            kwargs["max_tokens"] = self.max_tokens
        if self.top_p is not None:
            kwargs["top_p"] = self.top_p
        return kwargs

    def to_manifest_dict(self) -> dict[str, object]:
        """返回可公开写入 run manifest 的 answer LLM 参数。"""

        return {
            "message_role": self.message_role,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
        }


def resolve_answer_llm_settings(
    *,
    method_name: str,
    benchmark_name: str,
    model: str = DEFAULT_OPENAI_MODEL,
) -> AnswerLLMSettings:
    """解析内置 benchmark 的官方 answer LLM 参数。

    输入:
        method_name: registry 中的 method 稳定名称。
        benchmark_name: registry 中的 benchmark 稳定名称。
        model: 当前运行指定的 answer LLM 模型名。

    输出:
        AnswerLLMSettings: 显式 answer LLM 参数。未知组合使用保守默认值。
    """

    key = (method_name.strip().lower(), benchmark_name.strip().lower())
    if key[1] == "locomo":
        # LoCoMo 已冻结的官方 answer LLM 参数，method 无关（见
        # docs/workstreams/ws02.6-first-smoke-hardening/plan-b0-b1-locomo.md
        # Task 5；官方来源
        # third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:283-289、
        # global_methods.py:92-127：role=user、temperature=0、max_tokens=32；
        # top-p 官方代码未显式传，论文 Appendix C.2 记为 1）。同一 benchmark 下
        # 所有 method 必须字节级一致，不再按 (method, benchmark) 分叉。
        return AnswerLLMSettings(
            model=model,
            message_role="user",
            temperature=0.0,
            max_tokens=32,
            top_p=1.0,
        )
    if key[1] == "longmemeval":
        # LongMemEval 官方非 CoT generation 参数，method 无关。来源：
        # third_party/benchmarks/LongMemEval-main/src/generation/
        # run_generation.py:360-368（role=user、n=1、temperature=0、
        # max_tokens=500；top_p 未显式传）。
        return AnswerLLMSettings(
            model=model,
            message_role="user",
            temperature=0.0,
            max_tokens=500,
            top_p=None,
        )
    if key[1] == "membench":
        # MemBench MCQ answer LLM 参数，method 无关。官方 answer LLM 封装在
        # 外部依赖 benchutils（不在官方仓库内），参数不可考；官方 agent 用
        # response_format=json_schema 强制单字母结构化输出
        # （MembenchAgent.py:93-112），本框架用自由文本 + 健壮解析替代（该
        # 偏差记入 frozen 记录）。因此以下取值均为框架决定并如实标注：
        # - temperature=0.0：框架确定性评测约定（与 locomo/longmemeval 的
        #   官方 temp=0 一致），非 MemBench 官方值
        # - max_tokens=None：官方未显式设置 → 按 ws02.6 规则用 API 默认；
        #   不设小上限，避免截断非顺从模型的回答使字母无机会出现（公平性）
        # - top_p=None：官方未显式设置，用 API 默认
        return AnswerLLMSettings(
            model=model,
            message_role="user",
            temperature=0.0,
            max_tokens=None,
            top_p=None,
        )
    if key[1] == "beam":
        # BEAM RAG answer reader 参数，method 无关。一手来源：
        # answer_generation.py:303-307 构造 reader_llm 时显式 temperature=0；
        # long_term_memory_methods.py:639-643 用字符串 prompt 调 model.invoke，
        # 对应 user/human message。BuildLLm 在 llm.py:19-26 只向 ChatOpenAI
        # 显式传 model/key/base_url/temperature，未传 max_tokens/top_p/n。
        # 官方 reader model 由 CLI 必填参数提供（answer_generation.py:235-240），
        # 没有固定模型名；本框架按 Phase 1 政策统一使用传入的 gpt-4o-mini。
        # max_tokens/top_p 使用 API 默认是框架决定，不冒充官方值。
        return AnswerLLMSettings(
            model=model,
            message_role="user",
            temperature=0.0,
            max_tokens=None,
            top_p=None,
        )
    if key[1] == "halumem":
        # HaluMem Mem0 QA 调用点只执行 llm_request(prompt)，没有逐调用采样参数
        # （eval_memzero.py:244-250）。llms.py:60-69 明确使用 user role；
        # max_tokens/temperature 仅在对应环境变量存在时才进入 common_params
        # （llms.py:25-31），top_p 未设置。因此三项均用 API 默认，模型仍按
        # Phase 1 政策使用传入的 gpt-4o-mini；这些 None 不是臆造的官方值。
        return AnswerLLMSettings(
            model=model,
            message_role="user",
            temperature=None,
            max_tokens=None,
            top_p=None,
        )
    return AnswerLLMSettings(model=model)


@dataclass(frozen=True)
class AppSettings:
    """项目总配置。

    字段:
        paths: 本地路径配置。
        openai: OpenAI API 调用配置。
    """

    paths: PathSettings
    openai: OpenAISettings


def load_settings(
    project_root: str | Path | None = None,
    env_file: str | Path | None = None,
    api_provider: str = PRIMARY_API_PROVIDER,
) -> AppSettings:
    """读取项目配置。

    输入:
        project_root: 项目根目录；为空时使用当前工作目录。
        env_file: `.env` 文件路径；为空时默认读取 `project_root/.env`。
        api_provider: 需要读取的 API provider profile。

    输出:
        AppSettings: 路径配置和 OpenAI 配置。

    异常:
        ConfigurationError: API key 缺失或配置格式不合法。
    """

    path_settings = load_path_settings(project_root=project_root)
    openai_settings = load_openai_settings(
        project_root=path_settings.project_root,
        env_file=env_file,
        api_provider=api_provider,
    )
    return AppSettings(paths=path_settings, openai=openai_settings)


def load_openai_settings(
    project_root: str | Path | None = None,
    env_file: str | Path | None = None,
    api_provider: str = PRIMARY_API_PROVIDER,
    expected_model: str | None = None,
) -> OpenAISettings:
    """读取 OpenAI 相关配置。

    输入:
        project_root: 项目根目录；为空时使用当前工作目录推断。
        env_file: `.env` 文件路径；为空时默认读取 `project_root/.env`。
        api_provider: `primary` 或 `opencodego`。
        expected_model: manifest/profile 已声明的公开模型。OpenCodeGo 会在已配置
            model slot 中精确匹配它；为空时选择当前第三槽 smoke 模型。

    输出:
        OpenAISettings: 只包含 API 连接所需字段的结构化配置。

    异常:
        ConfigurationError: API key 缺失或环境变量配置不合法。
    """

    path_settings = load_path_settings(project_root=project_root)
    root = path_settings.project_root
    if env_file is None:
        selected_env_file = root / ".env"
    else:
        selected_env_file = Path(env_file).expanduser()
        if not selected_env_file.is_absolute():
            selected_env_file = root / selected_env_file
        selected_env_file = selected_env_file.resolve()
    load_dotenv(dotenv_path=selected_env_file, override=False)

    normalized_provider = api_provider.strip().lower()
    if normalized_provider == PRIMARY_API_PROVIDER:
        api_key = _first_non_empty_env("OPENAI_KEY", "OPENAI_API_KEY")
        if not api_key:
            raise ConfigurationError(
                "Missing primary API key: set OPENAI_KEY in .env or environment"
            )
        base_url = _first_non_empty_env("BASE_URL", "OPENAI_BASE_URL")
        model = DEFAULT_OPENAI_MODEL
        if expected_model is not None and expected_model != model:
            raise ConfigurationError(
                "Primary API model does not match expected runtime identity: "
                f"{expected_model!r}"
            )
        judge_transport = RESPONSES_JUDGE_TRANSPORT
    elif normalized_provider == OPENCODEGO_API_PROVIDER:
        api_key = _first_non_empty_env("opencode_go_key", "OPENCODE_GO_KEY")
        base_url = _first_non_empty_env(
            "opencode_base_url",
            "OPENCODE_BASE_URL",
        )
        legacy_model = _first_non_empty_env(
            "opencode_model_name",
            "OPENCODE_MODEL_NAME",
        )
        previous_smoke_model = _first_non_empty_env(
            "opencode_model_name_2",
            "OPENCODE_MODEL_NAME_2",
        )
        smoke_model = _first_non_empty_env(
            "opencode_model_name_3",
            "OPENCODE_MODEL_NAME_3",
        )
        missing = [
            field_name
            for field_name, value in (
                ("opencode_go_key", api_key),
                ("opencode_base_url", base_url),
            )
            if value is None
        ]
        if expected_model is None and smoke_model is None:
            missing.append("opencode_model_name_3")
        if missing:
            raise ConfigurationError(
                "Missing opencodego setting(s): " + ", ".join(missing)
            )
        configured_models = tuple(
            candidate
            for candidate in (smoke_model, previous_smoke_model, legacy_model)
            if candidate is not None
        )
        if expected_model is None:
            # 上面的 missing 门已证明 smoke_model 非空；再锁 tracked identity，避免
            # 通用 loader 在 runner manifest 预检之外静默接受环境漂移。
            assert smoke_model is not None
            if smoke_model != OPENCODEGO_SMOKE_MODEL:
                raise ConfigurationError(
                    "OpenCodeGo smoke model slot does not match tracked runtime "
                    f"identity: {smoke_model!r}"
                )
            model = smoke_model
        elif expected_model in configured_models:
            model = expected_model
        else:
            raise ConfigurationError(
                "Expected OpenCodeGo model is not present in configured model slots: "
                f"{expected_model!r}"
            )
        judge_transport = CHAT_COMPLETIONS_JUDGE_TRANSPORT
    else:
        raise ConfigurationError(
            f"Unsupported API provider: {api_provider!r}; expected one of "
            f"{sorted(SUPPORTED_API_PROVIDERS)}"
        )

    return OpenAISettings(
        api_key=api_key,
        base_url=base_url,
        model=model,
        provider=normalized_provider,
        judge_transport=judge_transport,
    )


def resolve_api_provider_for_profile(profile_name: str) -> str:
    """把运行 profile 映射到显式 API provider，不读取 secret。"""

    normalized = profile_name.strip().lower()
    if normalized == "smoke":
        return OPENCODEGO_API_PROVIDER
    if (
        normalized in {"official-full", "official_full"}
        or normalized.startswith("author-")
        or normalized.startswith("author_")
    ):
        return PRIMARY_API_PROVIDER
    raise ConfigurationError(
        f"Unsupported run profile for API provider routing: {profile_name!r}"
    )


def resolve_api_model_for_provider(api_provider: str) -> str:
    """返回公开 runtime profile 锁定的模型名，供 secret load 前 manifest 使用。"""

    normalized = api_provider.strip().lower()
    if normalized == OPENCODEGO_API_PROVIDER:
        return OPENCODEGO_SMOKE_MODEL
    if normalized == PRIMARY_API_PROVIDER:
        return DEFAULT_OPENAI_MODEL
    raise ConfigurationError(
        f"Unsupported API provider: {api_provider!r}"
    )


def load_path_settings(project_root: str | Path | None = None) -> PathSettings:
    """读取不依赖 API key 的本地路径配置。

    输入:
        project_root: 项目根目录；为空时从当前工作目录向上查找项目根。

    输出:
        PathSettings: 项目根目录、runtime data、models、outputs 和第三方源码目录。
    """

    root = _resolve_project_root(project_root)
    return PathSettings(
        project_root=root,
        data_root=root / "data",
        models_root=root / "models",
        outputs_root=root / "outputs",
        third_party_root=root / "third_party",
        third_party_benchmarks_root=root / "third_party" / "benchmarks",
        third_party_methods_root=root / "third_party" / "methods",
    )


def _resolve_project_root(project_root: str | Path | None = None) -> Path:
    """解析项目根目录。

    输入:
        project_root: 显式项目根路径；为空时从当前工作目录向上查找。

    输出:
        Path: 解析后的项目根目录。
    """

    if project_root is not None:
        return Path(project_root).resolve()

    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if _looks_like_project_root(candidate):
            return candidate
    return current


def _first_non_empty_env(*keys: str) -> str | None:
    """按优先级读取第一个非空环境变量。

    输入:
        keys: 候选配置键，越靠前优先级越高。

    输出:
        str | None: 第一个非空值；所有候选都为空时返回 None。
    """

    for key in keys:
        value = os.getenv(key)
        if value and value.strip():
            return value.strip()
    return None


def _redact_secret(secret: str) -> str:
    """脱敏显示敏感字符串。

    输入:
        secret: API key 或类似敏感值。

    输出:
        str: 只保留前 4 位和后 4 位的安全摘要。
    """

    if len(secret) <= 8:
        return "<redacted>"
    return f"{secret[:4]}...{secret[-4:]}"


def _looks_like_project_root(candidate: Path) -> bool:
    """判断目录是否像项目根目录。

    输入:
        candidate: 待检查的目录。

    输出:
        bool: 同时满足 `pyproject.toml` 存在且包含迁移前或迁移后的包目录时返回 True。
    """

    if not (candidate / "pyproject.toml").exists():
        return False
    return (candidate / "memory_benchmark").is_dir() or (candidate / "src" / "memory_benchmark").is_dir()


def _path_is_within(base_path: Path, candidate_path: Path) -> bool:
    """判断目标路径是否位于基准路径内部或等于基准路径。

    输入:
        base_path: 作为边界的目录。
        candidate_path: 待检查的目录或文件路径。

    输出:
        bool: 目标路径在边界内时返回 True。
    """

    try:
        candidate_path.relative_to(base_path)
        return True
    except ValueError:
        return False
