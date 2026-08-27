"""配置层公共入口。

本模块导出项目配置对象和加载函数。配置层负责读取 `.env`、环境变量、默认值和
TOML profile，但不负责创建 OpenAI client 或执行 API 请求。
"""

from .profiles import load_typed_profile
from .run_profiles import (
    ApiRuntimeProfile,
    ExecutionProfile,
    RunComposition,
    load_run_composition,
)
from .settings import (
    APILIO_API_PROVIDER,
    AppSettings,
    AnswerLLMSettings,
    CHAT_COMPLETIONS_JUDGE_TRANSPORT,
    build_api_runtime_manifest,
    OPENCODEGO_API_PROVIDER,
    OPENCODEGO_SMOKE_MODEL,
    OpenAISettings,
    PathSettings,
    PRIMARY_API_PROVIDER,
    RESPONSES_JUDGE_TRANSPORT,
    load_openai_settings,
    load_path_settings,
    load_settings,
    resolve_api_model_for_provider,
    resolve_api_provider_for_profile,
    resolve_answer_llm_settings,
)

__all__ = [
    "APILIO_API_PROVIDER",
    "AppSettings",
    "AnswerLLMSettings",
    "ApiRuntimeProfile",
    "build_api_runtime_manifest",
    "CHAT_COMPLETIONS_JUDGE_TRANSPORT",
    "load_openai_settings",
    "load_run_composition",
    "load_path_settings",
    "load_typed_profile",
    "OPENCODEGO_API_PROVIDER",
    "OPENCODEGO_SMOKE_MODEL",
    "OpenAISettings",
    "ExecutionProfile",
    "PathSettings",
    "PRIMARY_API_PROVIDER",
    "RESPONSES_JUDGE_TRANSPORT",
    "resolve_api_model_for_provider",
    "resolve_api_provider_for_profile",
    "resolve_answer_llm_settings",
    "RunComposition",
    "load_settings",
]
