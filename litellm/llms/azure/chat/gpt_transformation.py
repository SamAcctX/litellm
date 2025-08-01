from typing import TYPE_CHECKING, Any, List, Optional, Union

from httpx._models import Headers, Response

import litellm
from litellm.litellm_core_utils.prompt_templates.factory import (
    convert_to_azure_openai_messages,
)
from litellm.llms.base_llm.chat.transformation import BaseLLMException
from litellm.types.llms.azure import (
    API_VERSION_MONTH_SUPPORTED_RESPONSE_FORMAT,
    API_VERSION_YEAR_SUPPORTED_RESPONSE_FORMAT,
)
from litellm.types.utils import ModelResponse

from ....exceptions import UnsupportedParamsError
from ....types.llms.openai import AllMessageValues
from ...base_llm.chat.transformation import BaseConfig
from ..common_utils import AzureOpenAIError

if TYPE_CHECKING:
    from litellm.litellm_core_utils.litellm_logging import Logging as LiteLLMLoggingObj

    LoggingClass = LiteLLMLoggingObj
else:
    LoggingClass = Any


class AzureOpenAIConfig(BaseConfig):
    """
    Reference: https://learn.microsoft.com/en-us/azure/ai-services/openai/reference#chat-completions

    The class `AzureOpenAIConfig` provides configuration for the OpenAI's Chat API interface, for use with Azure. Below are the parameters::

    - `frequency_penalty` (number or null): Defaults to 0. Allows a value between -2.0 and 2.0. Positive values penalize new tokens based on their existing frequency in the text so far, thereby minimizing repetition.

    - `function_call` (string or object): This optional parameter controls how the model calls functions.

    - `functions` (array): An optional parameter. It is a list of functions for which the model may generate JSON inputs.

    - `logit_bias` (map): This optional parameter modifies the likelihood of specified tokens appearing in the completion.

    - `max_tokens` (integer or null): This optional parameter helps to set the maximum number of tokens to generate in the chat completion.

    - `n` (integer or null): This optional parameter helps to set how many chat completion choices to generate for each input message.

    - `presence_penalty` (number or null): Defaults to 0. It penalizes new tokens based on if they appear in the text so far, hence increasing the model's likelihood to talk about new topics.

    - `stop` (string / array / null): Specifies up to 4 sequences where the API will stop generating further tokens.

    - `temperature` (number or null): Defines the sampling temperature to use, varying between 0 and 2.

    - `top_p` (number or null): An alternative to sampling with temperature, used for nucleus sampling.
    """

    def __init__(
        self,
        frequency_penalty: Optional[int] = None,
        function_call: Optional[Union[str, dict]] = None,
        functions: Optional[list] = None,
        logit_bias: Optional[dict] = None,
        max_tokens: Optional[int] = None,
        n: Optional[int] = None,
        presence_penalty: Optional[int] = None,
        stop: Optional[Union[str, list]] = None,
        temperature: Optional[int] = None,
        top_p: Optional[int] = None,
    ) -> None:
        locals_ = locals().copy()
        for key, value in locals_.items():
            if key != "self" and value is not None:
                setattr(self.__class__, key, value)

    @classmethod
    def get_config(cls):
        return super().get_config()

    def get_supported_openai_params(self, model: str) -> List[str]:
        return [
            "temperature",
            "n",
            "stream",
            "stream_options",
            "stop",
            "max_tokens",
            "max_completion_tokens",
            "tools",
            "tool_choice",
            "presence_penalty",
            "frequency_penalty",
            "logit_bias",
            "user",
            "function_call",
            "functions",
            "tools",
            "tool_choice",
            "top_p",
            "logprobs",
            "top_logprobs",
            "response_format",
            "seed",
            "extra_headers",
            "parallel_tool_calls",
            "prediction",
            "modalities",
            "audio",
            "web_search_options",
        ]

    def _is_response_format_supported_model(self, model: str) -> bool:
        """
        Determines if the model supports response_format.
        - Handles Azure deployment names (e.g., azure/gpt-4.1-suffix)
        - Normalizes model names (e.g., gpt-4-1 -> gpt-4.1)
        - Strips deployment-specific suffixes
        - Passes provider to supports_response_schema
        - Backwards compatible with previous model name patterns
        """
        import re

        # Normalize model name: e.g., gpt-3-5-turbo -> gpt-3.5-turbo
        normalized_model = re.sub(r"(\d)-(\d)", r"\1.\2", model)

        if "gpt-3.5" in normalized_model or "gpt-35" in model:
            return False

        return True

    def _is_response_format_supported_api_version(
        self, api_version_year: str, api_version_month: str
    ) -> bool:
        """
        - check if api_version is supported for response_format
        - returns True if the API version is equal to or newer than the supported version
        """
        api_year = int(api_version_year)
        api_month = int(api_version_month)
        supported_year = int(API_VERSION_YEAR_SUPPORTED_RESPONSE_FORMAT)
        supported_month = int(API_VERSION_MONTH_SUPPORTED_RESPONSE_FORMAT)

        # If the year is greater than supported year, it's definitely supported
        if api_year > supported_year:
            return True
        # If the year is less than supported year, it's not supported
        elif api_year < supported_year:
            return False
        # If same year, check if month is >= supported month
        else:
            return api_month >= supported_month

    def map_openai_params(
        self,
        non_default_params: dict,
        optional_params: dict,
        model: str,
        drop_params: bool,
        api_version: str = "",
    ) -> dict:
        supported_openai_params = self.get_supported_openai_params(model)

        api_version_times = api_version.split("-")

        if len(api_version_times) >= 3:
            api_version_year = api_version_times[0]
            api_version_month = api_version_times[1]
            api_version_day = api_version_times[2]
        else:
            api_version_year = None
            api_version_month = None
            api_version_day = None

        for param, value in non_default_params.items():
            if param == "tool_choice":
                """
                This parameter requires API version 2023-12-01-preview or later

                tool_choice='required' is not supported as of 2024-05-01-preview
                """
                ## check if api version supports this param ##
                if (
                    api_version_year is None
                    or api_version_month is None
                    or api_version_day is None
                ):
                    optional_params["tool_choice"] = value
                else:
                    if (
                        api_version_year < "2023"
                        or (api_version_year == "2023" and api_version_month < "12")
                        or (
                            api_version_year == "2023"
                            and api_version_month == "12"
                            and api_version_day < "01"
                        )
                    ):
                        if litellm.drop_params is True or (
                            drop_params is not None and drop_params is True
                        ):
                            pass
                        else:
                            raise UnsupportedParamsError(
                                status_code=400,
                                message=f"""Azure does not support 'tool_choice', for api_version={api_version}. Bump your API version to '2023-12-01-preview' or later. This parameter requires 'api_version="2023-12-01-preview"' or later. Azure API Reference: https://learn.microsoft.com/en-us/azure/ai-services/openai/reference#chat-completions""",
                            )
                    elif value == "required" and (
                        api_version_year == "2024" and api_version_month <= "05"
                    ):  ## check if tool_choice value is supported ##
                        if litellm.drop_params is True or (
                            drop_params is not None and drop_params is True
                        ):
                            pass
                        else:
                            raise UnsupportedParamsError(
                                status_code=400,
                                message=f"Azure does not support '{value}' as a {param} param, for api_version={api_version}. To drop 'tool_choice=required' for calls with this Azure API version, set `litellm.drop_params=True` or for proxy:\n\n`litellm_settings:\n drop_params: true`\nAzure API Reference: https://learn.microsoft.com/en-us/azure/ai-services/openai/reference#chat-completions",
                            )
                    else:
                        optional_params["tool_choice"] = value
            elif param == "response_format" and isinstance(value, dict):
                _is_response_format_supported_model = (
                    self._is_response_format_supported_model(model)
                )

                if api_version_year is None or api_version_month is None:
                    is_response_format_supported_api_version = True
                else:
                    is_response_format_supported_api_version = (
                        self._is_response_format_supported_api_version(
                            api_version_year, api_version_month
                        )
                    )
                is_response_format_supported = (
                    is_response_format_supported_api_version
                    and _is_response_format_supported_model
                )

                optional_params = self._add_response_format_to_tools(
                    optional_params=optional_params,
                    value=value,
                    is_response_format_supported=is_response_format_supported,
                )
            elif param == "tools" and isinstance(value, list):
                optional_params.setdefault("tools", [])
                optional_params["tools"].extend(value)
            elif param in supported_openai_params:
                optional_params[param] = value

        return optional_params

    def transform_request(
        self,
        model: str,
        messages: List[AllMessageValues],
        optional_params: dict,
        litellm_params: dict,
        headers: dict,
    ) -> dict:
        messages = convert_to_azure_openai_messages(messages)
        return {
            "model": model,
            "messages": messages,
            **optional_params,
        }

    def transform_response(
        self,
        model: str,
        raw_response: Response,
        model_response: ModelResponse,
        logging_obj: LoggingClass,
        request_data: dict,
        messages: List[AllMessageValues],
        optional_params: dict,
        litellm_params: dict,
        encoding: Any,
        api_key: Optional[str] = None,
        json_mode: Optional[bool] = None,
    ) -> ModelResponse:
        raise NotImplementedError(
            "Azure OpenAI handler.py has custom logic for transforming response, as it uses the OpenAI SDK."
        )

    def get_mapped_special_auth_params(self) -> dict:
        return {"token": "azure_ad_token"}

    def map_special_auth_params(self, non_default_params: dict, optional_params: dict):
        for param, value in non_default_params.items():
            if param == "token":
                optional_params["azure_ad_token"] = value
        return optional_params

    def get_eu_regions(self) -> List[str]:
        """
        Source: https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models#gpt-4-and-gpt-4-turbo-model-availability
        """
        return ["europe", "sweden", "switzerland", "france", "uk"]

    def get_us_regions(self) -> List[str]:
        """
        Source: https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models#gpt-4-and-gpt-4-turbo-model-availability
        """
        return [
            "us",
            "eastus",
            "eastus2",
            "eastus2euap",
            "eastus3",
            "southcentralus",
            "westus",
            "westus2",
            "westus3",
            "westus4",
        ]

    def get_error_class(
        self, error_message: str, status_code: int, headers: Union[dict, Headers]
    ) -> BaseLLMException:
        return AzureOpenAIError(
            message=error_message, status_code=status_code, headers=headers
        )

    def validate_environment(
        self,
        headers: dict,
        model: str,
        messages: List[AllMessageValues],
        optional_params: dict,
        litellm_params: dict,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
    ) -> dict:
        raise NotImplementedError(
            "Azure OpenAI has custom logic for validating environment, as it uses the OpenAI SDK."
        )
