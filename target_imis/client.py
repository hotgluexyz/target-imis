from target_hotglue.client import HotglueSink
import requests
from singer_sdk.plugin_base import PluginBase
from typing import Dict, List, Optional
import singer
from singer_sdk.exceptions import FatalAPIError, RetriableAPIError
from target_imis.auth import IMISAuth

LOGGER = singer.get_logger()

class IMISSink(HotglueSink):
    """IMIS target sink class."""
    
    def __init__(
        self,
        target: PluginBase,
        stream_name: str,
        schema: Dict,
        key_properties: Optional[List[str]],
    ) -> None:
        super().__init__(target, stream_name, schema, key_properties)
        self.__auth = IMISAuth(dict(self.config))

    @property
    def base_url(self):
        return f"{self.config.get('site_url')}/api/"
    
    @property
    def lookup_fields_dict(self):
        return self.config.get("lookup_fields") or {}
    
    @property
    def lookup_method(self):
        return self.config.get("lookup_method") or "all"

    def validate_response(self, response: requests.Response) -> None:
        """Validate HTTP response."""
        if response.status_code in [409]:
            msg = response.reason
            raise FatalAPIError(msg)
        elif response.status_code in [429] or 500 <= response.status_code < 600:
            msg = self.response_error_message(response)
            raise RetriableAPIError(msg, response)
        elif 400 <= response.status_code < 500:
            try:
                msg = response.text
            except:
                msg = self.response_error_message(response)
            raise FatalAPIError(msg)

    def prepare_request_headers(self):
        """Prepare request headers."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": self.__auth()
        }
